# Document-content isolation

PDF text and pixels are evidence, not instructions. Project SuperJoin places
source excerpts inside an explicitly delimited untrusted-document field for
provider calls. It does not allow the document to alter system prompts,
endpoints, model roles, budgets, review status, or tools. Responses are
validated server-side; a model cannot grant verification by returning a status
label.

The offline fixture suite in `evals/fixtures/prompt_injection.jsonl` covers
native text, role-delimiter spoofing, exfiltration URLs, and an image-route
equivalent. Suspicious excerpts remain attached to the source claim when they
are quarantined, so an evaluator can inspect the failure. The acceptance
condition is zero strict Trust Gate false-allows. Run:

```powershell
python scripts/run_security_eval.py
```

Legitimate control text is included to protect extraction recall. A configured
vision endpoint receives only a rendered page image plus the same untrusted
content boundary; it has no browsing or execution tool.
