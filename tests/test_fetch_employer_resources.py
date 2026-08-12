from __future__ import annotations

import unittest
from pathlib import Path

from lmiacsv.fetch_employer_resources import validate_content, versioned_path
from lmiacsv.scrape_catalogue import CatalogueError


RESOURCE = {
    "dataset_id": "dataset-a",
    "resource_id": "resource-a",
    "source_filename": "collision.xlsx",
}


class EmployerResourceFetcherTests(unittest.TestCase):
    def test_versioned_path_uses_dataset_resource_and_content_hash(self) -> None:
        first = versioned_path(Path("raw"), RESOURCE, "a" * 64)
        second = versioned_path(Path("raw"), RESOURCE, "b" * 64)
        collision = versioned_path(
            Path("raw"),
            {**RESOURCE, "resource_id": "resource-b"},
            "a" * 64,
        )

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, collision)
        self.assertEqual(first.name, "collision.xlsx")
        self.assertIn("resource-a", first.parts)

    def test_rejects_html_masquerading_as_csv(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "returned HTML"):
            validate_content(b"<!doctype html><title>Error</title>", "CSV", "resource-a")

    def test_validates_spreadsheet_container_magic(self) -> None:
        self.assertEqual(
            validate_content(b"PK\x03\x04payload", "XLSX", "xlsx-resource"),
            "XLSX",
        )
        self.assertEqual(
            validate_content(b"\xd0\xcf\x11\xe0payload", "XLS", "xls-resource"),
            "XLS",
        )
        self.assertEqual(
            validate_content(b"Employer,Positions\nExample,2\n", "XLSX", "csv-resource"),
            "CSV",
        )

        with self.assertRaisesRegex(CatalogueError, "not recognizable"):
            validate_content(b"\x00\x01\x02", "XLSX", "bad-resource")


if __name__ == "__main__":
    unittest.main()
