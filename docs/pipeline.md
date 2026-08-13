# Pipeline contract

`lmiacsv` separates discovery, acquisition, inspection, normalization, and publication
so a bad source cannot silently become a clean-looking row.

```text
Open Government JSON-LD catalogues
  -> collision-safe paired English/French resource catalogue
  -> immutable dataset/resource/SHA archive
  -> file, sheet, encoding, format, and header census
  -> schema-specific row adapters
  -> English canonical UTF-8 CSV
  -> bilingual underlying-data reconciliation
  -> shared translations CSV
  -> schemas and reconciliation ledgers
  -> full/min manifests and compact column projections
```

## 1. Catalogue

`lmiacsv catalogue` reads the official positive and negative employer-list JSON-LD
records. Dataset UUID and resource UUID form remote identity. Government filenames are
retained as evidence but never treated as globally unique.

## 2. Fetch

`lmiacsv fetch` validates response hosts and content signatures, calculates SHA-256, and
archives each file below:

```text
data/raw/employer-lists/<dataset UUID>/<resource UUID>/<SHA-256>/<source filename>
```

The manifest records catalogue format, detected format, redirect target, size, and
checksum. Existing downloads are reused only after checksum verification.

## 3. Census

`lmiacsv census` inspects every English and French resource and every workbook sheet.
It records encoding, delimiter, actual format, sheet visibility, title rows, header candidates,
notes boundaries, row estimates, exact headers, and stable schema signatures. It does
not coerce an unknown layout into the latest schema.

## 4. Canonical build

`lmiacsv build` joins catalogue, manifest, and census by resource UUID, verifies the
selected source checksum again, and applies only recognized three-, five-, six-, or
eight-column adapters. Unknown headers, non-integer measures, extra nonempty columns,
missing employers, duplicate record IDs, or input-set disagreement stop the build.

Generated record IDs bind resource UUID, selected-file checksum, sheet, and source row.
Grouped province, stream, employer, and address cells are forward-filled only where the
source layout requires it; the literal blank remains in the corresponding `*_raw` field
and the row receives a quality flag.

The combined CSV is written to a temporary file, flushed and synced, and atomically
replaces the previous output only after every selected resource succeeds.

The employer build deliberately selects English source rows for the canonical output.
The paired French editions remain first-class archived inputs to `bilingual-verify`;
they are not appended as a second copy of the same records.

One narrowly defined source exception also uses the French edition as build evidence.
The English 2022 Q2 positive workbook has requested-style measure headers, while its
official French positive counterpart has approved-style headers. The builder accepts
approved semantics only after verifying both resource identities and checksums and an
exact language-neutral normalized-record multiset and totals match. The English raw
headers remain auditable, every affected row is flagged, and any future disagreement
stops the build. This is an interpretation rule, not a silent source repair. Its full
evidence contract is documented in
[2022-q2-positive-measure-resolution.md](2022-q2-positive-measure-resolution.md).

## 5. Full and min products

The source-specific builders write complete products to `data/full/` and flat audit
metadata to `data/meta/`. The metadata filenames carry their family
(`employers.schema.json`, `aggregates.reconciliation.json`, and so on), so useful
context does not depend on a tower of directories.

`lmiacsv min-build` is the final local stage. It reads only the completed full CSVs,
copies a versioned subset of employer and NOC columns, and refuses unexpected headers,
blank keys, duplicate keys, or row-count drift. The three already-small
`positive-*.csv` aggregate products are copied byte-for-byte so `min/` is a
self-contained consumer tier without a second aggregate contract. The stage then
writes deterministic `manifest.json` files for both ignored product tiers. It
performs no normalization of its own, which makes every min product mechanically
reproducible from its full counterpart.

## 6. Publication boundary

The normalizer publishes source-faithful rows and audit metadata. Classifiers,
rankings, shares, charts, prose, and other editorial interpretations belong downstream.
The sibling `lmiareport` repository reads the canonical CSV and owns those choices.

## Aggregate Table 14 branch

The aggregate branch is deliberately separate from the employer-list branch because
the sources have different grains and completeness rules:

```text
Quarterly and annual statistics JSON-LD
  -> paired current English/French Table 14 identities
  -> generated historical filename probes bound to the quarterly resource UUID
  -> immutable dataset/resource/SHA archive
  -> workbook-layout validation
  -> overlapping-release comparison and newest-release selection
  -> quarterly and annual positive-LMIA CSVs
  -> national arithmetic tabulation and reconciliation ledger
```

`lmiacsv aggregate-catalogue` selects exactly one English and one French Table 14 from
each official quarterly and annual dataset and verifies that all four count positive
LMIAs rather than positions or employers.

