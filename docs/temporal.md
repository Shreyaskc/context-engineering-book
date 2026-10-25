# Temporal, ingestion, snapshot and disclosure contract

Source publication is not system ingestion, and ingestion is not index readiness.
The source envelope has `available_at`, `valid_from`, optional `valid_until`,
`deleted_at`, `supersedes`, and branch. An independent versioned synthetic system
event ledger (`fixtures/ingestion-events.jsonl`) names `ref`, `ingested_at`, and
`index_ready_at`. An observation's event time can live in its typed record.

`--as-of` selects applicability/validity time. `--knowledge-at` selects system
knowledge/index cutoff and defaults to as-of. Eligibility requires publication,
ingestion, and index readiness by the knowledge cutoff, validity at as-of, no
applicable deletion/supersession, the explicit branch, and current disclosure
permission. Current identities and `fixtures/access-policy.json` never rewind
with the historical clock. The revoked training note remains denied to Service
Operations even in historical reconstruction.

## Actual fixed teaching clocks

The canonical v3 reset is `2026-01-15T12:00:00Z`. Most synthetic sources are
available/valid from January 1 at 00:00Z, ingested at 00:01Z, and indexed at
00:02Z. The correction note's revision 2 is published January 12 and supersedes
revision 1 only after its ingestion/index readiness. A retired note is deleted
January 14. A future training note is unavailable until February 1.

The independent April observation is unrelated to CASE-SYN-104 fulfillment:

| Event | Fictional UTC time |
|---|---|
| observation | 2026-04-14 09:00 |
| source available | 09:20 |
| system ingested | 09:25 |
| index ready | 09:28 |

Queries at 09:10, 09:22, and 09:26 cannot retrieve that record. A query at 09:30
can. At 09:22, external availability alone does not establish system knowledge.
With as-of 09:10 and knowledge-at 09:30, a retrospective reconstruction can use
the later-known observation, explicitly labeled by its different clocks.

V4 remains a separate explicit branch. It is published **February 1, 2026
09:30Z**, ingested 09:31Z, indexed 09:32Z, and effective **10:00Z**. A v4 query
at 09:45 lacks an applicable policy even though indexing has finished. A later
query can use it only with `--branch northstar-v4`. The v3 branch is unchanged.

## Real Mac import and index timestamps

The historical event ledger is explicitly synthetic. It does not claim the real
Mac imported or indexed these files in January or April. Each workspace SQLite
metadata table separately records actual UTC import start and index-ready time,
source/event-log hashes, and reconstruction mode. Receipts include that actual
snapshot metadata plus both requested teaching clocks. Historical eligibility
uses the declared fixture events; it is a controlled reconstruction exercise,
not evidence about a production system's past knowledge.

Deletion exercises erase the affected source from the isolated live projection,
FTS/chunks and derived caches/artifacts, retain non-content receipts/tombstones,
and refuse content reconstruction after invalidation. They do not erase the
immutable synthetic authoring corpus or claim physical/forensic erasure.
