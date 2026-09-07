# Starter dataset redistribution audit

Audit date: 2026-09-07. Auditor: Project SuperJoin implementation record.

The six starter PDFs are third-party publications. The assignment materials
identify the files and provide official source links, but the repository does
not currently have a blanket license to redistribute the original PDFs,
rendered pages, or copied evidence excerpts. Public availability is not
treated as permission. No source PDFs, page renders, or copied full-page
derivatives are committed to this repository.

| Source family | Official URL | Status | Action |
|---|---|---|---|
| Delhivery prospectus | delhivery.com | unresolved | Keep local; prepare only from a supplied archive or an explicitly permitted source. |
| Delhivery annual report | delhivery.com | unresolved | Keep local; retain attribution and hash when prepared. |
| Delhivery earnings presentation | bseindia.com filing | unresolved | Keep local; do not publish copied slides. |
| Economic Survey | indiabudget.gov.in | unresolved | Keep local; verify government reuse terms before release. |
| RBI Annual Report | rbi.org.in | unresolved | Keep local; verify the applicable RBI copyright notice. |
| IMF Article IV report | imf.org | unresolved | Keep local; verify IMF publication terms and any image restrictions. |

The tracked `datasets/starter/manifest.json` is provenance metadata only. It
does not claim that hashes or retained pages have been verified. Run
`scripts/prepare_dataset.py` against a locally supplied archive to compute
hashes and page counts without silently substituting sources. Any future
release containing source or derivative material must update this audit with
the exact permission basis, checked date, hashes, attribution, and an
allowlist review.

Recorded demo claims are limited to the compact, source-linked evidence needed
for the assignment cases. They are marked as recorded demo data in the UI and
must not be represented as a redistribution of the underlying publications.
