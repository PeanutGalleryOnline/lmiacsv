from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from processor.inventory import (
    build_inventory,
    detect_quarter,
    detect_status,
    inspect_csv,
)


class InventoryTests(unittest.TestCase):
    def test_half_year_quarter_is_detected_before_q1(self) -> None:
        self.assertEqual(detect_quarter("2017q1q2_positive_en.csv", ""), "Q1-Q2")

    def test_ambiguous_filename_uses_content_status(self) -> None:
        filename = "department-employer-list2021q1.csv"
        probe = "Employers who received a negative Labour Market Impact Assessment"
        self.assertEqual(detect_status(filename, probe), "negative")

    def test_csv_reader_preserves_embedded_quotes_and_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2025q1_positive_en.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Published positive decisions for 2025 Q1"])
                writer.writerow(["Province/Territory", "Employer", "Address", "Positions"])
                writer.writerow(["Ontario", 'Park "A" Motel', "Toronto, ON", "1"])
                writer.writerow(["Quebec", "Two\nLine Employer", "Montréal, QC", "2"])

            columns, rows, _ = inspect_csv(path)
            self.assertEqual(columns[1], "Employer")
            self.assertEqual(rows, 2)

    def test_inventory_writes_isolated_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            source_path = Path(source)
            csv_path = source_path / "tfwp_2025q1_pos_en.csv"
            csv_path.write_text(
                "Positive decisions January to March 2025\n"
                "Province/Territory,Employer,Address,Approved Positions\n"
                "Ontario,Example Inc.,Toronto ON,2\n",
                encoding="utf-8",
            )
            (source_path / "tfwp_2025q1_pos_en.xlsx").write_bytes(b"fixture")

            overview = build_inventory(source_path, Path(output))

            self.assertEqual(overview["inventory"]["csv_files"], 1)
            self.assertEqual(overview["inventory"]["raw_rows"], 1)
            catalogue = json.loads(
                (Path(output) / "content" / "releases" / "index.json").read_text()
            )
            self.assertTrue(catalogue["releases"][0]["has_xlsx_pair"])
            self.assertFalse(catalogue["releases"][0]["publication_ready"])


if __name__ == "__main__":
    unittest.main()

