"""Catalogue official Statistics Canada NOC structures and correspondence CSVs.

The Statistics Canada classification pages are the source of download identity. This
stage discovers paired English and French CSV links from those pages and preserves the
page snapshots instead of maintaining an unaudited list of copied download URLs.
"""

from __future__ import annotations

import argparse
import re
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from lmiacsv.scrape_catalogue import (
    CatalogueError,
    USER_AGENT,
    atomic_write,
    sha256_bytes,
    write_json,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = WORKSPACE_ROOT / "data" / "raw" / "noc" / "catalogue"
OUTPUT_PATH = WORKSPACE_ROOT / "data" / "meta" / "noc.catalogue.json"
ALLOWED_HOST = "www.statcan.gc.ca"
MAX_PAGE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_kind: str
    noc_version: str | None
    noc_release: str | None
    source_version: str | None
    target_version: str | None
    language: str
    page_url: str
    download_suffix: str
    expected_unit_groups: int | None


SPECS = (
    SourceSpec(
        source_id="noc-2011-structure-en",
        source_kind="classification_structure",
        noc_version="2011",
        noc_release="NOC 2011",
        source_version=None,
        target_version=None,
        language="en",
        page_url="https://www.statcan.gc.ca/en/subjects/standard/noc/2011/index",
        download_suffix="/noc-cnp-2011-structure-eng.csv",
        expected_unit_groups=500,
    ),
    SourceSpec(
        source_id="noc-2011-structure-fr",
        source_kind="classification_structure",
        noc_version="2011",
        noc_release="CNP 2011",
        source_version=None,
        target_version=None,
        language="fr",
        page_url="https://www.statcan.gc.ca/fr/sujets/norme/cnp/2011/index",
        download_suffix="/noc-cnp-2011-structure-fra.csv",
        expected_unit_groups=500,
    ),
    SourceSpec(
        source_id="noc-2016-v1.3-structure-en",
        source_kind="classification_structure",
        noc_version="2016",
        noc_release="NOC 2016 Version 1.3",
        source_version=None,
        target_version=None,
        language="en",
        page_url="https://www.statcan.gc.ca/en/subjects/standard/noc/2016/indexV1.3",
        download_suffix="/noc-cnp-2016-structure-v4-eng.csv",
        expected_unit_groups=500,
    ),
    SourceSpec(
        source_id="noc-2016-v1.3-structure-fr",
        source_kind="classification_structure",
        noc_version="2016",
        noc_release="CNP 2016 version 1.3",
        source_version=None,
        target_version=None,
        language="fr",
        page_url="https://www.statcan.gc.ca/fr/sujets/norme/cnp/2016/indexV1.3",
        download_suffix="/noc-cnp-2016-structure-v4-fra.csv",
        expected_unit_groups=500,
    ),
    SourceSpec(
        source_id="noc-2021-v1.0-structure-en",
        source_kind="classification_structure",
        noc_version="2021",
        noc_release="NOC 2021 Version 1.0",
        source_version=None,
        target_version=None,
        language="en",
        page_url="https://www.statcan.gc.ca/en/subjects/standard/noc/2021/indexV1",
        download_suffix="/noc-2021-v1.0-classification-structure.csv",
        expected_unit_groups=516,
    ),
    SourceSpec(
        source_id="noc-2021-v1.0-structure-fr",
        source_kind="classification_structure",
        noc_version="2021",
        noc_release="CNP 2021 version 1.0",
        source_version=None,
        target_version=None,
        language="fr",
        page_url="https://www.statcan.gc.ca/fr/sujets/norme/cnp/2021/indexV1",
        download_suffix="/cnp-2021-v1.0-structure-classification.csv",
        expected_unit_groups=516,
    ),
    SourceSpec(
        source_id="noc-2016-v1.3-to-2021-v1.0-en",
        source_kind="correspondence",
        noc_version=None,
        noc_release=None,
        source_version="2016",
        target_version="2021",
        language="en",
        page_url=(
            "https://www.statcan.gc.ca/en/statistical-programs/document/"
            "noc2016v1_3-noc2021v1_0"
        ),
        download_suffix="/noc2016v1_3-noc2021v1_0-eng.csv",
        expected_unit_groups=None,
    ),
    SourceSpec(
        source_id="noc-2016-v1.3-to-2021-v1.0-fr",
        source_kind="correspondence",
        noc_version=None,
        noc_release=None,
        source_version="2016",
        target_version="2021",
        language="fr",
        page_url=(
            "https://www.statcan.gc.ca/fr/programmes-statistiques/document/"
            "noc2016v1_3-noc2021v1_0"
        ),
        download_suffix="/noc2016v1_3-noc2021v1_0-fra.csv",
        expected_unit_groups=None,
    ),
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        values = dict(attrs)
        if values.get("href"):
            self._href = str(values["href"])
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        self.links.append(
            {
                "href": self._href,
                "text": re.sub(r"\s+", " ", " ".join(self._text)).strip(),
            }
        )
        self._href = None
        self._text = []


def fetch_html(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/html", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.headers.get_content_type() != "text/html":
            raise CatalogueError(f"Unexpected NOC catalogue content type for {url}")
        content = response.read(MAX_PAGE_BYTES + 1)
    if len(content) > MAX_PAGE_BYTES:
        raise CatalogueError(f"NOC catalogue page exceeds {MAX_PAGE_BYTES:,} bytes: {url}")
    return content


def discover_source(content: bytes, spec: SourceSpec) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CatalogueError(f"NOC catalogue page is not UTF-8: {spec.page_url}") from error
    parser = LinkParser()
    parser.feed(text)
    matches = []
    for link in parser.links:
        absolute = urljoin(spec.page_url, link["href"])
        parsed = urlparse(absolute)
        if parsed.path.endswith(spec.download_suffix):
            matches.append({**link, "download_url": absolute})
    if len(matches) != 1:
        raise CatalogueError(
            f"Expected one {spec.source_id} CSV link on {spec.page_url}, found {len(matches)}"
        )
    match = matches[0]
    parsed = urlparse(match["download_url"])
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise CatalogueError(f"Untrusted NOC download URL: {match['download_url']}")
    return {
        **asdict(spec),
        "title": match["text"],
        "download_url": match["download_url"],
        "source_filename": Path(parsed.path).name,
        "format": "CSV",
        "language": spec.language,
        "publisher": "Statistics Canada / Statistique Canada",
        "page_snapshot": {
            "sha256": sha256_bytes(content),
            "bytes": len(content),
        },
    }


def build_catalogue(pages: dict[str, bytes]) -> dict[str, Any]:
    if set(pages) != {spec.source_id for spec in SPECS}:
        raise CatalogueError("NOC catalogue page set does not match the declared source set")
    sources = [discover_source(pages[spec.source_id], spec) for spec in SPECS]
    if len({source["download_url"] for source in sources}) != len(sources):
        raise CatalogueError("NOC catalogue resolved duplicate download URLs")
    return {
        "schema_version": "0.2.0",
        "sources": sources,
        "checks": [
            "Each CSV URL was discovered on its official Statistics Canada page.",
            "Every resolved download uses HTTPS on www.statcan.gc.ca.",
            "The catalogue includes paired English/French NOC/CNP 2011, 2016 V1.3, "
            "and 2021 V1.0 structures plus the paired official 2016-to-2021 "
            "correspondence.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    pages = {}
    for spec in SPECS:
        content = fetch_html(spec.page_url)
        pages[spec.source_id] = content
        atomic_write(args.raw_root.resolve() / f"{spec.source_id}.html", content)
    catalogue = build_catalogue(pages)
    write_json(args.output.resolve(), catalogue)
    print(f"Catalogued {len(catalogue['sources'])} official NOC reference sources.")


if __name__ == "__main__":
    main()
