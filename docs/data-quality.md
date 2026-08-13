# Known source-quality conditions

The reconciliation ledger is the authoritative machine-readable account. This page
summarizes the conditions that materially affect interpretation.

## 2021 Q2 negative English resource is mislinked

The Open Government resource catalogued as 2021 Q2 negative English serves a file that
is byte-for-byte identical to the 2020 Q2 negative resource and identifies itself
internally as April-June 2020.

The build quarantines that catalogue blob and selects the separately available official
ESDC English workbook only after matching its pinned SHA-256. The dated evidence bundle
also retains the official French workbook and verifies that all 498 employer, address,
NOC, and position rows agree across languages.

## 2022 Q2 positive English headers are resolved by the paired French release

The English resource title and sheet identify a positive list, but its final columns
are `Requested LMIAs` and `Requested Positions`. Its separately published official
French positive workbook instead labels those columns `EIMT Approuvés` and `Postes
Approuvés`. The two editions contain the same 15,167 language-neutral normalized
records and the same totals: 19,214 LMIAs and 45,198 positions.

That bilingual symmetry is enough to resolve the measure semantics without rewriting
the source. The English rows enter the canonical table as positive decisions with
`approved_lmias` and `approved_positions`; the literal English headers remain in the
reconciliation ledger, and every row carries
`english_requested_headers_interpreted_as_approved_from_matching_french_release`.
The exception is deliberately fail-closed: it is tied to the two known resource UUIDs,
checksums, period, decision, language, opposing header signals, exact normalized-record
multiset, and totals. If any of that evidence changes, the build stops rather than
guessing. See
[2022-q2-positive-measure-resolution.md](2022-q2-positive-measure-resolution.md) for
the complete source identities, product impact, and verification record.

## Catalogue packaging does not always match content

Several resources declared as XLS are actually XLSX containers. One resource declared
as XLSX is CSV. These mismatches are preserved as source-level quality flags; content is
parsed according to its validated signature.

## Historical layouts use grouping

The 2014 and 2015 CSVs place province headings above repeated three-column tables.
Later files sometimes leave province, stream, employer, or address cells blank to mean
"same as above." The canonical dataset retains raw blanks and flags each forward fill.

## English and French employer files are not presumed identical

The pipeline archives and parses both official-language editions of every employer
release. It does not accept matching release titles or equal summary totals as proof
that the underlying rows match.

In the checked 78-pair build:

- 56 pairs match at the normalized employer-record level;
- 8 more match after employer spelling is removed from the language-neutral identity;
- 7 more match only at the province/stream/measure-distribution level;
- 5 match only in release-level row, LMIA, and position totals; and
- 2 have different release-level totals.

The two summary-level disagreements are material:

- The 2016 negative English file contains 3,932 rows and 7,377 requested positions;
  the French file contains 3,662 rows and 6,741 positions.
- The 2022 Q1 positive French file contains one extra record: 10,513 rows, 44,169
  approved positions, and 13,773 LMIAs versus 10,512 rows, 44,167 positions, and
  13,772 LMIAs in English. The extra French observation is a Quebec primary-
  agriculture record for `9114-1911 Quebec Inc. / Bio-Oeufs`, NOC 8431, one LMIA and
  two positions.

Other equal-total pairs still contain genuine field-level differences. For example,
many French 2016 occupation values omit the NOC code present in English. Employer
names can differ because one edition preserves accents while the other contains
encoding loss. These conditions remain row-level mismatches in
`data/meta/bilingual.reconciliation.json`; they are not “fixed” by translation.

The French files also contain damaged labels such as `Qu bec`, `Nouvelle- cosse`, and
`le-du-Prince- douard`. The verifier recognizes these only through explicit aliases,
retains every literal spelling as translation evidence, and emits a clean display
value separately. One English 2025 Q1 negative record contains the literal program
stream value `99` with no corresponding French value. `translations.csv` preserves it
without inventing a translation.

## Period and population scope changes

The earliest releases are annual or partial-year, and 2017 Q1-Q2 is a combined period.
They remain unsplit. From 2018 Q1 through 2023 Q3 the employer lists exclude LMIAs used
only to support permanent-residence applications; those records are included from 2023
Q4 onward. `comparability_regime` records this boundary.

## Measure limits

The lists publish employer/occupation rows and positions, not one row per application.
LMIA counts appear only in newer layouts. Therefore neither row counts nor position
counts can honestly be presented as an LMIA application approval or denial rate.

## Aggregate quarterly history is not presented as an archive

