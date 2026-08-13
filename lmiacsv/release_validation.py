"""Verify and package a source-auditable lmiacsv release candidate."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Iterable


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CANDIDATE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
SKIPPED_JSON_DIRECTORIES = {
    ".git",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
REQUIRED_LEGAL_FILES = ("LICENSE", "NOTICE", "DATA_LICENSES.md")
REQUIRED_REPOSITORY_FILES = (
    *REQUIRED_LEGAL_FILES,
    "README.md",
    "RELEASING.md",
    "pyproject.toml",
)


class ReleaseValidationError(RuntimeError):
    """Raised when a release invariant is not satisfied."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(root: Path, base: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ReleaseValidationError(f"Absolute path is not allowed: {relative}")
    resolved_root = root.resolve()
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ReleaseValidationError(f"Path escapes repository root: {relative}") from error
    return resolved


def verify_json_documents(root: Path) -> int:
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonld"}:
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in SKIPPED_JSON_DIRECTORIES for part in relative_parts):
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReleaseValidationError(f"Invalid JSON document {path}: {error}") from error
        count += 1
    if count == 0:
        raise ReleaseValidationError("Repository contains no JSON documents to validate")
    return count


def verify_checksum_manifest(path: Path, root: Path | None = None) -> int:
    repository_root = (root or path.parent).resolve()
    checked = 0
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line or raw_line.startswith("#"):
            continue
        expected, separator, relative = raw_line.partition("  ")
        if not separator or not HEX_SHA256.fullmatch(expected) or not relative:
            raise ReleaseValidationError(f"Malformed checksum entry {path}:{line_number}")
        target = _safe_path(repository_root, path.parent, relative)
        if not target.is_file():
            raise ReleaseValidationError(f"Checksummed file is missing: {target}")
        actual = file_sha256(target)
        if actual != expected:
            raise ReleaseValidationError(
                f"Checksum mismatch for {target}: expected {expected}, got {actual}"
            )
        checked += 1
    if checked == 0:
        raise ReleaseValidationError(f"Checksum manifest contains no entries: {path}")
    return checked


def verify_evidence(root: Path) -> int:
    evidence_root = root / "evidence"
    manifests = sorted(evidence_root.rglob("SHA256SUMS")) if evidence_root.is_dir() else []
    if not manifests:
        raise ReleaseValidationError("No evidence checksum manifests were found")
    return sum(verify_checksum_manifest(path, root) for path in manifests)


def _required_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ReleaseValidationError(f"{label} must be a non-empty list")
    return value


def _verify_reference(root: Path, base: Path, reference: Any, label: str, required: bool) -> None:
    if not isinstance(reference, dict):
        raise ReleaseValidationError(f"{label} must be an object")
    relative = reference.get("path")
    expected = reference.get("sha256")
    if not isinstance(relative, str) or not HEX_SHA256.fullmatch(str(expected)):
        raise ReleaseValidationError(f"{label} must contain path and SHA-256")
    target = _safe_path(root, base, relative)
    if not target.is_file():
        if required:
            raise ReleaseValidationError(f"Referenced file is missing: {target}")
        return
    actual = file_sha256(target)
    if actual != expected:
        raise ReleaseValidationError(
            f"Referenced-file checksum mismatch for {target}: expected {expected}, got {actual}"
        )


def _verify_csv_product(path: Path, entry: dict[str, Any]) -> None:
    expected_sha256 = entry.get("sha256")
    if not isinstance(expected_sha256, str) or not HEX_SHA256.fullmatch(expected_sha256):
        raise ReleaseValidationError(f"Invalid product SHA-256 in manifest for {path}")
    if file_sha256(path) != expected_sha256:
        raise ReleaseValidationError(f"Product checksum mismatch: {path}")
    if path.stat().st_size != entry.get("bytes"):
        raise ReleaseValidationError(f"Product byte-size mismatch: {path}")

    fields = _required_list(entry.get("fields"), f"fields for {path}")
    if not all(isinstance(field, str) and field for field in fields) or len(fields) != len(
        set(fields)
    ):
        raise ReleaseValidationError(f"Product fields are invalid or duplicated: {path}")
    if entry.get("columns") != len(fields):
        raise ReleaseValidationError(f"Product column-count mismatch: {path}")
    primary_key = entry.get("primary_key")
    if not isinstance(primary_key, list) or not all(field in fields for field in primary_key):
        raise ReleaseValidationError(f"Product primary key is invalid: {path}")

    seen_keys: set[tuple[str, ...]] = set()
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if list(reader.fieldnames or []) != fields:
            raise ReleaseValidationError(f"Product header mismatch: {path}")
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ReleaseValidationError(f"Extra CSV values in {path}:{row_number}")
            if primary_key:
                key = tuple(row[field] for field in primary_key)
                if not all(key):
                    raise ReleaseValidationError(f"Blank primary key in {path}:{row_number}")
                if key in seen_keys:
                    raise ReleaseValidationError(f"Duplicate primary key in {path}:{row_number}")
                seen_keys.add(key)
            row_count += 1
    if row_count != entry.get("rows"):
        raise ReleaseValidationError(f"Product row-count mismatch: {path}")


