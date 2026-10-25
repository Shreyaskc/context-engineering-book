# Context engineering companion labs

One Python system teaches an evidence/context supply chain using an original 54-envelope synthetic corpus, immutable source versions, SQLite metadata/FTS5 and shared retrieval, packing, memory, lifecycle, graph and evaluation functions.

Use Python 3.12 or newer with SQLite FTS5. The required track has no third-party Python packages, model download, account, paid key or public service.

```sh
python3 -m contextlab doctor --json
python3 -m contextlab readiness --json
python3 scripts/check_baseline.py
python3 -m unittest discover -s tests -v
python3 -m contextlab lab run all --workspace .local/lab --reset --json
```

Start with [setup](docs/setup.md), [the fourteen-chapter contract](docs/chapter-contract.md), [readiness](docs/readiness.md) and [lab commands](docs/labs.md). See [architecture](docs/architecture.md), [temporal semantics](docs/temporal.md), [budget units](docs/budgets.md), [metric definitions](docs/metrics.md), [data provenance](docs/data-provenance.md) and [references](docs/references.md).

Dense/hybrid retrieval needs a separately configured real local MiniLM encoder; no hash-vector substitute is used. Generation is optional, requires explicit local approval and is excluded from hosted CI. No weights or tokenizer assets are distributed. Packing counts UTF-8 bytes and does not claim exact model-template token preflight. The capstone is a deterministic read-only synthetic assessment with no payment, refund or other business action.

The provided tests and finite fixtures check concrete teaching contracts, not general semantic entailment, production authentication, broad injection resistance or large-corpus quality. Reproduce results for the revision and environment you use. Private execution records and editorial/review ledgers are not distributed.

[MIT](LICENSE) covers user-owned companion code, synthetic fixtures and associated documentation. [NOTICE](NOTICE) preserves separate dataset, model and dependency terms. Manuscripts, covers, illustrations and book-production source belong to separate private repositories.
