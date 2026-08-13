"""Command-line dispatcher for the lmiacsv pipeline."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence


COMMANDS = {
    "catalogue": (
        "lmiacsv.scrape_employer_catalogues",
        "refresh the official positive and negative employer-list catalogue",
    ),
    "statistics-catalogue": (
        "lmiacsv.scrape_catalogue",
        "audit the separate official quarterly statistics catalogue",
    ),
    "aggregate-catalogue": (
        "lmiacsv.scrape_aggregate_catalogues",
        "catalogue the official quarterly and annual aggregate Table 14 resources",
    ),
    "aggregate-fetch": (
        "lmiacsv.fetch_aggregate_resources",
        "discover and archive current and retained historical Table 14 releases",
    ),
    "aggregate-build": (
        "lmiacsv.build_aggregate_tables",
        "normalize positive-LMIA quarterly and annual aggregate tables",
    ),
    "bilingual-verify": (
        "lmiacsv.verify_bilingual_data",
        "reconcile paired English/French employer and aggregate source data",
    ),
    "translations-build": (
        "lmiacsv.build_translations",
        "build the shared translation registry from bilingual evidence",
    ),
    "noc-catalogue": (
        "lmiacsv.scrape_noc_catalogue",
        "catalogue official Statistics Canada NOC reference CSVs",
    ),
    "noc-fetch": (
        "lmiacsv.fetch_noc_resources",
        "archive official NOC structures and correspondence by checksum",
    ),
    "noc-build": (
        "lmiacsv.build_noc_tables",
        "normalize versioned NOC unit groups and crosswalks",
    ),
    "fetch": (
        "lmiacsv.fetch_employer_resources",
        "download employer-list resources into immutable checksum paths",
    ),
    "census": (
        "lmiacsv.census_employer_resources",
        "inspect every downloaded file, sheet, header, and format",
    ),
    "build": (
        "lmiacsv.build_canonical_records",
        "build the full employer CSV, schema, and reconciliation ledger",
    ),
    "min-build": (
        "lmiacsv.build_min_products",
        "build deterministic compact projections and full/min manifests",
    ),
    "receipts": (
        "lmiacsv.collect_2021q2_receipts",
        "refresh the dated 2021 Q2 negative-resource evidence bundle",
    ),
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="lmiacsv",
        description="Reproduce the canonical LMIA employer-list CSV.",
    )
    value.add_argument("command", nargs="?", choices=COMMANDS, help="pipeline stage to run")
    value.epilog = "\n".join(
        f"  {command:20} {description}" for command, (_module, description) in COMMANDS.items()
    )
    value.formatter_class = argparse.RawDescriptionHelpFormatter
    return value


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in COMMANDS:
        command = arguments.pop(0)
    else:
        options = parser().parse_args(arguments)
        if options.command is None:
            parser().print_help()
            return
        command = options.command

    module_name, _description = COMMANDS[command]
    module = importlib.import_module(module_name)
    sys.argv = [f"lmiacsv {command}", *arguments]
    module.main()


if __name__ == "__main__":
    main()
