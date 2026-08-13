"""Normalize official NOC structures and correspondence into reference CSVs.

The unit-group dimension is keyed by NOC version and code. The crosswalk preserves
one-to-many and many-to-one class relationships and does not invent allocation weights.
The build also audits every versioned NOC code in the canonical LMIA employer records.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from lmiacsv.scrape_catalogue import CatalogueError, atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = WORKSPACE_ROOT / "data" / "raw" / "noc" / "manifest.json"
CANONICAL_PATH = WORKSPACE_ROOT / "data" / "full" / "employers.csv"
OUTPUT_ROOT = WORKSPACE_ROOT / "data" / "full"
UNIT_GROUP_OUTPUT = OUTPUT_ROOT / "noc.csv"
CROSSWALK_OUTPUT = OUTPUT_ROOT / "noc-crosswalk.csv"
META_ROOT = WORKSPACE_ROOT / "data" / "meta"
SCHEMA_OUTPUT = META_ROOT / "noc.schema.json"
RECONCILIATION_OUTPUT = META_ROOT / "noc.reconciliation.json"

UNIT_FIELDS = [
    "noc_version",
    "noc_release_en",
    "noc_release_fr",
    "noc_code",
    "title_en",
    "title_fr",
    "definition_en",
    "definition_fr",
    "teer_category",
    "broad_category_code",
    "broad_category_title_en",
    "broad_category_title_fr",
    "major_group_code",
    "major_group_title_en",
    "major_group_title_fr",
    "sub_major_group_code",
    "sub_major_group_title_en",
    "sub_major_group_title_fr",
    "minor_group_code",
    "minor_group_title_en",
    "minor_group_title_fr",
    "source_id_en",
    "source_id_fr",
    "source_page_url_en",
    "source_page_url_fr",
    "source_download_url_en",
    "source_download_url_fr",
    "source_sha256_en",
    "source_sha256_fr",
    "source_row_en",
    "source_row_fr",
]
CROSSWALK_FIELDS = [
    "source_version",
    "source_release_en",
    "source_release_fr",
    "source_code",
    "source_title_en",
    "source_title_fr",
    "target_version",
    "target_release_en",
    "target_release_fr",
    "target_code",
    "target_title_en",
    "target_title_fr",
    "mapping_cardinality",
    "mapping_basis",
    "is_direct_official_correspondence",
    "gsim_change_en",
    "gsim_change_fr",
    "notes_en",
    "notes_fr",
    "source_id_en",
    "source_id_fr",
    "source_page_url_en",
    "source_page_url_fr",
    "source_download_url_en",
    "source_download_url_fr",
    "source_sha256_en",
    "source_sha256_fr",
    "source_row_en",
    "source_row_fr",
]
EXPECTED_ROLES_BY_LEVEL = {
    "2011": {"1": "broad", "2": "major", "3": "minor", "4": "unit"},
    "2016": {"1": "broad", "2": "major", "3": "minor", "4": "unit"},
    "2021": {
        "1": "broad",
        "2": "major",
        "3": "sub_major",
        "4": "minor",
        "5": "unit",
    },
}
STRUCTURE_FIELDS = {
    "en": {
        "level": "Level",
        "hierarchy": "Hierarchical structure",
        "title": "Class title",
        "definition": "Class definition",
    },
    "fr": {
        "level": "Niveau",
        "hierarchy": "Structure hiérarchique",
        "title": "Titres de classes",
        "definition": "Définitions de la classe",
    },
}
CORRESPONDENCE_FIELDS = {
    "en": {
        "source_code": "NOC 2016 V1.3 Code",
        "source_title": "NOC 2016 V1.3 Title",
        "change": "GSIM Type of Change",
        "target_code": "NOC 2021 V1.0 Code",
        "target_title": "NOC 2021 V1.0 Title",
        "notes": "Notes",
    },
    "fr": {
        "source_code": "Code CNP 2016 v1.3",
        "source_title": "Titre de la CNP 2016 v1.3",
        "change": "Type de changement GSIM",
        "target_code": "Code CNP 2021 v1.0",
        "target_title": "Titre de la CNP 2021 v1.0",
        "notes": "Notes",
    },
}
EXPECTED_CODE_WIDTH = {"2011": 4, "2016": 4, "2021": 5}


class NocBuildError(CatalogueError):
    """Raised when an official NOC source violates the normalized contract."""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_path(source: dict[str, Any]) -> Path:
    path = Path(source["archive_path"])
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(WORKSPACE_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def decoded_dict_rows(source: dict[str, Any]) -> list[tuple[int, dict[str, str]]]:
    path = source_path(source)
    if not path.is_file():
        raise NocBuildError(f"NOC archive source is missing: {path}")
    if file_sha256(path) != source["sha256"]:
        raise NocBuildError(f"NOC archive checksum mismatch: {path}")
    text = path.read_bytes().decode(source["text_encoding"])
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise NocBuildError(f"NOC source has no header: {source['source_id']}")
    return [(index, row) for index, row in enumerate(reader, start=2)]


def structure_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    version = source["noc_version"]
    roles = EXPECTED_ROLES_BY_LEVEL.get(version)
    language = source.get("language")
    names = STRUCTURE_FIELDS.get(language)
    if roles is None:
        raise NocBuildError(f"Unsupported NOC version {version!r}")
    if names is None:
        raise NocBuildError(f"Unsupported NOC language {language!r}")
    rows = decoded_dict_rows(source)
    if not rows:
        raise NocBuildError(f"Empty NOC structure source: {source['source_id']}")
    fields = list(rows[0][1])
    code_fields = [field for field in fields if clean_text(field).casefold().startswith("code")]
    required = set(names.values())
    if len(code_fields) != 1 or not required.issubset(fields):
        raise NocBuildError(f"Unexpected NOC structure header: {fields!r}")
    code_field = code_fields[0]
    current: dict[str, tuple[str, str]] = {}
    units = []
    seen = set()
    for source_row, row in rows:
        level = clean_text(row[names["level"]])
        hierarchy = clean_text(row[names["hierarchy"]])
        code = clean_text(row[code_field])
        title = clean_text(row[names["title"]])
        definition = clean_text(row[names["definition"]])
        if not any((level, hierarchy, code, title, definition)):
            continue
        role = roles.get(level)
        if role is None:
            raise NocBuildError(
                f"Unknown hierarchy level {level!r} in {source['source_id']} row {source_row}"
            )
        if not hierarchy or not code or not title:
            raise NocBuildError(
                f"Incomplete hierarchy row in {source['source_id']} row {source_row}"
            )
        if role != "unit":
            current[role] = (code, title)
            for descendant in ("major", "sub_major", "minor"):
                if role == "broad" or (role == "major" and descendant != "major") or (
                    role == "sub_major" and descendant == "minor"
                ):
                    current.pop(descendant, None)
            continue
        required_parents = {"broad", "major", "minor"}
        if version == "2021":
            required_parents.add("sub_major")
        if not required_parents.issubset(current):
            raise NocBuildError(
                f"Unit group {code} is missing a hierarchy parent in {source['source_id']}"
            )
        if len(code) != EXPECTED_CODE_WIDTH[version] or not code.isdigit():
            raise NocBuildError(f"Invalid NOC {version} unit-group code {code!r}")
        key = (version, code)
        if key in seen:
            raise NocBuildError(f"Duplicate NOC unit group {key!r}")
        seen.add(key)
        unit = {
            "noc_version": version,
            "noc_release": source["noc_release"],
            "noc_code": code,
            "title": title,
            "definition": definition,
            "teer_category": code[1] if version == "2021" else "",
            "broad_category_code": current["broad"][0],
            "broad_category_title": current["broad"][1],
            "major_group_code": current["major"][0],
            "major_group_title": current["major"][1],
            "sub_major_group_code": current.get("sub_major", ("", ""))[0],
            "sub_major_group_title": current.get("sub_major", ("", ""))[1],
            "minor_group_code": current["minor"][0],
            "minor_group_title": current["minor"][1],
            "language": language,
            "source_id": source["source_id"],
            "source_page_url": source["page_url"],
            "source_download_url": source["download_url"],
            "source_sha256": source["sha256"],
            "source_row": source_row,
        }
        units.append(unit)
    expected = source.get("expected_unit_groups")
    if expected is not None and len(units) != expected:
        raise NocBuildError(
            f"NOC {version} has {len(units)} unit groups; expected {expected}"
        )
    return units


def bilingual_unit_rows(
    english_rows: list[dict[str, Any]], french_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair official English and French structures and validate their code hierarchy."""

    english = {(row["noc_version"], row["noc_code"]): row for row in english_rows}
    french = {(row["noc_version"], row["noc_code"]): row for row in french_rows}
    if set(english) != set(french):
        english_only = sorted(set(english) - set(french))[:10]
        french_only = sorted(set(french) - set(english))[:10]
        raise NocBuildError(
            "English/French NOC structure code sets differ: "
            f"English-only {english_only!r}; French-only {french_only!r}"
        )
    values = []
    hierarchy_codes = (
        "broad_category_code",
        "major_group_code",
        "sub_major_group_code",
        "minor_group_code",
    )
    for key in sorted(english):
        en = english[key]
        fr = french[key]
        mismatched = [field for field in hierarchy_codes if en[field] != fr[field]]
        if mismatched:
            raise NocBuildError(
                f"English/French hierarchy differs for NOC {key!r}: {mismatched!r}"
            )
        row = {
            "noc_version": en["noc_version"],
            "noc_release_en": en["noc_release"],
            "noc_release_fr": fr["noc_release"],
            "noc_code": en["noc_code"],
            "title_en": en["title"],
            "title_fr": fr["title"],
            "definition_en": en["definition"],
            "definition_fr": fr["definition"],
            "teer_category": en["teer_category"],
        }
        for stem in ("broad_category", "major_group", "sub_major_group", "minor_group"):
            row[f"{stem}_code"] = en[f"{stem}_code"]
            row[f"{stem}_title_en"] = en[f"{stem}_title"]
            row[f"{stem}_title_fr"] = fr[f"{stem}_title"]
        for suffix, source_key in (
            ("id", "source_id"),
            ("page_url", "source_page_url"),
            ("download_url", "source_download_url"),
            ("sha256", "source_sha256"),
            ("row", "source_row"),
        ):
            row[f"source_{suffix}_en"] = en[source_key]
            row[f"source_{suffix}_fr"] = fr[source_key]
        values.append(row)
    return values


