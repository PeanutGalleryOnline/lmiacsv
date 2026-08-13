from __future__ import annotations

import unittest
import csv
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from lmiacsv.build_canonical_records import (
    CanonicalBuildError,
    RESOLVED_2022_Q2_POSITIVE_EN,
    RESOLVED_2022_Q2_POSITIVE_FR,
    RESOLVED_2022_Q2_QUALITY_FLAG,
    SourcePlan,
    build_source_plans,
    canonical_records,
    file_sha256,
    header_roles,
    normalize_incorporate_status,
    normalize_province,
    normalize_stream,
    source_rows,
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
            "title": {"en": "Employer list using National Occupational Classification (NOC) 2011"},
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
    def test_french_source_categories_normalize_to_shared_values(self) -> None:
        self.assertEqual(("Quebec", "QC"), normalize_province("Qu bec"))
        self.assertEqual(
            ("Outside Canada", "INT"), normalize_province("À l'extérieur du Canada")
        )
        self.assertEqual(
            "Permanent Resident Only", normalize_stream("Résident permanent seulement")
        )
        self.assertEqual(
            "Sole Proprietorship",
            normalize_incorporate_status("Entreprise à propriétaire unique"),
        )
        self.assertEqual("Co-operative", normalize_incorporate_status("Coopérative"))

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
        source = replace(
            plan(
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
            ),
            catalogue={
                **plan([], period="2025-q1").catalogue,
                "title": {
                    "en": "Employer list using National Occupational Classification (NOC) 2021"
                },
            },
        )
        rows = [
            (1, ["Report title"]),
            (2, source.header_values),
            (3, ["Ontario", "High Wage", "Example Inc.", "Toronto", "62020-Cooks", "Yes", 1, 0]),
        ]

        record = list(canonical_records(source, rows))[0]

        self.assertEqual("approved_lmias", record["lmia_measure"])
        self.assertEqual("high_wage", record["program_stream_key"])
        self.assertEqual("incorporated", record["incorporate_status_key"])
        self.assertEqual(1, record["lmia_count"])
        self.assertEqual(0, record["position_count"])
        self.assertIn("zero_positions_preserved", record["quality_flags"])

    def test_noc_version_comes_from_source_metadata_not_record_year(self) -> None:
        source = plan(
            [
                "Province/Territory",
                "Program Stream",
                "Employer",
                "Address",
                "Occupation",
                "Approved Positions",
            ],
            period="2024-q1",
        )
        rows = [
            (1, ["Report title"]),
            (2, source.header_values),
            (3, ["Ontario", "High Wage", "Example", "Toronto", "6322-Cooks", 1]),
        ]

        record = list(canonical_records(source, rows))[0]

        self.assertEqual(record["noc_version"], "2011")


class BilingualMeasureOverrideTests(unittest.TestCase):
    def documents(
        self,
        directory: Path,
        *,
        french_positions: int = 1,
    ) -> tuple[dict, dict, dict]:
        period = {
            "key": "2022-q2",
            "year": 2022,
            "quarter": "Q2",
            "precision": "quarter",
        }
        definitions = [
            {
                "resource_id": RESOLVED_2022_Q2_POSITIVE_EN,
                "language": "en",
                "filename": "positive-en.csv",
                "headers": [
                    "Province/Territory",
                    "Program Stream",
                    "Employer",
                    "Address",
                    "Occupation",
                    "Incorporate Status",
                    "Requested LMIAs",
                    "Requested Positions",
                ],
                "row": [
                    "Ontario",
                    "High Wage",
                    "Example Inc.",
                    "Toronto, ON M5V 1A1",
                    "6322-Cooks",
                    "Unknown",
                    1,
                    1,
                ],
            },
            {
                "resource_id": RESOLVED_2022_Q2_POSITIVE_FR,
                "language": "fr",
                "filename": "positive-fr.csv",
                "headers": [
                    "Province/Territoire",
                    "Volet du programme",
                    "Employeur",
                    "Adresse",
                    "Profession",
                    "Incorporer le statut",
                    "EIMT Approuvés",
                    "Postes Approuvés",
                ],
                "row": [
                    "Ontario",
                    "Haut salaire",
                    "Example Inc.",
                    "Toronto, ON M5V 1A1",
                    "6322-Cuisiniers",
                    "Inconnu",
                    1,
                    french_positions,
                ],
            },
        ]
        catalogue_resources = []
        census_resources = []
        raw_resources = []
        for definition in definitions:
            path = directory / definition["filename"]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(definition["headers"])
                writer.writerow(definition["row"])
            catalogue = {
                "dataset_id": "positive-dataset",
                "resource_id": definition["resource_id"],
                "resource_page_url": "https://example.test/resource",
                "download_url": "https://example.test/download",
                "source_filename": definition["filename"],
                "format": "CSV",
                "decision": "positive",
                "language": definition["language"],
                "title": {
                    "en": "Positive employer list using NOC 2011",
                    "fr": "Liste positive utilisant la CNP 2011",
                },
                "period": period,
            }
            census = {
                **catalogue,
                "selected_sheet": "CSV",
                "selected_schema_signature": "schema",
                "sha256": file_sha256(path),
                "sheets": [
                    {
                        "name": "CSV",
                        "header": {"row": 1, "values": definition["headers"]},
                        "estimated_data_rows": 1,
                    }
                ],
            }
            raw = {
                **catalogue,
                "status": "downloaded",
                "sha256": file_sha256(path),
                "catalogue_format": "CSV",
                "format": "CSV",
                "format_matches_catalogue": True,
                "source_filename": definition["filename"],
                "archive_path": str(path),
            }
            catalogue_resources.append(catalogue)
            census_resources.append(census)
            raw_resources.append(raw)
        return (
            {"resources": catalogue_resources},
            {"resources": census_resources},
            {"resources": raw_resources},
        )

    def test_requested_english_headers_use_matching_approved_french_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            documents = self.documents(Path(directory))
            plans, quarantines = build_source_plans(*documents)

            self.assertEqual([], quarantines)
            self.assertEqual(1, len(plans))
            selected = plans[0]
            self.assertEqual(
                "normalized_with_bilingual_measure_override",
                selected.disposition,
            )
            self.assertIn(RESOLVED_2022_Q2_QUALITY_FLAG, selected.anomaly_flags)
            self.assertTrue(
                selected.interpretation_evidence["normalized_record_multiset_match"]
            )
            with source_rows(selected) as rows:
                record = next(canonical_records(selected, rows))
            self.assertEqual("approved_lmias", record["lmia_measure"])
            self.assertEqual("approved_positions", record["position_measure"])
            self.assertIn(RESOLVED_2022_Q2_QUALITY_FLAG, record["quality_flags"])

    def test_override_fails_closed_when_language_pair_differs(self) -> None:
        with TemporaryDirectory() as directory:
            documents = self.documents(Path(directory), french_positions=2)
            with self.assertRaisesRegex(
                CanonicalBuildError,
                "records no longer match exactly",
            ):
                build_source_plans(*documents)


if __name__ == "__main__":
    unittest.main()
