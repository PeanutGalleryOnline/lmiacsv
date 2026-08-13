"""Download official NOC CSVs into immutable source/checksum paths."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from lmiacsv.scrape_catalogue import CatalogueError, USER_AGENT, atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
CATALOGUE_PATH = WORKSPACE_ROOT / "data" / "meta" / "noc.catalogue.json"
RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "noc" / "resources"
MANIFEST_PATH = WORKSPACE_ROOT / "data" / "raw" / "noc" / "manifest.json"
MAX_RESOURCE_BYTES = 3 * 1024 * 1024
ALLOWED_HOST = "www.statcan.gc.ca"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def decode_csv(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            header = next(csv.reader(io.StringIO(text)))
        except (csv.Error, StopIteration):
            continue
        if len(header) >= 4 and all(value.strip() for value in header[:4]):
            return encoding, text
    raise CatalogueError("NOC resource is not a recognized CSV")


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def archive_path(raw_root: Path, source: dict[str, Any], digest: str) -> Path:
    return raw_root / source["source_id"] / digest / source["source_filename"]


def download_source(source: dict[str, Any], raw_root: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        source["download_url"],
        headers={"Accept": "text/csv", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        final_url = response.geturl()
        parsed = urlparse(final_url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise CatalogueError(f"NOC download redirected to an untrusted URL: {final_url}")
        content_type = response.headers.get_content_type()
        content = response.read(MAX_RESOURCE_BYTES + 1)
    if len(content) > MAX_RESOURCE_BYTES:
        raise CatalogueError(f"NOC resource exceeds {MAX_RESOURCE_BYTES:,} bytes")
    encoding, _text = decode_csv(content)
    digest = sha256_bytes(content)
    path = archive_path(raw_root, source, digest)
    if path.exists():
        if sha256_bytes(path.read_bytes()) != digest:
            raise CatalogueError(f"Existing NOC archive file is corrupt: {path}")
    else:
        atomic_write(path, content)
    return {
        **source,
        "status": "downloaded",
        "detected_format": "CSV",
        "text_encoding": encoding,
        "content_type": content_type,
        "final_url": urlunparse(parsed._replace(query="", fragment="")),
        "downloaded_bytes": len(content),
        "sha256": digest,
        "archive_path": relative_path(path),
    }


def reusable_sources(path: Path, refresh: bool) -> dict[str, dict[str, Any]]:
    if refresh or not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    reusable = {}
    for source in manifest.get("sources", []):
        if source.get("status") != "downloaded":
            continue
        archive = Path(source["archive_path"])
        if not archive.is_absolute():
            archive = WORKSPACE_ROOT / archive
        if archive.is_file() and sha256_bytes(archive.read_bytes()) == source.get("sha256"):
            reusable[source["source_id"]] = source
    return reusable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")

    catalogue = json.loads(args.catalogue.read_text(encoding="utf-8"))
    sources = catalogue["sources"]
    reusable = reusable_sources(args.manifest, args.refresh)
    results = []
    pending = []
    for source in sources:
        old = reusable.get(source["source_id"])
        if old and old.get("download_url") == source["download_url"]:
            results.append({**old, **source})
        else:
            pending.append(source)
    if results:
        print(f"Reusing {len(results)} checksum-verified NOC sources.", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_source, source, args.raw_root.resolve()): source
            for source in pending
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    **source,
                    "status": "error",
                    "error": f"{type(error).__name__}: {error}",
                }
            results.append(result)
            print(f"{result['status']}: {source['source_id']}", flush=True)
    results.sort(key=lambda value: value["source_id"])
    manifest = {
        "schema_version": "0.1.0",
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "catalogue_path": relative_path(args.catalogue),
        "source_count": len(results),
        "error_count": sum(value["status"] == "error" for value in results),
        "sources": results,
    }
    write_json(args.manifest.resolve(), manifest)
    if manifest["error_count"]:
        raise SystemExit(f"{manifest['error_count']} NOC resource downloads failed")
    print(f"Archived {len(results)} official NOC CSVs.")


if __name__ == "__main__":
    main()