def normalized_title(value: str) -> str:
    return (
        clean_text(value)
        .casefold()
        .replace("–", "-")
        .replace("—", "-")
        .replace("’", "'")
        .replace("‘", "'")
    )


def mapping_cardinalities(rows: list[dict[str, Any]]) -> None:
    by_source: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_target: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        by_source[(row["source_version"], row["source_code"])].add(row["target_code"])
        by_target[(row["source_version"], row["target_code"])].add(row["source_code"])
    for row in rows:
        outgoing = len(by_source[(row["source_version"], row["source_code"])])
        incoming = len(by_target[(row["source_version"], row["target_code"])])
        if outgoing > 1 and incoming > 1:
            value = "many_to_many"
        elif outgoing > 1:
            value = "one_to_many"
        elif incoming > 1:
            value = "many_to_one"
        else:
            value = "one_to_one"
        row["mapping_cardinality"] = value


def correspondence_rows(
    source: dict[str, Any], units: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Parse and validate one language of the official 2016-to-2021 table."""

    language = source.get("language")
    names = CORRESPONDENCE_FIELDS.get(language)
    if names is None:
        raise NocBuildError(f"Unsupported NOC correspondence language {language!r}")
    by_key = {(row["noc_version"], row["noc_code"]): row for row in units}
    rows = decoded_dict_rows(source)
    expected_fields = set(names.values())
    values = []
    seen_pairs = set()
    for source_row, raw in rows:
        row = {clean_text(key): clean_text(value) for key, value in raw.items() if key is not None}
        if not expected_fields.issubset(row):
            raise NocBuildError(f"Unexpected NOC correspondence header: {sorted(row)!r}")
        source_code = row[names["source_code"]]
        target_code = row[names["target_code"]]
        pair = (source_code, target_code)
        if pair in seen_pairs:
            raise NocBuildError(f"Duplicate NOC correspondence pair {pair!r}")
        seen_pairs.add(pair)
        source_unit = by_key.get(("2016", source_code))
        target_unit = by_key.get(("2021", target_code))
        if source_unit is None or target_unit is None:
            raise NocBuildError(f"Correspondence references an unknown NOC code: {pair!r}")
        source_title = row[names["source_title"]]
        target_title = row[names["target_title"]]
        values.append(
            {
                "source_code": source_code,
                "target_code": target_code,
                "source_title_correspondence": source_title,
                "target_title_correspondence": target_title,
                "source_title_matches_structure": (
                    normalized_title(source_title)
                    == normalized_title(source_unit[f"title_{language}"])
                ),
                "target_title_matches_structure": (
                    normalized_title(target_title)
                    == normalized_title(target_unit[f"title_{language}"])
                ),
                "gsim_change": row[names["change"]],
                "notes": row[names["notes"]],
                "language": language,
                "source_id": source["source_id"],
                "source_page_url": source["page_url"],
                "source_download_url": source["download_url"],
                "source_sha256": source["sha256"],
                "source_row": source_row,
            }
        )
    return values


def crosswalk_rows(
    english_source: dict[str, Any],
    french_source: dict[str, Any],
    units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pair official bilingual correspondence rows and add the labelled 2011 bridge."""

    by_key = {(row["noc_version"], row["noc_code"]): row for row in units}
    english = {
        (row["source_code"], row["target_code"]): row
        for row in correspondence_rows(english_source, units)
    }
    french = {
        (row["source_code"], row["target_code"]): row
        for row in correspondence_rows(french_source, units)
    }
    if set(english) != set(french):
        english_only = sorted(set(english) - set(french))[:10]
        french_only = sorted(set(french) - set(english))[:10]
        raise NocBuildError(
            "English/French correspondence code pairs differ: "
            f"English-only {english_only!r}; French-only {french_only!r}"
        )

    values = []
    for pair in sorted(english):
        en = english[pair]
        fr = french[pair]
        source_code, target_code = pair
        source_unit = by_key[("2016", source_code)]
        target_unit = by_key[("2021", target_code)]
        common = {
            "target_version": "2021",
            "target_release_en": target_unit["noc_release_en"],
            "target_release_fr": target_unit["noc_release_fr"],
            "target_code": target_code,
            "target_title_en": target_unit["title_en"],
            "target_title_fr": target_unit["title_fr"],
            "mapping_cardinality": "",
            "gsim_change_en": en["gsim_change"],
            "gsim_change_fr": fr["gsim_change"],
            "notes_en": en["notes"],
            "notes_fr": fr["notes"],
            "_source_title_correspondence_en": en["source_title_correspondence"],
            "_source_title_correspondence_fr": fr["source_title_correspondence"],
            "_target_title_correspondence_en": en["target_title_correspondence"],
            "_target_title_correspondence_fr": fr["target_title_correspondence"],
            "_source_title_match_en": en["source_title_matches_structure"],
            "_source_title_match_fr": fr["source_title_matches_structure"],
            "_target_title_match_en": en["target_title_matches_structure"],
            "_target_title_match_fr": fr["target_title_matches_structure"],
            "source_id_en": en["source_id"],
            "source_id_fr": fr["source_id"],
            "source_page_url_en": en["source_page_url"],
            "source_page_url_fr": fr["source_page_url"],
            "source_download_url_en": en["source_download_url"],
            "source_download_url_fr": fr["source_download_url"],
            "source_sha256_en": en["source_sha256"],
            "source_sha256_fr": fr["source_sha256"],
            "source_row_en": en["source_row"],
            "source_row_fr": fr["source_row"],
        }
        values.append(
            {
                "source_version": "2016",
                "source_release_en": source_unit["noc_release_en"],
                "source_release_fr": source_unit["noc_release_fr"],
                "source_code": source_code,
                "source_title_en": source_unit["title_en"],
                "source_title_fr": source_unit["title_fr"],
                "mapping_basis": "official_2016_v1.3_to_2021_v1.0_correspondence",
                "is_direct_official_correspondence": "true",
                **common,
            }
        )
        source_2011 = by_key.get(("2011", source_code))
        if source_2011 is None:
            raise NocBuildError(
                f"NOC 2016 code {source_code} has no same-code NOC 2011 structural predecessor"
            )
        values.append(
            {
                "source_version": "2011",
                "source_release_en": source_2011["noc_release_en"],
                "source_release_fr": source_2011["noc_release_fr"],
                "source_code": source_code,
                "source_title_en": source_2011["title_en"],
                "source_title_fr": source_2011["title_fr"],
                "mapping_basis": "composed_via_unchanged_2011_to_2016_unit_group_structure",
                "is_direct_official_correspondence": "false",
                **common,
            }
        )
    mapping_cardinalities(values)
    values.sort(
        key=lambda value: (
            value["source_version"],
            value["source_code"],
            value["target_code"],
        )
    )
    return values


def audit_canonical(path: Path, units: list[dict[str, Any]]) -> dict[str, Any]:
    official = defaultdict(set)
    for unit in units:
        official[unit["noc_version"]].add(unit["noc_code"])
    observed = defaultdict(set)
    record_counts = Counter()
    blank_code_records = 0
    unparsed_records = 0
    total_records = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"noc_version", "noc_code", "quality_flags"}
        if not required.issubset(reader.fieldnames or []):
            raise NocBuildError("Canonical LMIA CSV is missing NOC audit columns")
        for row in reader:
            total_records += 1
            version = row["noc_version"]
            code = row["noc_code"]
            if not code:
                blank_code_records += 1
            else:
                observed[version].add(code)
                record_counts[(version, code)] += 1
            if "unparsed_occupation_code" in row["quality_flags"].split("|"):
                unparsed_records += 1
    coverage = []
    unmatched = []
    for version in sorted(set(official) | set(observed)):
        missing = sorted(observed[version] - official[version])
        unmatched.extend(
            {
                "noc_version": version,
                "noc_code": code,
                "canonical_record_count": record_counts[(version, code)],
            }
            for code in missing
        )
        coverage.append(
            {
                "noc_version": version,
                "official_unit_group_count": len(official[version]),
                "observed_code_count": len(observed[version]),
                "matched_observed_code_count": len(observed[version] & official[version]),
                "unmatched_observed_code_count": len(missing),
                "unused_official_code_count": len(official[version] - observed[version]),
                "canonical_records_with_code": sum(
                    count for (item_version, _code), count in record_counts.items()
                    if item_version == version
                ),
            }
        )
    return {
        "canonical_path": display_path(path),
        "canonical_sha256": file_sha256(path),
        "canonical_record_count": total_records,
        "blank_noc_code_record_count": blank_code_records,
        "unparsed_occupation_record_count": unparsed_records,
        "join_status": "complete" if not unmatched else "unmatched_codes",
        "coverage_by_version": coverage,
        "unmatched_codes": unmatched,
    }