def verify_product_manifest(path: Path, root: Path, require_products: bool = False) -> int:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseValidationError(f"Invalid product manifest {path}: {error}") from error
    if not isinstance(document, dict):
        raise ReleaseValidationError(f"Product manifest must be an object: {path}")
    products = _required_list(document.get("products"), f"products in {path}")

    verified = 0
    seen_paths: set[str] = set()
    for raw_entry in products:
        if not isinstance(raw_entry, dict):
            raise ReleaseValidationError(f"Product entry must be an object: {path}")
        relative = raw_entry.get("path")
        if not isinstance(relative, str) or not relative.endswith(".csv"):
            raise ReleaseValidationError(f"Product path must name a CSV: {relative!r}")
        if relative in seen_paths:
            raise ReleaseValidationError(f"Duplicate product path in {path}: {relative}")
        seen_paths.add(relative)
        product = _safe_path(root, path.parent, relative)
        if not product.is_file():
            if require_products:
                raise ReleaseValidationError(f"Required product is missing: {product}")
        else:
            _verify_csv_product(product, raw_entry)
            verified += 1

        if "source" in raw_entry:
            _verify_reference(
                root,
                path.parent,
                {"path": raw_entry["source"], "sha256": raw_entry.get("source_sha256")},
                f"source for {relative}",
                require_products,
            )

    for key in ("derived_from", "schema"):
        if key in document:
            _verify_reference(root, path.parent, document[key], f"{key} in {path}", True)
    return verified


