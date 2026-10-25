# Runnable prerequisites

Run `python3 -m contextlab readiness --json` before chapter 1. No model or package
installation is required. These examples execute computations and SQLite queries;
this command is different from `doctor`, which checks environment capabilities.

| Topic | Actual example and expected observation |
|---|---|
| Shell vs Python | Run `python3 -m contextlab readiness --json` at the shell prompt. The Python expression `2 + 2` evaluates to 4 inside Python. |
| JSON, None and zero | JSON `null` becomes `None`; `0` remains a known number. Both can be falsey, but only `None is None` is true. JSON `false` becomes `False`. |
| UTC and half-open time | `[09:00Z, 10:00Z)` includes 09:00 and excludes 10:00; timestamps must be timezone-aware. |
| Lexical ranking | Actual SQLite FTS5 `bm25` sorts lower first. The lab's negative-BM25 display score sorts higher first. |
| Dot product / cosine | Math vectors `[3,4]` and `[6,8]` have dot product 50 and cosine 1; orthogonal unit vectors have cosine 0. These are math vectors, not embeddings. |
| Precision / recall | Retrieving policy plus an unrelated record when policy, purchase and case are relevant gives precision 1/2 and recall 1/3. |
| Budget units | `Café` has 4 Python characters and 5 UTF-8 bytes. Model tokens are unmeasured, represented as null, not zero or a byte-derived estimate. |

The checks are in `tests/test_readiness.py` and are included in Mac verification.
If shell/Python syntax is unfamiliar, start by editing a small `.py` file and
running it with `python3 filename.py`; do not paste terminal commands into `>>>`.
