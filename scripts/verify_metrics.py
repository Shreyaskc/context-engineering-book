"""Verify two preserved historical dense rows using independent hand arithmetic."""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contextlab.pipeline import retrieval_metrics
from contextlab.store import digest


def main():
    rows = []
    for filename in ["retrieval-baseline.json", "retrieval-clean-baseline.json"]:
        path = ROOT / "evidence" / filename
        data = json.loads(path.read_text())
        for query in ["Q20", "Q07"]:
            row = next(q for q in data["queries"] if q["id"] == query)
            ranked = row["results"]["dense"]["ranked_source_ids"]
            hand = 1/math.log2(3) if query == "Q20" else (1/math.log2(3)+1/math.log2(4))/(1+1/math.log2(3))
            function = retrieval_metrics(ranked, row["relevant"])
            stored = row["results"]["dense"]["ndcg_at_5"]
            passed = abs(function["ndcg_at_5"]-hand) <= 1e-12 and abs(stored-hand) <= 1e-12
            rows.append({"historical_report": str(path.relative_to(ROOT)), "report_sha256": digest(path.read_bytes()), "query_id": query, "partition": row["split"], "ranked_source_ids": ranked, "complete_relevant_labels": row["relevant"], "hand_ndcg_at_5": hand, "function_metrics": function, "stored_ndcg_at_5": stored, "tolerance": 1e-12, "passed": passed})
    output = {"status": "passed" if all(r["passed"] for r in rows) else "failed", "scope": "historical row/arithmetic verification, not fresh model inference", "definition": "Binary source gains; deduplicate source IDs before top five; ideal denominator uses full unique relevant set capped at five. No labels: recall/nDCG null, MRR 0.", "rows": rows}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["status"] == "passed" else 4


if __name__ == "__main__":
    sys.exit(main())
