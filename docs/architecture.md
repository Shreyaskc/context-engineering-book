# Provisional architecture — implemented v0.1

The unit of work is an evidence supply chain. The read-only assessment has no
agent scheduler, payment integration, or autonomous refund action. This is a
small teaching implementation, not a production multi-tenant service.

| Module | Responsibility |
|---|---|
| `store.py` | versioned envelopes, validation, exact span chunks, SQLite/FTS5, current grants, temporal eligibility, isolated live projection |
| `retrieval.py` | eligible-only FTS5 statistics, pinned local MiniLM, standard-library exact cosine, RRF, labeled metadata heuristic |
| `pipeline.py` | shared fourteen stages, exact case assembly, byte packs, finite support labels, state, memory, graph, evaluation and replay |
| `exercises.py` | deliberately broken inputs and corrections through those same functions |
| `readiness.py` | runnable conceptual prerequisites |
| `__main__.py` | one CLI over those modules |

## Stage boundaries

Immutable JSONL sources feed a local SQLite metadata/chunk store. Eligibility
checks current identity/disclosure grants, tenant/team/principal scope, branch,
publication, fixture ingestion/index readiness, applicability, deletion,
supersession, and trusted quarantine labels. Only eligible chunks enter the
query's FTS5 statistics or scope-specific dense cache. Authorization occurs
before evidence leaves retrieval and is rechecked on cached vectors and graph facts.

The stored all-source FTS table is a local synthetic authoring projection; query
ranking builds its own eligible-only FTS view to avoid hidden documents influencing
BM25 statistics. This costs more than a production index, but the corpus is tiny.
There is no network database or vector service. Dense similarity uses Python's
exact cosine arithmetic over genuine model vectors; NumPy is a model-runtime
dependency, not a requirement for the similarity search loop.

RRF combines rank contributions with offset 60 and stable chunk-ID ties. The
metadata reranker prioritizes required case sources and authoritative fixture trust,
then previous rank. It is a heuristic, not a learned cross-encoder. Benchmark
reports compare plain lexical, dense, and RRF hybrid; the heuristic is separately
visible and is not silently included under a dense/hybrid benchmark label.

Exact tenant/case/invoice/policy records are assembled explicitly for the capstone,
separately from search rankings. Required evidence is packed as complete spans
inside canonical JSON under a named UTF-8 byte budget. If the required bundle is
missing, ambiguous, unauthorized, or cannot fit, the capstone abstains. Complete
evidence serialization is counted; full backend prompt/token capacity is not claimed.

## Records and trust

The source schema is `contracts/source.schema.json`. `fixtures/ingestion-events.jsonl`
is a separate historical system-event fixture. Actual workspace import/index
observations are separate SQLite metadata; see the temporal guide. Source versions
and hashes are immutable, while the current disclosure policy is independently
versioned and never rewound by a historical query.

Chunks retain source revision/hash, exact character and UTF-8 byte spans, text,
kind and trust. Candidate records add method, score definition, rank, and explicit
fusion contributions. Packs retain source IDs/revisions/spans, serialization cost,
excluded evidence/reasons, and missing required refs. State separates purchase,
reported claim, unknown fulfillment, pending checks, and branch policy.

Citations first check source eligibility and exact spans. Semantic support is
represented by a finite curated claim/source-hash/full-span ledger; it is not a
general entailment checker. The deterministic tool reducer checks typed values,
exact requested scope, currently eligible source refs, and equality to source-backed
check states. Plausible text alone never completes a purchase or case check.

Memory is a purpose-bound, scoped, seven-day deterministic projection with source
refs and explicit lossy omissions. It preserves uncertainty, rejects use before
admission or after expiry, and is rebuilt from current authorized records.
Graph edges carry source refs, tenant, trust and qualified inference; traversal
rechecks all refs and the finite fixture projection. No delivered-color fact is
licensed by this case. These validators do not generalize into universal semantic
or security guarantees.

## Boundaries, deletion and replay

Service Operations and Inventory Operations share the Northstar tenant but have
different grants. Platform support does not imply customer-content access. Harbor
is separate. CLI principal flags simulate fixture identities; a production identity
provider, policy engine, hostile ingestion pipeline, concurrency service, and
production authorization enforcement are outside this teaching implementation.

V4 is an explicit named branch. It never edits v3 or the canonical fixture.
Deletion removes content from the isolated live projection and invalidates FTS,
chunks, dense cache, candidate/pack/claim/state/memory/graph artifacts. Non-content
receipts and tombstones remain. Immutable synthetic authoring sources and external
copies/backups are outside that deletion scope; no forensic erasure is promised.

Receipts record code/input/projection/artifact hashes, actual snapshot metadata,
versions, scope and both clocks, command arguments, byte limits, encoder evidence,
and timings. Replay checks drift first. With `--reexecute`, it re-executes the same
stage and compares stable fields, explicitly excluding measured timing fields.
Missing/deleted artifacts are never reconstructed. No LLM generation occurs in
the deterministic pipeline; optional Ollama smoke usage remains a separate record.
