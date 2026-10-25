"""Meaningful guardrails against misrepresenting the canonical synthetic case."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_baseline import load_inputs, validate


class BaselineGuardrails(unittest.TestCase):
    def test_canonical_case_and_contract(self):
        validate(*load_inputs())

    def test_bad_claims_are_rejected(self):
        changes = [
            ("fulfillment", {"status": "delivered", "source_id": "invented"}),
            ("policy_v4", {"activation": "global", "active": True}),
            ("tenant", "harbor-retail"),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                inputs = copy.deepcopy(load_inputs())
                inputs[0][key] = value
                with self.assertRaises(ValueError):
                    validate(*inputs)

    def test_automatic_refund_is_rejected(self):
        inputs = load_inputs()
        inputs[0]["policy"]["automatic_refund_authorized"] = True
        with self.assertRaisesRegex(ValueError, "automatic refund"):
            validate(*inputs)

    def test_future_prerequisite_is_rejected(self):
        inputs = load_inputs()
        inputs[1]["chapters"][0]["needs"] = [14]
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            validate(*inputs)

    def test_false_uci_derivation_is_rejected(self):
        inputs = load_inputs()
        inputs[2]["synthetic_fixture"]["derived_from_uci_rows"] = True
        with self.assertRaisesRegex(ValueError, "UCI-derived"):
            validate(*inputs)


if __name__ == "__main__":
    unittest.main()
