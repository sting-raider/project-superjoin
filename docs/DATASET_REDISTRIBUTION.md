# Starter dataset redistribution audit

Audit date: 2026-09-08. Auditor: Project SuperJoin implementation record.
The official policy links below were rechecked on the audit date; a current
page being reachable does not itself grant permission to redistribute source
material.

The six starter PDFs are third-party publications. The assignment materials
identify the files and provide official source links, but the repository does
not currently have a blanket license to redistribute the original PDFs,
rendered pages, or copied evidence excerpts. Public availability is not
treated as permission. No source PDFs, page renders, or copied full-page
derivatives are committed to this repository.

| Source family | Official URL | Status | Action |
|---|---|---|---|
| Delhivery prospectus | delhivery.com | not cleared | Keep local; prepare only from a supplied archive or an explicitly permitted source. |
| Delhivery annual report | delhivery.com | not cleared | Keep local; retain attribution and hash when prepared. |
| Delhivery earnings presentation | bseindia.com filing | unresolved | Keep local; do not publish copied slides. |
| Economic Survey | indiabudget.gov.in | not cleared | Keep local; verify government reuse terms before release. |
| RBI Annual Report | rbi.org.in | unresolved | Keep local; verify the applicable RBI copyright notice. |
| IMF Article IV report | imf.org | not cleared | Keep local; verify IMF publication terms and any image restrictions. |

## Official policy checks

These checks are evidence for the audit, not a permission grant. They were
reviewed on 2026-09-08 and intentionally leave the affected sources uncleared:

* **Delhivery.** [Delhivery Terms and Conditions](https://www.delhivery.com/terms-and-conditions)
  states that Delhivery owns or licenses the site content and restricts copying,
  storing, publishing, reproducing, modifying, derivative works, and distribution
  beyond personal non-commercial use without explicit permission. The two
  Delhivery documents therefore remain **not cleared** for repository or demo
  redistribution.
* **Economic Survey.** The current [India Budget Website Policies](https://www.indiabudget.gov.in/website-policies.php)
  page says site contents may not be reproduced partially or fully without
  permission from the Ministry of Finance and requires source acknowledgement.
  The Economic Survey remains **not cleared**.
* **IMF Article IV.** The [IMF Copyright and Usage](https://www.imf.org/en/about/copyright-and-terms)
  policy allows limited personal, non-commercial use under stated conditions,
  but requires written permission for substantial copying or dissemination and
  does not authorize this project's copied evidence, page renders, or recorded
  outputs by default. The report remains **not cleared** pending a source-
  specific permission or compatible license review.
* **BSE filing and RBI report.** No source-specific reuse permission was
  verified during this audit. The official filing/report URLs remain useful for
  local attribution and retrieval, but they do not establish a redistribution
  license. They remain **unresolved** and are not included in tracked demo
  artifacts.

The checked policies do not change the release gate: until a compatible license
or written permission is recorded for every source, do not commit source PDFs,
page renders, copied excerpts, source-text-bearing recorded outputs, or video
frames that expose those materials. A local evaluator may supply the PDFs and
run the pipeline without making them part of the repository or release.

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
