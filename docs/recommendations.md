# Recommendations for less heroic public data

This project began with a fairly modest request: download the public LMIA data, put it
in rows, and make some charts. It became an archaeological exercise involving rolling
workbooks, filename divination, bilingual reconciliation, format detection, checksum
receipts, a positive English file whose French twin supplied the missing semantic
clue, and one resource that quietly travelled backward in time.

None of this requires a grand new portal. Most of it requires treating a statistical
release as a durable public record rather than a spreadsheet-shaped announcement.

The recommendations below are offered in that spirit. They are wry because the
alternative is screaming, but they are not cynical. Large parts of the system worked,
and those successes point directly to a better publishing model.

## First, preserve what is already working

### Dataset and resource UUIDs are genuinely useful

Open Government dataset and resource UUIDs gave the files stable remote identities
even when filenames collided, changed, or proved too generic to identify anything.
The JSON-LD catalogue was machine-readable enough to build a reproducible scraper,
and resource-bound download URLs made conservative historical discovery possible.

Keep the UUIDs. Make them more visible in manifests and documentation. They solve a
real problem that filenames such as `positive_employers_en.csv` never will.

### Much of the bilingual publication process is sound

The bilingual data should not be judged only by its exceptions. Of 78 paired employer
releases, 76 have matching release-level row, LMIA, and position totals. Fifty-six
pairs match at the normalized employer-record level. All 17 recoverable English/French
aggregate Table 14 comparisons match exactly at period × province/territory × program
stream × positive-LMIA count.

That is strong evidence of an underlying bilingual production regimen, not two people
independently saving whatever happened to be open in Excel. The answer is to automate
and publish the comparison, not to replace a process that usually works.

### Separate annual totals are valuable

The independently published annual Table 14 is useful. It exposes revisions, category
differences, and scope changes that would otherwise be invisible in the rolling
quarterly workbook. Independent totals are not redundant; they are controls.

Keep publishing them, but also publish the reconciliation that the existence of two
official tabulations naturally invites.

### The NOC/CNP reference data are close to the right model

Statistics Canada's paired English NOC and French CNP structures provide stable codes,
versioned classifications, hierarchy, definitions, and official correspondence files.
The English and French code sets and hierarchy codes reconcile. The correspondence
also makes classification change explicit instead of pretending that an occupation
code is timeless.

There is one recorded French wording disagreement between the structure and
correspondence files. That is not a failure of the model; it is exactly the sort of
small discrepancy a versioned, coded reference system allows users to identify.

### The employer lists contain unusually useful detail

Employer, address, occupation, NOC code, province, program stream, incorporation
status, LMIA count where available, and position count make many legitimate analyses
possible. The source rows are valuable. The difficulty lies mostly in packaging,
definitions, and change management—not in an absence of public data.

## Publish releases, not moving targets

The quarterly statistics catalogue behaves like a shop window: the current workbook
replaces the old one, while the resource UUID remains the same. A shop window is a
reasonable way to show what is new. It is not an archive.

Every release should remain available at an immutable URL. A minimal release record
should include:

- dataset UUID and resource UUID;
- release ID and publication timestamp;
- reporting period and period precision;
- language;
- decision scope and population scope;
- analytical grain and measure unit;
- filename, media type, byte size, and SHA-256;
- schema version;
- whether the release supersedes an earlier release; and
- a link to a revision record.

If a workbook for 2025 Q4 was published, both official-language editions should remain
retrievable after 2026 Q1 arrives. Consumers should not need to reconstruct old
filenames from surviving naming conventions and ask the server whether history still
exists there.

## Make filenames useful, even though UUIDs remain authoritative

Filenames are not identity, but humans download files and then put them in folders.
Repeated names such as `positive_employers_en.csv` guarantee collisions. The presence
of a good UUID elsewhere does not stop Finder from adding “(7)”.

A filename should contain, at minimum, the dataset family, period, decision, language,
and schema or release version. For example:

```text
tfwp_employer_list_2025_q4_positive_en_v1.csv
tfwp_table14_2025_q4_positive_lmias_fr_v1.csv
```

This is not a substitute for UUIDs and checksums. It is a courtesy to everyone who has
ever had a `Downloads` folder.

