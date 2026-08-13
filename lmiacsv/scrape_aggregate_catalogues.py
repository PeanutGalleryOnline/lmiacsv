"""Catalogue the official quarterly and annual aggregate LMIA Table 14 resources.

The employer lists and aggregate statistics are different public products. This
stage records paired current English and French Table 14 resources from each aggregate
dataset without assuming that the portal retains superseded quarterly workbooks.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lmiacsv.scrape_catalogue import (
    CatalogueError,
    atomic_write,
    fetch_source,
    linked_id,
    literal,
    localized,
    resource_id_from_uri,
    sha256_bytes,
    write_json,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
QUARTERLY_DATASET_ID = "e8745429-21e7-4a73-b3f5-90a779b78d1e"
ANNUAL_DATASET_ID = "76defa14-473e-41e2-abfa-60021c4d934b"
DATASET_IDS = (QUARTERLY_DATASET_ID, ANNUAL_DATASET_ID)
DEFAULT_RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "catalogue"
DEFAULT_OUTPUT_PATH = (
    WORKSPACE_ROOT / "data" / "meta" / "aggregates.catalogue.json"
)
ALLOWED_DOWNLOAD_HOSTS = {"open.canada.ca"}


def page_url(dataset_id: str) -> str:
    return f"https://open.canada.ca/data/en/dataset/{dataset_id}"


def jsonld_url(dataset_id: str) -> str:
    return f"{page_url(dataset_id)}.jsonld"


def distribution_nodes(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = document.get("@graph")
    if not isinstance(graph, list):
        raise CatalogueError("JSON-LD source must contain an @graph array")
    datasets = [node for node in graph if node.get("@type") == "dcat:Dataset"]
    if len(datasets) != 1:
        raise CatalogueError(f"Expected one dcat:Dataset node, found {len(datasets)}")
    distributions = {
        str(node.get("@id", "")): node
        for node in graph
        if node.get("@type") == "dcat:Distribution"
    }
    return datasets[0], distributions


def is_table_14(title: str) -> bool:
    return bool(re.match(r"^(?:table|tableau)\s*0?14\b", title, re.I))


def select_table_14(
    dataset: dict[str, Any],
    distributions: dict[str, dict[str, Any]],
    dataset_id: str,
    language: str,
) -> dict[str, Any]:
    referenced = [linked_id(value) for value in dataset.get("dcat:distribution", [])]
    candidates: list[dict[str, Any]] = []
    for uri in referenced:
        node = distributions.get(uri)
        if node is None:
            raise CatalogueError(f"Dataset references missing distribution {uri!r}")
        if str(node.get("dct:language", "")) != language:
            continue
        title = localized(node.get("dct:title"), language)
        if is_table_14(title):
            candidates.append(node)
    if len(candidates) != 1:
        raise CatalogueError(
            f"Expected one {language} Table 14 in dataset {dataset_id}, "
            f"found {len(candidates)}"
        )

    node = candidates[0]
    uri = str(node.get("@id", ""))
    resource_id = resource_id_from_uri(uri)
    download_url = linked_id(node.get("dcat:accessURL"))
    parsed = urlparse(download_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise CatalogueError(f"Table 14 has untrusted download URL: {download_url}")
    title = localized(node.get("dct:title"), language)
    lowered = title.casefold()
    positive_measure = (
        "positive labour market impact assessment" in lowered
        if language == "en"
        else "positive" in lowered and "marché du travail" in lowered
    )
    if not positive_measure:
        raise CatalogueError(f"Table 14 is not explicitly a positive-LMIA measure: {title}")
    if any(term in lowered for term in ("positions", "employers", "employeurs", "postes")):
        raise CatalogueError(f"Table 14 has an unexpected analytical unit: {title}")
    format_name = str(node.get("dct:format", "")).upper()
    if format_name not in {"XLSX", "CSV"}:
        raise CatalogueError(f"Table 14 has unsupported format {format_name!r}")

    return {
        "dataset_id": dataset_id,
        "dataset_page_url": page_url(dataset_id),
        "resource_id": resource_id,
        "resource_page_url": f"{page_url(dataset_id)}/resource/{resource_id}",
        "download_url": download_url,
        "source_filename": Path(parsed.path).name,
        "format": format_name,
        "bytes": int(float(literal(node.get("dcat:byteSize"))))
        if literal(node.get("dcat:byteSize"))
        else None,
        "issued_at": literal(node.get("dct:issued")),
        "modified_at": literal(node.get("dct:modified")),
        "title": title,
        "language": language,
        "table_number": 14,
        "unit": "lmias",
        "decision_scope": "positive",
        "population_scope": "general",
    }


def parse_source(content: bytes, dataset_id: str, source_url: str) -> dict[str, Any]:
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogueError("Source is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise CatalogueError("JSON-LD source must be an object")
    dataset, distributions = distribution_nodes(document)
    actual_id = str(dataset.get("dct:identifier", ""))
    if actual_id != dataset_id:
        raise CatalogueError(f"Expected dataset {dataset_id}, found {actual_id!r}")
    return {
        "dataset_id": dataset_id,
        "page_url": page_url(dataset_id),
        "machine_readable_url": source_url,
        "title": {
            "en": localized(dataset.get("dct:title"), "en"),
            "fr": localized(dataset.get("dct:title"), "fr"),
        },
        "issued_at": literal(dataset.get("dct:issued")),
        "modified_at": literal(dataset.get("dct:modified")),
        "source_snapshot": {
            "sha256": sha256_bytes(content),
            "bytes": len(content),
        },
        "table_14": {
            language: select_table_14(dataset, distributions, dataset_id, language)
            for language in ("en", "fr")
        },
    }


def build_catalogue(sources: Iterable[tuple[str, bytes, str]]) -> dict[str, Any]:
    datasets = [
        parse_source(content, dataset_id=dataset_id, source_url=source_url)
        for dataset_id, content, source_url in sources
    ]
    actual = {dataset["dataset_id"] for dataset in datasets}
    if actual != set(DATASET_IDS):
        raise CatalogueError(f"Aggregate catalogue dataset mismatch: {sorted(actual)!r}")
    datasets.sort(key=lambda dataset: DATASET_IDS.index(dataset["dataset_id"]))
    return {
        "schema_version": "0.2.0",
        "datasets": datasets,
        "checks": [
            "Each JSON-LD source identifies the expected official dataset UUID.",
            "Exactly one English and one French Table 14 are selected from each dataset.",
            "All four selected tables explicitly count positive LMIAs/EIMT, not positions "
            "or employers.",
            "Download URLs are HTTPS resources hosted by open.canada.ca.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarterly-input", type=Path)
    parser.add_argument("--annual-input", type=Path)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    inputs = {
        QUARTERLY_DATASET_ID: args.quarterly_input,
        ANNUAL_DATASET_ID: args.annual_input,
    }
    sources = []
    for dataset_id in DATASET_IDS:
        source_url = jsonld_url(dataset_id)
        input_path = inputs[dataset_id]
        content = input_path.read_bytes() if input_path else fetch_source(source_url)
        raw_path = args.raw_root.resolve() / f"{dataset_id}.jsonld"
        atomic_write(raw_path, content)
        sources.append((dataset_id, content, source_url))

    catalogue = build_catalogue(sources)
    write_json(args.output.resolve(), catalogue)
    print("Catalogued official quarterly and annual positive-LMIA Table 14 resources.")


if __name__ == "__main__":
    main()
