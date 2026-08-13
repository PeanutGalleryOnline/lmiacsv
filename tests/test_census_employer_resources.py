from __future__ import annotations

import unittest

from lmiacsv.census_employer_resources import (
    analyze_rows,
    decision_signal,
    header_candidate,
    schema_signature,
)


class EmployerResourceCensusTests(unittest.TestCase):
    def test_finds_header_below_title_without_assuming_first_row(self) -> None:
        rows = [
            ["Employers issued positive LMIAs, January to March 2025"],
            [
                "Province/Territory",
                "Program Stream",
                "Employer",
                "Address",
                "Occupation (NOC 2021)",
                "Positions Approved",
            ],
            ["Ontario", "High Wage", "Example Inc.", "Toronto", "62020", 2],
            ["Notes:"],
        ]

        analysis = analyze_rows(iter(rows))

        self.assertEqual(analysis["header"]["row"], 2)
        self.assertEqual(analysis["estimated_data_rows"], 1)
        self.assertEqual(analysis["first_note_row"], 4)

    def test_requires_multiple_domain_terms_for_header(self) -> None:
        self.assertIsNone(header_candidate([["A report title"], ["Name", "Value"]]))

    def test_schema_signature_uses_normalized_header_values(self) -> None:
        first = header_candidate([["Employer", "Program Stream", "Positions Approved", "NOC 2021"]])
        second = header_candidate(
            [["  EMPLOYER ", "Program—Stream", "Positions Approved", "NOC 2021"]]
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(schema_signature(first), schema_signature(second))

    def test_header_measure_signals_decision_without_using_filename(self) -> None:
        positive = header_candidate(
            [["Employer", "Program Stream", "Approved LMIAs", "Approved Positions"]]
        )
        negative = header_candidate(
            [["Employer", "Program Stream", "Requested LMIAs", "Requested Positions"]]
        )

        self.assertEqual(decision_signal(positive), "positive")
        self.assertEqual(decision_signal(negative), "negative")

    def test_french_headers_are_first_class_census_candidates(self) -> None:
        positive = header_candidate(
            [["Province/Territoire", "Volet du programme", "Employeur", "Postes approuvés"]]
        )
        negative = header_candidate(
            [["Province/Territoire", "Volet", "Employeur", "Postes demandés"]]
        )

        self.assertIsNotNone(positive)
        self.assertIsNotNone(negative)
        self.assertEqual(decision_signal(positive), "positive")
        self.assertEqual(decision_signal(negative), "negative")


if __name__ == "__main__":
    unittest.main()
