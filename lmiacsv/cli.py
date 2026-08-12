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
        "build the canonical CSV, schema, and reconciliation ledger",
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
