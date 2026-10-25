import unittest

from contextlab.readiness import examples


class Prerequisites(unittest.TestCase):
    def test_none_is_distinct_from_known_zero(self):
        result = examples()["json_none_zero"]
        self.assertTrue(result["unknown_is_none"])
        self.assertFalse(result["zero_is_none"])
        self.assertTrue(result["zero_is_falsey"])

    def test_utc_half_open_boundaries(self):
        result = examples()["utc_half_open"]
        self.assertTrue(result["start_included"])
        self.assertFalse(result["end_included"])

    def test_actual_fts_ranking_direction(self):
        rows = examples()["lexical_direction"]["sqlite_fts5_rows_in_native_best_first_order"]
        self.assertEqual(len(rows), 2)
        self.assertLessEqual(rows[0]["native_bm25"], rows[1]["native_bm25"])
        self.assertGreaterEqual(rows[0]["display_score_negative_bm25"], rows[1]["display_score_negative_bm25"])

    def test_vector_intuition_and_metrics(self):
        result = examples()
        self.assertEqual(result["dot_and_cosine"]["dot_product"], 50)
        self.assertAlmostEqual(result["dot_and_cosine"]["cosine"], 1)
        self.assertEqual(result["dot_and_cosine"]["orthogonal_cosine"], 0)
        self.assertEqual(result["precision_recall"]["precision"], 0.5)
        self.assertAlmostEqual(result["precision_recall"]["recall"], 1/3)

    def test_bytes_are_not_tokens(self):
        result = examples()["bytes_versus_tokens"]
        self.assertEqual(result["characters"], 4)
        self.assertEqual(result["utf8_bytes"], 5)
        self.assertIsNone(result["model_tokens"])


if __name__ == "__main__":
    unittest.main()
