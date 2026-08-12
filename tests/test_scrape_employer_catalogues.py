from __future__ import annotations

import json
import unittest

from lmiacsv.scrape_catalogue import CatalogueError
from lmiacsv.scrape_employer_catalogues import CATALOGUES, build_inventory


def resource_node(
    decision: str,
    resource_id: str,
    period: str,
    language: str,
    filename: str,
    *,
    download_dataset_id: str | None = None,
    legacy_direct_url: bool = False,
) -> dict[str, object]:
    spec = CATALOGUES[decision]
    dataset_id = download_dataset_id or spec.dataset_id
    uri = f"https://open.canada.ca/data/dataset/{spec.dataset_id}/resource/{resource_id}"
    decision_title = decision.title()
    access_url = (
        f"https://www.esdc.gc.ca/ouvert-open/bca-seb/imt-lmi/{filename}"
        if legacy_direct_url
        else (
            f"https://open.canada.ca/data/dataset/{dataset_id}/resource/"
            f"{resource_id}/download/{filename}"
        )
    )
    return {
        "@id": uri,
        "@type": "dcat:Distribution",
        "dcat:accessURL": {"@id": access_url},
        "dcat:byteSize": {"@type": "xsd:decimal", "@value": "1234.0"},
        "dct:format": filename.rsplit(".", 1)[-1].upper(),
        "dct:issued": {"@type": "xsd:dateTime", "@value": "2025-01-01"},
        "dct:modified": {"@type": "xsd:dateTime", "@value": "2026-01-01"},
        "dct:language": language,
        "dct:title": [
            {
                "@language": "en",
                "@value": (
                    f"{period}-Employers Who Were Issued a {decision_title} Labour Market "
                    "Impact Assessment (LMIA) by Business Location"
                ),
            },
            {
                "@language": "fr",
                "@value": f"{period}-Employeurs ayant obtenu une EIMT {decision}",
            },
        ],
    }


def source_document(
    decision: str,
    *,
    shared_filename: str = "government-collision.xlsx",
    bad_download_dataset: bool = False,
) -> bytes:
    spec = CATALOGUES[decision]
    resources = [
        resource_node(
            decision,
            f"{decision}-2020q4-en",
            "2020Q4",
            "en",
            shared_filename,
            download_dataset_id="wrong-dataset" if bad_download_dataset else None,
        ),
        resource_node(
            decision,
            f"{decision}-2020q4-fr",
            "2020Q4",
            "fr",
            shared_filename,
        ),
        resource_node(
            decision,
            f"{decision}-2021q1-en",
            "2021Q1",
            "en",
            f"{decision}-2021q1-en.csv",
        ),
        resource_node(
            decision,
            f"{decision}-2021q1-fr",
            "2021Q1",
            "fr",
            f"{decision}-2021q1-fr.csv",
        ),
    ]
    publisher_uri = "https://open.canada.ca/organization/esdc"
    graph: list[dict[str, object]] = [
        {
            "@id": f"https://open.canada.ca/data/dataset/{spec.dataset_id}",
            "@type": "dcat:Dataset",
            "dcat:distribution": [{"@id": resource["@id"]} for resource in resources],
            "dct:identifier": spec.dataset_id,
            "dct:title": [
                {"@language": "en", "@value": f"{decision.title()} employer lists"},
                {"@language": "fr", "@value": f"Listes {decision}"},
            ],
            "dct:description": [
                {"@language": "en", "@value": "Official employer-list catalogue"},
                {"@language": "fr", "@value": "Catalogue officiel"},
            ],
            "dct:publisher": {"@id": publisher_uri},
            "dct:issued": {"@type": "xsd:dateTime", "@value": "2016-01-01"},
            "dct:modified": {"@type": "xsd:dateTime", "@value": "2026-01-01"},
            "dct:accrualPeriodicity": "P3M",
        },
        {
            "@id": publisher_uri,
            "@type": "foaf:Organization",
            "foaf:name": [
                {
                    "@language": "en",
                    "@value": "Employment and Social Development Canada",
                },
                {"@language": "fr", "@value": "Emploi et Développement social Canada"},
            ],
        },
        *resources,
    ]
    return json.dumps({"@context": {}, "@graph": graph}).encode()


