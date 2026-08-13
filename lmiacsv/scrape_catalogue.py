"""Inventory the official ESDC quarterly LMIA statistics catalogue.

This scraper intentionally stops at source metadata. It records what the portal
publishes, classifies measures from their official titles, and reports whether
the catalogue contains the inputs needed for a national decision rate. It does
not download workbooks or treat similarly named measures as interchangeable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "e8745429-21e7-4a73-b3f5-90a779b78d1e"
PAGE_URL = f"https://open.canada.ca/data/en/dataset/{DATASET_ID}"
JSONLD_URL = f"{PAGE_URL}.jsonld"
DEFAULT_RAW_PATH = WORKSPACE_ROOT / "data" / "raw" / "catalogue" / f"{DATASET_ID}.jsonld"
DEFAULT_OUTPUT_PATH = WORKSPACE_ROOT / "data" / "meta" / "statistics.catalogue.json"
ALLOWED_DOWNLOAD_HOSTS = {"open.canada.ca"}
MAX_SOURCE_BYTES = 5 * 1024 * 1024
USER_AGENT = "lmiacsv/0.1 (public data normalizer)"

TABLE_FAMILIES = {
    **{table: "tfw_positions" for table in (*range(1, 11), 12, 13, 22, 23, 24)},
    **{table: "lmia_applications" for table in range(14, 19)},
    **{table: "employers" for table in (11, 19, 20, 21)},
    **{table: "sawp" for table in (25, 26, 27, 28)},
}
ARCHIVED_TABLES = {5, 8, 17, 24}
TABLE_RE = re.compile(r"^Table\s*0?(\d{1,2})\b", re.I)
COVERAGE_RE = re.compile(r"between\s+(\d{4}Q[1-4])\s+and\s+(\d{4}Q[1-4])", re.I)


class CatalogueError(ValueError):
    """Raised when the source no longer satisfies the declared contract."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def localized(value: Any, language: str) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    for item in value:
        if isinstance(item, dict) and item.get("@language") == language:
            return str(item.get("@value", ""))
    return ""


def literal(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("@value", ""))
    return ""


def linked_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("@id", ""))
    return ""


def resource_id_from_uri(uri: str) -> str:
    marker = "/resource/"
    if marker not in uri:
        raise CatalogueError(f"Distribution URI does not contain {marker!r}: {uri}")
    resource_id = uri.rsplit(marker, 1)[1].strip("/")
    if not resource_id:
        raise CatalogueError(f"Distribution URI has no resource ID: {uri}")
    return resource_id


def table_number(title: str) -> int | None:
    match = TABLE_RE.match(title)
    return int(match.group(1)) if match else None


def measure_unit(title: str) -> str:
    lowered = title.casefold()
    if "positions" in lowered:
        return "positions"
    if "employers" in lowered:
        return "employers"
    if "labour market impact assessment" in lowered:
        return "lmias"
    return "documentation"


def decision_scope(title: str) -> str:
    lowered = title.casefold()
    if "positive and negative" in lowered:
        return "positive_and_negative"
    if "positive or negative" in lowered:
        return "positive_or_negative"
    if "positive labour market impact assessment" in lowered:
        return "positive"
    if "negative labour market impact assessment" in lowered:
        return "negative"
    if "requested labour market impact assessment" in lowered:
        return "requested"
    return "unspecified"


def population_scope(title: str) -> str:
    return "sawp" if "seasonal agricultural worker program" in title.casefold() else "general"


def coverage(title: str) -> dict[str, str] | None:
    match = COVERAGE_RE.search(title)
    if not match:
        return None
    return {"start": match.group(1).upper(), "end": match.group(2).upper()}


