import csv
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from lmiacsv.release_validation import (
    ReleaseValidationError,
    build_release_assets,
    file_sha256,
    verify_checksum_manifest,
    verify_distribution_archives,
    verify_repository,
)


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name in (
            "LICENSE",
            "NOTICE",
            "DATA_LICENSES.md",
            "README.md",
            "RELEASING.md",
            "pyproject.toml",
        ):
            (self.root / name).write_text(f"{name}\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "method.md").write_text("method\n", encoding="utf-8")
        (self.root / "data" / "full").mkdir(parents=True)
        (self.root / "data" / "min").mkdir(parents=True)
        (self.root / "data" / "meta").mkdir(parents=True)
        schema = self.root / "data" / "meta" / "min.schema.json"
        schema.write_text('{"schema_version": "1.0.0"}\n', encoding="utf-8")

        full_csv = self.root / "data" / "full" / "rows.csv"
        self._write_csv(full_csv)
        full_manifest = self._manifest_entry(full_csv)
        full_manifest_path = self.root / "data" / "full" / "manifest.json"
        full_manifest_path.write_text(
            json.dumps({"products": [full_manifest]}) + "\n", encoding="utf-8"
        )

        min_csv = self.root / "data" / "min" / "rows.csv"
        self._write_csv(min_csv)
        min_manifest = {
            "products": [
                {
                    **self._manifest_entry(min_csv),
                    "source": "../full/rows.csv",
                    "source_sha256": file_sha256(full_csv),
                }
            ],
            "derived_from": {
                "path": "../full/manifest.json",
                "sha256": file_sha256(full_manifest_path),
            },
            "schema": {"path": "../meta/min.schema.json", "sha256": file_sha256(schema)},
        }
        (self.root / "data" / "min" / "manifest.json").write_text(
            json.dumps(min_manifest) + "\n", encoding="utf-8"
        )

        evidence = self.root / "evidence" / "case"
        evidence.mkdir(parents=True)
        evidence_file = evidence / "source.txt"
        evidence_file.write_text("source\n", encoding="utf-8")
        (evidence / "SHA256SUMS").write_text(
            f"{file_sha256(evidence_file)}  source.txt\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_csv(path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "value"])
            writer.writeheader()
            writer.writerow({"id": "1", "value": "alpha"})
            writer.writerow({"id": "2", "value": "beta"})

    @staticmethod
    def _manifest_entry(path: Path) -> dict[str, object]:
        return {
            "path": path.name,
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
            "rows": 2,
            "columns": 2,
            "fields": ["id", "value"],
            "primary_key": ["id"],
        }

    def test_repository_and_products_verify(self) -> None:
        result = verify_repository(self.root, require_products=True)
        self.assertEqual(result["product_files"], 2)
        self.assertEqual(result["evidence_files"], 1)

    def test_tampered_product_fails(self) -> None:
        path = self.root / "data" / "full" / "rows.csv"
        path.write_text("id,value\n1,changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseValidationError, "checksum mismatch"):
            verify_repository(self.root, require_products=True)

    def test_checksum_path_escape_fails(self) -> None:
        checksum = self.root / "evidence" / "case" / "SHA256SUMS"
        checksum.write_text(f"{'0' * 64}  ../../../outside\n", encoding="utf-8")
        with self.assertRaisesRegex(ReleaseValidationError, "escapes repository root"):
            verify_checksum_manifest(checksum, self.root)

    def test_distribution_legal_metadata_verifies(self) -> None:
        dist = self.root / "dist"
        dist.mkdir()
        metadata = (
            "Metadata-Version: 2.4\n"
            "License-Expression: Apache-2.0\n"
            "License-File: LICENSE\n"
            "License-File: NOTICE\n"
            "License-File: DATA_LICENSES.md\n"
        )
        with zipfile.ZipFile(dist / "lmiacsv-0.1.0-py3-none-any.whl", "w") as archive:
            archive.writestr("lmiacsv-0.1.0.dist-info/METADATA", metadata)
            for name in ("LICENSE", "NOTICE", "DATA_LICENSES.md"):
                archive.writestr(f"lmiacsv-0.1.0.dist-info/licenses/{name}", name)
        with tarfile.open(dist / "lmiacsv-0.1.0.tar.gz", "w:gz") as archive:
            for name, content in {
                "lmiacsv-0.1.0/PKG-INFO": metadata,
                "lmiacsv-0.1.0/LICENSE": "LICENSE",
                "lmiacsv-0.1.0/NOTICE": "NOTICE",
                "lmiacsv-0.1.0/DATA_LICENSES.md": "DATA_LICENSES.md",
            }.items():
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        self.assertEqual(verify_distribution_archives(dist), 2)

    def test_release_archives_are_deterministic(self) -> None:
        first = self.root / "release-one"
        second = self.root / "release-two"
        revision = "a" * 40
        first_assets = build_release_assets(
            self.root, first, "v0.1.0", revision, 1_700_000_000
        )
        second_assets = build_release_assets(
            self.root, second, "v0.1.0", revision, 1_700_000_000
        )
        first_hashes = {path.name: file_sha256(path) for path in first_assets}
        second_hashes = {path.name: file_sha256(path) for path in second_assets}
        self.assertEqual(first_hashes, second_hashes)
        min_archive = first / "lmiacsv-v0.1.0-data-min.tar.gz"
        with tarfile.open(min_archive, "r:gz") as archive:
            names = set(archive.getnames())
        self.assertIn("RELEASING.md", names)
        self.assertIn("data/full/manifest.json", names)


if __name__ == "__main__":
    unittest.main()