def _metadata_text_from_archive(path: Path) -> tuple[set[str], str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise ReleaseValidationError(f"Wheel has no unique METADATA file: {path}")
            metadata = archive.read(metadata_names[0]).decode("utf-8")
        return names, metadata
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = {member.name for member in archive.getmembers() if member.isfile()}
            metadata_names = [
                name for name in names if name.endswith("/PKG-INFO") and name.count("/") == 1
            ]
            if len(metadata_names) != 1:
                raise ReleaseValidationError(f"Sdist has no unique PKG-INFO file: {path}")
            member = archive.extractfile(metadata_names[0])
            if member is None:
                raise ReleaseValidationError(f"Cannot read sdist metadata: {path}")
            metadata = member.read().decode("utf-8")
        return names, metadata
    raise ReleaseValidationError(f"Unsupported distribution archive: {path}")


def verify_distribution_archives(dist_dir: Path) -> int:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseValidationError(
            f"Expected one wheel and one sdist in {dist_dir}; found {len(wheels)} and {len(sdists)}"
        )
    for path in [*wheels, *sdists]:
        names, metadata = _metadata_text_from_archive(path)
        if "License-Expression: Apache-2.0" not in metadata:
            raise ReleaseValidationError(f"Distribution lacks Apache-2.0 metadata: {path}")
        for legal_file in REQUIRED_LEGAL_FILES:
            if not any(name == legal_file or name.endswith(f"/{legal_file}") for name in names):
                raise ReleaseValidationError(f"Distribution omits {legal_file}: {path}")
            if f"License-File: {legal_file}" not in metadata:
                raise ReleaseValidationError(
                    f"Distribution metadata omits License-File: {legal_file}: {path}"
                )
    return 2


def verify_repository(root: Path, require_products: bool = False) -> dict[str, int]:
    resolved_root = root.resolve()
    for relative in REQUIRED_REPOSITORY_FILES:
        path = resolved_root / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise ReleaseValidationError(f"Required repository file is missing or empty: {path}")
    json_count = verify_json_documents(resolved_root)
    evidence_count = verify_evidence(resolved_root)
    product_count = sum(
        verify_product_manifest(path, resolved_root, require_products)
        for path in (
            resolved_root / "data" / "full" / "manifest.json",
            resolved_root / "data" / "min" / "manifest.json",
        )
    )
    return {
        "json_documents": json_count,
        "evidence_files": evidence_count,
        "product_files": product_count,
    }


def _archive_inputs(root: Path, tier: str) -> list[Path]:
    manifest_path = root / "data" / tier / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = [root / relative for relative in REQUIRED_LEGAL_FILES]
    inputs.append(root / "README.md")
    inputs.append(root / "RELEASING.md")
    inputs.extend(path for path in sorted((root / "docs").rglob("*")) if path.is_file())
    inputs.extend(path for path in sorted((root / "data" / "meta").rglob("*")) if path.is_file())
    inputs.append(manifest_path)
    if tier == "min":
        inputs.append(root / "data" / "full" / "manifest.json")
    for entry in manifest["products"]:
        inputs.append(_safe_path(root, manifest_path.parent, entry["path"]))
    unique = sorted(set(inputs), key=lambda value: value.relative_to(root).as_posix())
    for path in unique:
        if path.is_symlink() or not path.is_file():
            raise ReleaseValidationError(f"Release input is not a regular file: {path}")
    return unique


def _write_deterministic_tar_gz(
    output: Path,
    root: Path,
    inputs: Iterable[Path],
    source_date_epoch: int,
) -> None:
    with output.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_handle,
            mtime=source_date_epoch,
        ) as gzip_handle:
            with tarfile.open(fileobj=gzip_handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in inputs:
                    relative = path.relative_to(root).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = source_date_epoch
                    info.mode = 0o644
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def build_release_assets(
    root: Path,
    output_dir: Path,
    candidate: str,
    revision: str,
    source_date_epoch: int,
    dist_dir: Path | None = None,
    prevalidated: bool = False,
) -> list[Path]:
    if not CANDIDATE_NAME.fullmatch(candidate):
        raise ReleaseValidationError(f"Unsafe release candidate name: {candidate!r}")
    if not GIT_REVISION.fullmatch(revision):
        raise ReleaseValidationError(f"Revision must be a full lowercase Git SHA: {revision!r}")
    if source_date_epoch < 0:
        raise ReleaseValidationError("SOURCE_DATE_EPOCH cannot be negative")

    resolved_root = root.resolve()
    if not prevalidated:
        verify_repository(resolved_root, require_products=True)
        if dist_dir is not None:
            verify_distribution_archives(dist_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ReleaseValidationError(f"Release output directory is not empty: {output_dir}")

    artifacts: list[tuple[Path, str]] = []
    for tier in ("full", "min"):
        archive_path = output_dir / f"lmiacsv-{candidate}-data-{tier}.tar.gz"
        _write_deterministic_tar_gz(
            archive_path,
            resolved_root,
            _archive_inputs(resolved_root, tier),
            source_date_epoch,
        )
        artifacts.append((archive_path, f"normalized data ({tier})"))

    if dist_dir is not None:
        for source in sorted([*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")]):
            destination = output_dir / source.name
            shutil.copyfile(source, destination)
            artifacts.append((destination, "Python distribution"))

    provenance = {
        "schema_version": "1.0.0",
        "project": "lmiacsv",
        "candidate": candidate,
        "revision": revision,
        "source_date_epoch": source_date_epoch,
        "artifacts": [
            {
                "path": path.name,
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path, role in artifacts
        ],
    }
    provenance_path = output_dir / "RELEASE_PROVENANCE.json"
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifacts.append((provenance_path, "release provenance"))

    checksum_path = output_dir / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{file_sha256(path)}  {path.name}\n" for path, _role in artifacts),
        encoding="utf-8",
    )
    verify_checksum_manifest(checksum_path, output_dir)
    return [path for path, _role in artifacts] + [checksum_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=WORKSPACE_ROOT)
    parser.add_argument("--require-products", action="store_true")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--build-assets", metavar="CANDIDATE")
    parser.add_argument("--revision")
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    try:
        summary = verify_repository(args.root, args.require_products or bool(args.build_assets))
        distributions = (
            verify_distribution_archives(args.dist_dir) if args.dist_dir is not None else 0
        )
        assets = 0
        if args.build_assets:
            if args.revision is None or args.source_date_epoch is None or args.output_dir is None:
                parser.error(
                    "--build-assets requires --revision, --source-date-epoch, and --output-dir"
                )
            assets = len(
                build_release_assets(
                    args.root,
                    args.output_dir,
                    args.build_assets,
                    args.revision,
                    args.source_date_epoch,
                    args.dist_dir,
                    prevalidated=True,
                )
            )
    except ReleaseValidationError as error:
        parser.exit(1, f"error: {error}\n")

    print(
        "Validated "
        f"{summary['json_documents']} JSON documents, "
        f"{summary['evidence_files']} evidence files, "
        f"{summary['product_files']} product files, "
        f"{distributions} distributions, and {assets} release assets."
    )


if __name__ == "__main__":
    main()
