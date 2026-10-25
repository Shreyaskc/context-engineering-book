"""Fixture-oracle limits and safe application handling; no inference in unit tests."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from contextlab.pipeline import Pipeline
from contextlab.store import ROOT, Scope
from contextlab.store import Workspace

sys.path.insert(0, str(ROOT / "scripts"))
from verify_capstone_generation import validate_answer


class ExtractiveGenerationValidation(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="generation-oracle-", dir=base))
        self.workspace = Workspace(self.path).initialize()
        self.scope = Scope()
        self.packed = Pipeline(self.workspace, budget=6000).stage_6()
        identifiers = {"policy": "SYN-POLICY-RETURNS-V3", "purchase": "SYN-PURCHASE-4817", "report": "SYN-REPORT-104", "fulfillment": "SYN-FULFILLMENT-104"}
        self.claims = []
        for kind, sid in identifiers.items():
            row = next(r for r in self.packed["pack"]["evidence"] if r["source_id"] == sid)
            self.claims.append({"kind": kind, "text": row["text"], "citation": {k: row[k] for k in ["ref", "char_start", "char_end"]}})

    def tearDown(self):
        shutil.rmtree(self.path)

    def test_exact_fixture_extraction_is_limited_but_accepted(self):
        answer = {"claims": self.claims, "observation": {"availability": "not_available", "citation": None}}
        result = validate_answer(answer, self.workspace, self.scope, self.packed)
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["business_actions"], [])

    def test_valid_locator_does_not_validate_unsupported_model_text(self):
        self.claims[0]["text"] = "An automatic refund is authorized."
        answer = {"claims": self.claims, "observation": {"availability": "not_available", "citation": None}}
        result = validate_answer(answer, self.workspace, self.scope, self.packed)
        self.assertTrue(result["claim_results"][0]["locator_valid_and_inside_authorized_pack"])
        self.assertFalse(result["claim_results"][0]["text_matches_cited_span_verbatim"])
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["application_response"], "withhold_unvalidated_model_answer")

    def test_future_observation_and_duplicate_kinds_are_rejected(self):
        self.claims[1]["kind"] = "policy"
        answer = {"claims": self.claims, "observation": {"availability": "available", "citation": {"ref": "SYN-OBSERVATION-APR14@1", "char_start": 0, "char_end": 10}}}
        result = validate_answer(answer, self.workspace, self.scope, self.packed)
        self.assertFalse(result["schema_and_required_kinds_valid"])
        self.assertFalse(result["observation_rubric_passed"])
        self.assertFalse(result["validation_passed"])


if __name__ == "__main__":
    unittest.main()
