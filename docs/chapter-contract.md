# Provisional executable contract — v0.1

Package: `contextlab`. Entry point: `python -m contextlab`. The fourteen stages
below are implemented in one shared pipeline. This remains a provisional teaching
implementation awaiting the comprehensive sequential review program and final
source-ledger alignment; command examples must follow actual tested behavior.

## Common interface

```sh
python3 -m contextlab doctor --json
python3 -m contextlab readiness --json
python3 -m contextlab lab run 01 --workspace .local/ch01 --reset --json
python3 -m contextlab stage run evidence-inventory --workspace .local/stage --reset --json
python3 -m contextlab exercise run 01 --workspace .local/ex01 --reset --json
python3 -m contextlab replay --workspace .local/ch01 --receipt .local/ch01/receipts/01-evidence-inventory.json --reexecute --json
```

Flags: `--principal`, `--tenant`, `--team`, `--as-of`, `--knowledge-at`, `--branch`,
`--track core|local-model`, `--model-dir`, `--budget` (UTF-8 bytes), `--workspace`,
`--reset`, `--json`. JSON is always emitted. `--knowledge-at` defaults to `--as-of`;
validity and system knowledge are separate clocks. Current disclosure policy is
never rewound by either clock. Fixture principals simulate a trusted binding;
this is not production authentication.

A fresh lab command starts from the same checked source corpus and can run
independently. Shared functions assemble dependencies, avoiding undocumented
interactive state. `lab run all` executes stages 01–14 in order. `--reset` can
replace only a marked workspace below this repository's ignored `.local/` tree;
it cannot reset the repository or an arbitrary directory.

Exit codes: 0 completed (whole core run can explicitly report unavailable optional
stages), 2 invalid input/runtime failure, 3 unavailable optional capability,
4 insufficient evidence, a failed exercise contract, or replay drift/mismatch. A deliberately broken exercise
returns 0 only when its expected rejection/correction sequence executes; unexpected
exceptions remain failures. Source JSON Schema is in `contracts/source.schema.json`;
the runtime adds hash, span, grant, and timestamp checks.

| Ch. | `stage run NAME` | Artifact | Main concept / failure |
|---|---|---|---|
| 00 | `readiness` (separate command) | JSON to stdout | shell/Python, null/zero, clocks, ranking, vectors, metrics, units |
| 01 | `evidence-inventory` | `01-evidence-inventory.json` | attributed, scoped evidence / missing provenance |
| 02 | `corpus` | `02-corpus.json` | envelope validation and exact spans / detached exception |
| 03 | `lexical` | `03-lexical.json` | scoped SQLite FTS5 BM25 / nearby invoice mismatch |
| 04 | `dense` | `04-dense.json` | genuine pinned MiniLM / encoder truncation |
| 05 | `hybrid-rerank` | `05-hybrid-rerank.json` | RRF plus labeled metadata heuristic / incompatible raw scores |
| 06 | `pack` | `06-pack.json` | whole-span UTF-8 byte packing / incomplete required bundle |
| 07 | `claims` | `07-claims.json` | structural citations vs curated support / unsupported delivery |
| 08 | `structured` | `08-structured.json` | exact scoped state and tool validation / forged completed check |
| 09 | `temporal` | `09-temporal.json` | availability/ingestion/index/validity and deletion / future knowledge |
| 10 | `memory` | `10-memory.json` | scoped, expiring lossy projection / uncertainty lost |
| 11 | `graph` | `11-graph.json` | sourced and qualified edges / invented delivered-color edge |
| 12 | `boundaries` | `12-boundaries.json` | grants before retrieval and per fact / tenant/team/injection trap |
| 13 | `evaluate` | `13-evaluate.json` | frozen query splits, actual wins/losses/ties, receipts / drift |
| 14 | `capstone` | `14-capstone.json` | read-only assessment / missing evidence requires abstention |

Artifacts and corresponding receipts live under the specified workspace.
Core stage 04 is unavailable; core stage 05 exposes lexical plus a metadata
heuristic and explicitly marks hybrid unavailable. No semantic stand-in is used.
The local-model track implements genuine dense and RRF hybrid retrieval. A learned
cross-encoder is not provided. The capstone uses exact scoped records plus selected
evidence and is explicitly deterministic; it is not an LLM answer-quality claim.

```sh
python3 -m contextlab scenario branch northstar-v3 northstar-v4 --workspace .local/v4 --json
python3 -m contextlab lab run 14 --branch northstar-v4 --as-of 2026-02-15T12:00:00Z --workspace .local/v4 --json
```

The branch command writes a scenario description; later commands must select v4
and its clock explicitly. V3 is never silently replaced. The [temporal contract](temporal.md)
is authoritative for the fictional publication/ingestion/effective clocks.

Chapter 14's focused optional generation verification is
`scripts/verify_capstone_generation.py`; it consumes the same authorized context
pipeline and records extractive claim/citation schema output, context manifests,
runtime tokens and limited-oracle validation. See the clean setup and exact
commands in [reproducibility-gates.md](reproducibility-gates.md). It adds no business
actions or new pipeline stage. Chapter 00's readiness command and tests are included
in both the core and clean-ML verification commands there.
