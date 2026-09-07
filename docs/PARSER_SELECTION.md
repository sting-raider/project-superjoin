# Parser selection record

The runtime primary parser is currently `pdfplumber` with a stable page,
word-geometry, and quality-flag contract. `pypdfium2` is retained only for
bounded rendering fallback work. PyMuPDF is a comparison candidate and is not
a runtime dependency because its AGPL/commercial licensing requires a separate
project-license decision.

Run the local comparison with:

```powershell
python scripts/benchmark_parsers.py C:\path\to\document.pdf --output evals/reports/parser.json
```

The report records actual timing, native text and word counts, empty-page
counts, rendering support, and local allocation peaks. The locally prepared
archive was available for a six-document comparison covering 20 pages from
each PDF; see `evals/reports/parser-six-document.json`. PyMuPDF was roughly two
orders of magnitude faster with comparable native text counts, but pdfplumber
remains the runtime choice because its permissive license and word geometry
contract are suitable for redistribution. This is a performance and coverage
record, not a source-verified claim-accuracy benchmark; PyMuPDF stays an
optional local candidate until a separate AGPL/commercial licensing decision.
