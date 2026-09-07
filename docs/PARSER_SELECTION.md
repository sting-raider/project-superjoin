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
counts, rendering support, and local allocation peaks. A source-verified
comparison must use at least 20 representative pages across all six prepared
documents and the annotated value/table regions. The repository does not
contain those third-party PDFs, so an available local assignment PDF smoke run
cannot be represented as the full 511-page selection benchmark. This remains a
measured release input rather than an invented accuracy claim.
