# Parser selection record

The runtime primary parser is `LiteParse 2.14.4`. It supplies local PDFium
text extraction, word geometry, classified layout blocks, table cells, and
page-complexity signals under Apache-2.0. The runtime serializes classified
blocks instead of LiteParse's spatial plain text, which avoids duplicated
characters while preserving reading order and geometry. `pdfplumber` remains
an automatic and configurable parser fallback, and `pypdfium2` remains the
bounded vision renderer.

Run the local comparison with:

```powershell
python scripts/benchmark_parser_backends.py C:\path\to\document.pdf --output evals/reports/liteparse-backend-benchmark.json
```

The adopted report covers seven documents and 169 pages: the 1, 27, and
100-page latency inputs plus unseen narrative, multicolumn, table-heavy, and
scanned fixtures. LiteParse completed native parsing in 3.17 seconds versus
60.30 seconds for pdfplumber, about 19 times faster. Its maximum measured RSS
delta was 89 MB versus 1.26 GB. Classified block serialization retained
601,861 characters on the 100-page document versus pdfplumber's 601,178.

Native parsing always runs first. Broad `sparse-text` or `embedded-images`
signals do not trigger OCR. Scanned/no-text pages, garbled pages, and vector
text pages with fewer than 80 usable characters enter local OCR in slices of
at most eight pages. If local OCR does not recover text, the page is explicitly
marked `vision-required`. Timeouts, OCR slice size, DPI, worker count, and the
fallback backend are deployment configuration.
