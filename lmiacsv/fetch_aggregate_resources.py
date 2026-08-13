"""Discover and archive official aggregate LMIA Table 14 workbooks.

The quarterly catalogue is a rolling window. Superseded uploads sometimes remain
reachable under their former filenames even after portal metadata is replaced.
This stage generates and probes those official resource-bound URLs, archives every
recognized file by checksum, and records unsuccessful probes without inventing data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from lmiacsv.fetch_employer_resources import fetch_bytes, validate_content
from lmiacsv.scrape_aggregate_catalogues import (
    ANNUAL_DATASET_ID,
    QUARTERLY_DATASET_ID,
)
from lmiacsv.scrape_catalogue import CatalogueError, atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = (
    WORKSPACE_ROOT / "data" / "meta" / "aggregates.catalogue.json"
)
RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "aggregate-tables"
MANIFEST_PATH = RAW_ROOT / "manifest.json"
FIRST_EXPECTED_PERIOD = "2018Q1"
FIRST_RELEASE_PERIOD = "2019Q1"
PERIOD_TOKEN_RE = re.compile(r"(?<!\d)(\d{4})_?q([1-4])(?!\d)", re.I)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def period_tuple(period: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})Q([1-4])", period.upper())
    if not match:
        raise CatalogueError(f"Invalid quarterly period {period!r}")
    return int(match.group(1)), int(match.group(2))


def period_range(start: str, end: str) -> list[str]:
    year, quarter = period_tuple(start)
    end_year, end_quarter = period_tuple(end)
    periods = []
    while (year, quarter) <= (end_year, end_quarter):
        periods.append(f"{year}Q{quarter}")
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return periods


def source_release_period(resource: dict[str, Any]) -> str:
    # Rolling-window titles and historical filenames contain both a start and
    # end period. The release is the final period, not the first token.
    title_matches = PERIOD_TOKEN_RE.findall(resource["title"])
    if title_matches:
        return f"{title_matches[-1][0]}Q{title_matches[-1][1]}"
    filename_matches = PERIOD_TOKEN_RE.findall(resource["source_filename"])
    if filename_matches:
        return f"{filename_matches[-1][0]}Q{filename_matches[-1][1]}"
    raise CatalogueError(
        f"Cannot determine release period from Table 14 resource {resource['resource_id']}"
    )


def candidate_filenames(release_period: str, language: str = "en") -> list[str]:
    if language not in {"en", "fr"}:
        raise CatalogueError(f"Unsupported aggregate source language {language!r}")
    suffix = "e" if language == "en" else "f"
    year, quarter = period_tuple(release_period)
    stems = [
        f"tfwp{year}_q{quarter}_table_14_{suffix}",
        f"tfwp_{year}q{quarter}_table_14_{suffix}",
        f"tfwp_{year}_q{quarter}_table_14_{suffix}",
        f"tfwp{year}q{quarter}_table_14_{suffix}",
        f"tfwp{year}_q{quarter}_table14_{suffix}",
        f"tfwp_{year}q{quarter}_table14_{suffix}",
    ]

    # Before 2022 the catalogue title named the complete rolling window (for
    # example, 2018Q1-2019Q3), not just the release quarter.  Those replaced
    # blobs are no longer in portal metadata, so try the conservative filename
    # forms implied by that contemporary title as well as the later convention.
    if (year, quarter) < (2022, 1):
        start_year = year - 1
        start = f"{start_year}q1"
        end = f"{year}q{quarter}"
        start_split = f"{start_year}_q1"
        end_split = f"{year}_q{quarter}"
        stems.extend(
            [
                f"tfwp{start_split}_{end_split}_table_14_{suffix}",
                f"tfwp_{start_split}_{end_split}_table_14_{suffix}",
                f"tfwp{start}_{end}_table_14_{suffix}",
                f"tfwp_{start}_{end}_table_14_{suffix}",
                f"tfwp{start_split}-{end_split}_table_14_{suffix}",
                f"tfwp_{start_split}-{end_split}_table_14_{suffix}",
                f"tfwp{start}-{end}_table_14_{suffix}",
                f"tfwp_{start}-{end}_table_14_{suffix}",
                f"tfwp{start_split}_to_{end_split}_table_14_{suffix}",
                f"tfwp_{start}_to_{end}_table_14_{suffix}",
                f"tfwp{start}_{end}_table14_{suffix}",
                f"tfwp_{start}-{end}_table14_{suffix}",
            ]
        )
    return [f"{stem}.{extension}" for stem in stems for extension in ("xlsx", "csv")]


def candidate_urls(resource: dict[str, Any], first_release: str) -> list[dict[str, str]]:
    current_release = source_release_period(resource)
    parsed = urlparse(resource["download_url"])
    base = resource["download_url"][: -len(Path(parsed.path).name)]
    values = []
    seen = set()
    for release_period in period_range(first_release, current_release):
        for filename in candidate_filenames(release_period, resource["language"]):
            url = f"{base}{quote(filename)}"
            if url in seen:
                continue
            seen.add(url)
            values.append(
                {
                    "source_kind": "quarterly_release",
                    "release_period": release_period,
                    "dataset_id": resource["dataset_id"],
                    "resource_id": resource["resource_id"],
                    "language": resource["language"],
                    "catalogue_format": Path(filename).suffix[1:].upper(),
                    "source_filename": filename,
                    "download_url": url,
                }
            )
    return values


def manifest_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def versioned_path(raw_root: Path, candidate: dict[str, Any], digest: str) -> Path:
    return (
        raw_root
        / candidate["dataset_id"]
        / candidate["resource_id"]
        / digest
        / candidate["source_filename"]
    )


def download_candidate(candidate: dict[str, Any], raw_root: Path) -> dict[str, Any]:
    try:
        content, final_url, content_type = fetch_bytes(
            candidate["download_url"],
            candidate["resource_id"],
            candidate["source_filename"],
            timeout=45,
        )
    except urllib.error.HTTPError as error:
        if error.code in {404, 410}:
            return {**candidate, "status": "not_found", "http_status": error.code}
        return {
            **candidate,
            "status": "error",
            "error": f"HTTPError: {error.code} {error.reason}",
        }
    except Exception as error:
        return {**candidate, "status": "error", "error": f"{type(error).__name__}: {error}"}

    try:
        detected_format = validate_content(
            content, candidate["catalogue_format"], candidate["resource_id"]
        )
    except Exception as error:
        return {**candidate, "status": "error", "error": f"{type(error).__name__}: {error}"}
    digest = sha256_bytes(content)
    path = versioned_path(raw_root, candidate, digest)
    if path.exists():
        if sha256_bytes(path.read_bytes()) != digest:
            raise CatalogueError(f"Existing aggregate source is corrupt: {path}")
    else:
        atomic_write(path, content)
    return {
        **candidate,
        "status": "downloaded",
        "format": detected_format,
        "format_matches_catalogue": detected_format == candidate["catalogue_format"],
        "final_url": final_url,
        "content_type": content_type,
        "downloaded_bytes": len(content),
        "sha256": digest,
        "archive_path": manifest_path(path),
    }


def catalogue_resources(catalogue: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_id = {dataset["dataset_id"]: dataset["table_14"] for dataset in catalogue["datasets"]}
    try:
        return by_id[QUARTERLY_DATASET_ID], by_id[ANNUAL_DATASET_ID]
    except KeyError as error:
        raise CatalogueError(f"Aggregate catalogue is missing dataset {error.args[0]}") from error


def declared_candidate(resource: dict[str, Any], source_kind: str) -> dict[str, Any]:
    value = {
        "source_kind": source_kind,
        "release_period": source_release_period(resource)
        if source_kind == "quarterly_release"
        else None,
        "dataset_id": resource["dataset_id"],
        "resource_id": resource["resource_id"],
        "language": resource["language"],
        "catalogue_format": resource["format"],
        "source_filename": resource["source_filename"],
        "download_url": resource["download_url"],
        "declared_current": True,
    }
    return value


def load_reusable(path: Path, refresh: bool) -> dict[str, dict[str, Any]]:
    if refresh or not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    reusable = {}
    for entry in document.get("resources", []):
        if entry.get("status") == "not_found":
            reusable[entry["download_url"]] = entry
            continue
        if entry.get("status") != "downloaded":
            continue
        archive = Path(entry["archive_path"])
        if not archive.is_absolute():
            archive = WORKSPACE_ROOT / archive
        if archive.is_file() and sha256_bytes(archive.read_bytes()) == entry.get("sha256"):
            reusable[entry["download_url"]] = entry
    return reusable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--first-release", default=FIRST_RELEASE_PERIOD)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 12:
        parser.error("--workers must be between 1 and 12")
    period_tuple(args.first_release)

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    quarterly_by_language, annual_by_language = catalogue_resources(catalogue)
    if set(quarterly_by_language) != {"en", "fr"} or set(annual_by_language) != {"en", "fr"}:
        raise CatalogueError("Aggregate catalogue does not contain both official languages")
    candidates = [
        candidate
        for language in ("en", "fr")
        for candidate in candidate_urls(quarterly_by_language[language], args.first_release)
    ]
    declared = [
        declared_candidate(resource, source_kind)
        for source_kind, resources in (
            ("quarterly_release", quarterly_by_language),
            ("annual_release", annual_by_language),
        )
        for resource in (resources["en"], resources["fr"])
    ]
    by_url = {candidate["download_url"]: candidate for candidate in candidates}
    for candidate in declared:
        existing = by_url.get(candidate["download_url"], {})
        by_url[candidate["download_url"]] = {**existing, **candidate}
    candidates = list(by_url.values())

    reusable = load_reusable(args.manifest, args.refresh)
    resources: list[dict[str, Any]] = []
    pending = []
    for candidate in candidates:
        entry = reusable.get(candidate["download_url"])
        if entry:
            resources.append({**entry, "language": candidate["language"]})
        else:
            pending.append(candidate)

    completed = len(resources)
    if completed:
        reused_files = sum(value.get("status") == "downloaded" for value in resources)
        reused_misses = sum(value.get("status") == "not_found" for value in resources)
        print(
            f"Reusing {reused_files} checksum-verified aggregate sources and "
            f"{reused_misses} recorded misses.",
            flush=True,
        )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_candidate, candidate, args.raw_root.resolve()): candidate
            for candidate in pending
        }
        for future in as_completed(futures):
            entry = future.result()
            resources.append(entry)
            completed += 1
            if entry["status"] != "not_found":
                print(
                    f"[{completed}/{len(candidates)}] {entry['status']}: "
                    f"{entry.get('release_period') or 'annual'} {entry['source_filename']}",
                    flush=True,
                )

    resources.sort(
        key=lambda entry: (
            entry["source_kind"] != "quarterly_release",
            entry.get("release_period") or "9999Q4",
            entry["language"],
            entry["source_filename"],
        )
    )
    required_urls = {candidate["download_url"] for candidate in declared}
    required_failures = [
        entry
        for entry in resources
        if entry["download_url"] in required_urls and entry["status"] != "downloaded"
    ]
    downloaded = [entry for entry in resources if entry["status"] == "downloaded"]
    discovered_quarterly = [
        entry for entry in downloaded if entry["source_kind"] == "quarterly_release"
    ]
    manifest = {
        "schema_version": "0.2.0",
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "catalogue_path": manifest_path(args.catalogue),
        "expected_quarterly_coverage_start": FIRST_EXPECTED_PERIOD,
        "discovery": {
            "first_release_probed": args.first_release,
            "last_release_probed": source_release_period(quarterly_by_language["en"]),
            "candidate_count": len(candidates),
            "not_found_count": sum(entry["status"] == "not_found" for entry in resources),
            "error_count": sum(entry["status"] == "error" for entry in resources),
            "discovered_quarterly_releases": sorted(
                {entry["release_period"] for entry in discovered_quarterly}
            ),
            "downloaded_quarterly_releases_by_language": {
                language: sorted(
                    {
                        entry["release_period"]
                        for entry in discovered_quarterly
                        if entry["language"] == language
                    }
                )
                for language in ("en", "fr")
            },
        },
        "downloaded_count": len(downloaded),
        "required_failure_count": len(required_failures),
        "resources": resources,
    }
    write_json(args.manifest.resolve(), manifest)
    print(
        f"Aggregate manifest: {len(downloaded)} files downloaded; "
        f"{len(discovered_quarterly)} quarterly releases discovered.",
        flush=True,
    )
    if required_failures:
        raise SystemExit("Current quarterly or annual Table 14 download failed")


if __name__ == "__main__":
    main()
