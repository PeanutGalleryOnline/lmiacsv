"""Build compact LMIA products as exact projections of the full CSV tier.

This stage performs no source parsing and no additional normalization. It reads
only data/full products, selects a documented subset of employer and NOC columns,
copies the already-small aggregate products byte-for-byte, verifies row-count and
key invariants, and writes deterministic manifests for both tiers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from lmiacsv.build_canonical_records import CANONICAL_FIELDS, build_schema_document
from lmiacsv.build_noc_tables import UNIT_FIELDS
from lmiacsv.scrape_catalogue import CatalogueError, atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
FULL_ROOT = WORKSPACE_ROOT / "data" / "full"
MIN_ROOT = WORKSPACE_ROOT / "data" / "min"
MIN_SCHEMA_PATH = WORKSPACE_ROOT / "data" / "meta" / "min.schema.json"
MANIFEST_VERSION = "1.0.0"
PROJECTION_VERSION = "1.0.0"

EMPLOYER_MIN_FIELDS = [
    "record_id",
    "period_key",
    "period_year",
    "period_quarter",
    "period_precision",
    "decision_status",
    "comparability_regime",
    "province_code",
    "program_stream_key",
    "employer",
    "employer_key",
    "postal_code",
    "noc_version",
    "noc_code",
    "incorporate_status_key",
    "lmia_count",
    "position_count",
    "quality_flags",
]

NOC_MIN_FIELDS = [
    "noc_version",
    "noc_code",
    "title_en",
    "title_fr",
    "teer_category",
    "broad_category_code",
]

FULL_PRODUCTS = [
    ("employers.csv", ["record_id"]),
    (
        "positive-quarterly.csv",
        ["period", "province_territory", "program_stream"],
    ),
    ("positive-annual.csv", ["year", "province_territory", "program_stream"]),
    ("positive-quarterly-national.csv", ["period"]),
    ("noc.csv", ["noc_version", "noc_code"]),
    ("noc-crosswalk.csv", []),
    ("translations.csv", ["translation_key"]),
]

PASSTHROUGH_PRODUCTS = [
    ("positive-quarterly.csv", ["period", "province_territory", "program_stream"]),
    ("positive-annual.csv", ["year", "province_territory", "program_stream"]),
    ("positive-quarterly-national.csv", ["period"]),
]


class MinBuildError(CatalogueError):
    """Raised when a full product cannot be projected without information loss."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_metrics(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        if not fields:
            raise MinBuildError(f"CSV has no header: {path}")
        rows = sum(1 for _row in reader)
    return {
        "path": path.name,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "columns": len(fields),
        "fields": fields,
    }


