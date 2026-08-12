from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from lmiacsv.build_canonical_records import (
    CONFLICTING_2022_Q2_POSITIVE,
    CanonicalBuildError,
    SourcePlan,
    build_source_plans,
    canonical_records,
    header_roles,
)


def plan(headers: list[str], *, decision: str = "positive", period: str = "2020-q1") -> SourcePlan:
    year = int(period[:4])
    quarter = period.split("-", 1)[1].upper() if "-" in period else None
    return SourcePlan(
        catalogue={
            "dataset_id": "dataset",
            "resource_id": "resource",
            "resource_page_url": "https://example.test/resource",
            "download_url": "https://example.test/download",
            "decision": decision,
            "language": "en",
            "period": {
                "key": period,
                "year": year,
                "quarter": quarter,
                "precision": "quarter" if quarter else "year_or_partial_year",
            },
        },
        census={},
        raw={},
        path=Path("source.csv"),
        format="CSV",
        catalogue_format="CSV",
        file_name="source.csv",
        sheet="CSV",
        header_row=2,
        header_values=headers,
        first_note_row=None,
        sha256="a" * 64,
        final_url="https://example.test/final",
        download_url="https://example.test/download",
        schema_signature="schema",
        disposition="normalized",
    )


class HeaderAdapterTests(unittest.TestCase):
    def test_all_historical_widths_map_to_canonical_roles(self) -> None:
        schemas = [
            ["Employer", "Address", "Positions approved"],
            [
                "Province/Territory",
                "Employer",
                "Address",
                "Occupations under NOC 2011",
                "Positions requested",
            ],
            [
                "Province/Territory",
                "Stream",
                "Employer Name",
                "Address",
                "Occupation",
                "Approved Positions",
            ],
            [
                "Province/Territory",
                "Program Stream",
                "Employer",
                "Address",
                "Occupation",
                "Incorporate Status",
                "Approved LMIAs",
                "Approved Positions",
            ],
        ]
        self.assertEqual([3, 5, 6, 8], [len(header_roles(values)) for values in schemas])

    def test_unknown_header_fails_closed(self) -> None:
        with self.assertRaisesRegex(CanonicalBuildError, "Unrecognized source header"):
            header_roles(["Employer", "Address", "Mystery total"])


class CanonicalRowTests(unittest.TestCase):
    def test_2014_grouped_province_rows_become_records_not_fake_headings(self) -> None:
        source = replace(
            plan(["Employer", "Address", "Positions"], period="2014"),
            header_row=3,
        )
        rows = [
            (1, ["Report title"]),
            (2, ["Ontario"]),
            (3, ["Employer", "Address", "Positions"]),
            (4, ["Employer", "Address", "Positions"]),
            (5, ["Example Inc.", "Toronto, ON M5V 1A1", 2]),
            (6, ["Notes:"]),
        ]

        records = list(canonical_records(source, rows))

        self.assertEqual(1, len(records))
        self.assertEqual("Ontario", records[0]["province"])
        self.assertEqual("ON", records[0]["province_code"])
        self.assertEqual("", records[0]["lmia_measure"])
        self.assertEqual("", records[0]["lmia_count"])
        self.assertEqual("approved_positions", records[0]["position_measure"])

    def test_grouped_employer_and_address_are_forward_filled_and_flagged(self) -> None:
        source = plan(
            [
                "Province/Territory",
                "Employer",
                "Address",
                "Occupations under NOC 2011",
                "Positions requested",
            ],
            decision="negative",
            period="2016",
        )
        rows = [
            (1, ["Report title"]),
            (2, source.header_values),
            (3, ["Nova Scotia", "Example Care", "Halifax, NS B3H 1A1", "3012-Nurses", 2]),
            (4, ["", "", "", "3413-Nurse aides", 1]),
        ]

        records = list(canonical_records(source, rows))

        self.assertEqual("Example Care", records[1]["employer"])
        self.assertEqual("", records[1]["employer_raw"])
        self.assertIn("employer_forward_filled_from_grouped_source", records[1]["quality_flags"])
        self.assertEqual(
            "requested_positions_on_negative_decisions", records[1]["position_measure"]
        )

    def test_modern_source_keeps_lmia_and_position_semantics_distinct(self) -> None:
        source = plan(
            [
                "Province/Territory",
                "Program Stream",
                "Employer",
                "Address",
                "Occupation",
                "Incorporate Status",
                "Approved LMIAs",
                "Approved Positions",
            ],
            period="2025-q1",
        )
        rows = [
            (1, ["Report title"]),
            (2, source.header_values),
            (3, ["Ontario", "High Wage", "Example Inc.", "Toronto", "62020-Cooks", "Yes", 1, 0]),
        ]

        record = list(canonical_records(source, rows))[0]

        self.assertEqual("approved_lmias", record["lmia_measure"])
        self.assertEqual(1, record["lmia_count"])
        self.assertEqual(0, record["position_count"])
        self.assertIn("zero_positions_preserved", record["quality_flags"])


class QuarantineTests(unittest.TestCase):
    def test_known_positive_resource_with_requested_headers_is_quarantined(self) -> None:
        resource_id = CONFLICTING_2022_Q2_POSITIVE
        catalogue_resource = {
            "dataset_id": "positive-dataset",
            "resource_id": resource_id,
            "resource_page_url": "https://example.test/resource",
            "download_url": "https://example.test/download",
            "source_filename": "source.xlsx",
            "format": "XLSX",
            "decision": "positive",
            "language": "en",
            "period": {"key": "2022-q2", "year": 2022, "quarter": "Q2", "precision": "quarter"},
        }
        headers = [
            "Province/Territory",
            "Program Stream",
            "Employer",
            "Address",
            "Occupation",
            "Incorporate Status",
            "Requested LMIAs",
            "Requested Positions",
        ]
        census_resource = {
            **catalogue_resource,
            "selected_sheet": "Positive_EN",
            "sheets": [
                {
                    "name": "Positive_EN",
                    "header": {"row": 2, "values": headers},
                    "estimated_data_rows": 15167,
                }
            ],
        }
        raw_resource = {
            **catalogue_resource,
            "status": "downloaded",
            "sha256": "b" * 64,
            "catalogue_format": "XLSX",
            "source_filename": "source.xlsx",
        }

        plans, quarantines = build_source_plans(
            {"resources": [catalogue_resource]},
            {"resources": [census_resource]},
            {"resources": [raw_resource]},
        )

        self.assertEqual([], plans)
        self.assertEqual(1, len(quarantines))
        self.assertEqual(0, quarantines[0]["canonical_records"])
        self.assertIn("requested_lmia", quarantines[0]["reason"])


if __name__ == "__main__":
    unittest.main()
