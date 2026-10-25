# Binary source relevance and two fixed nDCG examples

The lab deduplicates retrieved source IDs **before** selecting the first five.
Each unique source has binary gain: 1 when its ID belongs to the complete set of
relevant labels, otherwise 0. At rank i, discounted gain is gain / log2(i + 1).
DCG@5 sums those discounted gains over the retrieved top five. IDCG@5 is the
best possible ordering of up to five sources from the full unique relevant set,
including relevant sources that retrieval missed. nDCG@5 is DCG@5 / IDCG@5.

The public fixture `fixtures/metric-examples.json` preserves the two documented
rank/label arrangements as fixed arithmetic inputs. It contains no raw execution
reports, timings or encoder observations and is not fresh retrieval or inference
evidence. The separate label fixture retains 12 development queries and 8 held-out
queries; a measured held-out partition must not become tuning data described as unseen.

| Fixed dense-rank example | Relevant ranks | DCG@5 | IDCG@5 | nDCG@5 |
|---|---|---|---|---|
| Q20 | SYN-OBSERVABILITY-GUIDE at 2 | 1/log2(3) | 1/log2(2) = 1 | 0.6309297535714575, about 0.6309 |
| Q07 | SYN-UNKNOWN-GUIDE at 2; SYN-COMPRESSION-GUIDE at 3 | 1/log2(3) + 1/log2(4) | 1/log2(2) + 1/log2(3) | 0.6934264036172708, about 0.6934 |

For Q20, binary gains at ranks 1–5 are 0, 1, 0, 0, 0. Its only relevant source
would ideally appear first, so the ideal gain is 1. For Q07 the gains are 0, 1,
1, 0, 0; the two ideal relevant sources would occupy ranks 1 and 2. This gives
approximately 1.13093 / 1.63093 = 0.69343, rather than the single-hit denominator.

A missing relevant source lowers recall. It also lowers ideal-normalized gain
when it leaves an attainable relevant position unfilled: retrieving only A when
A and B are relevant gives recall 1/2 and nDCG 1 / (1 + 1/log2(3)). Duplicate
labels do not increase the denominator. With more than five relevant labels,
IDCG@5 is capped at five positions, while recall still uses every unique relevant
label; five relevant hits can therefore have nDCG@5 = 1 and recall below 1.

No relevance labels means recall and nDCG are null, not perfect scores. The
current function returns MRR 0 in that case, which is a separate convention.

`python3 -B scripts/verify_metrics.py` retains both complete rankings and label
sets and compares expected example values, the function, and independent arithmetic at an
absolute tolerance of 1e-12. `tests/test_metrics.py` also checks cutoff ordering,
unretrieved labels, duplicate labels, more than five labels and absent labels.
