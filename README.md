# lmiacsv

`lmiacsv` is a reproducible normalizer for Canada's public Labour Market Impact
Assessment data. It downloads the official employer lists and aggregate statistics,
preserves their identities and checksums, inventories spreadsheet drift, and builds
source-auditable CSVs without concealing defects in the government data.

This repository is the data layer. It contains no Peanut Gallery presentation code and
no editorial analysis. The separate `lmiareport` repository consumes its outputs.

## What it produces

The employer-list build writes:

- `data/full/employers.csv`: the generated 47-column source-faithful dataset. It is
  intentionally ignored by Git and is roughly 515 MiB for the current archive.
- `data/meta/employers.schema.json`: the machine-readable column contract and measure
  definitions.
- `data/meta/employers.reconciliation.json`: resource-level source selection,
  row and measure totals, checksum receipts, recoveries, interpretation overrides,
  quarantines, and quality flags.

The aggregate build separately writes:

- `data/full/positive-quarterly.csv`: positive LMIAs at
  quarter × province/territory × program-stream grain.
- `data/full/positive-annual.csv`: the corresponding official
  annual Table 14 observations used as a cross-check.
- `data/full/positive-quarterly-national.csv`: arithmetic
  national totals by quarter, with revision, annual-mismatch, and scope flags suitable
  for downstream charts.
- `data/meta/aggregates.schema.json`: the aggregate products' grain, measure, and
  non-claims.
- `data/meta/aggregates.reconciliation.json`: discovered releases, missing
  historical quarters, overlap revisions, category differences, and annual
  comparisons.

The currently recoverable quarterly Table 14 window is 2021 Q1 onward. The separate
annual Table 14 starts in 2018; it is preserved for comparison but is not divided into
invented quarterly values.

The NOC reference build writes:

- `data/full/noc.csv`: official NOC/CNP 2011, 2016
  Version 1.3, and 2021 Version 1.0 unit groups with paired English/French titles,
  definitions, hierarchy, TEER category where applicable, and provenance for both
  official language sources.
- `data/full/noc-crosswalk.csv`: the official NOC 2016 Version 1.3 to
  NOC 2021 Version 1.0 correspondence plus an explicitly labelled NOC 2011 to 2021
  composition that uses the unchanged 2011/2016 unit-group structure, with paired
  English/French titles, change descriptions, notes, and source provenance.
- `data/meta/noc.schema.json`: reference and crosswalk contracts.
- `data/meta/noc.reconciliation.json`: bilingual source checksums, class
  counts, crosswalk cardinalities, correspondence-title disagreements, and the join
  audit against employer records.

The bilingual verification and shared-language build writes:

- `data/meta/bilingual.reconciliation.json`: a data-level comparison of
  all 78 paired employer-list releases and every recoverable paired English/French
  aggregate Table 14 release. It separately reports summary totals, language-neutral
  measure distributions, record dimensions, and employer identity.
- `data/full/translations.csv`: 46 stable English/French keys for
  recurring provinces, streams, incorporation statuses, field labels, measures, and
  period labels. Source-value rows include literal variants and observation counts
  from the reconciliation ledger.
- `data/meta/translations.schema.json`: the registry contract and the
  boundary between source-verified values and editorial interface phrases.

French employer and aggregate files are verification inputs. They are not appended as
duplicate normalized employer rows. Versioned NOC/CNP titles and definitions remain in
the NOC tables because they are reference data rather than common phrases.

The full employer CSV retains the government dataset and resource UUIDs, source checksum,
filename, sheet, row number, raw values, normalized values, period precision, decision
status, stable translation keys, and explicit LMIA and position measures.

### Which normalized product should I use?

| Question | Product | Important limit |
| --- | --- | --- |
| Which employers, occupations, locations, or naming patterns appear in the lists? | `employers.csv` | One row is a published employer/occupation record, not necessarily one application or LMIA. |
| How many positive LMIAs were published by quarter, province, and stream? | `positive-quarterly.csv` | Recovered quarterly coverage begins at 2021 Q1, with a stream-scope break before 2022. |
| How many positive LMIAs were published nationally each quarter? | `positive-quarterly-national.csv` | Read `quality_flags`; this is a sum of the categories present in the quarterly source. |
| What annual positive-LMIA totals exist from 2018 onward? | `positive-annual.csv` | Annual observations cannot be divided to manufacture missing quarters. |
| What percentage of all LMIA applications were approved or denied? | Not available | The public sources do not provide a complete all-stream denominator and negative-decision numerator. |
| What does an observed NOC code mean in its published version? | `noc.csv` | Join on both `noc_version` and `noc_code`; code alone is not a stable cross-version key. |
| How does a NOC 2011 or 2016 class relate to NOC 2021? | `noc-crosswalk.csv` | Relationships can be one-to-many or many-to-one and do not include allocation weights. |
| How should recurring labels be displayed in English or French? | `translations.csv` | Check `verification_status`; editorial phrases are not evidence of bilingual row identity. |

