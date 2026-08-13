"""Build one shared English/French registry for recurring LMIA phrases.

Source-category translations are accompanied by counts and literal variants from
the bilingual reconciliation ledger.  Editorial interface phrases are clearly
marked and are never represented as if the underlying data had verified them.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
from typing import Any

from lmiacsv.scrape_catalogue import atomic_write, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_PATH = (
    WORKSPACE_ROOT
    / "data"
    / "meta"
    / "bilingual.reconciliation.json"
)
OUTPUT_PATH = WORKSPACE_ROOT / "data" / "full" / "translations.csv"
SCHEMA_PATH = WORKSPACE_ROOT / "data" / "meta" / "translations.schema.json"

FIELDS = [
    "translation_key",
    "category",
    "en",
    "fr",
    "translation_basis",
    "verification_status",
    "en_observation_count",
    "fr_observation_count",
    "source_variants_en",
    "source_variants_fr",
    "notes",
]

PROVINCES = [
    ("AB", "Alberta", "Alberta"),
    ("BC", "British Columbia", "Colombie-Britannique"),
    ("MB", "Manitoba", "Manitoba"),
    ("NB", "New Brunswick", "Nouveau-Brunswick"),
    ("NL", "Newfoundland and Labrador", "Terre-Neuve-et-Labrador"),
    ("NS", "Nova Scotia", "Nouvelle-Écosse"),
    ("NT", "Northwest Territories", "Territoires du Nord-Ouest"),
    ("NU", "Nunavut", "Nunavut"),
    ("ON", "Ontario", "Ontario"),
    ("PE", "Prince Edward Island", "Île-du-Prince-Édouard"),
    ("QC", "Quebec", "Québec"),
    ("SK", "Saskatchewan", "Saskatchewan"),
    ("YT", "Yukon", "Yukon"),
    ("INT", "Outside Canada", "À l’extérieur du Canada"),
]

PROGRAM_STREAMS = [
    ("high_wage", "High Wage", "Haut salaire"),
    ("low_wage", "Low Wage", "Bas salaire"),
    ("primary_agriculture", "Primary Agriculture", "Agriculture primaire"),
    ("global_talent_stream", "Global Talent Stream", "Talent mondial"),
    (
        "permanent_resident_only",
        "Permanent Resident Only",
        "Résident permanent seulement",
    ),
    ("unspecified", "Unspecified", "Non spécifié"),
]

INCORPORATION_STATUSES = [
    ("unknown", "Unknown", "Inconnu"),
    ("corporation", "Corporation", "Corporation"),
    ("partnership", "Partnership", "Partenariat"),
    (
        "sole_proprietorship",
        "Sole Proprietorship",
        "Entreprise à propriétaire unique",
    ),
    ("co_operative", "Co-operative", "Coopérative"),
    (
        "non_profit_organization",
        "Non-Profit Organization",
        "Organisme sans but lucratif",
    ),
    ("incorporated", "Incorporated", "Incorporé"),
    (
        "registered_charity",
        "Registered Charity",
        "Organisme de bienfaisance enregistré",
    ),
    (
        "no_response_provided",
        "No response provided",
        "Aucune réponse fournie",
    ),
]

COMMON_PHRASES = [
    ("field.province_territory", "field_label", "Province/Territory", "Province/Territoire"),
    ("field.program_stream", "field_label", "Program Stream", "Volet du programme"),
    ("field.employer", "field_label", "Employer", "Employeur"),
    ("field.address", "field_label", "Address", "Adresse"),
    ("field.occupation", "field_label", "Occupation", "Profession"),
    ("field.incorporation_status", "field_label", "Incorporation Status", "Statut juridique"),
    ("decision.positive", "decision_status", "Positive", "Positive"),
    ("decision.negative", "decision_status", "Negative", "Négative"),
    ("measure.positive_lmias", "measure", "Positive LMIAs", "EIMT positives"),
    ("measure.approved_lmias", "measure", "Approved LMIAs", "EIMT approuvées"),
    ("measure.requested_lmias", "measure", "Requested LMIAs", "EIMT demandées"),
    ("measure.approved_positions", "measure", "Approved Positions", "Postes approuvés"),
    ("measure.requested_positions", "measure", "Requested Positions", "Postes demandés"),
    ("period_precision.quarter", "period_precision", "Quarter", "Trimestre"),
    (
        "period_precision.multi_quarter",
        "period_precision",
        "Multiple quarters",
        "Plusieurs trimestres",
    ),
    (
        "period_precision.year_or_partial_year",
        "period_precision",
        "Year or partial year",
        "Année ou année partielle",
    ),
]


class TranslationBuildError(RuntimeError):
    """Raised when the shared translation registry is incomplete or ambiguous."""


def evidence_values(
    reconciliation: dict[str, Any], category: str, key: str, language: str
) -> tuple[int, str]:
    values = (
        reconciliation.get("translation_evidence", {})
        .get(category, {})
        .get(key, {})
        .get(language, [])
    )
    count = sum(int(value["observation_count"]) for value in values)
    variants = " | ".join(value["raw_value"] for value in values)
    return count, variants


def source_row(
    reconciliation: dict[str, Any],
    category: str,
    key: str,
    en: str,
    fr: str,
    *,
    notes: str = "",
) -> dict[str, Any]:
    en_count, en_variants = evidence_values(reconciliation, category, key, "en")
    fr_count, fr_variants = evidence_values(reconciliation, category, key, "fr")
    if en_count and fr_count:
        status = "observed_in_both_language_sources"
    elif en_count or fr_count:
        status = "unpaired_source_value"
    else:
        status = "not_observed_in_record_values"
    return {
        "translation_key": f"{category}.{key}",
        "category": category,
        "en": en,
        "fr": fr,
        "translation_basis": "official_source_values",
        "verification_status": status,
        "en_observation_count": en_count,
        "fr_observation_count": fr_count,
        "source_variants_en": en_variants,
        "source_variants_fr": fr_variants,
        "notes": notes,
    }


def build_rows(reconciliation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        source_row(reconciliation, "province_territory", code, en, fr)
        for code, en, fr in PROVINCES
    ]
    rows.extend(
        source_row(reconciliation, "program_stream", key, en, fr)
        for key, en, fr in PROGRAM_STREAMS
    )
    rows.extend(
        source_row(reconciliation, "incorporation_status", key, en, fr)
        for key, en, fr in INCORPORATION_STATUSES
    )
    rows.append(
        source_row(
            reconciliation,
            "program_stream",
            "source_code_99",
            "99",
            "",
            notes=(
                "Literal value preserved from one English 2025 Q1 negative record; "
                "the paired French source has no corresponding value."
            ),
        )
    )
    rows.extend(
        {
            "translation_key": key,
            "category": category,
            "en": en,
            "fr": fr,
            "translation_basis": "official_terminology_or_editorial",
            "verification_status": "not_a_record_value_check",
            "en_observation_count": "",
            "fr_observation_count": "",
            "source_variants_en": "",
            "source_variants_fr": "",
            "notes": "Shared interface phrase; not evidence of bilingual row identity.",
        }
        for key, category, en, fr in COMMON_PHRASES
    )
    keys = [row["translation_key"] for row in rows]
    if len(keys) != len(set(keys)):
        duplicates = sorted(key for key in set(keys) if keys.count(key) > 1)
        raise TranslationBuildError(f"Duplicate translation keys: {duplicates!r}")
    for row in rows:
        if not row["en"]:
            raise TranslationBuildError(
                f"Translation {row['translation_key']} has no English value"
            )
        if not row["fr"] and row["translation_key"] != "program_stream.source_code_99":
            raise TranslationBuildError(
                f"Translation {row['translation_key']} has no French value"
            )
    return rows


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def schema_document(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "product": "translations.csv",
        "grain": "stable translation key",
        "primary_key": ["translation_key"],
        "fields": FIELDS,
        "row_count": len(rows),
        "contracts": [
            "Source-value rows cite observation counts and literal variants from the "
            "bilingual reconciliation ledger.",
            "Observation counts measure nonblank literal source cells; grouped blanks that "
            "are forward-filled during parsing are not counted as repeated spellings.",
            "Editorial and interface phrases are marked not_a_record_value_check.",
            "Literal source code 99 is retained without inventing a French translation.",
            "Versioned NOC/CNP titles and definitions remain in noc.csv and "
            "noc-crosswalk.csv; they are source data, not common phrases.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, default=RECONCILIATION_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--schema-output", type=Path, default=SCHEMA_PATH)
    args = parser.parse_args()

    reconciliation = json.loads(args.reconciliation.read_text(encoding="utf-8"))
    rows = build_rows(reconciliation)
    atomic_write(args.output.resolve(), csv_bytes(rows))
    write_json(args.schema_output.resolve(), schema_document(rows))
    verified = sum(
        row["verification_status"] == "observed_in_both_language_sources"
        for row in rows
    )
    print(
        f"Built {len(rows)} shared translations; {verified} recurring source values "
        "were observed in both official languages."
    )


if __name__ == "__main__":
    main()
