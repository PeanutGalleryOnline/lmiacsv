from __future__ import annotations

import unittest

from lmiacsv.scrape_catalogue import CatalogueError
from lmiacsv.scrape_noc_catalogue import SPECS, build_catalogue, discover_source


def page(spec, href: str | None = None) -> bytes:
    link = href or f"https://www.statcan.gc.ca{spec.download_suffix}"
    return f'<html><body><a href="{link}">Official {spec.source_id} CSV</a></body></html>'.encode()


class NocCatalogueTests(unittest.TestCase):
    def test_discovers_each_declared_official_csv_from_its_page(self) -> None:
        catalogue = build_catalogue({spec.source_id: page(spec) for spec in SPECS})

        self.assertEqual(len(catalogue["sources"]), 8)
        self.assertEqual(
            {source["language"] for source in catalogue["sources"]},
            {"en", "fr"},
        )
        self.assertEqual(
            {source["source_kind"] for source in catalogue["sources"]},
            {"classification_structure", "correspondence"},
        )
        self.assertTrue(
            all(
                source["download_url"].startswith("https://www.statcan.gc.ca/")
                for source in catalogue["sources"]
            )
        )

    def test_rejects_a_matching_path_on_an_untrusted_host(self) -> None:
        spec = SPECS[0]
        with self.assertRaisesRegex(CatalogueError, "Untrusted"):
            discover_source(page(spec, f"https://example.test{spec.download_suffix}"), spec)


if __name__ == "__main__":
    unittest.main()
