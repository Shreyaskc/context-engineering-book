# Progressive runnable labs and failure exercises

All chapters use the same `contextlab` package, source envelopes, scoped SQLite
store, and shared functions. A lab can reset from the checked fixture, so readers
can enter at a chapter without carrying hidden prior state. Use a dedicated
workspace per exercise; all resets are limited to marked `.local/` descendants.

```sh
python3 -m contextlab lab run 01 --workspace .local/ch01 --reset --json
python3 -m contextlab exercise run 01 --workspace .local/ex01 --reset --json
```

Replace `01` with the chapter number. Run readiness first. The machine-readable
chapter map names prerequisites; earlier concepts matter even when a fixture
checkpoint makes execution independent. The following exercises deliberately
break an input or assumption, observe the failure, then perform a concrete
correction. They operate in memory or in the isolated workspace, never by
silently changing the canonical source fixture.

| Ch. | Inspect in the normal run | Broken case and correction |
|---|---|---|
| 01 | eligible source IDs, origin/license/scope | remove provenance; validator rejects; original envelope passes |
| 02 | content hashes and character/byte spans | first 64-character policy fragment loses refund exception; preserve the full policy unit |
| 03 | BM25 scores and scoped candidates | select nearby invoice 4818 for case 104; exact scoped reducer rejects; use 4817 |
| 04 | encoder revision, dimensions, prefixes, truncation | >256-token input is truncated; select a coherent short unit and measure again |
| 05 | individual RRF contributions and heuristic label | raw BM25/cosine have incompatible scales; fuse ranks explicitly |
| 06 | complete serialized byte cost and exclusions | 100-byte pack cannot carry required evidence; abstain; 3600-byte pack completes case bundle |
| 07 | citation spans vs finite support labels | purchase citation is valid but does not support delivered-red claim; use supported purchase claim |
| 08 | typed state, exact scope, pending checks | forge completed purchase check; provenance-aware reducer rejects; use source-backed pending state |
| 09 | four distinct observation/publication/ingestion/index times | 09:22 availability is insufficient; at 09:30 the fixture index is usable; delete a scratch projection and invalidate derivatives |
| 10 | explicit unknowns, scope, expiry and lossy omissions | replace summary with invented delivery/refund; fixture-summary validation rejects; rebuild from current evidence |
| 11 | source refs, trust, qualified inference | add delivered-color edge citing purchase; curated graph projection excludes it |
| 12 | finite cross-tenant/team/principal/injection checks | query Harbor/bin/instruction traps; eligibility and trusted ingestion labels exclude unauthorized sources |
| 13 | code/input/projection/artifact hashes | alter recorded artifact; replay detects drift; restore and re-execute stable fields |
| 14 | exact facts, pending checks, empty business-actions list | remove report from live projection; abstain; explicit synthetic reset restores the teaching fixture |

Chapters 04 and 05 require the optional real local encoder:

```sh
MODEL_DIR=/path/to/existing/minilm/snapshot
python3 -m contextlab lab run 04 --track local-model --model-dir "$MODEL_DIR" --workspace .local/ch04 --reset --json
python3 -m contextlab exercise run 04 --track local-model --model-dir "$MODEL_DIR" --workspace .local/ex04 --reset --json
```

Use the interpreter/environment that has the optional dependencies. Missing models
produce exit 3 and an unavailable report, never a substitute. The complete core
run still succeeds with these availability limits stated. `scripts/verify_on_mac.py`
executes the normal stages, prerequisites, tests, failure exercises, branching,
and replay; optional model arguments add genuine dense/hybrid execution.

The graph, support-label, state, and summary validators are finite teaching
projections. They do not prove general entailment, secure production identity,
universal injection resistance, or arbitrary answer quality. Live-projection
deletion is not forensic storage erasure and never claims to erase the immutable
authoring fixture, prior external backups, or a reader's copied output.

The corrected exercise gate recomputes its finite predicates in the producer,
CLI and comprehensive verifier. A missing broken/corrected condition retains the
observations with `exercise_contract_failed` and exit 4. These exercises use the
canonical Service Operations/v3/January-15 scope; use `lab run` for other scenarios.
See round1-corrections.md (consult the source tests and technical limitations) for the candidate changes and
the distinction between validation completion and review closure.