def both_sources(**kwargs: object) -> dict[str, bytes]:
    return {
        "positive": source_document("positive", **kwargs),
        "negative": source_document("negative", **kwargs),
    }


class EmployerCatalogueScraperTests(unittest.TestCase):
    def test_colliding_government_filenames_receive_unique_archive_paths(self) -> None:
        inventory = build_inventory(both_sources())
        collisions = inventory["audit"]["filename_collisions"]

        self.assertEqual(inventory["resource_count"], 8)
        self.assertEqual(inventory["release_count"], 4)
        self.assertEqual(inventory["period_count"], 2)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]["resource_count"], 4)
        self.assertTrue(collisions[0]["cross_decision"])
        self.assertEqual(len(set(collisions[0]["archive_paths"])), 4)
        self.assertTrue(
            all(
                resource["dataset_id"] in resource["archive_path"]
                for resource in inventory["resources"]
            )
        )
        self.assertTrue(
            all(
                resource["resource_id"] in resource["archive_path"]
                for resource in inventory["resources"]
            )
        )

    def test_builds_complete_bilingual_release_pairs(self) -> None:
        inventory = build_inventory(both_sources())

        self.assertEqual(inventory["counts"]["languages"], {"en": 4, "fr": 4})
        self.assertEqual(inventory["counts"]["decisions"], {"negative": 4, "positive": 4})
        self.assertEqual(inventory["audit"]["language_pairing_issues"], [])
        self.assertTrue(
            all(set(release["resources"]) == {"en", "fr"} for release in inventory["releases"])
        )

    def test_rejects_download_url_bound_to_another_dataset(self) -> None:
        sources = both_sources()
        sources["positive"] = source_document("positive", bad_download_dataset=True)

        with self.assertRaisesRegex(CatalogueError, "not bound to its dataset and UUID"):
            build_inventory(sources)

    def test_accepts_declared_legacy_esdc_direct_download_without_using_it_as_identity(
        self,
    ) -> None:
        document = json.loads(source_document("negative"))
        resource = next(
            node for node in document["@graph"] if node.get("@type") == "dcat:Distribution"
        )
        filename = "TFWP_2021Q2_Negative_FR.xlsx"
        resource["dcat:accessURL"] = {
            "@id": f"https://www.esdc.gc.ca/ouvert-open/bca-seb/imt-lmi/{filename}"
        }
        resource["dct:format"] = "XLSX"
        sources = both_sources()
        sources["negative"] = json.dumps(document).encode()

        inventory = build_inventory(sources)
        parsed = next(
            item
            for item in inventory["resources"]
            if item["resource_id"] == resource["@id"].rsplit("/", 1)[1]
        )

        self.assertEqual(parsed["download_url_identity"], "trusted_legacy_direct_url")
        self.assertIn(parsed["dataset_id"], parsed["archive_path"])
        self.assertIn(parsed["resource_id"], parsed["archive_path"])

    def test_jsonld_graph_order_does_not_change_semantic_fingerprint(self) -> None:
        first_sources = both_sources()
        reordered_sources = {}
        for decision, content in first_sources.items():
            document = json.loads(content)
            document["@graph"].reverse()
            reordered_sources[decision] = json.dumps(document).encode()

        first = build_inventory(first_sources)
        second = build_inventory(reordered_sources)

        self.assertEqual(first["catalogues"], second["catalogues"])
        self.assertEqual(first["resources"], second["resources"])
        self.assertEqual(
            first["source_snapshots"][0]["combined_semantic_sha256"],
            second["source_snapshots"][0]["combined_semantic_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