## Treat bilingual symmetry as a release condition

Official-language files should be generated from one language-neutral fact table,
with labels applied at export. Before publication, compare the two outputs after
mapping labels back to stable keys. Publish the result with the release.

The current archive shows why this matters:

- The 2016 negative English list contains 3,932 rows and 7,377 requested positions;
  the French list contains 3,662 rows and 6,741 positions.
- The 2022 Q1 positive French list contains one extra record, one extra LMIA, and two
  extra positions.
- The English 2025 Q4 aggregate workbook is recoverable while its French release is
  not, although the later rolling bilingual release confirms the underlying quarter.
- Several French values have damaged accents, including forms equivalent to
  `Qu bec`, `Nouvelle- cosse`, and `le-du-Prince- douard`.

These are different kinds of failure: tabulation, release completeness, and encoding.
They should not share a single green or red “bilingual” status.

At minimum, bilingual QA should report:

1. both files exist;
2. both parse against the declared schema;
3. dimension keys match;
4. row and measure totals match;
5. language-neutral record multisets match; and
6. all localized labels exist in the approved translation table.

The encouraging news is that the aggregate files passed this test 17 times out of 17.
The process is plainly capable of producing symmetric data. It should prove that it
did so on every release.

## Admit where tabulation is asymmetric

Not all asymmetry is an error. Undocumented asymmetry is the error.

The present publications vary across several axes:

- positive versus negative decisions;
- LMIAs versus positions;
- quarterly versus annual periods;
- employer-detail tables versus aggregate tables;
- four-stream, five-stream, and six-category scopes;
- English versus French source fields; and
- older rows without LMIA counts versus newer rows with both LMIA and position counts.

For example, quarterly Table 14 publishes positive LMIAs, but no equivalent complete
all-stream negative table supplies the other side of a national decision rate. Table
12 counts requested positions, which is a different unit. Table 25 has positive and
negative decisions, but only for the Seasonal Agricultural Worker Program. Those
tables are adjacent, not interchangeable.

Likewise, the 2021 quarterly Table 14 omits `Permanent Resident Only`, while the annual
table reports 1,254 positive LMIAs in that category and two `Unspecified`
observations. Later quarterly releases add the permanent-resident-only stream, while
the annual source retains `Unspecified` as an additional category.

Each table should therefore declare, in machine-readable fields:

- `measure`;
- `unit`;
- `decision_scope`;
- `population_scope`;
- `program_stream_scope`;
- `period_basis`;
- `period_precision`;
- `geographic_scope`; and
- known comparability boundaries.

If annual and quarterly tables are intentionally different, say so in the data, not
only in prose. Better still, publish a scope matrix showing which dimensions and
categories exist in each product and period.

## Publish the denominator—or say plainly that it does not exist

The most obvious public question is: what percentage of LMIA applications are
approved or denied by quarter?

The currently published data cannot answer it nationally. Employer-list rows are not
applications. Positions are not applications. Positive LMIAs are not approved
positions. A program-specific positive/negative table is not an all-program national
rate. Dividing whichever two numbers happen to be nearby would produce a percentage,
but not knowledge.

If this question is intended to be answerable, publish a quarterly decision table with
one stable grain and complete mutually exclusive outcomes across all in-scope program
streams. It should distinguish at least:

- applications received;
- applications decided;
- positive decisions;
- negative decisions;
- withdrawn or cancelled applications;
- decisions still pending; and
- the treatment of reconsiderations and revised decisions.

If operational or disclosure constraints prevent that publication, add a prominent
machine-readable non-claim: `national_approval_rate_supported: false`, with the reason.
That would save many analysts from manufacturing a denominator out of optimism.

## Prefer tidy UTF-8 data to presentation-shaped spreadsheets

The source workbooks frequently encode visual grouping by leaving cells blank to mean
“same as above,” repeating headers under province headings, or placing notes inside the
data rectangle. This is legible to a patient human and ambiguous to software—which is
an unfortunate property for open data.

Publish a tidy UTF-8 CSV (or Parquet) as the canonical machine-readable product:

