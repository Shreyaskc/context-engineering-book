"""Check fixed source-ranking examples with independent binary-gain arithmetic."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contextlab.pipeline import retrieval_metrics
from contextlab.store import digest


def verify_examples(data):
    examples = data.get("examples")
    if not isinstance(examples, list) or len(examples) != 2 or {row.get("query_id") for row in examples} != {"Q20", "Q07"}:
        raise ValueError("expected examples Q20 and Q07 exactly once")
    rows = []
    for row in examples:
        query = row["query_id"]
        ranked, relevant = row["ranked_source_ids"], row["complete_relevant_labels"]
        hand = 1/math.log2(3) if query == "Q20" else (1/math.log2(3)+1/math.log2(4))/(1+1/math.log2(3))
        function = retrieval_metrics(ranked, relevant)
        expected = row["expected_ndcg_at_5"]
        passed = abs(function["ndcg_at_5"]-hand) <= 1e-12 and abs(expected-hand) <= 1e-12
        rows.append({"example_id": query, "ranked_source_ids": ranked, "complete_relevant_labels": relevant,
                     "hand_ndcg_at_5": hand, "function_metrics": function, "expected_ndcg_at_5": expected,
                     "tolerance": 1e-12, "passed": passed})
    return rows


def main():
    path = ROOT / "fixtures/metric-examples.json"
    rows = verify_examples(json.loads(path.read_text()))
    output = {"status": "passed" if all(row["passed"] for row in rows) else "failed",
              "scope": "Fixed arithmetic examples only; not fresh retrieval or real model validation.",
              "fixture": str(path.relative_to(ROOT)), "fixture_sha256": digest(path.read_bytes()),
              "definition": "Binary source gains; deduplicate source IDs before top five; ideal denominator uses full unique relevant set capped at five. No labels: recall/nDCG null, MRR 0.",
              "rows": rows}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "passed" else 4


if __name__ == "__main__":
    sys.exit(main())