def project_csv(
    source: Path,
    output: Path,
    *,
    expected_source_fields: Iterable[str],
    projection_fields: Iterable[str],
    key_fields: Iterable[str],
) -> dict[str, Any]:
    expected = list(expected_source_fields)
    projection = list(projection_fields)
    keys = list(key_fields)
    missing_projection = [field for field in projection if field not in expected]
    if missing_projection:
        raise MinBuildError(
            f"Projection refers to fields absent from its contract: {missing_projection}"
        )
    missing_keys = [field for field in keys if field not in projection]
    if missing_keys:
        raise MinBuildError(f"Projection key fields are not retained: {missing_keys}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        prefix=f".{output.stem}-",
        suffix=".csv",
        dir=output.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    row_count = 0
    seen_keys: set[tuple[str, ...]] = set()
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as source_handle:
            reader = csv.DictReader(source_handle)
            actual_fields = list(reader.fieldnames or [])
            if actual_fields != expected:
                raise MinBuildError(
                    f"Unexpected header in {source}: expected {expected!r}, got {actual_fields!r}"
                )
            writer = csv.DictWriter(
                temporary,
                fieldnames=projection,
                extrasaction="raise",
            )
            writer.writeheader()
            for row_number, row in enumerate(reader, start=2):
                values = {field: row.get(field) for field in projection}
                missing_values = [field for field, value in values.items() if value is None]
                if missing_values:
                    raise MinBuildError(
                        f"{source}:{row_number} is missing projected values: {missing_values}"
                    )
                key = tuple(str(values[field]) for field in keys)
                if keys and (not all(key) or key in seen_keys):
                    reason = "blank" if not all(key) else "duplicate"
                    raise MinBuildError(
                        f"{reason.capitalize()} projected key in {source}:{row_number}: {key}"
                    )
                seen_keys.add(key)
                writer.writerow(values)
                row_count += 1
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        temporary_path.chmod(0o644)
        temporary_path.replace(output)
    except Exception:
        temporary.close()
        temporary_path.unlink(missing_ok=True)
        raise

    metrics = csv_metrics(output)
    if metrics["rows"] != row_count:
        raise MinBuildError(
            f"Projection row-count mismatch for {output}: wrote {row_count}, read {metrics['rows']}"
        )
    return metrics


def product_entry(path: Path, primary_key: list[str]) -> dict[str, Any]:
    if not path.is_file():
        raise MinBuildError(f"Required full product is missing: {path}")
    entry = csv_metrics(path)
    absent = [field for field in primary_key if field not in entry["fields"]]
    if absent:
        raise MinBuildError(f"{path} is missing declared key fields: {absent}")
    entry["primary_key"] = primary_key
    return entry


def copy_csv_exact(source: Path, output: Path, primary_key: list[str]) -> dict[str, Any]:
    if not source.is_file():
        raise MinBuildError(f"Required full product is missing: {source}")
    atomic_write(output, source.read_bytes())
    source_sha256 = file_sha256(source)
    output_sha256 = file_sha256(output)
    if output_sha256 != source_sha256:
        raise MinBuildError(f"Byte-for-byte copy checksum mismatch: {source} -> {output}")
    entry = product_entry(output, primary_key)
    entry.update(
        {
            "source": f"../full/{source.name}",
            "source_sha256": source_sha256,
            "derivation": "byte_for_byte_copy",
        }
    )
    return entry


def min_schema_document() -> dict[str, Any]:
    employer_definitions = {field["name"]: field for field in build_schema_document()["fields"]}
    noc_definitions = {
        "noc_version": "NOC version required to interpret the code.",
        "noc_code": "Four- or five-digit NOC unit-group code.",
        "title_en": "Official English unit-group title.",
        "title_fr": "Official French unit-group title.",
        "teer_category": "TEER category for NOC 2021; blank for older versions.",
        "broad_category_code": "Top-level NOC broad-category code.",
    }
    return {
        "schema_version": "1.0.0",
        "projection_version": PROJECTION_VERSION,
        "derivation": (
            "Deterministic derivatives of data/full. Employer and NOC rows are exact column "
            "projections; positive aggregate products are byte-for-byte copies because they "
            "are already compact. No source parsing or normalization occurs in this stage."
        ),
        "products": {
            "employers.csv": {
                "source": "../full/employers.csv",
                "primary_key": ["record_id"],
                "fields": [employer_definitions[name] for name in EMPLOYER_MIN_FIELDS],
            },
            "noc.csv": {
                "source": "../full/noc.csv",
                "primary_key": ["noc_version", "noc_code"],
                "fields": [
                    {
                        "name": name,
                        "type": "string",
                        "nullable": name in {"teer_category"},
                        "description": noc_definitions[name],
                    }
                    for name in NOC_MIN_FIELDS
                ],
            },
            **{
                filename: {
                    "source": f"../full/{filename}",
                    "derivation": "byte_for_byte_copy",
                    "schema": "../meta/aggregates.schema.json",
                }
                for filename, _primary_key in PASSTHROUGH_PRODUCTS
            },
        },
    }


def build(
    full_root: Path = FULL_ROOT,
    min_root: Path = MIN_ROOT,
    schema_path: Path = MIN_SCHEMA_PATH,
) -> dict[str, Any]:
    employer_metrics = project_csv(
        full_root / "employers.csv",
        min_root / "employers.csv",
        expected_source_fields=CANONICAL_FIELDS,
        projection_fields=EMPLOYER_MIN_FIELDS,
        key_fields=["record_id"],
    )
    noc_metrics = project_csv(
        full_root / "noc.csv",
        min_root / "noc.csv",
        expected_source_fields=UNIT_FIELDS,
        projection_fields=NOC_MIN_FIELDS,
        key_fields=["noc_version", "noc_code"],
    )
    passthrough_metrics = [
        copy_csv_exact(
            full_root / filename,
            min_root / filename,
            primary_key,
        )
        for filename, primary_key in PASSTHROUGH_PRODUCTS
    ]

    full_manifest = {
        "manifest_version": MANIFEST_VERSION,
        "tier": "full",
        "description": "Complete source-faithful normalized LMIA products.",
        "products": [
            product_entry(full_root / filename, primary_key)
            for filename, primary_key in FULL_PRODUCTS
        ],
    }
    full_manifest_path = full_root / "manifest.json"
    write_json(full_manifest_path, full_manifest)
    write_json(schema_path, min_schema_document())

    min_manifest = {
        "manifest_version": MANIFEST_VERSION,
        "projection_version": PROJECTION_VERSION,
        "tier": "min",
        "description": (
            "Compact deterministic projections plus already-small aggregate products "
            "for ordinary data-product use."
        ),
        "derived_from": {
            "path": "../full/manifest.json",
            "sha256": file_sha256(full_manifest_path),
        },
        "invariants": [
            "Every source row is retained exactly once and in source order.",
            "Every retained value is copied without transformation.",
            "Projected primary keys are nonblank and unique.",
            "CSV headers exactly match the versioned full and min contracts.",
        ],
        "products": [
            {
                **employer_metrics,
                "source": "../full/employers.csv",
                "source_sha256": file_sha256(full_root / "employers.csv"),
                "primary_key": ["record_id"],
            },
            *passthrough_metrics,
            {
                **noc_metrics,
                "source": "../full/noc.csv",
                "source_sha256": file_sha256(full_root / "noc.csv"),
                "primary_key": ["noc_version", "noc_code"],
            },
        ],
        "schema": {
            "path": "../meta/min.schema.json",
            "sha256": file_sha256(schema_path),
        },
    }
    min_manifest_path = min_root / "manifest.json"
    write_json(min_manifest_path, min_manifest)
    return {"full": full_manifest, "min": min_manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-root", type=Path, default=FULL_ROOT)
    parser.add_argument("--min-root", type=Path, default=MIN_ROOT)
    parser.add_argument("--schema-output", type=Path, default=MIN_SCHEMA_PATH)
    args = parser.parse_args()
    try:
        result = build(
            full_root=args.full_root.resolve(),
            min_root=args.min_root.resolve(),
            schema_path=args.schema_output.resolve(),
        )
    except MinBuildError as error:
        parser.exit(1, f"error: {error}\n")
    employer = next(
        product for product in result["min"]["products"] if product["path"] == "employers.csv"
    )
    print(
        f"Built min employers.csv with {employer['rows']:,} rows and "
        f"{employer['columns']} columns; wrote full/min manifests."
    )


if __name__ == "__main__":
    main()
