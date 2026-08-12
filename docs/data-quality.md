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

## 2022 Q2 positive resource has negative-style measures

The resource title and sheet identify a positive list, but its final columns are
`Requested LMIAs` and `Requested Positions`. `lmiacsv` does not relabel those columns as
approved. The entire 15,167-row resource remains quarantined and contributes zero
canonical records until an authoritative correction or explanation is available.

## Catalogue packaging does not always match content

Several resources declared as XLS are actually XLSX containers. One resource declared
as XLSX is CSV. These mismatches are preserved as source-level quality flags; content is
parsed according to its validated signature.

## Historical layouts use grouping

The 2014 and 2015 CSVs place province headings above repeated three-column tables.
Later files sometimes leave province, stream, employer, or address cells blank to mean
"same as above." The canonical dataset retains raw blanks and flags each forward fill.

## Period and population scope changes

The earliest releases are annual or partial-year, and 2017 Q1-Q2 is a combined period.
They remain unsplit. From 2018 Q1 through 2023 Q3 the employer lists exclude LMIAs used
only to support permanent-residence applications; those records are included from 2023
Q4 onward. `comparability_regime` records this boundary.

## Measure limits

The lists publish employer/occupation rows and positions, not one row per application.
LMIA counts appear only in newer layouts. Therefore neither row counts nor position
counts can honestly be presented as an LMIA application approval or denial rate.
