# lmiacsv

`lmiacsv` is a reproducible normalizer for Canada's public Labour Market Impact
Assessment employer lists. It downloads the official resources, preserves their
identity and checksums, inventories spreadsheet drift, and builds one source-auditable
CSV without concealing defects in the government data.

This repository is the data layer. It contains no Peanut Gallery presentation code and
no editorial analysis. The separate `lmiareport` repository consumes its outputs.

## What it produces

The main build writes:

- `data/normalized/canonical/lmia-employer-records.csv`: the generated 45-column
  canonical dataset. It is intentionally ignored by Git and is roughly 493 MiB for the
  current archive.
- `data/published/canonical/schema.json`: the machine-readable column contract and
  measure definitions.
- `data/published/canonical/reconciliation.json`: resource-level source selection,
  row and measure totals, checksum receipts, recoveries, quarantines, and quality flags.

The canonical CSV retains the government dataset and resource UUIDs, source checksum,
filename, sheet, row number, raw values, normalized values, period precision, decision
status, and explicit LMIA and position measures.

## Reproduce the current build

Python 3.11 or newer and LibreOffice are required. LibreOffice is used only if a true
legacy XLS workbook needs conversion during inspection. Create an environment and
install the package:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Then run the source pipeline:

```bash
# Refresh the official employer-list metadata catalogue.
.venv/bin/lmiacsv catalogue

# Download English resources into immutable dataset/resource/SHA paths.
.venv/bin/lmiacsv fetch

# Inspect every file, sheet, header, encoding, and detected format.
.venv/bin/lmiacsv census

# Build the canonical CSV, schema, and reconciliation ledger.
.venv/bin/lmiacsv build

# Run the deterministic test suite.
.venv/bin/python -m unittest discover -s tests
```

The repository includes the dated evidence bundle and checksum-pinned recovered
workbook required for the known 2021 Q2 negative-resource defect. The raw download
archive is ignored because it can be recreated by `lmiacsv fetch`.

For a strict run that refuses to emit data while any known resource is quarantined:

```bash
.venv/bin/lmiacsv build --fail-on-quarantine
```

## Honesty rules

- Unknown headers and malformed rows fail closed.
- Annual and combined-quarter releases are not silently divided into quarters.
- Missing historical LMIA counts remain null.
- Positive-list positions and positions requested on negative decisions remain
  different measures.
- Grouped source cells may be forward-filled, but the raw blank and a quality flag are
  retained.
- Employer normalization is text cleanup and search-key generation, not entity
  resolution.
- Employer-list rows are not application-level observations and cannot supply an LMIA
  application approval or denial rate.

See [docs/pipeline.md](docs/pipeline.md) for the stage contract and
[docs/data-quality.md](docs/data-quality.md) for known source defects and scope changes.

## Repository layout

```text
lmiacsv/         normalizer package and command-line entry point
tests/           deterministic unit and contract tests
data/raw/        ignored immutable downloads and raw manifests
data/published/  reviewable catalogues, schema, and reconciliation ledger
data/normalized/ ignored generated canonical CSV
evidence/        durable source-defect receipts and recovered official files
docs/            pipeline and data-quality documentation
```

## License

An open-source license has not yet been selected. Add the chosen license before the
repository is published publicly; no license terms are inferred here.
