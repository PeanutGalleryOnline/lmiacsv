# Normalized data products

`lmiacsv` publishes three related but deliberately separate analytical data families,
plus a shared translation registry. The
employer-list product preserves the grain of the public employer lists. The aggregate
products normalize official Table 14 counts of positive LMIAs. The bilingual NOC/CNP
references supply versioned occupation labels and class relationships. Aggregate counts
must not be joined as though they can be assigned to an employer row.

The values below describe the checked build retrieved on 2026-08-12. Coverage and row
counts will advance when the official catalogues publish new resources.

## Product tiers

`data/full/` contains every normalized field and source-provenance column. It is the
review and research tier. `data/min/` contains exact, deterministic column
projections intended for web builds and ordinary analysis. A min build never filters,
reorders, translates, aggregates, or repairs a row.

Both tiers use the same basename where a compact form exists:

| Product | Full | Min |
| --- | ---: | ---: |
| Employer records | 47 columns | 18-column projection |
| Positive quarterly | 16 columns | byte-for-byte copy |
| Positive annual | 13 columns | byte-for-byte copy |
| Positive quarterly national | 7 columns | byte-for-byte copy |
| NOC unit groups | 31 columns | 6-column projection |

The min employer fields are `record_id`, period key/year/quarter/precision, decision,
comparability regime, province code, stream key, cleaned employer and search key,
postal code, NOC version/code, incorporation-status key, the LMIA and position counts,
and quality flags. The min NOC fields retain version, code, both official titles, TEER,
and broad-category code. The aggregate files are already compact, so the min tier
retains their complete provenance and quality columns instead of introducing another
aggregate schema.

`data/meta/min.schema.json` is the versioned projection contract.
`data/full/manifest.json` and `data/min/manifest.json` record exact headers, row
counts, byte sizes, primary keys, and SHA-256 checksums. The min manifest also pins the
source full-manifest checksum.

## Employer-level records

### `data/full/employers.csv`

- Grain: one published employer, address, occupation, and measure row in one source
  resource.
- Current size: 483,546 records from 78 normalized resources, including one recovered
  official alternate and one bilingual-evidence measure override. No current resource
  is quarantined.
- Source-release coverage: 2014 through 2026 Q1. Early releases may cover a year,
  partial year, or combined quarters and remain at that precision.
- Decisions: positive and negative employer lists.
- Measures: `lmia_count` where the source supplies it and `position_count` under the
  semantic label in `position_measure`.

This product supports employer naming, geography, occupation, stream, and published
measure summaries. It does not support counting applications by counting rows.
`lmia_count` is blank where older sources do not publish an LMIA measure, and
`employer_key` is a search key rather than entity resolution.

`program_stream_key` and `incorporate_status_key` are language-neutral joins to
`program_stream.<key>` and `incorporation_status.<key>` in `translations.csv`.
Province labels join as `province_territory.<province_code>`. The adjacent display and
`*_raw` fields remain available for source review.

The 15,167 rows from the English 2022 Q2 positive release retain their literal
`Requested LMIAs` and `Requested Positions` source headers in the audit metadata but
use `approved_lmias` and `approved_positions` as canonical measure labels. This narrow
interpretation is supported by the paired official French positive workbook: it uses
approved labels and matches every language-neutral normalized record and measure
total. Each affected row is marked
`english_requested_headers_interpreted_as_approved_from_matching_french_release`; the
build fails closed if the language pair stops matching.

The complete decision record, including source UUIDs and checksums, before/after
product counts, and verification steps, is in
[2022-q2-positive-measure-resolution.md](2022-q2-positive-measure-resolution.md).

The authoritative column dictionary is
`data/meta/employers.schema.json`. Resource selection, interpretation evidence,
quarantines, recoveries, record totals, measure totals, and quality counts are in
`data/meta/employers.reconciliation.json`.

## Aggregate positive-LMIA records

The aggregate branch uses official ESDC Table 14. `positive_lmias` counts positive
Labour Market Impact Assessments by decision period. It does not count positions,
workers, work permits, employers, or applications submitted.

### `data/full/positive-quarterly.csv`

- Grain: decision quarter × province/territory × program stream.
- Current coverage: 2021 Q1 through 2026 Q1, 21 consecutive quarters and 1,313 rows.
- Measure: `positive_lmias`.
- Selection rule: when rolling releases repeat an observation, the newest recovered
  release is selected after every changed value is written to the reconciliation
  ledger.