- one header row;
- one observation per row;
- no merged cells;
- no implied values through blank-cell grouping;
- stable column names;
- explicit nulls;
- unformatted numeric measures;
- ISO-like period keys such as `2025Q4`; and
- notes and methodology in separate metadata.

An accessible, styled XLSX may be published alongside it. The spreadsheet should be a
view of the data, not the only surviving expression of the data model.

All text exports should be UTF-8. French accents should survive contact with the CSV
format; this is a solved problem and should be allowed to enjoy retirement.

## Make format metadata tell the truth

Some resources declared as XLS are XLSX containers. One declared XLSX resource is
CSV. A consumer should not need file-signature detection to learn what was downloaded.

Validate the actual response before publishing catalogue metadata. Record both the
media type and the serialization. If the portal displays “Validation status: Invalid
data,” it should also display the failed rule, affected field or row, validation time,
validator version, and whether publication was intentionally allowed despite the
failure. “Invalid data” without an explanation is less a diagnosis than a mood.

## Make corrections first-class public data

The 2021 Q2 negative English resource points to a file that is byte-for-byte identical
to 2020 Q2 and identifies itself internally as April–June 2020. A correct official
2021 Q2 workbook exists elsewhere. The 2022 Q2 positive English employer list
identifies itself as positive but labels its measures `Requested LMIAs` and `Requested
Positions`; its paired French positive release labels the same, exactly matching
records and totals as approved. Here bilingual publication worked as a forensic
control. It should have been a pre-publication one.

These conditions deserve more than silent replacement. Publish a correction ledger
with:

- affected dataset, resource, release, and language IDs;
- issue type and plain-language description;
- date detected and date corrected;
- old and new checksums;
- whether the corrected release changes rows or totals;
- replacement URL; and
- contact or ticket reference.

Keep superseded files accessible and visibly marked. Reproducibility requires knowing
what the government said then as well as what it says now.

## Publish revisions as revisions

Rolling aggregate workbooks revise earlier observations. This can be legitimate and
useful. It should not be discoverable only by retaining old files and comparing every
cell.

For each release, publish a compact revision table:

```text
period,province_territory,program_stream,measure,old_value,new_value,reason
```

Also publish whether a historical value is preliminary or final. A revision log turns
an apparent contradiction into documented statistical maintenance.

## Give every category a stable key and every classification a version

Display labels are not identifiers. `High Wage`, `High-Wage`, and `Haut salaire`
should resolve to one program-stream key. Provinces should have stable codes.
Incorporation statuses should come from a controlled bilingual vocabulary. Literal
source values should still be retained for audit.

NOC already demonstrates the right instinct: version plus code is the key, and
cross-version relationships are explicit. Apply the same discipline to program
streams, measures, decision statuses, incorporation statuses, and quality flags.

Do not assign a French label to a mystery value merely because a bilingual column
looks tidier. The observed program-stream value `99` is more honestly published as an
unresolved code than translated by séance.

## Ship a small, complete release package

A high-quality release does not need to be elaborate. The following package would
eliminate most downstream heroics:

```text
manifest.json
data_en.csv
data_fr.csv
schema.json
translations.csv
quality-report.json
revisions.csv
README.md
```

The manifest should checksum every file. The quality report should contain row counts,
measure totals, bilingual reconciliation results, schema-validation results, and any
known exceptions. The README should define the grain, measures, population, period
basis, and non-claims in plain language.

Finally, test the published URLs from outside the departmental environment after the
release goes live. A file that passed QA on a shared drive but redirects to last
year's CSV in public is, from the public's perspective, last year's CSV.

## A reasonable standard

Public data need not be perfect. It should be identifiable, retrievable, versioned,
defined, internally checked, and honest about its limits.

The current LMIA publications already contain the hard part: valuable underlying data,
stable catalogue identities, official bilingual editions, independent annual checks,
and strong classification references. The remaining work is mostly disciplined
publication engineering.

That is encouraging. It means improving access does not require inventing a new data
strategy. It requires ensuring that the file called 2021 Q2 contains 2021 Q2, that the
French and English totals belong to the same fact table, that a quarterly series keeps
its quarters, and that a positive LMIA is not asked to moonlight as an application,
position, worker, work permit, or denominator.

The sausage may remain complicated. The ingredient list should not be.
