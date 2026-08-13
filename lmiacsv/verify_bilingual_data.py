"""Reconcile paired English and French LMIA publications at the data level.

French resources are validation inputs, not duplicate canonical records.  The
ledger distinguishes exact normalized-record agreement, agreement after removing
employer spelling, agreement only in language-neutral measure distributions, and
agreement only in release-level totals.  Source differences are preserved.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lmiacsv.build_aggregate_tables import parse_source as parse_aggregate_source
from lmiacsv.build_canonical_records import (
    MISLINKED_2021_Q2_NEGATIVE,
    SourcePlan,
    canonical_records,
    catalogued_source_plan,
    incorporate_status_key,
    program_stream_key,
    recovered_2021_q2_plan,
    source_rows,
)
from lmiacsv.scrape_catalogue import CatalogueError, write_json


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
EMPLOYER_CATALOGUE_PATH = (
    WORKSPACE_ROOT / "data" / "meta" / "employers.catalogue.json"
)
EMPLOYER_CENSUS_PATH = (
    WORKSPACE_ROOT
    / "data"
    / "meta"
    / "employers.census.json"
)
EMPLOYER_MANIFEST_PATH = (
    WORKSPACE_ROOT / "data" / "raw" / "employer-lists" / "manifest.json"
)
AGGREGATE_MANIFEST_PATH = (
    WORKSPACE_ROOT / "data" / "raw" / "aggregate-tables" / "manifest.json"
)
OUTPUT_PATH = (
    WORKSPACE_ROOT
    / "data"
    / "meta"
    / "bilingual.reconciliation.json"
)

class BilingualVerificationError(CatalogueError):
    """Raised when source pairing or a declared verification invariant fails."""


def index_all(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = {
        resource["resource_id"]: resource
        for resource in document.get("resources", [])
        if resource.get("resource_id")
    }
    if len(values) != len(document.get("resources", [])):
        raise BilingualVerificationError("Resource IDs are missing or duplicated")
    return values


def add_evidence(
    evidence: dict[str, dict[str, Counter[str]]],
    category: str,
    key: str,
    raw_value: str,
) -> None:
    raw = str(raw_value or "").strip()
    if key and raw:
        evidence[category][key][raw] += 1


@dataclass
class EmployerParse:
    plan: SourcePlan
    exact: Counter[tuple[Any, ...]]
    core: Counter[tuple[Any, ...]]
    measures: Counter[tuple[Any, ...]]
    totals: dict[str, int]
    evidence: dict[str, dict[str, Counter[str]]]


def employer_plan(
    catalogue: dict[str, Any],
    census: dict[str, Any],
    raw: dict[str, Any],
) -> SourcePlan:
    if catalogue["resource_id"] == MISLINKED_2021_Q2_NEGATIVE and catalogue["language"] == "en":
        return recovered_2021_q2_plan(catalogue, census, raw)
    return catalogued_source_plan(
        catalogue,
        census,
        raw,
        allow_decision_mismatch=True,
    )


def parse_employer_resource(
    catalogue: dict[str, Any], census: dict[str, Any], raw: dict[str, Any]
) -> EmployerParse:
    plan = employer_plan(catalogue, census, raw)
    exact: Counter[tuple[Any, ...]] = Counter()
    core: Counter[tuple[Any, ...]] = Counter()
    measures: Counter[tuple[Any, ...]] = Counter()
    evidence: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    totals = {"record_count": 0, "position_count": 0, "lmia_count": 0}
    with source_rows(plan) as rows:
        for record in canonical_records(plan, rows):
            stream = program_stream_key(record["program_stream"])
            incorporation = incorporate_status_key(record["incorporate_status"])
            totals["record_count"] += 1
            totals["position_count"] += int(record["position_count"])
            totals["lmia_count"] += int(record["lmia_count"] or 0)
            common = (
                record["province_code"],
                stream,
                record["postal_code"],
                record["noc_version"],
                record["noc_code"],
                record["lmia_count"],
                record["position_count"],
                incorporation,
            )
            exact[common + (record["employer_key"],)] += 1
            core[common] += 1
            measures[
                (
                    record["province_code"],
                    stream,
                    record["lmia_count"],
                    record["position_count"],
                )
            ] += 1
            add_evidence(
                evidence,
                "province_territory",
                record["province_code"],
                record["province_raw"],
            )
            add_evidence(
                evidence,
                "program_stream",
                stream,
                record["program_stream_raw"],
            )
            add_evidence(
                evidence,
                "incorporation_status",
                incorporation,
                record["incorporate_status_raw"],
            )
    return EmployerParse(plan, exact, core, measures, totals, evidence)


EMPLOYER_EXAMPLE_FIELDS = (
    "province_territory",
    "program_stream",
    "postal_code",
    "noc_version",
    "noc_code",
    "lmia_count",
    "position_count",
    "incorporation_status",
    "employer_key",
)


def counter_examples(
    left: Counter[tuple[Any, ...]],
    right: Counter[tuple[Any, ...]],
    fields: tuple[str, ...],
    limit: int = 5,
) -> list[dict[str, Any]]:
    values = []
    for item, count in (left - right).items():
        values.append({**dict(zip(fields, item, strict=True)), "multiplicity": count})
        if len(values) == limit:
            break
    return values


def employer_pair_status(en: EmployerParse, fr: EmployerParse) -> str:
    if en.exact == fr.exact:
        return "normalized_record_match"
    if en.core == fr.core:
        return "language_neutral_core_match"
    if en.measures == fr.measures:
        return "measure_distribution_match"
    if en.totals == fr.totals:
        return "summary_totals_only_match"
    return "summary_totals_mismatch"


def employer_pair_document(en: EmployerParse, fr: EmployerParse) -> dict[str, Any]:
    return {
        "period": en.plan.catalogue["period"],
        "decision": en.plan.decision,
        "status": employer_pair_status(en, fr),
        "checks": {
            "summary_totals_match": en.totals == fr.totals,
            "measure_distribution_match": en.measures == fr.measures,
            "language_neutral_core_match": en.core == fr.core,
            "normalized_record_match": en.exact == fr.exact,
        },
        "en": {
            "resource_id": en.plan.resource_id,
            "source_file": en.plan.file_name,
            "source_sha256": en.plan.sha256,
            "source_disposition": en.plan.disposition,
            "anomaly_flags": list(en.plan.anomaly_flags),
            **en.totals,
        },
        "fr": {
            "resource_id": fr.plan.resource_id,
            "source_file": fr.plan.file_name,
            "source_sha256": fr.plan.sha256,
            "source_disposition": fr.plan.disposition,
            "anomaly_flags": list(fr.plan.anomaly_flags),
            **fr.totals,
        },
        "differences": {
            "en_only_normalized_record_count": sum((en.exact - fr.exact).values()),
            "fr_only_normalized_record_count": sum((fr.exact - en.exact).values()),
            "en_only_core_count": sum((en.core - fr.core).values()),
            "fr_only_core_count": sum((fr.core - en.core).values()),
            "en_only_measure_count": sum((en.measures - fr.measures).values()),
            "fr_only_measure_count": sum((fr.measures - en.measures).values()),
            "en_only_examples": counter_examples(
                en.exact, fr.exact, EMPLOYER_EXAMPLE_FIELDS
            ),
            "fr_only_examples": counter_examples(
                fr.exact, en.exact, EMPLOYER_EXAMPLE_FIELDS
            ),
        },
    }


def merge_evidence(
    target: dict[str, dict[str, dict[str, Counter[str]]]],
    language: str,
    source: dict[str, dict[str, Counter[str]]],
) -> None:
    for category, keys in source.items():
        for key, variants in keys.items():
            target[category][key][language].update(variants)


def add_language_evidence(
    evidence: dict[str, dict[str, dict[str, Counter[str]]]],
    language: str,
    category: str,
    key: str,
    raw_value: str,
) -> None:
    raw = str(raw_value or "").strip()
    if key and raw:
        evidence[category][key][language][raw] += 1


def employer_reconciliation(
    catalogue_document: dict[str, Any],
    census_document: dict[str, Any],
    raw_document: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Counter[str]]]]]:
    catalogue = index_all(catalogue_document)
    census = index_all(census_document)
    raw = index_all(raw_document)
    if set(catalogue) != set(census) or set(catalogue) != set(raw):
        raise BilingualVerificationError(
            "Employer catalogue, census, and raw manifest resource sets disagree"
        )
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for resource in catalogue.values():
        grouped[(resource["period"]["key"], resource["decision"])][
            resource["language"]
        ] = resource
    invalid = [key for key, languages in grouped.items() if set(languages) != {"en", "fr"}]
    if invalid:
        raise BilingualVerificationError(f"Employer releases lack language pairs: {invalid!r}")

    pairs = []
    evidence: dict[str, dict[str, dict[str, Counter[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(Counter))
    )
    for key in sorted(grouped):
        resources = grouped[key]
        parsed = {
            language: parse_employer_resource(
                resource,
                census[resource["resource_id"]],
                raw[resource["resource_id"]],
            )
            for language, resource in resources.items()
        }
        pairs.append(employer_pair_document(parsed["en"], parsed["fr"]))
        for language in ("en", "fr"):
            merge_evidence(evidence, language, parsed[language].evidence)

    statuses = Counter(pair["status"] for pair in pairs)
    return {
        "resource_count": len(catalogue),
        "pair_count": len(pairs),
        "status_counts": dict(sorted(statuses.items())),
        "summary_totals_mismatch_count": statuses["summary_totals_mismatch"],
        "normalized_record_match_count": statuses["normalized_record_match"],
        "pairs": pairs,
    }, evidence


AGGREGATE_EXAMPLE_FIELDS = (
    "period",
    "province_territory",
    "program_stream",
    "positive_lmias",
)


def aggregate_reconciliation(
    manifest: dict[str, Any],
    evidence: dict[str, dict[str, dict[str, Counter[str]]]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for resource in manifest.get("resources", []):
        if resource.get("status") != "downloaded":
            continue
        release = resource.get("release_period") or "annual"
        grouped[(release, resource["language"])].append(resource)

    parsed: dict[tuple[str, str], tuple[dict[str, Any], Counter[tuple[Any, ...]]]] = {}
    for key, sources in grouped.items():
        unique_sha = {source["sha256"] for source in sources}
        if len(unique_sha) != 1:
            raise BilingualVerificationError(
                f"Aggregate release {key!r} has multiple distinct archived sources"
            )
        source = sorted(
            sources,
            key=lambda value: (
                not value.get("declared_current", False),
                value["source_filename"],
            ),
        )[0]
        observations, _audit = parse_aggregate_source(source)
        signature: Counter[tuple[Any, ...]] = Counter()
        for observation in observations:
            period = str(observation.get("period", observation.get("year")))
            signature[
                (
                    period,
                    observation["province_territory"],
                    observation["program_stream"],
                    observation["positive_lmias"],
                )
            ] += 1
            add_language_evidence(
                evidence,
                source["language"],
                "province_territory",
                observation["province_territory"],
                observation["province_territory_raw"],
            )
            add_language_evidence(
                evidence,
                source["language"],
                "program_stream",
                observation["program_stream"],
                observation["program_stream_raw"],
            )
        parsed[key] = (source, signature)

    releases = sorted({release for release, _language in parsed}, key=lambda value: (value == "annual", value))
    pairs = []
    unpaired = []
    for release in releases:
        languages = {language for candidate, language in parsed if candidate == release}
        if languages != {"en", "fr"}:
            unpaired.append({"release": release, "available_languages": sorted(languages)})
            continue
        en_source, en = parsed[(release, "en")]
        fr_source, fr = parsed[(release, "fr")]
        pairs.append(
            {
                "release": release,
                "status": "match" if en == fr else "mismatch",
                "observation_count_en": sum(en.values()),
                "observation_count_fr": sum(fr.values()),
                "en": {
                    "resource_id": en_source["resource_id"],
                    "source_file": en_source["source_filename"],
                    "source_sha256": en_source["sha256"],
                },
                "fr": {
                    "resource_id": fr_source["resource_id"],
                    "source_file": fr_source["source_filename"],
                    "source_sha256": fr_source["sha256"],
                },
                "en_only_observation_count": sum((en - fr).values()),
                "fr_only_observation_count": sum((fr - en).values()),
                "en_only_examples": counter_examples(
                    en, fr, AGGREGATE_EXAMPLE_FIELDS
                ),
                "fr_only_examples": counter_examples(
                    fr, en, AGGREGATE_EXAMPLE_FIELDS
                ),
            }
        )
    return {
        "downloaded_resource_count": len(parsed),
        "paired_release_count": len(pairs),
        "match_count": sum(pair["status"] == "match" for pair in pairs),
        "mismatch_count": sum(pair["status"] == "mismatch" for pair in pairs),
        "unpaired_release_count": len(unpaired),
        "unpaired_releases": unpaired,
        "pairs": pairs,
    }


def evidence_document(
    evidence: dict[str, dict[str, dict[str, Counter[str]]]]
) -> dict[str, Any]:
    return {
        category: {
            key: {
                language: [
                    {"raw_value": raw, "observation_count": count}
                    for raw, count in sorted(variants.items())
                ]
                for language, variants in sorted(languages.items())
            }
            for key, languages in sorted(keys.items())
        }
        for category, keys in sorted(evidence.items())
    }


def build_reconciliation(
    employer_catalogue: dict[str, Any],
    employer_census: dict[str, Any],
    employer_manifest: dict[str, Any],
    aggregate_manifest: dict[str, Any],
) -> dict[str, Any]:
    employer, evidence = employer_reconciliation(
        employer_catalogue, employer_census, employer_manifest
    )
    aggregate = aggregate_reconciliation(aggregate_manifest, evidence)
    return {
        "schema_version": "0.1.0",
        "purpose": (
            "Verify that paired English and French official publications contain the same "
            "underlying data after explicit categorical translation normalization."
        ),
        "method": {
            "french_data_role": "verification_only",
            "canonical_employer_language": "en",
            "excluded_from_employer_identity_check": [
                "translated occupation title",
                "full address text",
                "raw categorical labels",
                "source row order",
            ],
            "preserved_in_employer_identity_check": [
                "province/territory code",
                "program-stream key",
                "employer key",
                "postal code",
                "NOC version and code",
                "LMIA count",
                "position count",
                "incorporation-status key",
            ],
        },
        "employer_lists": employer,
        "aggregate_table_14": aggregate,
        "translation_evidence": evidence_document(evidence),
        "interpretation": [
            "A summary-total match does not prove row-level bilingual identity.",
            "A normalized-record mismatch is retained even when it appears attributable to "
            "accents, encoding loss, translated legal status, or source typos.",
            "The French 2025 Q4 aggregate release was not recoverable from the official "
            "resource-bound filename archive and therefore is not treated as a match.",
        ],
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employer-catalogue", type=Path, default=EMPLOYER_CATALOGUE_PATH)
    parser.add_argument("--employer-census", type=Path, default=EMPLOYER_CENSUS_PATH)
    parser.add_argument("--employer-manifest", type=Path, default=EMPLOYER_MANIFEST_PATH)
    parser.add_argument("--aggregate-manifest", type=Path, default=AGGREGATE_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    document = build_reconciliation(
        read_json(args.employer_catalogue),
        read_json(args.employer_census),
        read_json(args.employer_manifest),
        read_json(args.aggregate_manifest),
    )
    write_json(args.output.resolve(), document)
    employer = document["employer_lists"]
    aggregate = document["aggregate_table_14"]
    print(
        f"Verified {employer['pair_count']} employer pairs "
        f"({employer['summary_totals_mismatch_count']} summary-total mismatches) and "
        f"{aggregate['paired_release_count']} aggregate pairs "
        f"({aggregate['mismatch_count']} mismatches; "
        f"{aggregate['unpaired_release_count']} unpaired releases)."
    )


if __name__ == "__main__":
    main()
