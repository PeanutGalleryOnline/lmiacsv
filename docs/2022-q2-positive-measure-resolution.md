# 2022 Q2 positive measure resolution

## Summary

The English 2022 Q2 positive employer workbook is included in the canonical employer
table. Its measure columns are interpreted as approved LMIAs and approved positions,
despite the English header cells saying `Requested LMIAs` and `Requested Positions`.

This is not a general rule that a positive title overrides requested-style headers.
It is a narrow, fail-closed interpretation supported by the separately published
official French edition of the same positive release. The French workbook labels the
same columns `EIMT Approuvés` and `Postes Approuvés`, and the two files match exactly
after language-dependent labels are removed from the record identity.

## Source evidence

| Role | Resource UUID | Source file | SHA-256 |
| --- | --- | --- | --- |
| English positive release | `dd627095-614a-45df-a7ef-df0a4a46a812` | `tfwp_2022q2_positive_en.xlsx` | `b1bcb07f56569623a6619f483a1c5dccbc05a562ebdddb8286e02000c71051cf` |
| French positive release | `d93b17b3-4c84-45d0-8d4a-b44a54f733e6` | `tfwp_2022q2_positive_fr.xlsx` | `0d688946030febde40b89682b86a3bdb721d0c18109026f521172eb406139d0d` |

Both resources are catalogued as positive decisions for `2022-q2`. The English sheet
is `Positive_EN` and the French sheet is `Positive_FR`. Their normalized comparison
produces:

- 15,167 records in each file;
- 19,214 LMIAs in each file;
- 45,198 positions in each file; and
- an identical multiset of province, program stream, postal code, NOC version and
  code, LMIA count, position count, incorporation-status key, and normalized employer
  identity.

There is also a distinct English 2022 Q2 negative resource,
`f1b6fd7d-8417-4130-bb5f-20e1220c9dec`. It contains 364 records, 386 requested LMIAs,
and 618 requested positions. Its existence and differing contents rule out the theory
that the positive English workbook is merely the negative list under another title.

## Normalization rule

The canonical builder accepts the English positive resource only while all of the
following remain true:

1. the known English and French resource UUIDs each occur exactly once in the
   catalogue, census, and raw manifest;
2. their archived files pass their recorded SHA-256 checks;
3. both resources remain positive releases for `2022-q2` in their declared language;
4. the English headers signal requested measures and the French headers signal
   approved measures; and
5. their language-neutral normalized record multisets and measure totals match
   exactly.

If any condition changes, the build stops. It does not silently fall back to the
positive title, accept a totals-only match, or discard the records.

The source evidence remains visible in the normalized products:

- the resource disposition is `normalized_with_bilingual_measure_override`;
- every affected row carries
  `english_requested_headers_interpreted_as_approved_from_matching_french_release`;
- the literal English headers and both source checksums remain in
  `data/meta/employers.reconciliation.json`; and
- the rule is machine-readable under `interpretation_rules` in
  `data/meta/employers.schema.json`.

The French rows are evidence, not duplicate canonical observations. As elsewhere in
the employer product, the canonical table contains the selected English records once.

## Product impact

The change moves the English positive resource from quarantine into the canonical
table:

| Measure | Before | After |
| --- | ---: | ---: |
| Canonical resources | 77 | 78 |
| Canonical employer records | 468,379 | 483,546 |
| Quarantined resources | 1 | 0 |
| Bilingual measure overrides | 0 | 1 |

The added records contribute 19,214 approved LMIAs and 45,198 approved positions for
2022 Q2. Full and min employer products both contain 483,546 rows after regeneration.

This does not create an application approval rate. Employer-list rows are not
application-level observations, and the positive and negative publications still do
not supply a complete common-denominator national decision table.

## Verification

The completed build was checked by:

- rebuilding with `lmiacsv build --fail-on-quarantine`;
- reconciling all 78 English/French employer-release pairs;
- rebuilding the NOC join audit with all observed LMIA NOC codes matched;
- rebuilding translations and the deterministic full/min manifests;
- verifying the full and min employer-file checksums against those manifests;
- checking all 15,167 affected canonical rows for the positive decision, approved
  measure labels, source disposition, and row quality flag;
- confirming the affected-row totals of 19,214 LMIAs and 45,198 positions;
- inspecting a representative 47-column CSV slice through the spreadsheet engine;
- running all 59 tests; and
- running Ruff and `git diff --check` successfully.

The synthetic unit tests also alter the French measure values and confirm that the
bilingual interpretation then fails closed.
