import tempfile
import unittest
from pathlib import Path

from lmiacsv.collect_2021q2_receipts import inspect_csv, sanitize_url, validation_status


class ReceiptHelperTests(unittest.TestCase):
    def test_signed_query_and_fragment_are_not_persisted(self) -> None:
        self.assertEqual(
            "https://example.test/source/file.xlsx",
            sanitize_url("https://example.test/source/file.xlsx?sv=1&sig=secret#fragment"),
        )

    def test_windows_1252_csv_is_inspected(self) -> None:
        source = (
            '"Employeurs – 2020",,,,,\r\n'
            "Province,Stream,Employer,Address,Occupation,Requested Positions\r\n"
            "Québec,Low Wage,Café Inc.,Montréal,6322-Cooks,2\r\n"
            "Notes:,,,,,\r\n"
        ).encode("cp1252")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.csv"
            path.write_bytes(source)
            result = inspect_csv(path)
        self.assertEqual("cp1252", result["encoding"])
        self.assertEqual(1, result["data_rows"])
        self.assertEqual(2, result["requested_positions"])

    def test_validation_status_is_extracted_from_saved_html(self) -> None:
        page = b"""
            <html><body><table>
              <tr><th>Validation status</th><td>Invalid data</td></tr>
              <tr><th>Validation timestamp</th><td>December 13, 2023</td></tr>
            </table></body></html>
        """
        self.assertEqual(
            {"status": "Invalid data", "timestamp": "December 13, 2023"},
            validation_status(page),
        )


if __name__ == "__main__":
    unittest.main()
