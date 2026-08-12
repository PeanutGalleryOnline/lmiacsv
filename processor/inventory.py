"""Build a provenance-first inventory of legacy LMIA CSV releases.

This is deliberately an inventory rather than the final normalizer. It reads the
legacy source directory, identifies the shape of each CSV, and writes generated
catalogue files inside this workspace. It never changes the source directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


YEAR_RE = re.compile(r"(20\d{2})")
QUARTER_PATTERNS = (
    (re.compile(r"q1\s*[-_]?\s*q2|q1q2", re.I), "Q1-Q2"),
    (re.compile(r"q3\s*[-_]?\s*q4|q3q4", re.I), "Q3-Q4"),
    (re.compile(r"q1", re.I), "Q1"),
    (re.compile(r"q2", re.I), "Q2"),
    (re.compile(r"q3", re.I), "Q3"),
    (re.compile(r"q4", re.I), "Q4"),
)


@dataclass(frozen=True)
class Release:
    id: str
    filename: str
    sha256: str
    bytes: int
    year: int | None
    quarter: str | None
    status: str | None
    language: str
    row_count: int
    columns: list[str]
    source_url: str | None
    has_xlsx_pair: bool
    publication_ready: bool
    warnings: list[str]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_cells(row: Iterable[str]) -> list[str]:
    return [cell.replace("\ufeff", "").strip() for cell in row]


def looks_like_header(row: list[str]) -> bool:
    text = " | ".join(normalized_cells(row)).casefold()
    employer = "employer" in text or "employeur" in text
    context = any(word in text for word in ("address", "adresse", "province", "occupation"))
    return employer and context


def inspect_csv(path: Path) -> tuple[list[str], int, str]:
    """Return columns, data-row count, and a small content probe."""

    columns: list[str] = []
    row_count = 0
    header_found = False
    probe_rows: list[str] = []

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            clean = normalized_cells(row)
            if index < 8:
                probe_rows.append(" ".join(clean))

            if not header_found:
                if looks_like_header(clean):
                    columns = [cell for cell in clean if cell]
                    header_found = True
                continue

            if any(clean):
                row_count += 1

    return columns, row_count, "\n".join(probe_rows)


def detect_year(filename: str, probe: str) -> int | None:
    filename_match = YEAR_RE.search(filename)
    if filename_match:
        return int(filename_match.group(1))

    candidates = [int(value) for value in YEAR_RE.findall(probe)]
    return next((year for year in candidates if year != 2011), None)


def detect_quarter(filename: str, probe: str) -> str | None:
    for pattern, quarter in QUARTER_PATTERNS:
        if pattern.search(filename):
            return quarter

    text = probe.casefold()
    if "january" in text and "march" in text:
        return "Q1"
    if "april" in text and "june" in text:
        return "Q2"
    if "july" in text and "september" in text:
        return "Q3"
    if "october" in text and "december" in text:
        return "Q4"
    if "june" in text and "december" in text:
        return "Q3-Q4"
    return None


def detect_status(filename: str, probe: str) -> str | None:
    text = f"{filename}\n{probe}".casefold()
    negative_tokens = ("negative", "negative_", "_neg_", "neg_en", "négative", "negative-e")
    positive_tokens = ("positive", "_pos_", "pos_en", "positive-e", "positive employer")
    if any(token in text for token in negative_tokens):
        return "negative"
    if any(token in text for token in positive_tokens):
        return "positive"
    return None


def detect_language(filename: str) -> str:
    lower = filename.casefold()
    if re.search(r"(?:^|[_-])fr(?:[._-]|$)", lower):
        return "fr"
    if re.search(r"(?:^|[_-])en(?:[._-]|$)", lower) or "employer" in lower:
        return "en"
    return "unknown"


def inventory_release(path: Path, xlsx_stems: set[str]) -> Release:
    columns, row_count, probe = inspect_csv(path)
    digest = file_sha256(path)
    year = detect_year(path.name, probe)
    quarter = detect_quarter(path.name, probe)
    status = detect_status(path.name, probe)
    warnings: list[str] = []

    if year is None:
        warnings.append("year-unresolved")
    if quarter is None:
        warnings.append("quarter-unresolved")
    if status is None:
        warnings.append("status-unresolved")
    if not columns:
        warnings.append("header-unresolved")

    # Government source URLs have not yet been reconstructed from the legacy archive.
    source_url = None
    warnings.append("source-url-missing")

    return Release(
        id=f"legacy-{digest[:12]}",
        filename=path.name,
        sha256=digest,
        bytes=path.stat().st_size,
        year=year,
        quarter=quarter,
        status=status,
        language=detect_language(path.name),
        row_count=row_count,
        columns=columns,
        source_url=source_url,
        has_xlsx_pair=path.stem.casefold() in xlsx_stems,
        publication_ready=False,
        warnings=warnings,
    )


def build_inventory(source_dir: Path, output_root: Path) -> dict[str, object]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    csv_paths = sorted(source_dir.glob("*.csv"), key=lambda path: path.name.casefold())
    xlsx_paths = sorted(source_dir.glob("*.xlsx"), key=lambda path: path.name.casefold())
    xlsx_stems = {path.stem.casefold() for path in xlsx_paths}
    releases = [inventory_release(path, xlsx_stems) for path in csv_paths]

    status_files = Counter(release.status or "unresolved" for release in releases)
    status_rows = Counter()
    yearly: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for release in releases:
        status = release.status or "unresolved"
        status_rows[status] += release.row_count
        if release.year is not None:
            yearly[release.year][f"{status}_files"] += 1
            yearly[release.year][f"{status}_rows"] += release.row_count

    years = sorted({release.year for release in releases if release.year is not None})
    unresolved = Counter(
        warning
        for release in releases
        for warning in release.warnings
        if warning != "source-url-missing"
    )

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    overview: dict[str, object] = {
        "data_contract_version": "0.1.0",
        "generated_at": generated_at,
        "publication_ready": False,
        "coverage": {
            "start_year": years[0] if years else None,
            "end_year": years[-1] if years else None,
            "years": years,
        },
        "inventory": {
            "csv_files": len(releases),
            "xlsx_files": len(xlsx_paths),
            "csv_xlsx_pairs": sum(release.has_xlsx_pair for release in releases),
            "raw_rows": sum(release.row_count for release in releases),
            "files_by_status": dict(sorted(status_files.items())),
            "rows_by_status": dict(sorted(status_rows.items())),
            "unresolved": dict(sorted(unresolved.items())),
        },
        "years": [
            {"year": year, **dict(sorted(yearly[year].items()))}
            for year in sorted(yearly)
        ],
        "blockers": [
            "Authoritative government source URLs have not been attached.",
            "Duplicate and same-name CSV/XLSX relationships require release-level review.",
            "The inventory counts raw source rows; it is not yet a deduplicated decision total.",
        ],
    }

    catalogue = {
        "schema_version": "0.1.0",
        "generated_at": generated_at,
        "releases": [asdict(release) for release in releases],
    }

    release_dir = output_root / "content" / "releases"
    published_dir = output_root / "data" / "published"
    release_dir.mkdir(parents=True, exist_ok=True)
    published_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "index.json").write_text(
        json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (published_dir / "overview.json").write_text(
        json.dumps(overview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return overview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="Legacy directory containing CSV/XLSX files")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Workspace receiving generated content (defaults to this project)",
    )
    args = parser.parse_args()
    overview = build_inventory(args.source_dir.resolve(), args.output_root.resolve())
    inventory = overview["inventory"]
    print(
        f"Inventoried {inventory['csv_files']} CSV files and "
        f"{inventory['xlsx_files']} XLSX files ({inventory['raw_rows']:,} raw rows)."
    )
    print("Publication status: foundation only; provenance blockers remain visible in overview.json.")


if __name__ == "__main__":
    main()