See [docs/normalized-data.md](docs/normalized-data.md) for grains, columns, coverage,
quality flags, joins, and charting guidance.

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

# Download both official-language editions into immutable dataset/resource/SHA paths.
.venv/bin/lmiacsv fetch

# Inspect every English and French file, sheet, header, encoding, and detected format.
.venv/bin/lmiacsv census

# Build the canonical CSV, schema, and reconciliation ledger.
.venv/bin/lmiacsv build

# Catalogue, discover/archive, and normalize aggregate positive-LMIA Table 14.
.venv/bin/lmiacsv aggregate-catalogue
# Add --refresh to deliberately recheck previously missing historical filenames.
.venv/bin/lmiacsv aggregate-fetch
.venv/bin/lmiacsv aggregate-build

# Reconcile paired underlying employer and aggregate data, then build shared labels.
.venv/bin/lmiacsv bilingual-verify
.venv/bin/lmiacsv translations-build

# Catalogue, archive, pair, and normalize official English NOC and French CNP references.
.venv/bin/lmiacsv noc-catalogue
.venv/bin/lmiacsv noc-fetch
.venv/bin/lmiacsv noc-build

# Build compact projections plus deterministic full/min manifests.
.venv/bin/lmiacsv min-build

# Run the deterministic test suite.
.venv/bin/python -m unittest discover -s tests
```

The repository includes the dated evidence bundle and checksum-pinned recovered
workbook required for the known 2021 Q2 negative-resource defect. The 2022 Q2 English
positive workbook is interpreted only after its archived official French counterpart
passes the build's exact bilingual evidence check. Raw download archives are ignored
because they can be recreated by `lmiacsv fetch` and `lmiacsv aggregate-fetch`.

The checked build has no unresolved quarantines. For a strict run that also refuses
to emit data if a future source condition creates one:

```bash
.venv/bin/lmiacsv build --fail-on-quarantine
```

The source evidence, decision rule, product impact, and verification for the 2022 Q2
measure interpretation are recorded in
[docs/2022-q2-positive-measure-resolution.md](docs/2022-q2-positive-measure-resolution.md).

## Honesty rules

- Unknown headers and malformed rows fail closed.
- Annual and combined-quarter releases are not silently divided into quarters.
- Missing historical LMIA counts remain null.
- Positive-list positions and positions requested on negative decisions remain
  different measures.
- The mislabeled 2022 Q2 English positive measures are treated as approved only while
  the paired official French release matches every language-neutral normalized record
  and measure total; every affected row carries an explicit quality flag.
- Grouped source cells may be forward-filled, but the raw blank and a quality flag are
  retained.
- Employer normalization is text cleanup and search-key generation, not entity
  resolution.
- Employer-list rows are not application-level observations and cannot supply an LMIA
  application approval or denial rate.
- The aggregate quarterly catalogue is a rolling window. Historical Table 14 releases
  are discovered from resource-bound official filenames; releases that are no longer
  retrievable remain explicit gaps.
- Annual totals are used to check complete quarterly years, never to manufacture
  missing quarterly observations.
- NOC joins always use version and code together. Crosswalk relationships are not
  treated as deterministic record-level recodes and receive no invented weights.
- NOC/CNP text is taken from paired official English and French files. Language pairs
  must contain identical code sets and hierarchy codes or the build fails closed.
- English/French employer releases are not presumed identical because their totals
  usually agree. The bilingual ledger preserves summary, dimensional, and row-level
  disagreements separately.
- A source value without a paired-language equivalent remains untranslated. The
  literal employer-list stream code `99` is retained on that basis.

See [docs/pipeline.md](docs/pipeline.md) for the stage contract and
[docs/data-quality.md](docs/data-quality.md) for known source defects and scope changes.
The normalized product contracts are documented in
[docs/normalized-data.md](docs/normalized-data.md).

## Repository layout

```text
lmiacsv/         normalizer package and command-line entry point
tests/           deterministic unit and contract tests
data/raw/        ignored immutable downloads and raw manifests
data/full/       ignored complete source-faithful normalized products
data/min/        ignored deterministic compact projections for ordinary consumers
data/meta/       tracked flat catalogues, schemas, censuses, and reconciliation ledgers
evidence/        durable source-defect receipts and recovered official files
docs/            pipeline and data-quality documentation
```

`full/` and `min/` deliberately reuse product basenames: for example,
`data/full/employers.csv` and `data/min/employers.csv`. The min employer file is an
exact 18-column projection with every full row preserved in the same order. The three
`positive-*.csv` aggregate products are copied byte-for-byte into `min/` because
they are already small and useful together. This is not a second normalization.
`data/meta/min.schema.json` documents the derivations; each tier's tracked
`manifest.json` records row counts, fields, sizes, and SHA-256 checksums while the
generated CSVs remain ignored.

## License

An open-source license has not yet been selected. Add the chosen license before the
repository is published publicly; no license terms are inferred here.
