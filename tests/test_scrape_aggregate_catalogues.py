from __future__ import annotations

import json
import unittest

from lmiacsv.scrape_aggregate_catalogues import (
    ANNUAL_DATASET_ID,
    QUARTERLY_DATASET_ID,
    build_catalogue,
    parse_source,
)
from lmiacsv.scrape_catalogue import CatalogueError


def source_document(
    dataset_id: str,
    title: str,
    *,
    table_title: str,
    table_title_fr: str | None = None,
) -> bytes:
    resource_ids = {language: f"table-14-{language}-{dataset_id[:4]}" for language in ("en", "fr")}
    resource_uris = {
        language: f"https://open.canada.ca/dataset/{dataset_id}/resource/{resource_id}"
        for language, resource_id in resource_ids.items()
    }
    if table_title_fr is None:
        table_title_fr = (
            "Tableau 14 – Nombre d’études d’impact positives sur le marché du travail "
            "(EIMT) selon le volet et la province ou le territoire"
        )
    distributions = []
    for language, resource_uri in resource_uris.items():
        localized_title = table_title if language == "en" else table_title_fr
        distributions.append(
            {
                "@id": resource_uri,
                "@type": "dcat:Distribution",
                "dct:language": language,
                "dct:title": [
                    {"@language": language, "@value": localized_title},
                ],
                "dct:format": "XLSX",
                "dct:issued": {"@value": "2026-01-01"},
                "dct:modified": {"@value": "2026-01-01"},
                "dcat:byteSize": {"@value": "1234"},
                "dcat:accessURL": {
                    "@id": (
                        "https://open.canada.ca/data/dataset/"
                        f"{dataset_id}/resource/{resource_ids[language]}/download/"
                        f"table14_{language}.xlsx"
                    )
                },
            }
        )
    return json.dumps(
        {
            "@graph": [
                {
                    "@id": f"https://open.canada.ca/dataset/{dataset_id}",
                    "@type": "dcat:Dataset",
                    "dct:identifier": dataset_id,
                    "dct:title": [
                        {"@language": "en", "@value": title},
                        {"@language": "fr", "@value": f"FR: {title}"},
                    ],
                    "dct:issued": {"@value": "2019-01-01"},
                    "dct:modified": {"@value": "2026-01-01"},
                    "dcat:distribution": [
                        {"@id": resource_uris[language]} for language in ("en", "fr")
                    ],
                },
                *distributions,
            ]
        }
    ).encode()


class AggregateCatalogueTests(unittest.TestCase):
    def test_builds_two_source_catalogue_with_lmia_unit(self) -> None:
        quarterly = source_document(
            QUARTERLY_DATASET_ID,
            "Quarterly statistics",
            table_title=(
                "Table 14-Number of Positive Labour Market Impact Assessments (LMIA) "
                "by Program Stream and Province/Territory between 2025Q1 and 2026Q1"
            ),
        )
        annual = source_document(
            ANNUAL_DATASET_ID,
            "Annual statistics",
            table_title=(
                "Table 14: Number of positive Labour Market Impact Assessments (LMIA) "
                "by stream and province/territory between 2018 and 2025"
            ),
        )

        catalogue = build_catalogue(
            [
                (QUARTERLY_DATASET_ID, quarterly, "quarterly.jsonld"),
                (ANNUAL_DATASET_ID, annual, "annual.jsonld"),
            ]
        )

        self.assertEqual(len(catalogue["datasets"]), 2)
        for dataset in catalogue["datasets"]:
            self.assertEqual(set(dataset["table_14"]), {"en", "fr"})
            for language in ("en", "fr"):
                self.assertEqual(dataset["table_14"][language]["unit"], "lmias")
                self.assertEqual(
                    dataset["table_14"][language]["decision_scope"], "positive"
                )

    def test_rejects_position_table_mislabeled_as_table_14(self) -> None:
        source = source_document(
            QUARTERLY_DATASET_ID,
            "Quarterly statistics",
            table_title="Table 14-Number of Positions on Positive Labour Market Impact Assessments",
        )

        with self.assertRaisesRegex(CatalogueError, "analytical unit"):
            parse_source(source, QUARTERLY_DATASET_ID, "source.jsonld")


if __name__ == "__main__":
    unittest.main()
