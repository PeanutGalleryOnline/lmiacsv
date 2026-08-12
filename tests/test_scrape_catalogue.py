from __future__ import annotations

import json
import unittest

from lmiacsv.scrape_catalogue import (
    DATASET_ID,
    CatalogueError,
    parse_catalogue,
)


def resource_node(
    resource_id: str,
    title: str,
    *,
    language: str = "en",
    download_host: str = "open.canada.ca",
) -> dict[str, object]:
    uri = f"https://open.canada.ca/dataset/{DATASET_ID}/resource/{resource_id}"
    return {
        "@id": uri,
        "@type": "dcat:Distribution",
        "dcat:accessURL": {
            "@id": f"https://{download_host}/data/dataset/{DATASET_ID}/resource/{resource_id}/download/source.xlsx"
        },
        "dcat:byteSize": {"@type": "xsd:decimal", "@value": "1234.0"},
        "dct:format": "XLSX",
        "dct:issued": {"@type": "xsd:dateTime", "@value": "2025-01-01T00:00:00"},
        "dct:modified": {"@type": "xsd:dateTime", "@value": "2026-01-01T00:00:00"},
        "dct:language": language,
        "dct:title": [
            {"@language": "en", "@value": title},
            {"@language": "fr", "@value": f"FR: {title}"},
        ],
    }


def source_document(
    *,
    include_general_negative: bool = False,
    bad_download_host: bool = False,
    omit_distribution_node: bool = False,
) -> bytes:
    positive_id = "positive-resource"
    requested_id = "requested-resource"
    sawp_id = "sawp-resource"
    resources = [
        resource_node(
            positive_id,
            "Table 14-Number of Positive Labour Market Impact Assessments (LMIA) by Program Stream and Province/Territory between 2025Q1 and 2026Q1",
            download_host="example.test" if bad_download_host else "open.canada.ca",
        ),
        resource_node(
            requested_id,
            "Table 12-Number of Temporary Foreign Worker (TFW) Positions on Requested Labour Market Impact Assessments (LMIAs) by Province/Territory between 2025Q1 and 2026Q1",
        ),
        resource_node(
            sawp_id,
            "Table 25-Number of Positive and Negative Labour Market Impact Assessments (LMIAs) under the Seasonal Agricultural Worker Program (SAWP) by Location of Employment between 2025Q1 and 2026Q1",
        ),
    ]
    if include_general_negative:
        resources.append(
            resource_node(
                "negative-resource",
                "Table 29-Number of Negative Labour Market Impact Assessments (LMIA) by Program Stream and Province/Territory between 2025Q1 and 2026Q1",
            )
        )

    publisher_uri = "https://open.canada.ca/organization/esdc"
    references = [{"@id": resource["@id"]} for resource in resources]
    graph: list[dict[str, object]] = [
        {
            "@id": f"https://open.canada.ca/dataset/{DATASET_ID}",
            "@type": "dcat:Dataset",
            "dcat:distribution": references,
            "dct:identifier": DATASET_ID,
            "dct:title": [
                {"@language": "en", "@value": "LMIA statistics"},
                {"@language": "fr", "@value": "Statistiques EIMT"},
            ],
            "dct:description": [
                {"@language": "en", "@value": "Official catalogue"},
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
    if omit_distribution_node:
        graph.pop()
    return json.dumps({"@context": {}, "@graph": graph}).encode()


class CatalogueScraperTests(unittest.TestCase):
    def test_classifies_units_without_treating_non_substitutes_as_negative_totals(self) -> None:
        catalogue = parse_catalogue(source_document())
        resources = {resource["table_number"]: resource for resource in catalogue["resources"]}
        audit = catalogue["audit"]["national_decision_rate"]

        self.assertEqual(resources[14]["family"], "lmia_applications")
        self.assertEqual(resources[14]["unit"], "lmias")
        self.assertEqual(resources[14]["decision_scope"], "positive")
        self.assertEqual(resources[12]["unit"], "positions")
        self.assertEqual(resources[12]["decision_scope"], "requested")
        self.assertEqual(resources[25]["population_scope"], "sawp")
        self.assertEqual(audit["status"], "not_computable_from_catalogue")
        self.assertEqual(audit["negative_lmia_resources"], [])
        self.assertEqual(
            audit["non_substitutes"]["requested_position_resources"],
            ["requested-resource"],
        )
        self.assertEqual(
            audit["non_substitutes"]["sawp_only_decision_resources"],
            ["sawp-resource"],
        )

    def test_audit_changes_when_a_general_negative_measure_is_published(self) -> None:
        catalogue = parse_catalogue(source_document(include_general_negative=True))
        audit = catalogue["audit"]["national_decision_rate"]

        self.assertEqual(audit["status"], "computable_from_catalogue")
        self.assertEqual(audit["negative_lmia_resources"], ["negative-resource"])
        self.assertIsNone(audit["missing_measure"])

    def test_rejects_untrusted_download_host(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "untrusted access URL"):
            parse_catalogue(source_document(bad_download_host=True))

    def test_rejects_distribution_reference_mismatch(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "Distribution graph mismatch"):
            parse_catalogue(source_document(omit_distribution_node=True))

    def test_equivalent_graph_order_produces_identical_catalogue(self) -> None:
        source = source_document()
        reordered_document = json.loads(source)
        reordered_document["@graph"].reverse()
        reordered_source = json.dumps(reordered_document).encode()

        first = parse_catalogue(source)
        second = parse_catalogue(reordered_source)

        self.assertEqual(first["dataset"], second["dataset"])
        self.assertEqual(first["resources"], second["resources"])
        self.assertEqual(
            first["source_snapshot"]["semantic_sha256"],
            second["source_snapshot"]["semantic_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
