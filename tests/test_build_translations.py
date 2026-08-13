from __future__ import annotations

import unittest

from lmiacsv.build_translations import FIELDS, build_rows, csv_bytes


class TranslationBuildTests(unittest.TestCase):
    def test_registry_is_unique_and_carries_underlying_observation_evidence(self) -> None:
        reconciliation = {
            "translation_evidence": {
                "program_stream": {
                    "high_wage": {
                        "en": [{"raw_value": "High Wage", "observation_count": 4}],
                        "fr": [{"raw_value": "Haut salaire", "observation_count": 4}],
                    },
                    "source_code_99": {
                        "en": [{"raw_value": "99", "observation_count": 1}]
                    },
                }
            }
        }

        rows = build_rows(reconciliation)
        by_key = {row["translation_key"]: row for row in rows}

        self.assertEqual(len(rows), len(by_key))
        self.assertEqual(
            "observed_in_both_language_sources",
            by_key["program_stream.high_wage"]["verification_status"],
        )
        self.assertEqual(4, by_key["program_stream.high_wage"]["fr_observation_count"])
        self.assertEqual("", by_key["program_stream.source_code_99"]["fr"])
        self.assertEqual(FIELDS, csv_bytes(rows).decode("utf-8").splitlines()[0].split(","))


if __name__ == "__main__":
    unittest.main()
