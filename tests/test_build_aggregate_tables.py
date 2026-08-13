from __future__ import annotations

import unittest

from lmiacsv.build_aggregate_tables import (
    annual_national_summary,
    annual_reconciliation,
    latest_quarterly,
    national_rows,
    parse_matrix,
    quarterly_period,
)


def source(kind: str, release: str | None, digest: str) -> dict[str, object]:
    return {
        "source_kind": kind,
        "dataset_id": "dataset-id",
        "resource_id": "resource-id",
        "release_period": release,
        "source_filename": f"source-{digest}.xlsx",
        "sha256": digest,
    }


class AggregateBuildTests(unittest.TestCase):
    def test_parses_month_range_headers_as_quarters(self) -> None:
        self.assertEqual(quarterly_period("Jan-Mar2025"), "2025Q1")
        self.assertEqual(quarterly_period("Apr - Jun 2025"), "2025Q2")
        self.assertEqual(quarterly_period("2025Q3"), "2025Q3")
        self.assertEqual(quarterly_period("janv.-mars 2025"), "2025Q1")
        self.assertEqual(quarterly_period("2025T4"), "2025Q4")

    def test_parses_source_faithful_quarterly_observations(self) -> None:
        matrix = [
            ["ID", "Province/Territory", "Program Stream", "Jan-Mar2025", "Apr-Jun2025"],
            [1, "NL", "High Wage", 10, 12],
            [2, "Ontario", "Low-Wage", 20, 22],
        ]

        observations, audit = parse_matrix(
            matrix,
            "Sheet1",
            source("quarterly_release", "2025Q2", "a" * 64),
        )

        self.assertEqual(audit["data_dimension_count"], 2)
        self.assertEqual(audit["periods"], ["2025Q1", "2025Q2"])
        self.assertEqual(len(observations), 4)
        self.assertEqual(observations[0]["province_territory"], "NL")
        self.assertEqual(observations[-1]["program_stream"], "low_wage")
        self.assertEqual(observations[-1]["positive_lmias"], 22)

    def test_parses_french_dimensions_and_periods_to_the_same_keys(self) -> None:
        matrix = [
            ["ID", "Province/Territoire", "Volet du programme", "janv.-mars 2025"],
            [1, "Colombie-Britannique", "Haut salaire", 17],
            [2, "Québec", "Bas salaire", 23],
        ]

        observations, audit = parse_matrix(
            matrix,
            "Feuil1",
            {**source("quarterly_release", "2025Q1", "f" * 64), "language": "fr"},
        )

        self.assertEqual(audit["periods"], ["2025Q1"])
        self.assertEqual(
            [
                (row["province_territory"], row["program_stream"], row["positive_lmias"])
                for row in observations
            ],
            [("BC", "high_wage", 17), ("QC", "low_wage", 23)],
        )
        self.assertTrue(all(row["source_language"] == "fr" for row in observations))

    def test_parses_legacy_multiline_year_header_and_excludes_published_totals(self) -> None:
        matrix = [
            ["Number of Positive LMIAs", None, None, None, None],
            [None, None, 2021, None, 2022],
            ["Province/Territory", "Program Stream", "Jan-Mar", "Apr-Jun", "Jan-Mar"],
            ["Canada", "High Wage", 100, 110, 120],
            ["Ontario", "High Wage", 10, 11, 12],
            ["Ontario", "Total", 20, 21, 22],
        ]

        observations, audit = parse_matrix(
            matrix,
            "CSV",
            source("quarterly_release", "2022Q1", "c" * 64),
        )

        self.assertEqual(audit["periods"], ["2021Q1", "2021Q2", "2022Q1"])
        self.assertEqual(audit["ignored_summary_rows"], [4, 6])
        self.assertEqual(len(observations), 3)
        self.assertEqual([value["positive_lmias"] for value in observations], [10, 11, 12])

    def test_newest_overlap_wins_only_after_revision_is_recorded(self) -> None:
        old_matrix = [
            ["Province/Territory", "Program Stream", "2025Q1"],
            ["ON", "High Wage", 100],
        ]
        new_matrix = [
            ["Province/Territory", "Program Stream", "2025Q1"],
            ["ON", "High Wage", 101],
        ]
        old, _audit = parse_matrix(
            old_matrix,
            "Sheet1",
            source("quarterly_release", "2025Q1", "a" * 64),
        )
        new, _audit = parse_matrix(
            new_matrix,
            "Sheet1",
            source("quarterly_release", "2025Q2", "b" * 64),
        )

        selected, revisions, revised_keys = latest_quarterly(old + new)

        self.assertEqual(selected[0]["positive_lmias"], 101)
        self.assertEqual(selected[0]["source_release_period"], "2025Q2")
        self.assertEqual(len(revisions), 1)
        self.assertIn(("2025Q1", "ON", "high_wage"), revised_keys)

    def test_reconciles_complete_quarterly_year_to_annual_value(self) -> None:
        quarterly = []
        for quarter, value in enumerate((10, 20, 30, 40), start=1):
            quarterly.append(
                {
                    "period": f"2024Q{quarter}",
                    "year": 2024,
                    "province_territory": "ON",
                    "program_stream": "High Wage",
                    "positive_lmias": value,
                }
            )
        annual = [
            {
                "year": 2024,
                "province_territory": "ON",
                "program_stream": "High Wage",
                "positive_lmias": 100,
            }
        ]

        checks = annual_reconciliation(quarterly, annual)

        self.assertEqual(checks[0]["status"], "match")
        self.assertEqual(checks[0]["difference"], 0)

    def test_reconciliation_records_annual_only_streams(self) -> None:
        quarterly = [
            {
                "period": f"2024Q{quarter}",
                "year": 2024,
                "province_territory": "ON",
                "program_stream": "High Wage",
                "positive_lmias": 10,
            }
            for quarter in range(1, 5)
        ]
        annual = [
            {
                "year": 2024,
                "province_territory": "ON",
                "program_stream": "High Wage",
                "positive_lmias": 40,
            },
            {
                "year": 2024,
                "province_territory": "ON",
                "program_stream": "Unspecified",
                "positive_lmias": 3,
            },
        ]

        checks = annual_reconciliation(quarterly, annual)

        self.assertEqual(
            [value["status"] for value in checks],
            ["match", "missing_quarterly_observation"],
        )
        self.assertEqual(checks[1]["annual_total"], 3)

        summary = annual_national_summary(checks)
        self.assertEqual(summary[0]["quarterly_total"], 40)
        self.assertEqual(summary[0]["annual_total"], 43)
        self.assertEqual(summary[0]["difference"], -3)
        self.assertEqual(summary[0]["annual_only_positive_lmias"], 3)

    def test_national_rows_surface_reconciliation_caveats(self) -> None:
        quarterly = [
            {
                "period": "2024Q1",
                "year": 2024,
                "quarter": 1,
                "province_territory": "ON",
                "program_stream": "High Wage",
                "positive_lmias": 10,
                "source_release_period": "2025Q1",
            }
        ]
        checks = [
            {
                "year": 2024,
                "status": "missing_quarterly_observation",
                "annual_total": 3,
            }
        ]

        rows = national_rows(quarterly, {("2024Q1", "ON", "High Wage")}, checks)

        self.assertEqual(
            rows[0]["quality_flags"],
            "annual_scope_has_unallocated_lmias;revised_across_releases",
        )


if __name__ == "__main__":
    unittest.main()
