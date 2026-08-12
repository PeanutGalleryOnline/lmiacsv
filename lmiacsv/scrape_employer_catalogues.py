"""Scrape the official positive and negative LMIA employer-list catalogues.

The Open Canada records contain distinct resources that sometimes share the
same download filename. This scraper treats the dataset ID and resource UUID as
the identity, preserves the government filename as metadata, and assigns every
resource a collision-safe archival path. It inventories metadata only; resource
workbooks are not downloaded by this command.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

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
RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "catalogue"
DEFAULT_OUTPUT_PATH = WORKSPACE_ROOT / "data" / "published" / "catalogue" / "employer-lists.json"
ALLOWED_DOWNLOAD_HOSTS = {"open.canada.ca", "www.esdc.gc.ca"}
PERIOD_RE = re.compile(r"^\s*(20\d{2})(?:Q([1-4])(?:Q([1-4]))?)?\b", re.I)


@dataclass(frozen=True)
class CatalogueSpec:
    decision: str
    dataset_id: str

    @property
    def page_url(self) -> str:
        return f"https://open.canada.ca/data/en/dataset/{self.dataset_id}"

    @property
    def jsonld_url(self) -> str:
        return f"{self.page_url}.jsonld"


CATALOGUES = {
    "positive": CatalogueSpec(
        decision="positive",
        dataset_id="90fed587-1364-4f33-a9ee-208181dc0b97",
    ),
    "negative": CatalogueSpec(
        decision="negative",
        dataset_id="f82f66f2-a22b-4511-bccf-e1d74db39ae5",
    ),
}


def period_from_title(title: str) -> dict[str, Any]:
    match = PERIOD_RE.match(title)
    if not match:
        raise CatalogueError(f"Employer-list title has no leading release period: {title!r}")
    year = int(match.group(1))
    first_quarter = match.group(2)
    second_quarter = match.group(3)
    if not first_quarter:
        return {
            "key": str(year),
            "year": year,
            "quarter": None,
            "precision": "year_or_partial_year",
        }
    quarter = f"Q{first_quarter}"
    precision = "quarter"
    if second_quarter:
        quarter = f"Q{first_quarter}-Q{second_quarter}"
        precision = "multi_quarter"
    return {
        "key": f"{year}-{quarter.casefold()}",
        "year": year,
        "quarter": quarter,
        "precision": precision,
    }


def validate_download_url(url: str, spec: CatalogueSpec, resource_id: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise CatalogueError(f"Resource {resource_id} has untrusted access URL: {url}")
    if parsed.username or parsed.password or parsed.port:
        raise CatalogueError(f"Resource {resource_id} has an unsafe access URL authority: {url}")
    if parsed.hostname == "open.canada.ca":
        expected_path = f"/dataset/{spec.dataset_id}/resource/{resource_id}/download/"
        if expected_path not in parsed.path:
            raise CatalogueError(
                f"Resource {resource_id} access URL is not bound to its dataset and UUID: {url}"
            )
        identity_binding = "catalogue_resource_path"
    else:
        if not parsed.path.startswith("/ouvert-open/"):
            raise CatalogueError(
                f"Resource {resource_id} has an unexpected legacy ESDC path: {url}"
            )
        identity_binding = "trusted_legacy_direct_url"
    filename = unquote(PurePosixPath(parsed.path).name)
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise CatalogueError(f"Resource {resource_id} has an unsafe source filename: {filename!r}")
    return filename, identity_binding


def parse_distribution(node: dict[str, Any], spec: CatalogueSpec) -> dict[str, Any]:
    distribution_uri = str(node.get("@id", ""))
    resource_id = resource_id_from_uri(distribution_uri)
    language = str(node.get("dct:language", ""))
    if language not in {"en", "fr"}:
        raise CatalogueError(f"Resource {resource_id} has unexpected language {language!r}")

    title_en = localized(node.get("dct:title"), "en")
    title_fr = localized(node.get("dct:title"), "fr")
    if not title_en or not title_fr:
        raise CatalogueError(f"Resource {resource_id} is missing a bilingual title")
    lowered_title = title_en.casefold()
    has_lmia_name = "labour market impact assessment" in lowered_title or "lmia" in lowered_title
    if spec.decision not in lowered_title or not has_lmia_name:
        raise CatalogueError(
            f"Resource {resource_id} title does not describe a {spec.decision} LMIA: {title_en}"
        )

    access_url = linked_id(node.get("dcat:accessURL"))
    source_filename, identity_binding = validate_download_url(access_url, spec, resource_id)
    format_name = str(node.get("dct:format", "")).upper()
    if format_name not in {"CSV", "XLS", "XLSX"}:
        raise CatalogueError(f"Resource {resource_id} has unexpected format {format_name!r}")
    byte_size_text = literal(node.get("dcat:byteSize"))
    byte_size = int(float(byte_size_text)) if byte_size_text else None
    period = period_from_title(title_en)
    archive_path = PurePosixPath(
        "data",
        "raw",
        "employer-lists",
        spec.dataset_id,
        resource_id,
        source_filename,
    )

    return {
        "dataset_id": spec.dataset_id,
        "decision": spec.decision,
        "resource_id": resource_id,
        "resource_page_url": f"{spec.page_url}/resource/{resource_id}",
        "download_url": access_url,
        "download_url_host": urlparse(access_url).hostname,
        "download_url_identity": identity_binding,
        "source_filename": source_filename,
        "archive_path": archive_path.as_posix(),
        "language": language,
        "format": format_name,
        "bytes": byte_size,
        "issued_at": literal(node.get("dct:issued")),
        "modified_at": literal(node.get("dct:modified")),
        "title": {"en": title_en, "fr": title_fr},
        "period": period,
    }


def parse_source(
    content: bytes, spec: CatalogueSpec
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogueError(f"{spec.decision} source is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("@graph"), list):
        raise CatalogueError(f"{spec.decision} JSON-LD source must contain an @graph array")
    graph = document["@graph"]

    dataset_nodes = [node for node in graph if node.get("@type") == "dcat:Dataset"]
    if len(dataset_nodes) != 1:
        raise CatalogueError(
            f"Expected one {spec.decision} dcat:Dataset node, found {len(dataset_nodes)}"
        )
    dataset = dataset_nodes[0]
    if str(dataset.get("dct:identifier", "")) != spec.dataset_id:
        raise CatalogueError(
            f"Expected dataset {spec.dataset_id}, found {dataset.get('dct:identifier')!r}"
        )

    distribution_nodes = {
        str(node.get("@id", "")): node for node in graph if node.get("@type") == "dcat:Distribution"
    }
    referenced_ids = {linked_id(reference) for reference in dataset.get("dcat:distribution", [])}
    if "" in referenced_ids:
        raise CatalogueError(f"{spec.decision} dataset has a distribution without an @id")
    missing = referenced_ids - distribution_nodes.keys()
    extra = distribution_nodes.keys() - referenced_ids
    if missing or extra:
        raise CatalogueError(
            f"{spec.decision} distribution graph mismatch; "
            f"missing={sorted(missing)!r}, extra={sorted(extra)!r}"
        )

    resources = [parse_distribution(distribution_nodes[uri], spec) for uri in referenced_ids]
    resource_ids = [resource["resource_id"] for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise CatalogueError(f"Duplicate resource IDs found in {spec.decision} catalogue")
    resources.sort(
        key=lambda resource: (
            resource["period"]["year"],
            resource["period"]["quarter"] or "",
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
        raise CatalogueError(f"{spec.decision} dataset publisher is missing")

    catalogue = {
        "decision": spec.decision,
        "dataset_id": spec.dataset_id,
        "page_url": spec.page_url,
        "machine_readable_url": spec.jsonld_url,
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
        "resource_count": len(resources),
    }
    return catalogue, resources


def build_releases(
    resources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        grouped[(resource["decision"], resource["period"]["key"])].append(resource)

    releases = []
    pairing_issues = []
    for (decision, period_key), members in sorted(
        grouped.items(),
        key=lambda item: (
            item[1][0]["period"]["year"],
            item[1][0]["period"]["quarter"] or "",
            item[0][0],
        ),
    ):
        by_language = {member["language"]: member for member in members}
        missing_languages = sorted({"en", "fr"} - by_language.keys())
        duplicate_languages = sorted(
            language
            for language, count in Counter(member["language"] for member in members).items()
            if count > 1
        )
        if missing_languages or duplicate_languages:
            pairing_issues.append(
                {
                    "decision": decision,
                    "period": period_key,
                    "missing_languages": missing_languages,
                    "duplicate_languages": duplicate_languages,
                    "resource_ids": sorted(member["resource_id"] for member in members),
                }
            )
        releases.append(
            {
                "release_key": f"{decision}:{period_key}",
                "decision": decision,
                "period": members[0]["period"],
                "resources": {
                    language: {
                        "resource_id": member["resource_id"],
                        "format": member["format"],
                        "source_filename": member["source_filename"],
                    }
                    for language, member in sorted(by_language.items())
                },
            }
        )
    return releases, pairing_issues


def collision_audit(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        groups[resource["source_filename"].casefold()].append(resource)
    collisions = []
    for _, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members.sort(
            key=lambda member: (member["decision"], member["language"], member["resource_id"])
        )
        collisions.append(
            {
                "source_filename": members[0]["source_filename"],
                "resource_count": len(members),
                "cross_decision": len({member["decision"] for member in members}) > 1,
                "decisions": sorted({member["decision"] for member in members}),
                "languages": sorted({member["language"] for member in members}),
                "periods": sorted({member["period"]["key"] for member in members}),
                "resource_ids": [member["resource_id"] for member in members],
                "archive_paths": [member["archive_path"] for member in members],
            }
        )
    return collisions


def build_inventory(sources: dict[str, bytes]) -> dict[str, Any]:
    if set(sources) != set(CATALOGUES):
        raise CatalogueError(
            f"Expected sources for {sorted(CATALOGUES)!r}, found {sorted(sources)!r}"
        )

    catalogues = []
    resources = []
    snapshots = []
    for decision in sorted(CATALOGUES):
        spec = CATALOGUES[decision]
        catalogue, parsed_resources = parse_source(sources[decision], spec)
        catalogues.append(catalogue)
        resources.extend(parsed_resources)
        snapshots.append(
            {
                "decision": decision,
                "dataset_id": spec.dataset_id,
                "format": "application/ld+json",
                "bytes": len(sources[decision]),
            }
        )

    resource_ids = [resource["resource_id"] for resource in resources]
    if len(resource_ids) != len(set(resource_ids)):
        raise CatalogueError("A resource UUID appears in more than one employer catalogue")
    archive_paths = [resource["archive_path"] for resource in resources]
    if len(archive_paths) != len(set(archive_paths)):
        raise CatalogueError("Collision-safe archive paths are not unique")
    resources.sort(
        key=lambda resource: (
            resource["period"]["year"],
            resource["period"]["quarter"] or "",
            resource["decision"],
            resource["language"],
            resource["resource_id"],
        )
    )
    releases, pairing_issues = build_releases(resources)
    collisions = collision_audit(resources)
    languages = Counter(resource["language"] for resource in resources)
    decisions = Counter(resource["decision"] for resource in resources)
    formats = Counter(resource["format"] for resource in resources)
    download_url_identities = Counter(resource["download_url_identity"] for resource in resources)
    periods = sorted({resource["period"]["key"] for resource in resources})

    semantic_content = json.dumps(
        {
            "catalogues": catalogues,
            "resources": resources,
            "releases": releases,
            "pairing_issues": pairing_issues,
            "collisions": collisions,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    for snapshot in snapshots:
        snapshot["combined_semantic_sha256"] = sha256_bytes(semantic_content)

    return {
        "schema_version": "0.1.0",
        "catalogues": catalogues,
        "source_snapshots": snapshots,
        "resource_count": len(resources),
        "release_count": len(releases),
        "period_count": len(periods),
        "counts": {
            "languages": dict(sorted(languages.items())),
            "decisions": dict(sorted(decisions.items())),
            "formats": dict(sorted(formats.items())),
            "download_url_identities": dict(sorted(download_url_identities.items())),
        },
        "resources": resources,
        "releases": releases,
        "audit": {
            "language_pairing_issues": pairing_issues,
            "filename_collisions": collisions,
            "collision_summary": {
                "colliding_filenames": len(collisions),
                "resources_at_risk_in_flat_directory": sum(
                    collision["resource_count"] for collision in collisions
                ),
                "cross_decision_filenames": sum(
                    collision["cross_decision"] for collision in collisions
                ),
                "archive_paths_unique": True,
            },
        },
        "checks": [
            "Each catalogue contains exactly one expected dataset node.",
            "Every distribution reference resolves to exactly one resource node.",
            "Every resource UUID and collision-safe archive path is globally unique.",
            "Government filenames are retained as metadata but never used as global identity.",
            "A resource URL must bind the expected dataset ID and resource UUID on open.canada.ca.",
            "Legacy direct downloads are accepted only from the exact www.esdc.gc.ca host and /ouvert-open/ path; catalogue UUIDs remain their identity.",
            "Annual or partial-year titles remain year-scoped; quarter precision is not inferred.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive-input", type=Path, help="Read a positive JSON-LD snapshot")
    parser.add_argument("--negative-input", type=Path, help="Read a negative JSON-LD snapshot")
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    input_paths = {
        "positive": args.positive_input,
        "negative": args.negative_input,
    }
    sources = {
        decision: path.read_bytes() if path else fetch_source(CATALOGUES[decision].jsonld_url)
        for decision, path in input_paths.items()
    }
    for decision, content in sources.items():
        raw_path = args.raw_root.resolve() / f"{CATALOGUES[decision].dataset_id}.jsonld"
        atomic_write(raw_path, content)
    inventory = build_inventory(sources)
    write_json(args.output.resolve(), inventory)
    collision_summary = inventory["audit"]["collision_summary"]
    print(
        f"Inventoried {inventory['resource_count']} official employer-list resources "
        f"across {inventory['period_count']} release periods."
    )
    print(
        f"Detected {collision_summary['colliding_filenames']} colliding government filenames "
        f"covering {collision_summary['resources_at_risk_in_flat_directory']} resources."
    )
    print("Archive paths are unique by dataset ID and resource UUID.")


if __name__ == "__main__":
    main()
