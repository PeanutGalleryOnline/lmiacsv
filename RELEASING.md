# Release process

A release is a versioned claim that a particular code revision reproduces particular
normalized data from particular source records. Publishing a tag is therefore the end
of review, not the beginning of it.

## 1. Prepare the source snapshot deliberately

Refresh catalogues only in an ordinary reviewed commit. Inspect every changed dataset
or resource identity, source timestamp, coverage boundary, schema, reconciliation,
and quality flag. Source refreshes must not be hidden inside the release workflow.

Run the documented pipeline locally, including the strict employer build:

```bash
lmiacsv build --fail-on-quarantine
lmiacsv release-verify --require-products
```

Commit the resulting tracked metadata and manifests. Generated CSVs remain ignored;
they are release artifacts rather than source-control objects.

## 2. Pass the offline gate

The `CI` workflow runs on Python 3.11 through 3.14. It runs all unit and contract tests,
Ruff, JSON parsing, evidence checksum verification, a Python package build, and checks
that the distributions contain the Apache licence and third-party notices.

Do not tag a revision whose required checks are failing or pending.

## 3. Reproduce a candidate

Run the `Release candidate` workflow manually before tagging. It downloads resources
identified by the committed catalogues without refreshing those catalogues, rebuilds
all products, fails on quarantines, verifies every product against its manifest, and
requires all regenerated tracked metadata and manifests to match the commit.

An upstream resource that has changed in place will therefore fail the candidate. It
must be investigated and represented by a separate, reviewed source-update commit;
the release workflow must not bless the drift automatically.

The workflow retains deterministic full and compact data archives, Python
distributions, `RELEASE_PROVENANCE.json`, and `SHA256SUMS` for 14 days.

## 4. Review the candidate independently

At least one reviewer other than the person preparing the release should:

- verify `SHA256SUMS` after downloading every candidate artifact;
- confirm the candidate revision and the proposed tag;
- review changes to schemas, reconciliations, quality flags, and documented non-claims;
- inspect every correction, interpretation override, and comparability boundary;
- reproduce a sample of row counts, totals, joins, and source links independently;
- confirm that no unresolved quarantine exists; and
- confirm that `NOTICE` and `DATA_LICENSES.md` accompany both data archives.

For politically salient findings, the reviewer should try to construct the strongest
plausible but invalid interpretation and confirm that the product contract and public
documentation reject it clearly.

## 5. Tag and publish

The tag must be `v` followed by the exact version in `pyproject.toml`, preferably as a
signed annotated tag. Pushing it reruns the entire candidate process and creates an
unpublished draft GitHub Release. The workflow never publishes a release directly.

Before manually publishing the draft:

- compare its checksums with the independently reviewed candidate;
- read the generated release notes for overstatement or missing corrections;
- state the source coverage window and material known limitations; and
- link `docs/data-quality.md`, `docs/normalized-data.md`, and `DATA_LICENSES.md`.

If any artifact, code, metadata, or release note changes, create a new commit and
candidate. Do not replace an asset silently after review.
