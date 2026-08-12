# Pipeline contract

`lmiacsv` separates discovery, acquisition, inspection, normalization, and publication
so a bad source cannot silently become a clean-looking row.

```text
Open Government JSON-LD catalogues
  -> collision-safe resource catalogue
  -> immutable dataset/resource/SHA archive
  -> file, sheet, encoding, format, and header census
  -> schema-specific row adapters
  -> canonical UTF-8 CSV
  -> schema and reconciliation ledger
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

`lmiacsv census` inspects every English resource and every workbook sheet. It records
encoding, delimiter, actual format, sheet visibility, title rows, header candidates,
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

## 5. Publication boundary

The normalizer publishes source-faithful rows and audit metadata. Classifiers,
rankings, shares, charts, prose, and other editorial interpretations belong downstream.
The sibling `lmiareport` repository reads the canonical CSV and owns those choices.
