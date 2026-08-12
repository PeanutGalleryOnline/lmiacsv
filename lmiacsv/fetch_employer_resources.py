"""Download versioned LMIA employer-list resources without filename collisions.

The catalogue's dataset ID and resource UUID establish remote identity. The
downloaded SHA-256 establishes immutable content identity. Government filenames
are retained as evidence at the final path segment, never used as a unique key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

from lmiacsv.scrape_catalogue import CatalogueError, USER_AGENT, atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = WORKSPACE_ROOT / "data" / "published" / "catalogue" / "employer-lists.json"
RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "employer-lists"
MANIFEST_PATH = RAW_ROOT / "manifest.json"
MAX_RESOURCE_BYTES = 50 * 1024 * 1024
ALLOWED_FINAL_HOSTS = {
    "open.canada.ca",
    "www.esdc.gc.ca",
    "opencanada.blob.core.windows.net",
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_content(content: bytes, format_name: str, resource_id: str) -> str:
    if not content:
        raise CatalogueError(f"Resource {resource_id} downloaded as an empty file")
    probe = content[:4096].lstrip().lower()
    if probe.startswith((b"<!doctype html", b"<html")):
        raise CatalogueError(f"Resource {resource_id} returned HTML instead of data")
    if content.startswith(b"PK\x03\x04"):
        return "XLSX"
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        return "XLS"
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content[:65536].decode(encoding)
        except UnicodeDecodeError:
            continue
        if (
            "\x00" not in text
            and "\n" in text
            and any(delimiter in text for delimiter in (",", ";", "\t", "|"))
        ):
            return "CSV"
    raise CatalogueError(
        f"Resource {resource_id} content is not recognizable as CSV, XLS or XLSX "
        f"(catalogue declared {format_name})"
    )


def versioned_path(raw_root: Path, resource: dict[str, Any], sha256: str) -> Path:
    return (
        raw_root
        / resource["dataset_id"]
        / resource["resource_id"]
        / sha256
        / resource["source_filename"]
    )


def fetch_bytes(
    url: str, resource_id: str, source_filename: str, timeout: int = 60
) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        parsed_final_url = urlparse(final_url)
        final_host = parsed_final_url.hostname
        if final_host not in ALLOWED_FINAL_HOSTS:
            raise CatalogueError(f"Download redirected to an untrusted host: {final_url}")
        if final_host == "opencanada.blob.core.windows.net":
            expected_path = f"/opengovprod/resources/{resource_id}/{quote(source_filename)}"
            if parsed_final_url.path != expected_path:
                raise CatalogueError(
                    f"Open Canada blob redirect is not bound to resource {resource_id}: "
                    f"{urlunparse(parsed_final_url._replace(query='', fragment=''))}"
                )
        content_type = response.headers.get_content_type()
        content = response.read(MAX_RESOURCE_BYTES + 1)
    if len(content) > MAX_RESOURCE_BYTES:
        raise CatalogueError(f"Download exceeds {MAX_RESOURCE_BYTES:,} bytes: {url}")
    sanitized_final_url = urlunparse(parsed_final_url._replace(query="", fragment=""))
    return content, sanitized_final_url, content_type


def manifest_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def download_resource(resource: dict[str, Any], raw_root: Path) -> dict[str, Any]:
    content, final_url, content_type = fetch_bytes(
        resource["download_url"], resource["resource_id"], resource["source_filename"]
    )
    detected_format = validate_content(content, resource["format"], resource["resource_id"])
    digest = sha256_bytes(content)
    path = versioned_path(raw_root, resource, digest)
    if path.exists():
        if sha256_bytes(path.read_bytes()) != digest:
            raise CatalogueError(f"Existing versioned blob is corrupt: {path}")
    else:
        atomic_write(path, content)
    advertised_bytes = resource.get("bytes")
    return {
        "status": "downloaded",
        "dataset_id": resource["dataset_id"],
        "decision": resource["decision"],
        "resource_id": resource["resource_id"],
        "language": resource["language"],
        "period": resource["period"],
        "format": detected_format,
        "catalogue_format": resource["format"],
        "format_matches_catalogue": detected_format == resource["format"],
        "source_filename": resource["source_filename"],
        "catalogue_modified_at": resource["modified_at"],
        "download_url": resource["download_url"],
        "final_url": final_url,
        "content_type": content_type,
        "catalogue_bytes": advertised_bytes,
        "downloaded_bytes": len(content),
        "size_matches_catalogue": advertised_bytes is None or advertised_bytes == len(content),
        "sha256": digest,
        "archive_path": manifest_path(path),
    }


def reusable_entry(
    resource: dict[str, Any], entry: dict[str, Any] | None, refresh: bool
) -> dict[str, Any] | None:
    if refresh or not entry or entry.get("status") != "downloaded":
        return None
    if entry.get("catalogue_modified_at") != resource.get("modified_at"):
        return None
    path = Path(entry.get("archive_path", ""))
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    if not path.is_file():
        return None
    if sha256_bytes(path.read_bytes()) != entry.get("sha256"):
        return None
    if "catalogue_format" not in entry:
        entry = {
            **entry,
            "catalogue_format": resource["format"],
            "format_matches_catalogue": entry.get("format") == resource["format"],
        }
    return entry


def load_existing_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        entry["resource_id"]: entry
        for entry in document.get("resources", [])
        if entry.get("resource_id")
    }


def select_resources(
    catalogue: dict[str, Any], language: str, decision: str
) -> list[dict[str, Any]]:
    resources = [
        resource
        for resource in catalogue["resources"]
        if (language == "all" or resource["language"] == language)
        and (decision == "all" or resource["decision"] == decision)
    ]
    return sorted(
        resources,
        key=lambda resource: (
            resource["period"]["year"],
            resource["period"]["quarter"] or "",
            resource["decision"],
            resource["language"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--language", choices=("en", "fr", "all"), default="en")
    parser.add_argument("--decision", choices=("positive", "negative", "all"), default="all")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    selected = select_resources(catalogue, args.language, args.decision)
    existing = load_existing_manifest(args.manifest)
    entries: list[dict[str, Any]] = []
    pending = []
    for resource in selected:
        reused = reusable_entry(resource, existing.get(resource["resource_id"]), args.refresh)
        if reused:
            entries.append(reused)
        else:
            pending.append(resource)

    completed = len(entries)
    if completed:
        print(f"Reusing {completed} checksum-verified resource blobs.", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_resource, resource, args.raw_root.resolve()): resource
            for resource in pending
        }
        for future in as_completed(futures):
            resource = futures[future]
            try:
                entry = future.result()
            except Exception as error:  # Preserve every resource failure in the manifest.
                entry = {
                    "status": "error",
                    "dataset_id": resource["dataset_id"],
                    "decision": resource["decision"],
                    "resource_id": resource["resource_id"],
                    "language": resource["language"],
                    "period": resource["period"],
                    "format": resource["format"],
                    "catalogue_format": resource["format"],
                    "source_filename": resource["source_filename"],
                    "catalogue_modified_at": resource["modified_at"],
                    "download_url": resource["download_url"],
                    "error": f"{type(error).__name__}: {error}",
                }
            entries.append(entry)
            completed += 1
            print(
                f"[{completed}/{len(selected)}] {entry['status']}: "
                f"{resource['decision']} {resource['period']['key']} "
                f"{resource['source_filename']}",
                flush=True,
            )

    entries.sort(
        key=lambda entry: (
            entry["period"]["year"],
            entry["period"]["quarter"] or "",
            entry["decision"],
            entry["language"],
            entry["resource_id"],
        )
    )
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    manifest = {
        "schema_version": "0.1.0",
        "retrieved_at": retrieved_at,
        "catalogue_path": manifest_path(args.catalogue),
        "selection": {"language": args.language, "decision": args.decision},
        "resource_count": len(entries),
        "downloaded_count": sum(entry["status"] == "downloaded" for entry in entries),
        "error_count": sum(entry["status"] == "error" for entry in entries),
        "resources": entries,
    }
    write_json(args.manifest.resolve(), manifest)
    print(
        f"Manifest: {manifest['downloaded_count']} downloaded, {manifest['error_count']} errors.",
        flush=True,
    )
    if manifest["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