The normalized dimensions are `province_territory` and `program_stream`.
`province_territory` is a language-neutral code and `program_stream` is a stable key
such as `high_wage` or `global_talent_stream`; both join to `translations.csv`. Their
source-faithful forms remain in `province_territory_raw` and `program_stream_raw`.
Every row also retains dataset UUID, resource UUID, release period, filename, SHA-256,
source language, sheet, and source row.

### `data/full/positive-annual.csv`

- Grain: decision year × province/territory × program stream.
- Current coverage: 2018 through 2025, 624 rows.
- Measure: `positive_lmias` from the separately published annual Table 14.

The annual file is an independent normalized source and a reconciliation reference.
It is not a fallback for missing quarterly data. In particular, its 2018-2020 totals
cannot reveal how observations were distributed across those missing quarters.

### `data/full/positive-quarterly-national.csv`

- Grain: decision quarter.
- Current coverage: 2021 Q1 through 2026 Q1, 21 rows.
- Formula: sum of the normalized province/territory and program-stream observations
  actually present in the selected quarterly source.

This is the convenient chart input. `contributing_rows` makes category coverage
visible, `source_release_periods` identifies the selected rolling release, and
`quality_flags` is a semicolon-delimited set containing zero or more of:

- `revised_across_releases`: at least one contributing value changed between recovered
  official releases.
- `annual_reconciliation_mismatch`: the four-quarter total differs from the separately
  published annual Table 14 for at least one comparable province/stream cell.
- `annual_scope_has_unallocated_lmias`: the annual source contains a positive count in
  a category absent from the quarterly source.

An empty `quality_flags` value means none of these checks raised a condition. It does
not mean the source supplies negative decisions or an approval-rate denominator.

## Coverage and comparability

The official quarterly catalogue is a rolling publication, not a historical archive.
Seventeen retained releases were recovered, from the 2022 Q1 release through 2026 Q1.
The oldest retained release contains observations beginning in 2021 Q1. The ledger
therefore records 2018 Q1 through 2020 Q4 as twelve missing quarterly periods even
though the annual source confirms that annual observations exist for those years.

Quarterly stream scope also changes:

- The recovered 2021 observations contain four streams and omit `Permanent Resident
  Only`.
- The annual source reports 1,254 positive LMIAs in `Permanent Resident Only` and two
  in `Unspecified` for 2021. Those counts cannot be allocated to quarters.
- The 2023 Q4 rolling release republishes 2022 onward with `Permanent Resident Only`
  included as a fifth quarterly stream.
- The annual source retains a sixth `Unspecified` category. It contains two positive
  LMIAs in 2022 and zero from 2023 through 2025.

For a like-for-like all-stream quarterly line, 2022 Q1 is the earliest defensible
starting point in the recovered data. A chart beginning in 2021 must annotate the
scope break or explicitly filter every period to the four streams common to 2021.

## Reconciliation products

`data/meta/aggregates.reconciliation.json` is the machine-readable audit record.
It contains:

- observed and missing quarterly coverage;
- source file, checksum, sheet, header, row, and period audits;
- every cell that changed across overlapping official releases;
- province/stream annual comparisons;
- annual-only and quarterly-only categories; and
- national annual-versus-quarterly summaries.

The current build records 353 changed cells across overlapping releases. National
four-quarter sums reconcile as follows:

| Year | Quarterly sum | Annual total | Difference | Annual-only positive LMIAs |
| --- | ---: | ---: | ---: | ---: |
| 2021 | 45,928 | 47,139 | -1,211 | 1,256 |
| 2022 | 85,524 | 85,214 | +310 | 2 |
| 2023 | 95,559 | 95,423 | +136 | 0 |
| 2024 | 109,199 | 109,199 | 0 | 0 |
| 2025 | 71,847 | 71,860 | -13 | 0 |

These differences are reported, not repaired. The ledger's
`common_scope_difference` separates changed comparable cells from annual-only scope.

## Downstream use

For a quarterly positive-LMIA chart, use `period` as the x-axis and `positive_lmias`
as the y-axis from `positive-quarterly-national.csv`. Display or translate its
quality flags into annotations. Label the measure “positive LMIAs,” not “approved
positions,” “approved applications,” or “approval rate.”

Use `positive-quarterly.csv` for province or stream breakdowns. Aggregate by
explicit dimension values; do not join it row-for-row to employer records. Use the
annual product for annual reporting and validation, not interpolation.

The tracked aggregate schema is `data/meta/aggregates.schema.json`. Generated CSVs
and raw downloads are ignored by Git; catalogues, schemas, reconciliation ledgers, and
known-defect evidence are tracked so a build can be reviewed and reproduced.

## Bilingual reconciliation and shared translations

### `data/meta/bilingual.reconciliation.json`

