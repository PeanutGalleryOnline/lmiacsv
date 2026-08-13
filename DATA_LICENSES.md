# Data licences and third-party material

This file identifies the licensing boundary between work authored for `lmiacsv` and
material obtained from public sources. It is an attribution and provenance record, not
a substitute for the source licences.

## Licensing boundary

The [Apache License 2.0](LICENSE) applies to the project's original software,
documentation, tests, schemas, selection and arrangement, and other original material.
It does not replace or override a licence that applies to source data or other
third-party material.

The generated files under `data/full/` and `data/min/` and the provenance records
under `data/meta/` are mixed works. The project's original transformation code,
schemas, field organization, quality annotations, and original metadata are available
under Apache-2.0. Source information embodied in those files remains subject to the
applicable source licence. No additional licence is asserted over underlying facts.

Material under `evidence/` preserves source pages, catalogue records, and files for
reproducibility. The project does not claim ownership of that source material and does
not grant rights in third-party content that its source licence excludes.

## Employment and Social Development Canada data

The employer lists, LMIA statistics, catalogue metadata, and source-derived portions
of the normalized products originate with Employment and Social Development Canada
(ESDC) and were obtained through the Government of Canada's Open Government Portal.
They are used under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada),
subject to any different terms stated on a particular source record.

Attribution:

> Contains information licensed under the Open Government Licence – Canada.

The principal source datasets are:

| Dataset | Open Government record | Repository source record |
| --- | --- | --- |
| Positive LMIA employer lists | [90fed587-1364-4f33-a9ee-208181dc0b97](https://open.canada.ca/data/en/dataset/90fed587-1364-4f33-a9ee-208181dc0b97) | `data/meta/employers.catalogue.json` |
| Negative LMIA employer lists | [f82f66f2-a22b-4511-bccf-e1d74db39ae5](https://open.canada.ca/data/en/dataset/f82f66f2-a22b-4511-bccf-e1d74db39ae5) | `data/meta/employers.catalogue.json` |
| LMIA statistics, current rolling release | [e8745429-21e7-4a73-b3f5-90a779b78d1e](https://open.canada.ca/data/en/dataset/e8745429-21e7-4a73-b3f5-90a779b78d1e) | `data/meta/statistics.catalogue.json` and `data/meta/aggregates.catalogue.json` |
| LMIA statistics, 2018–2025 release | [76defa14-473e-41e2-abfa-60021c4d934b](https://open.canada.ca/data/en/dataset/76defa14-473e-41e2-abfa-60021c4d934b) | `data/meta/aggregates.catalogue.json` |

The machine-readable records named above preserve exact resource identifiers,
versions, source URLs, and checksums. The dated receipts under `evidence/` preserve the
retrieval context for the documented 2021 Q2 source defect.

The Open Government Licence excludes some material, including personal information,
third-party rights, and official symbols, insignia, and logos. Nothing in this
repository grants permission to use excluded material.

## Statistics Canada NOC/CNP data

The NOC/CNP structures, titles, definitions, hierarchy, and correspondence data used
by the NOC products originate with Statistics Canada and are used under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence).

Attribution for the adapted products:

> Adapted from Statistics Canada, National Occupational Classification (NOC) /
> Classification nationale des professions (CNP) structures for reference years 2011,
> 2016, and 2021, and related correspondence tables. This does not constitute an
> endorsement by Statistics Canada of this product.

`data/meta/noc.catalogue.json` identifies every official English and French source
page, download, product version, and archived checksum. The affected generated
products include `data/full/noc.csv`, `data/full/noc-crosswalk.csv`, their compact
projections, and the source-derived portions of the corresponding metadata files.

## Independence and non-endorsement

`lmiacsv` is an independent project. It is not affiliated with or endorsed by the
Government of Canada, ESDC, or Statistics Canada. Source names are used only to
identify provenance. Government names, official marks, and logos are not licensed for
promotional use by this repository.

Downstream distributors should preserve [NOTICE](NOTICE), this file, source links, and
the provenance columns and records relevant to the data they redistribute.
