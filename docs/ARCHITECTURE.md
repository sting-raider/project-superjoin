# Project SuperJoin architecture

Project SuperJoin is a local, evidence-first temporal fact layer. Its central design choice is to keep three different things separate:

1. **Source claims** are immutable observations of what a document says. A claim keeps its raw wording, document/page identity, extraction method, and evidence anchors.
2. **Claim interpretations** are append-only, deterministic projections of a claim. They add normalized decimals, units, periods, entity/predicate mappings, security flags, and grounding status without rewriting the source claim.
3. **Canonical fact versions** group compatible interpretations into a queryable fact family. A version records the evidence membership, alternatives, relationship conclusions, review dependence, and knowledge revision that justify its current state.

This separation lets the product answer two different questions honestly: “What did the source assert?” and “What may a downstream system safely use for this context and policy?” The Trust Gate answers the second question and returns `block`, `needs_context`, `needs_review`, or `allow` with evidence and reason codes. Historical queries select the latest immutable `fact_versions` row whose workspace knowledge revision is at or before `known_at_revision`; they do not reinterpret today’s fact as historical truth.

## Runtime flow

```mermaid
flowchart LR
    U[PDF upload] --> D[Hash and durable document record]
    D --> P[Native parser and page quality checks]
    P -->|grounded text| E[Deterministic candidate extraction]
    P -->|low quality page| V[Optional configured vision fallback]
    V --> E
    E --> C[Immutable claims + anchors]
    C --> N[Normalization and registry resolution]
    N --> R[Exact / FTS5 / optional vector retrieval]
    R --> A[Deterministic relationship assessment]
    A -->|ambiguous only| S[Optional grounded reasoning role]
    S --> A
    A --> F[Versioned fact families]
    F --> K[Knowledge Diff and review records]
    F --> T[Trust Gate]
    C --> I[Evidence inspector]
```

The implementation is one FastAPI process with a SQLite WAL database and a static React/Vite client. A `BackgroundTasks` job performs document work, while durable `runs`, `run_events`, extraction checkpoints, cancellation guards, and explicit retry/resume routes make interruption recoverable in the supported one-container deployment. The runtime does not claim automatic cross-process leases or heartbeat recovery; adding a queue would increase setup and failure surface for this evaluator path. Publication is a transaction over claims, interpretations, relationships, fact versions, and the workspace revision. The same runtime is therefore useful in a Docker demo and understandable in an interview.

## Why these technologies

- **SQLite** supplies transactions, foreign keys, WAL, and FTS5 without a service dependency. Stored normalized vectors are scanned with NumPy only over the bounded workspace population. A normal query can use one cached, budgeted embedding against an active space; there is no claim of ANN performance.
- **pdfplumber** is the current compatible primary parser because the local smoke comparison found comparable native text output while PyMuPDF's AGPL/commercial licensing is unresolved for distribution. The benchmark harness and decision are documented in [`PARSER_SELECTION.md`](PARSER_SELECTION.md); a full source-verified corpus comparison remains an explicit evidence task.
- **FastAPI/Pydantic** keeps the API contract typed and exposes OpenAPI automatically. Provider calls use a small OpenAI-compatible adapter instead of a framework that hides prompts, retries, or budgets.
- **React/Vite** keeps the evaluator path fast and static. The UI is intentionally an evidence inspector and review workspace rather than a chatbot. The main interaction is a dense facts table with an adjacent evidence/trust panel.

## What was deliberately removed

The assignment does not benefit from Neo4j, a graph UI, Redis/Celery, Kubernetes, microservices, LangChain, autonomous web research, learned authority scores, or a generic event-sourcing framework. These would increase setup and failure surface without improving the required evidence, temporal, review, or Trust Gate behavior. The application keeps the useful audit properties as ordinary append-only relational records.

## Provider boundary

Extraction, reasoning, vision, and embeddings have independent model/base URL/key settings, timeout/output/concurrency controls, request paths, auth-header schemes, and capability metadata. The adapter accepts arbitrary model strings and does not contain a provider allowlist. API keys are optional for local endpoints; a configured endpoint with a missing model is reported as unavailable, while a remote failure is surfaced as a provider error. Azure-style API-key headers, deployment paths, OpenAI-compatible gateways, and services that omit response-format or embedding-dimension hints are configuration choices. Transient HTTP 429/5xx and connection/timeout failures use bounded retries, honor `Retry-After` where supplied, persist attempt counts, reserve the configured retry envelope, and charge only the attempts actually consumed. Cache and extraction-checkpoint fingerprints include the nonsecret endpoint/path/model/request-shape identity, preventing a provider switch from replaying another endpoint's output. The Settings API exposes only this nonsecret contract; credentials never leave the process. Document text is passed as explicitly delimited untrusted content; it never becomes a system instruction and cannot select a tool, endpoint, budget, or eligibility status. Chat responses pass a Pydantic claims-envelope check; malformed extraction receives one corrective request under a new budget/cache fingerprint before deterministic fallback. Responses are validated and budgeted before they can affect the claim pipeline. With no key, the seeded recorded dataset powers Demo Mode; recorded semantic responses are replayed through the normal relationship assessor and fact publisher. With a configured endpoint, arbitrary PDFs can enter the same pipeline.

## State and revision model

The source PDF and source claim are retained. A new interpretation, registry correction, review, or document changes the current projection by publishing a new workspace knowledge revision. Older fact versions and review decisions remain addressable. When new evidence changes a reviewed fact family, the previous decision is marked stale; the strict Trust Gate will not silently reuse it.