`lmiacsv aggregate-fetch` generates historical quarterly filenames from 2019 Q1
forward and probes them only below the official Table 14 dataset/resource UUID. Files
that still exist are archived by checksum. For pre-2022 releases it also generates the
rolling-window forms used by contemporary catalogue titles. HTTP 404/410 responses are
evidence of an unavailable release, not pipeline failures. The currently declared
quarterly and annual resources are mandatory and fail the stage if unavailable.
Recorded 404/410 probes are reused on routine reruns to avoid repeatedly requesting
known-missing objects. `aggregate-fetch --refresh` explicitly rechecks every candidate.

`lmiacsv aggregate-build` detects period columns from workbook headers, normalizes
province and program-stream labels, and retains row-level source provenance. For an
observation repeated across releases, values are compared and the newest release is
selected. Every changed value remains in the reconciliation ledger. A complete set of
four quarters is compared with the separately published annual Table 14; an annual
value is never divided to fill missing quarters. Categories present on only one side
of that comparison are recorded explicitly rather than treated as zero.

The build emits detailed quarterly and annual tables plus a national quarterly
tabulation. The national product carries flags for overlapping-release revisions,
annual mismatches, and positive annual categories absent from the quarterly source.
See [normalized-data.md](normalized-data.md) for the complete product contract and
downstream charting guidance.

## Bilingual reconciliation and translation branch

```text
78 English/French employer release pairs
+ recoverable paired aggregate Table 14 releases
  -> explicit categorical normalization
  -> summary-total comparison
  -> language-neutral measure-distribution comparison
  -> record-dimension and employer-identity comparison
  -> bilingual.reconciliation.json
  -> translations.csv with evidence counts and literal source variants
```

`lmiacsv bilingual-verify` parses both languages through the same source adapters.
Employer identity excludes translated occupation titles, full address prose, raw
labels, and row order, but retains province, stream, employer search key, postal code,
NOC version/code, LMIA count, position count, and incorporation-status key. Its status
ladder distinguishes an exact normalized-record match from a language-neutral core
match, a measure-distribution match, a summary-totals-only match, and a summary-total
mismatch. A high-level match is never used to erase a lower-level disagreement.

Aggregate Table 14 editions are compared at period × province/territory × program
stream × positive-LMIA count. An unrecoverable language edition is recorded as
unpaired rather than inferred from the available file.

`lmiacsv translations-build` converts recurring verified source categories into one
stable-key CSV. It reports per-language observation counts and every literal spelling
encountered, including damaged accents. Shared field and interface labels are marked
`not_a_record_value_check`; they are useful translations, not evidence that two source
files contain identical data. NOC/CNP titles and definitions remain in the versioned
NOC tables.

## NOC reference branch

The NOC branch turns the classification versions named by the employer-list sources
into joinable, versioned reference data:

```text
Official Statistics Canada NOC/CNP pages
  -> discovered paired English/French structure and correspondence CSV URLs
  -> immutable source/SHA archive
  -> per-language parsing and cross-language code/hierarchy validation
  -> bilingual versioned unit-group dimension
  -> direct and composed crosswalk rows with cardinality
  -> correspondence-title disagreement ledger
  -> canonical employer-record join audit
```

`lmiacsv noc-catalogue` scrapes the official Statistics Canada pages rather than
copying download links into a manual manifest. It requires paired English NOC and
French CNP structure CSVs for 2011, 2016 Version 1.3, and 2021 Version 1.0, plus both
official-language editions of the 2016 Version 1.3 to 2021 Version 1.0 correspondence.

`lmiacsv noc-fetch` validates the CSV response, records its encoding, calculates its
SHA-256, and archives it under `data/raw/noc/resources/<source ID>/<SHA-256>/`.

`lmiacsv noc-build` pairs each language on version and code, refuses unequal code sets
or parent hierarchy codes, and emits explicit `*_en` and `*_fr` human-readable fields
and provenance. NOC 2021 TEER is derived from the second digit of the official
five-digit unit-group code. The NOC 2011 to NOC 2021 rows are composed through
same-code 2011/2016 structural continuity and the official 2016/2021 correspondence;
they are labelled as composed rather than direct official rows. One-to-many and
many-to-one relationships remain separate rows.

Correspondence titles are checked against the same-language structure. A mismatch is
recorded in `noc.reconciliation.json`; the unit-group structure title remains the
normalized dimension value, and the published correspondence wording is retained in
the mismatch record.

Finally, the build checks every (`noc_version`, `noc_code`) pair in the canonical
employer CSV against the reference. An unmatched observed code fails the build.
