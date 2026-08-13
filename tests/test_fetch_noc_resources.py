from __future__ import annotations

import unittest

from lmiacsv.fetch_noc_resources import decode_csv


class NocFetchTests(unittest.TestCase):
    def test_detects_utf8_and_legacy_cp1252_csvs(self) -> None:
        utf8 = "Level,Hierarchical structure,Code,Class title\n4,Unit group,0001,Café\n".encode()
        cp1252 = (
            "Level,Hierarchical structure,Code,Class title\n"
            "4,Unit group,6511,Maîtres d'hôtel\n"
        ).encode("cp1252")

        self.assertEqual(decode_csv(utf8)[0], "utf-8-sig")
        self.assertEqual(decode_csv(cp1252)[0], "cp1252")


if __name__ == "__main__":
    unittest.main()