This tracked ledger compares all 78 English/French employer release pairs and the
recoverable paired aggregate Table 14 files. Employer comparisons retain distinct
checks for summary totals, province/stream/measure distributions, language-neutral
record dimensions, and employer identity. The checked build has 56 normalized-record
matches, 20 weaker row- or measure-level matches, and two summary-total mismatches.
Those mismatches are the 2016 negative pair and 2022 Q1 positive pair described in
[data-quality.md](data-quality.md).

All 17 paired aggregate comparisons match exactly. The French 2025 Q4 release is not
recoverable and is recorded as unpaired, not assumed equal. The ledger also stores the
literal English and French variants and observation counts used by the translation
registry.

### `data/full/translations.csv`

- Grain: stable translation key.
- Current size: 46 rows.
- Primary key: `translation_key`.
- Languages: `en` and `fr`.

The registry contains recurring provinces and territories, program streams,
incorporation statuses, field labels, measures, decisions, and period-precision
labels. For the 29 recurring source values observed in both languages,
`verification_status` is `observed_in_both_language_sources` and the row includes
per-language counts of nonblank literal source cells plus every literal source
spelling. Forward-filled grouped blanks are not counted as repeated spellings. This
makes source damage such as `Qu bec` reviewable without using it as the display value.

Interface and editorial phrases use `not_a_record_value_check`; their presence is not
evidence that an English/French release pair contains identical records. The literal
English stream value `99` is `unpaired_source_value` and has a blank French value rather
than an invented translation. Join normalized aggregate dimensions using keys such as
`province_territory.ON` and `program_stream.high_wage`.

NOC/CNP titles, definitions, and change descriptions are intentionally absent from
this registry. They are versioned source data and remain in the NOC tables with paired
language provenance. The tracked registry contract is
`data/meta/translations.schema.json`.

## NOC reference data

### `data/full/noc.csv`

- Grain: NOC version × official unit-group code.
- Versions: NOC 2011 (500 groups), NOC 2016 Version 1.3 (500 groups), and NOC 2021
  Version 1.0 (516 groups).
- Primary key: (`noc_version`, `noc_code`).
- Employer-record join: (`noc_version`, `noc_code`).

Each row pairs the official English NOC and French CNP publications. Unit-group titles
and definitions are in `title_en`, `title_fr`, `definition_en`, and `definition_fr`;
each human-readable hierarchy title likewise has explicit `_en` and `_fr` columns.
Codes remain language-neutral. `source_*_en` and `source_*_fr` preserve both page URLs,
download URLs, SHA-256 values, source IDs, and row numbers. The build refuses unequal
English/French code sets or hierarchy codes.

`teer_category` is populated for NOC 2021 from the second digit of the official
five-digit code. It is blank for the four-digit NOC 2011 and NOC 2016 structures.

The current employer build uses NOC 2011 for 304,229 coded rows from 2016 through 2024
Q1 and NOC 2021 for 140,726 coded rows from 2024 Q2 onward. All 961 distinct observed
version/code pairs match the official dimension. Another 23,424 employer records have
no NOC code because the source omitted occupation detail; 19 occupation strings remain
explicitly flagged as unparsed.

### `data/full/noc-crosswalk.csv`

- Grain: source NOC version/code × target NOC 2021 code relationship.
- Direct source: Statistics Canada's 585-row NOC 2016 Version 1.3 to NOC 2021 Version
  1.0 correspondence.
- Composed source: 585 NOC 2011 to NOC 2021 rows produced through unchanged 2011/2016
  unit-group code structure and the official 2016/2021 correspondence.

`mapping_basis` and `is_direct_official_correspondence` distinguish direct from
composed rows. `mapping_cardinality` records `one_to_one`, `one_to_many`,
`many_to_one`, or `many_to_many`. Source/target titles use the paired structure
dimension; GSIM change descriptions and notes use paired `_en` and `_fr` fields from
the two official correspondence files. Provenance is retained separately by language.

The cross-language relationship code pairs are identical in the checked build. One
French correspondence title differs from the French CNP 2021 structure title for code
`44200`; both official wordings are recorded in `noc.reconciliation.json`, while the
structure title remains the dimension and crosswalk label.

The crosswalk has no allocation weights. A source-code count may be mapped directly
only when the analytical method accepts that class-level correspondence. In particular,
a one-to-many relationship does not reveal which target class contains any individual
LMIA record. Preserve the source-version series or show the classification break when
that uncertainty matters.

The tracked contracts are `data/meta/noc.schema.json` and
`data/meta/noc.reconciliation.json`.
