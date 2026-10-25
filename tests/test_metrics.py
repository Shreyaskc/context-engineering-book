"""Independent binary-gain arithmetic and exact historical report regressions."""
import json
import math
import unittest

from contextlab.pipeline import retrieval_metrics
from contextlab.store import ROOT

TOLERANCE = 1e-12


class HistoricalMetricDerivations(unittest.TestCase):
    def test_exact_q20_and_q07_dense_rows_in_both_preserved_reports(self):
        for filename in ["retrieval-baseline.json", "retrieval-clean-baseline.json"]:
            report = json.loads((ROOT / "evidence" / filename).read_text())
            for query_id in ["Q20", "Q07"]:
                with self.subTest(report=filename, query=query_id):
                    row = next(q for q in report["queries"] if q["id"] == query_id)
                    ranked = row["results"]["dense"]["ranked_source_ids"]
                    if query_id == "Q20":
                        self.assertEqual(row["relevant"], ["SYN-OBSERVABILITY-GUIDE"])
                        self.assertEqual(ranked.index("SYN-OBSERVABILITY-GUIDE")+1, 2)
                        expected = (1/math.log2(3)) / (1/math.log2(2))
                        self.assertAlmostEqual(expected, 0.6309297535714575, delta=TOLERANCE)
                    else:
                        self.assertEqual(set(row["relevant"]), {"SYN-UNKNOWN-GUIDE", "SYN-COMPRESSION-GUIDE"})
                        self.assertEqual(ranked.index("SYN-UNKNOWN-GUIDE")+1, 2)
                        self.assertEqual(ranked.index("SYN-COMPRESSION-GUIDE")+1, 3)
                        expected = (1/math.log2(3)+1/math.log2(4))/(1/math.log2(2)+1/math.log2(3))
                        self.assertAlmostEqual(expected, 0.6934264036172708, delta=TOLERANCE)
                    self.assertAlmostEqual(row["results"]["dense"]["ndcg_at_5"], expected, delta=TOLERANCE)
                    self.assertAlmostEqual(retrieval_metrics(ranked, row["relevant"])["ndcg_at_5"], expected, delta=TOLERANCE)
            self.assertEqual([q["split"] for q in report["queries"]].count("dev"), 12)
            self.assertEqual([q["split"] for q in report["queries"]].count("heldout"), 8)

    def test_deduplicate_sources_before_cutoff(self):
        result = retrieval_metrics(['X', 'X', 'A', 'B', 'C', 'D'], ['D'])
        self.assertEqual(result["recall_at_5"], 1)
        self.assertAlmostEqual(result["ndcg_at_5"], 1/math.log2(6), delta=TOLERANCE)

    def test_unretrieved_label_still_contributes_to_ideal(self):
        result = retrieval_metrics(['A'], ['A', 'B'])
        self.assertEqual(result["recall_at_5"], 0.5)
        self.assertAlmostEqual(result["ndcg_at_5"], 1/(1+1/math.log2(3)), delta=TOLERANCE)

    def test_duplicate_labels_do_not_inflate_denominator(self):
        self.assertEqual(retrieval_metrics(['A'], ['A', 'A']), retrieval_metrics(['A'], ['A']))

    def test_more_than_five_labels_caps_ideal_but_not_recall_denominator(self):
        labels = list('ABCDEF')
        result = retrieval_metrics(labels, labels)
        self.assertAlmostEqual(result["ndcg_at_5"], 1, delta=TOLERANCE)
        self.assertAlmostEqual(result["recall_at_5"], 5/6, delta=TOLERANCE)

    def test_no_labels_are_null_not_perfect(self):
        result = retrieval_metrics(['A'], [])
        self.assertIsNone(result["ndcg_at_5"])
        self.assertIsNone(result["recall_at_5"])
        self.assertEqual(result["mrr_at_5"], 0)


if __name__ == "__main__":
    unittest.main()
