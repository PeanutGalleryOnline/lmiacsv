from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from lmiacsv.build_canonical_records import CANONICAL_FIELDS
from lmiacsv.build_min_products import (
    EMPLOYER_MIN_FIELDS,
    NOC_MIN_FIELDS,
    MinBuildError,
    build,
    file_sha256,
    project_csv,
)
from lmiacsv.build_noc_tables import CROSSWALK_FIELDS, UNIT_FIELDS
from lmiacsv.build_translations import FIELDS as TRANSLATION_FIELDS


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def blank_row(fields: list[str], **values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in fields}


class MinBuildTests(unittest.TestCase):
    def test_builds_exact_projections_and_deterministic_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            full = root / "full"
            minimum = root / "min"
            schema = root / "meta" / "min.schema.json"
            write_csv(
                full / "employers.csv",
                CANONICAL_FIELDS,
                [
                    blank_row(
                        CANONICAL_FIELDS,
                        record_id="record-1",
                        period_key="2025-q1",
                        period_year="2025",
                        decision_status="positive",
                        employer="A Ltd.",
                    ),
                    blank_row(
                        CANONICAL_FIELDS,
                        record_id="record-2",
                        period_key="2025-q1",
                        period_year="2025",
                        decision_status="negative",
                        employer="B Inc.",
                    ),
                ],
            )
            write_csv(
                full / "noc.csv",
                UNIT_FIELDS,
                [
                    blank_row(
                        UNIT_FIELDS,
                        noc_version="2021",
                        noc_code="21232",
                        title_en="Software developers and programmers",
                        title_fr="Développeurs/développeuses et programmeurs/programmeuses",
                    )
                ],
            )
            write_csv(
                full / "positive-quarterly.csv",
                ["period", "province_territory", "program_stream", "positive_lmias"],
                [
                    {
                        "period": "2025-q1",
                        "province_territory": "BC",
                        "program_stream": "high_wage",
                        "positive_lmias": "3",
                    }
                ],
            )
            write_csv(
                full / "positive-annual.csv",
                ["year", "province_territory", "program_stream", "positive_lmias"],
                [
                    {
                        "year": "2025",
                        "province_territory": "BC",
                        "program_stream": "high_wage",
                        "positive_lmias": "3",
                    }
                ],
            )
            write_csv(
                full / "positive-quarterly-national.csv",
                ["period", "positive_lmias"],
                [{"period": "2025-q1", "positive_lmias": "3"}],
            )
            write_csv(full / "noc-crosswalk.csv", CROSSWALK_FIELDS, [])
            write_csv(
                full / "translations.csv",
                TRANSLATION_FIELDS,
                [
                    blank_row(
                        TRANSLATION_FIELDS,
                        translation_key="program_stream.high_wage",
                        en="High Wage",
                        fr="Haut salaire",
                    )
                ],
            )

            result = build(full_root=full, min_root=minimum, schema_path=schema)

            with (minimum / "employers.csv").open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            self.assertEqual(EMPLOYER_MIN_FIELDS, reader.fieldnames)
            self.assertEqual(["record-1", "record-2"], [row["record_id"] for row in rows])
            self.assertEqual("A Ltd.", rows[0]["employer"])

            with (minimum / "noc.csv").open("r", encoding="utf-8", newline="") as handle:
                noc_reader = csv.DictReader(handle)
                noc_rows = list(noc_reader)
            self.assertEqual(NOC_MIN_FIELDS, noc_reader.fieldnames)
            self.assertEqual("21232", noc_rows[0]["noc_code"])
            self.assertEqual(2, result["min"]["products"][0]["rows"])
            for filename in (
                "positive-quarterly.csv",
                "positive-annual.csv",
                "positive-quarterly-national.csv",
            ):
                self.assertEqual(
                    (full / filename).read_bytes(),
                    (minimum / filename).read_bytes(),
                )
            self.assertEqual(
                {
                    "employers.csv",
                    "positive-quarterly.csv",
                    "positive-annual.csv",
                    "positive-quarterly-national.csv",
                    "noc.csv",
                },
                {product["path"] for product in result["min"]["products"]},
            )
            self.assertEqual(
                file_sha256(full / "manifest.json"),
                result["min"]["derived_from"]["sha256"],
            )
            self.assertTrue(schema.is_file())
            self.assertEqual(
                EMPLOYER_MIN_FIELDS,
                [
                    field["name"]
                    for field in json.loads(schema.read_text(encoding="utf-8"))["products"][
                        "employers.csv"
                    ]["fields"]
                ],
            )

    def test_projection_fails_on_duplicate_primary_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            output = root / "output.csv"
            write_csv(
                source,
                ["record_id", "value"],
                [
                    {"record_id": "same", "value": "a"},
                    {"record_id": "same", "value": "b"},
                ],
            )
            with self.assertRaisesRegex(MinBuildError, "Duplicate projected key"):
                project_csv(
                    source,
                    output,
                    expected_source_fields=["record_id", "value"],
                    projection_fields=["record_id"],
                    key_fields=["record_id"],
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