def parse_distribution(node: dict[str, Any]) -> dict[str, Any]:
    distribution_uri = str(node.get("@id", ""))
    resource_id = resource_id_from_uri(distribution_uri)
    language = str(node.get("dct:language", ""))
    if language not in {"en", "fr"}:
        raise CatalogueError(f"Resource {resource_id} has unexpected language {language!r}")

    title_en = localized(node.get("dct:title"), "en")
    title_fr = localized(node.get("dct:title"), "fr")
    if not title_en or not title_fr:
        raise CatalogueError(f"Resource {resource_id} is missing a bilingual title")

    access_url = linked_id(node.get("dcat:accessURL"))
    parsed_url = urlparse(access_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise CatalogueError(f"Resource {resource_id} has untrusted access URL: {access_url}")

    format_name = str(node.get("dct:format", "")).upper()
    if not format_name:
        raise CatalogueError(f"Resource {resource_id} has no format")
    byte_size_text = literal(node.get("dcat:byteSize"))
    byte_size = int(float(byte_size_text)) if byte_size_text else None
    number = table_number(title_en)

    return {
        "resource_id": resource_id,
        "resource_page_url": f"{PAGE_URL}/resource/{resource_id}",
        "download_url": access_url,
        "language": language,
        "format": format_name,
        "bytes": byte_size,
        "issued_at": literal(node.get("dct:issued")),
        "modified_at": literal(node.get("dct:modified")),
        "title": {"en": title_en, "fr": title_fr},
        "table_number": number,
        "family": TABLE_FAMILIES.get(number, "documentation" if number is None else "unknown"),
        "unit": measure_unit(title_en),
        "decision_scope": decision_scope(title_en),
        "population_scope": population_scope(title_en),
        "coverage": coverage(title_en),
        "archived": number in ARCHIVED_TABLES,
    }


def rate_audit(resources: list[dict[str, Any]]) -> dict[str, Any]:
    english = [resource for resource in resources if resource["language"] == "en"]
    positive = [
        resource
        for resource in english
        if resource["unit"] == "lmias"
        and resource["decision_scope"] == "positive"
        and resource["population_scope"] == "general"
    ]
    negative = [
        resource
        for resource in english
        if resource["unit"] == "lmias"
        and resource["decision_scope"] in {"negative", "positive_and_negative"}
        and resource["population_scope"] == "general"
    ]
    requested_positions = [
        resource
        for resource in english
        if resource["unit"] == "positions" and resource["decision_scope"] == "requested"
    ]
    sawp_decisions = [
        resource
        for resource in english
        if resource["unit"] == "lmias"
        and resource["decision_scope"] == "positive_and_negative"
        and resource["population_scope"] == "sawp"
    ]

    available = bool(positive and negative)
    return {
        "question": "What share of finalized LMIA decisions were positive or negative, by quarter?",
        "formula": "positive_lmias / (positive_lmias + negative_lmias)",
        "status": "computable_from_catalogue" if available else "not_computable_from_catalogue",
        "positive_lmia_resources": [resource["resource_id"] for resource in positive],
        "negative_lmia_resources": [resource["resource_id"] for resource in negative],
        "missing_measure": None
        if available
        else "Complete negative LMIA decisions across all program streams",
        "non_substitutes": {
            "requested_position_resources": [
                resource["resource_id"] for resource in requested_positions
            ],
            "sawp_only_decision_resources": [
                resource["resource_id"] for resource in sawp_decisions
            ],
            "reason": "Requested positions, employer counts, and SAWP-only decisions use different units or populations and are not a national negative-LMIA denominator.",
        },
    }


def parse_catalogue(content: bytes, source_url: str = JSONLD_URL) -> dict[str, Any]:
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogueError("Source is not valid UTF-8 JSON") from error

    if not isinstance(document, dict) or not isinstance(document.get("@graph"), list):
        raise CatalogueError("JSON-LD source must contain an @graph array")
    graph = document["@graph"]
    dataset_nodes = [node for node in graph if node.get("@type") == "dcat:Dataset"]
    if len(dataset_nodes) != 1:
        raise CatalogueError(f"Expected one dcat:Dataset node, found {len(dataset_nodes)}")
    dataset = dataset_nodes[0]
    if str(dataset.get("dct:identifier", "")) != DATASET_ID:
        raise CatalogueError(
            f"Expected dataset {DATASET_ID}, found {dataset.get('dct:identifier')!r}"
        )

    distribution_nodes = {
        str(node.get("@id", "")): node for node in graph if node.get("@type") == "dcat:Distribution"
    }
    referenced_ids = {linked_id(reference) for reference in dataset.get("dcat:distribution", [])}
    if "" in referenced_ids:
        raise CatalogueError("Dataset contains a distribution reference without an @id")
    missing = referenced_ids - distribution_nodes.keys()
    extra = distribution_nodes.keys() - referenced_ids
    if missing or extra:
        raise CatalogueError(
            f"Distribution graph mismatch; missing={sorted(missing)!r}, extra={sorted(extra)!r}"
        )

    resources = [parse_distribution(distribution_nodes[uri]) for uri in referenced_ids]
    resource_ids = [resource["resource_id"] for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise CatalogueError("Duplicate resource IDs found")
    table_language_keys = [
        (resource["table_number"], resource["language"])
        for resource in resources
        if resource["table_number"] is not None
    ]
    if len(table_language_keys) != len(set(table_language_keys)):
        raise CatalogueError("Duplicate table/language resources found")
    resources.sort(
        key=lambda resource: (
            resource["table_number"] is None,
            resource["table_number"] or 0,
            resource["language"],
            resource["resource_id"],
        )
    )

    publisher_uri = linked_id(dataset.get("dct:publisher"))
    publisher_node = next(
        (node for node in graph if str(node.get("@id", "")) == publisher_uri), None
    )
    publisher_name = localized(publisher_node.get("foaf:name"), "en") if publisher_node else ""
    if not publisher_name:
        raise CatalogueError("Dataset publisher is missing from the JSON-LD graph")

    languages = Counter(resource["language"] for resource in resources)
    formats = Counter(resource["format"] for resource in resources)
    families = Counter(resource["family"] for resource in resources)
    dataset_record = {
        "dataset_id": DATASET_ID,
        "page_url": PAGE_URL,
        "machine_readable_url": source_url,
        "title": {
            "en": localized(dataset.get("dct:title"), "en"),
            "fr": localized(dataset.get("dct:title"), "fr"),
        },
        "description": {
            "en": localized(dataset.get("dct:description"), "en"),
            "fr": localized(dataset.get("dct:description"), "fr"),
        },
        "publisher": {"name": publisher_name, "uri": publisher_uri},
        "issued_at": literal(dataset.get("dct:issued")),
        "modified_at": literal(dataset.get("dct:modified")),
        "update_frequency": str(dataset.get("dct:accrualPeriodicity", "")),
    }
    semantic_content = json.dumps(
        {"dataset": dataset_record, "resources": resources},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "0.1.0",
        "dataset": dataset_record,
        "source_snapshot": {
            "format": "application/ld+json",
            # JSON-LD graph ordering changes between equivalent portal responses.
            # Fingerprint the normalized semantics so tracked output stays stable;
            # the exact response bytes remain in the ignored raw snapshot.
            "semantic_sha256": sha256_bytes(semantic_content),
            "bytes": len(content),
        },
        "resource_count": len(resources),
        "counts": {
            "languages": dict(sorted(languages.items())),
            "formats": dict(sorted(formats.items())),
            "families": dict(sorted(families.items())),
        },
        "resources": resources,
        "audit": {"national_decision_rate": rate_audit(resources)},
        "checks": [
            "The JSON-LD graph contains exactly one expected dataset node.",
            "Every dataset distribution reference resolves to exactly one resource node.",
            "Every resource has a unique ID, bilingual title, language, format, and trusted HTTPS download URL.",
            "Analytical units and scopes are classified from official English resource titles; workbook contents are not inferred.",
        ],
    }


def fetch_source(url: str = JSONLD_URL, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/ld+json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"application/ld+json", "application/json"}:
            raise CatalogueError(f"Unexpected source content type: {content_type}")
        content = response.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise CatalogueError(f"Source exceeds {MAX_SOURCE_BYTES:,} bytes")
    return content


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o644)
    temporary_path.replace(path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    content = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    atomic_write(path, content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Read an existing JSON-LD snapshot")
    parser.add_argument("--source-url", default=JSONLD_URL)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    content = args.input.read_bytes() if args.input else fetch_source(args.source_url)
    catalogue = parse_catalogue(content, source_url=args.source_url)
    atomic_write(args.raw_output.resolve(), content)
    write_json(args.output.resolve(), catalogue)
    audit = catalogue["audit"]["national_decision_rate"]
    print(
        f"Inventoried {catalogue['resource_count']} official resources from dataset {DATASET_ID}."
    )
    print(f"National decision rate: {audit['status']}.")
    if audit["missing_measure"]:
        print(f"Missing: {audit['missing_measure']}.")


if __name__ == "__main__":
    main()
