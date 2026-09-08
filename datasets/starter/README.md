# Starter corpus preparation

Project SuperJoin does not redistribute the six source PDFs by default. The
assignment archive and the publishers' terms do not provide a single,
project-wide redistribution grant, so source files stay outside Git until a
rights review permits a specific artifact.

Use `scripts/prepare_dataset.py` with either the supplied local archive or a
directory containing the PDFs:

```powershell
python scripts/prepare_dataset.py --input C:\path\to\starter-archive.zip
```

The command computes hashes, records the observed page counts, and writes a
local preparation manifest under `data/starter/`. It never substitutes a
different document when a source is missing or has changed. The tracked
manifest contains the official source URLs, expected logical documents, and
the page selections used by the starter evaluation cases; the local preparation manifest is
the source of truth for the actual bytes available to an evaluator.

The application never loads this corpus automatically. It starts empty and
only processes PDFs explicitly uploaded into a user-created workspace.