def csv_bytes(rows: Iterable[dict[str, Any]], fields: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    return output.getvalue().encode("utf-8")


def schema_document() -> dict[str, Any]:
    return {
        "schema_version": "0.2.0",
        "products": {
            "noc.csv": {
                "grain": "NOC version × official unit-group code",
                "primary_key": ["noc_version", "noc_code"],
                "join_to_lmia_employer_records": ["noc_version", "noc_code"],
                "languages": ["en", "fr"],
                "language_contract": (
                    "Human-readable labels, definitions, and source provenance are "
                    "paired from official English NOC and French CNP publications."
                ),
                "fields": UNIT_FIELDS,
            },
            "noc-crosswalk.csv": {
                "grain": "source NOC version/code × target NOC 2021 code correspondence",
                "primary_key": ["source_version", "source_code", "target_code"],
                "languages": ["en", "fr"],
                "language_contract": (
                    "Titles use the paired English/French structure dimensions; GSIM "
                    "change descriptions, notes, and provenance are paired from the "
                    "official English and French correspondence files."
                ),
                "fields": CROSSWALK_FIELDS,
            },
        },
        "non_claims": [
            "NOC correspondence rows are class relationships, not record-level recodes.",
            "No allocation weights are supplied or inferred for one-to-many relationships.",
            "The composed NOC 2011-to-2021 rows are not a direct Statistics Canada "
            "correspondence table.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--canonical", type=Path, default=CANONICAL_PATH)
    parser.add_argument("--unit-output", type=Path, default=UNIT_GROUP_OUTPUT)
    parser.add_argument("--crosswalk-output", type=Path, default=CROSSWALK_OUTPUT)
    parser.add_argument("--schema-output", type=Path, default=SCHEMA_OUTPUT)
    parser.add_argument("--reconciliation-output", type=Path, default=RECONCILIATION_OUTPUT)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sources = [source for source in manifest["sources"] if source["status"] == "downloaded"]
    if len(sources) != 8:
        raise NocBuildError(f"Expected eight downloaded NOC sources, found {len(sources)}")
    structures = [
        source for source in sources if source["source_kind"] == "classification_structure"
    ]
    correspondences = [
        source for source in sources if source["source_kind"] == "correspondence"
    ]
    if len(structures) != 6 or len(correspondences) != 2:
        raise NocBuildError("NOC manifest has an unexpected source-kind composition")

    structures_by_key = {
        (source["noc_version"], source["language"]): source for source in structures
    }
    expected_structure_keys = {
        (version, language)
        for version in ("2011", "2016", "2021")
        for language in ("en", "fr")
    }
    if set(structures_by_key) != expected_structure_keys:
        raise NocBuildError("NOC manifest does not contain every bilingual structure pair")
    correspondences_by_language = {
        source["language"]: source for source in correspondences
    }
    if set(correspondences_by_language) != {"en", "fr"}:
        raise NocBuildError("NOC manifest does not contain both correspondence languages")

    english_units = []
    french_units = []
    source_audit = []
    for source in sorted(
        structures, key=lambda value: (value["noc_version"], value["language"])
    ):
        parsed = structure_rows(source)
        (english_units if source["language"] == "en" else french_units).extend(parsed)
        source_audit.append(
            {
                "source_id": source["source_id"],
                "source_kind": source["source_kind"],
                "noc_version": source["noc_version"],
                "language": source["language"],
                "sha256": source["sha256"],
                "unit_group_count": len(parsed),
            }
        )
    units = bilingual_unit_rows(english_units, french_units)
    units.sort(key=lambda value: (value["noc_version"], value["noc_code"]))
    crosswalk = crosswalk_rows(
        correspondences_by_language["en"],
        correspondences_by_language["fr"],
        units,
    )
    correspondence_title_mismatches = []
    for row in crosswalk:
        if row["is_direct_official_correspondence"] != "true":
            continue
        for role in ("source", "target"):
            for language in ("en", "fr"):
                if row[f"_{role}_title_match_{language}"]:
                    continue
                correspondence_title_mismatches.append(
                    {
                        "language": language,
                        "source_code": row["source_code"],
                        "target_code": row["target_code"],
                        "title_role": role,
                        "structure_title": row[f"{role}_title_{language}"],
                        "correspondence_title": row[
                            f"_{role}_title_correspondence_{language}"
                        ],
                    }
                )
    for language in ("en", "fr"):
        source = correspondences_by_language[language]
        source_audit.append(
            {
                "source_id": source["source_id"],
                "source_kind": source["source_kind"],
                "language": language,
                "sha256": source["sha256"],
                "official_correspondence_row_count": len(crosswalk) // 2,
                "structure_title_mismatch_count": sum(
                    item["language"] == language
                    for item in correspondence_title_mismatches
                ),
            }
        )
    canonical_audit = audit_canonical(args.canonical.resolve(), units)

    atomic_write(args.unit_output.resolve(), csv_bytes(units, UNIT_FIELDS))
    atomic_write(args.crosswalk_output.resolve(), csv_bytes(crosswalk, CROSSWALK_FIELDS))
    write_json(args.schema_output.resolve(), schema_document())
    reconciliation = {
        "schema_version": "0.2.0",
        "languages": ["en", "fr"],
        "bilingual_pair_status": "complete",
        "source_audit": source_audit,
        "unit_group_count": len(units),
        "unit_group_count_by_version": dict(
            sorted(Counter(row["noc_version"] for row in units).items())
        ),
        "crosswalk_row_count": len(crosswalk),
        "crosswalk_row_count_by_source_version": dict(
            sorted(Counter(row["source_version"] for row in crosswalk).items())
        ),
        "crosswalk_cardinality_counts": dict(
            sorted(Counter(row["mapping_cardinality"] for row in crosswalk).items())
        ),
        "correspondence_title_mismatches": correspondence_title_mismatches,
        "canonical_join_audit": canonical_audit,
        "limitations": [
            "The LMIA source metadata identifies NOC 2011 through 2024 Q1 and NOC "
            "2021 from 2024 Q2 onward.",
            "NOC 2016 V1.3 is retained as the official bridge to NOC 2021, not "
            "assigned to LMIA rows that declare NOC 2011.",
            "Crosswalk rows do not provide weights for splitting an observed count "
            "among multiple target codes.",
        ],
    }
    write_json(args.reconciliation_output.resolve(), reconciliation)
    if canonical_audit["join_status"] != "complete":
        raise NocBuildError("Canonical LMIA records contain NOC codes absent from the reference")
    print(
        f"Built {len(units):,} NOC unit groups and {len(crosswalk):,} crosswalk rows; "
        f"all observed LMIA NOC codes matched."
    )


if __name__ == "__main__":
    main()
