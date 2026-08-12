from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from processor.pilot_2025q1 import (
    build_summary,
    normalize_row,
    postal_code,
    search_key,
    write_outputs,
)


POSITIVE_RESOURCE = {
    "id": "2025-q1-positive-en",
    "status": "positive",
    "language": "en",
    "dataset_id": "dataset-positive",
    "resource_id": "resource-positive",
    "resource_page_url": "https://example.test/positive",
    "download_url": "https://example.test/positive.xlsx",
    "filename": "positive.xlsx",
    "sheet": "Positive",
    "sha256": "a" * 64,
}

NEGATIVE_RESOURCE = {
    **POSITIVE_RESOURCE,
    "id": "2025-q1-negative-en",
    "status": "negative",
    "dataset_id": "dataset-negative",
    "resource_id": "resource-negative",
    "resource_page_url": "https://example.test/negative",
    "download_url": "https://example.test/negative.xlsx",
    "filename": "negative.xlsx",
    "sheet": "Negative",
    "sha256": "b" * 64,
}


def sample_row(
    employer: str = 'Park "A" Motel',
    lmias: int = 1,
    positions: int = 2,
) -> list[object]:
    return [
        "Ontario  ",
        "High-wage Stream",
        employer,
        "10 King St W, Toronto, ON M5V 2T6",
        "62020 - Food service supervisors",
        "Incorporated",
        lmias,
        positions,
    ]


class PilotNormalizationTests(unittest.TestCase):
    def test_preserves_raw_values_and_normalizes_search_fields(self) -> None:
        record = normalize_row(POSITIVE_RESOURCE, 3, sample_row())

        self.assertEqual(record.province_raw, "Ontario  ")
        self.assertEqual(record.province_code, "ON")
        self.assertEqual(record.employer, 'Park "A" Motel')
        self.assertEqual(record.employer_key, "park a motel")
        self.assertEqual(record.postal_code, "M5V 2T6")
        self.assertEqual(record.noc_code, "62020")
        self.assertEqual(record.noc_version, "2021")
        self.assertEqual(record.lmia_measure, "approved")
        self.assertEqual(record.position_measure, "approved")
        self.assertEqual(record.source_row, 3)

    def test_negative_measure_is_requested_on_negative_decision(self) -> None:
        record = normalize_row(NEGATIVE_RESOURCE, 8, sample_row())

        self.assertEqual(record.decision_status, "negative")
        self.assertEqual(record.lmia_measure, "requested")
        self.assertEqual(record.position_measure, "requested_on_negative_decision")
        self.assertNotIn("denied", record.position_measure)

    def test_published_zero_position_is_preserved(self) -> None:
        record = normalize_row(POSITIVE_RESOURCE, 3377, sample_row(positions=0))

        self.assertEqual(record.lmia_count, 1)
        self.assertEqual(record.position_count, 0)

    def test_search_and_postal_normalization(self) -> None:
        self.assertEqual(search_key("Café—Québec Inc."), "cafe quebec inc")
        self.assertEqual(postal_code("Vancouver bc v6b1a1"), "V6B 1A1")

    def test_summary_keeps_positive_and_negative_measures_separate(self) -> None:
        records = [
            normalize_row(POSITIVE_RESOURCE, 3, sample_row(positions=3)),
            normalize_row(NEGATIVE_RESOURCE, 3, sample_row(positions=4)),
        ]
        manifest = {
            "period": {
                "year": 2025,
                "quarter": "Q1",
                "start": "2025-01-01",
                "end": "2025-03-31",
            },
            "resources": [
                {
                    **POSITIVE_RESOURCE,
                    "expected_rows": 1,
                    "published_at": "2025-06-19",
                },
                {
                    **NEGATIVE_RESOURCE,
                    "expected_rows": 1,
                    "published_at": "2025-06-19",
                },
            ],
            "limitations": [],
        }

        summary = build_summary(records, manifest)

        self.assertEqual(summary["totals"]["approved_positions"], 3)
        self.assertEqual(
            summary["totals"]["requested_positions_on_negative_decisions"], 4
        )
        self.assertNotIn("approval_rate", summary["totals"])

    def test_public_search_index_has_explicit_compact_schema(self) -> None:
        records = [
            normalize_row(POSITIVE_RESOURCE, 3, sample_row(positions=3)),
            normalize_row(NEGATIVE_RESOURCE, 3, sample_row(positions=4)),
        ]
        summary = {"totals": {"records": 2}}

        with TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            write_outputs(records, summary, output_root)
            payload = json.loads(
                (output_root / "public/data/2025q1/employers.json").read_text()
            )

        self.assertEqual(payload["period"], "2025-Q1")
        self.assertEqual(
            payload["fields"],
            [
                "id",
                "name",
                "search_key",
                "provinces",
                "positive_records",
                "negative_records",
                "approved_positions",
                "requested_positions_on_negative_decisions",
            ],
        )
        self.assertEqual(len(payload["employers"]), 1)
        self.assertEqual(len(payload["employers"][0]), len(payload["fields"]))


if __name__ == "__main__":
    unittest.main()
