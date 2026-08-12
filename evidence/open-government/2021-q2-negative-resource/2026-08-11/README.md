# 2021 Q2 negative LMIA resource receipts

Collected at: `2026-08-12T06:10:43+00:00`

This immutable bundle preserves the evidence for a linkage error in the Open
Government English 2021 Q2 negative LMIA employer resource.

## Finding

The English 2021 Q2 resource serves a byte-for-byte copy of the 2020 Q2 CSV. The
downloaded CSV's own title identifies April–June 2020. Matching English and French
2021 Q2 XLSX workbooks remain available on official ESDC infrastructure.

The recovered workbooks contain 498 data rows and
850 requested positions. Employer names, addresses,
NOC codes, and requested-position counts match between the English and French
workbooks on every row.

## Contents

- `sources/`: the two portal CSV downloads and two recovered ESDC workbooks.
- `pages/`: dated HTML snapshots of the affected and comparison resource pages.
- `catalogue/`: the machine-readable negative-employer-list JSON-LD snapshot.
- `receipts.json`: requested/final URLs, selected response headers, sizes, and hashes.
- `verification.json`: independent CSV, workbook, duplicate, and bilingual checks.
- `SHA256SUMS`: checksums for every downloaded source asset.

Final URLs and response headers are sanitized so temporary signed-query parameters
are not persisted. The recovered English URL was inferred from the catalogued French
workbook's official ESDC URL and then validated against that French workbook.
