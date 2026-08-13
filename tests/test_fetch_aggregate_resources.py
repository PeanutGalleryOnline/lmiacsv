from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lmiacsv.fetch_aggregate_resources import (
    candidate_filenames,
    candidate_urls,
    load_reusable,
    period_range,
    source_release_period,
)


class AggregateFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resource = {
            "dataset_id": "dataset-id",
            "resource_id": "resource-id",
            "language": "en",
            "source_filename": "tfwp2026_q1_table_14_e.xlsx",
            "download_url": (
                "https://open.canada.ca/data/dataset/dataset-id/resource/resource-id/"
                "download/tfwp2026_q1_table_14_e.xlsx"
            ),
            "title": "Table 14 between 2025Q1 and 2026Q1",
        }

    def test_period_range_crosses_year_boundary(self) -> None:
        self.assertEqual(
            period_range("2024Q3", "2025Q2"),
            ["2024Q3", "2024Q4", "2025Q1", "2025Q2"],
        )

    def test_release_period_comes_from_official_filename(self) -> None:
        self.assertEqual(source_release_period(self.resource), "2026Q1")

    def test_release_period_is_end_of_a_legacy_rolling_window(self) -> None:
        resource = {
            **self.resource,
            "source_filename": "tfwp2018_q1_2019_q3_table_14_e.csv",
            "title": "Table 14",
        }
        self.assertEqual(source_release_period(resource), "2019Q3")

    def test_candidate_generation_is_deterministic_and_includes_known_style(self) -> None:
        filenames = candidate_filenames("2025Q4")
        self.assertIn("tfwp2025_q4_table_14_e.xlsx", filenames)
        self.assertIn("tfwp_2025q4_table_14_e.csv", filenames)
        self.assertIn("tfwp2025_q4_table_14_f.xlsx", candidate_filenames("2025Q4", "fr"))

        candidates = candidate_urls(self.resource, "2025Q4")
        self.assertEqual({value["release_period"] for value in candidates}, {"2025Q4", "2026Q1"})
        self.assertEqual(len(candidates), len({value["download_url"] for value in candidates}))

    def test_pre_2022_candidates_include_the_published_rolling_window(self) -> None:
        filenames = candidate_filenames("2019Q3")
        self.assertIn("tfwp2018_q1_2019_q3_table_14_e.csv", filenames)
        self.assertIn("tfwp_2018q1-2019q3_table_14_e.xlsx", filenames)

        later_filenames = candidate_filenames("2022Q1")
        self.assertNotIn("tfwp2021_q1_2022_q1_table_14_e.csv", later_filenames)

    def test_recorded_misses_are_reused_unless_refresh_is_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            url = "https://open.canada.ca/missing.csv"
            manifest.write_text(
                json.dumps(
                    {
                        "resources": [
                            {"download_url": url, "status": "not_found", "http_status": 404}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertIn(url, load_reusable(manifest, refresh=False))
            self.assertEqual(load_reusable(manifest, refresh=True), {})


if __name__ == "__main__":
    unittest.main()
