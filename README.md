# The LMIA Record

Working title for a Peanut Gallery data publication that makes Canada's published
Labour Market Impact Assessment decision lists searchable, sourced, and legible.

This workspace is intentionally isolated. It does not require changes to the
Peanut Gallery root workspace, shared component library, site registry, or deploy
scripts while the product and data contract are being proven.

## Current vertical slice

- Inventories the legacy `lmiacrunch` CSV collection without modifying it.
- Pins the official English 2025 Q1 positive and negative workbooks by URL and
  SHA-256 checksum.
- Normalizes 20,586 workbook rows into auditable canonical records with stable IDs
  and source-row provenance.
- Publishes a verified Q1 aggregate and compact employer search index while keeping
  positive and negative decision measures separate.
- Produces a release catalogue with checksums, detected periods, statuses, columns,
  and source row counts.
- Publishes a small Astro site using Peanut Gallery's existing visual language.
- Makes unresolved provenance and duplicate-source work visible instead of treating
  the legacy dataset as publication-ready.

## Commands

```bash
# Inventory the legacy source directory
python3 -m processor.inventory /Users/koop/Vibe/lmiacrunch/data/opengov

# Run deterministic importer tests
python3 -m unittest discover -s processor/tests

# Generate the verified 2025 Q1 pilot from ignored official downloads
python3 -m processor.pilot_2025q1 data/raw/2025q1

# Build the site (dependencies are currently available from the parent workspace)
npm run build
```

## Data layers

```text
data/raw/         immutable downloaded source files (not tracked yet)
data/normalized/  canonical audit records (generated CSV is not tracked)
data/published/   compact aggregates consumed by Astro
content/releases/ source catalogue and publication provenance
```

The legacy inventory is evidence, not the final normalized dataset. A release is
not publication-ready until it has an authoritative government URL, an archived
checksum, an explicit sheet, and a resolved relationship to any duplicate files.