The aggregate statistics dataset began with a window covering 2018 Q1 onward, but its
catalogue record is continually rewritten to show only the four quarters of the prior
calendar year and the available quarters of the current year. Resource UUIDs are
reused while filenames and workbook contents change.

`aggregate-fetch` probes generated historical filenames beneath the official Table 14
resource UUID and preserves every surviving workbook. This includes both the newer
release-quarter filenames and the rolling-window filename forms used in contemporary
dataset titles before 2022. A missing workbook remains a missing quarter in the
published reconciliation ledger. The annual Table 14 series, which currently starts
in 2018, is retained as a separate source and is not used to estimate quarterly
values.

The surviving quarterly releases begin at 2022 Q1, and that release contains a rolling
window beginning at 2021 Q1. The presently recoverable quarterly series is therefore
2021 Q1 onward. The annual source proves that aggregate observations exist from 2018,
but it cannot restore the missing 2018-2020 quarterly distribution.

## Quarterly and annual aggregate scopes differ

The quarterly Table 14 releases recovered for 2021 contain four streams and omit the
`Permanent Resident Only` category. The annual Table 14 reports 1,254 positive LMIAs
in that category for 2021, plus two `Unspecified` observations. Starting with the
2023 Q4 release, the rolling quarterly source republishes 2022 onward with a fifth
`Permanent Resident Only` stream. The annual source has a sixth `Unspecified` category,
which has two positive LMIAs in 2022 and zero from 2023 through 2025.

The reconciliation ledger records these annual-only categories as
`missing_quarterly_observation`; it does not quietly treat them as zero. Consequently,
the national quarterly total is a sum of the categories actually published in the
quarterly source, not a reconstructed annual-scope total.

## Paired aggregate Table 14 data match, with one archive gap

The checked archive contains 17 paired aggregate comparisons: 16 quarterly releases
from 2022 Q1 through 2026 Q1 plus the annual workbook. Every pair matches exactly at
period × province/territory × program stream × positive-LMIA count after categorical
translation normalization.

The official English 2025 Q4 quarterly release is recoverable but the corresponding
French release filename is not. That release remains explicitly unpaired. This is an
archive gap, not a bilingual match or mismatch; the later paired 2026 Q1 rolling
workbooks still contain and verify the underlying 2025 Q4 observations.

## Aggregate sources still do not provide a national decision rate

Quarterly and annual Table 14 publish positive LMIA counts. The statistics family does
not publish complete negative LMIA counts across all program streams. Table 12 counts
requested positions, and Table 25 contains positive and negative decisions only for
the Seasonal Agricultural Worker Program. Neither is a valid national denominator.

See [normalized-data.md](normalized-data.md) for the resulting normalized files,
quality-flag meanings, reconciliation summary, and safe downstream uses.

## Employer-list NOC versions come from source metadata

Four-digit code width does not distinguish NOC 2011 from NOC 2016. The official LMIA
employer-resource titles identify NOC 2011 from the first occupation-bearing 2016
release through 2024 Q1, then NOC 2021 from 2024 Q2 onward. The canonical normalizer
uses that explicit metadata and validates it against the four- or five-digit code
width. It does not infer NOC 2016 from the calendar year.

NOC 2016 Version 1.3 is retained in the reference data because it is the source side
of Statistics Canada's official correspondence to NOC 2021. It is not assigned to an
LMIA row whose government metadata says NOC 2011.

## NOC correspondence is not a record-level recode

The official correspondence contains splits, mergers, transfers, and other real or
virtual changes. The normalized crosswalk therefore has one row per class relationship
and records whether it is one-to-one, one-to-many, many-to-one, or many-to-many. It
does not create weights. Counts attached to a source code cannot be distributed among
multiple target codes without additional evidence.

## Official English/French NOC files are paired, not translated locally

Statistics Canada publishes separate English NOC and French CNP structures and
correspondence CSVs. The pipeline archives both, pairs rows by version and code, and
requires identical unit-group code sets and parent hierarchy codes. It never generates
one language by machine-translating the other.

The checked build found one wording disagreement between two official French files.
For target code `44200`, the CNP 2021 structure says “Combattants de première ligne des
Forces armées canadiennes,” while the French 2016-to-2021 correspondence says
“Combattants/combattantes de première ligne des Forces armées canadiennes.” The
normalized dimension uses the structure title. Both wordings, their codes, language,
and relationship are retained in `data/meta/noc.reconciliation.json` under
`correspondence_title_mismatches`; the discrepancy is not silently erased.
