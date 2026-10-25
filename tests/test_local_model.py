"""Optional real-model checks. No downloading and no fallback vectors."""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from contextlab.retrieval import LocalEncoder, Retriever
from contextlab.store import ROOT, Scope, Workspace


@unittest.skipUnless(os.environ.get("CONTEXTLAB_MINILM_DIR"), "existing local model path is not configured")
class RealLocalEncoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoder = LocalEncoder(os.environ["CONTEXTLAB_MINILM_DIR"])

    def test_real_dimensions_normalization_and_truncation(self):
        vectors, counts = self.encoder.encode(["two blue mugs", "policy " * 400])
        self.assertEqual([len(vector) for vector in vectors], [384, 384])
        self.assertGreater(counts[1], 256)
        self.assertEqual(self.encoder.metadata["max_tokens_including_specials"], 256)
        self.assertEqual(self.encoder.metadata["query_prefix"], "")
        self.assertEqual(self.encoder.metadata["document_prefix"], "")
        for vector in vectors:
            self.assertAlmostEqual(math.sqrt(sum(x*x for x in vector)), 1, places=5)
        self.assertNotEqual(vectors[0], vectors[1])

    def test_actual_dense_and_hybrid_scope_and_post_deletion_filtering(self):
        base = ROOT / ".local" / "tests"
        base.mkdir(exist_ok=True, parents=True)
        path = Path(tempfile.mkdtemp(prefix="real-model-", dir=base))
        try:
            workspace = Workspace(path).initialize()
            scope = Scope()
            retriever = Retriever(workspace, scope, os.environ["CONTEXTLAB_MINILM_DIR"])
            retriever.encoder = self.encoder
            for method in ["dense", "hybrid"]:
                rows = retriever.search("Harbor invoice and warehouse bin blue mugs", method, 20)
                ids = {row["source_id"] for row in rows}
                self.assertFalse({"SYN-HARBOR-INVOICE", "SYN-INVENTORY-COUNT", "SYN-INJECTION-TRAP", "SYN-REVOKED-NOTE"}.intersection(ids))
            long_query = retriever.search("policy " * 400, "dense", 1)
            self.assertTrue(long_query[0]["query_truncated"])
            workspace.delete_projection("SYN-REPORT-104", scope.as_of)
            self.assertFalse(any(r["source_id"] == "SYN-REPORT-104" for r in retriever.search("one red mug customer report", "dense", 30)))
            self.assertFalse((path / "dense.json").exists())
        finally:
            shutil.rmtree(path)


if __name__ == "__main__":
    unittest.main()
