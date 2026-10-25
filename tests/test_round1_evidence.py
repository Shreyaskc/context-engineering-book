"""Durability and semantic-gate regressions; all subprocesses are bounded fixtures."""
import contextlib
import copy
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from contextlab.pipeline import Pipeline, code_hashes, input_hashes, pack_context
from contextlab.store import ROOT, Scope, Workspace, canonical, digest

sys.path.insert(0, str(ROOT / "scripts"))
import evidence_run
import setup_clean_ml as setup
import verify_capstone_generation as generation
import verify_on_mac as verifier


class GenerationGate(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="round1-gate-evidence-", dir=base))

    # These deliberately failed/partial records are retained for review, not erased.
    def make_positive_fixture(self, directory):
        directory.mkdir(exist_ok=True)
        rows = []
        identifiers = {"policy": "SYN-POLICY-RETURNS-V3", "purchase": "SYN-PURCHASE-4817", "report": "SYN-REPORT-104", "fulfillment": "SYN-FULFILLMENT-104"}
        for name, at, expected in generation.EXPECTED_CASES:
            scope = Scope(as_of=at, knowledge_at=at)
            workspace = Workspace(directory / name).initialize()
            assembly = Pipeline(workspace, scope).assembly_rows()
            exact = [row for row in assembly if row["method"] == "exact_scoped_record_assembly"]
            observation = [row for row in workspace.chunks(scope) if row["source_id"] == generation.OBSERVATION]
            packed = pack_context(exact + observation, 6000)
            claims = []
            for kind, sid in identifiers.items():
                row = next(r for r in packed["pack"]["evidence"] if r["source_id"] == sid)
                claims.append({"kind": kind, "text": row["text"], "citation": {k: row[k] for k in ["ref", "char_start", "char_end"]}})
            observed = next((r for r in packed["pack"]["evidence"] if r["source_id"] == generation.OBSERVATION), None)
            answer = {"claims": claims, "observation": {"availability": expected, "citation": {k: observed[k] for k in ["ref", "char_start", "char_end"]} if observed else None}}
            rows.append({"name": name, "status": "observed_pass", "manifest": {"scope": asdict(scope), "context": packed["pack"], "context_sha256": digest(canonical(packed["pack"])), "input_sha256": input_hashes(), "code_sha256": code_hashes()}, "response": {"response": json.dumps(answer), "done": True}, "validation": generation.validate_answer(answer, workspace, scope, packed, expected)})
        return {"status": "completed_all_validated", "source_commit": "controlled-fixture-not-model-evidence", "script_sha256": digest(Path(generation.__file__).read_bytes()), "model": {"manifest_digest": generation.EXPECTED_MODEL_DIGEST, "template_sha256": generation.EXPECTED_TEMPLATE_DIGEST}, "business_actions": [], "cases": rows}

    def test_positive_gate_fixture_and_each_false_nested_predicate(self):
        directory = self.path / "valid"
        fixture = self.make_positive_fixture(directory)
        path = directory / "experiment.json"
        path.write_text(json.dumps(fixture))
        self.assertTrue(generation.assess_experiment_file(path, "controlled-fixture-not-model-evidence")["passed"])
        for predicate in ["locator_valid_and_inside_authorized_pack", "text_matches_cited_span_verbatim", "finite_full_source_support_label", "limited_fixture_support"]:
            bad = copy.deepcopy(fixture)
            bad["cases"][0]["validation"]["claim_results"][0][predicate] = False
            path.write_text(json.dumps(bad))
            with self.subTest(predicate=predicate):
                self.assertFalse(generation.assess_experiment_file(path)["passed"])

    def test_false_completion_missing_cases_and_literal_unsupported_output(self):
        directory = self.path / "variants"
        fixture = self.make_positive_fixture(directory)
        path = directory / "experiment.json"
        variants = []
        bad = copy.deepcopy(fixture);bad["status"] = "completed_with_failures_or_unvalidated_outputs";variants.append(bad)
        bad = copy.deepcopy(fixture);bad["cases"] = bad["cases"][:2];variants.append(bad)
        bad = copy.deepcopy(fixture);bad["cases"][0]["validation"]["validation_passed"] = False;variants.append(bad)
        bad = copy.deepcopy(fixture);answer = json.loads(bad["cases"][0]["response"]["response"]);answer["claims"][0]["text"] = "An automatic refund is authorized.";bad["cases"][0]["response"]["response"] = json.dumps(answer);variants.append(bad)
        bad = copy.deepcopy(fixture);bad["cases"][0]["manifest"]["scope"]["knowledge_at"] = "2026-04-14T09:30:00Z";variants.append(bad)
        for index, bad in enumerate(variants):
            path.write_text(json.dumps(bad))
            with self.subTest(index=index):
                self.assertFalse(generation.assess_experiment_file(path)["passed"])

    def test_zero_exit_producer_stub_cannot_pass_missing_or_invalid_experiment(self):
        stub = self.path / "producer_stub.py"
        stub.write_text("import pathlib,sys\np=pathlib.Path(sys.argv[2]);p.parent.mkdir(parents=True,exist_ok=True)\nmode=sys.argv[1]\nif mode=='bad': p.write_text('{\"status\":\"completed_with_failures_or_unvalidated_outputs\",\"cases\":[{\"name\":\"baseline\",\"validation\":{\"validation_passed\":false}}]}')\nif mode=='truncated': p.write_text('{\"cases\":')\nif mode=='missing-case': p.write_text('{\"status\":\"completed_all_validated\",\"cases\":[]}')\nprint('CONTROLLED_ZERO_EXIT_PRODUCER')\n")
        for mode in ["bad", "missing", "truncated", "missing-case"]:
            output = self.path / mode
            output.mkdir()
            record = {"git_head_at_start": "controlled-fixture", "checks": []}
            code = verifier.run_plan([("authorized-context-generation", [str(stub), mode, str(output / "capstone-generation/experiment.json")], 0)], output, record, output / "verification.json", timeout_override=2)
            with self.subTest(mode=mode):
                saved = json.loads((output / "verification.json").read_text())
                self.assertEqual(code, 4)
                self.assertEqual(saved["checks"][0]["exit_code"], 0)
                self.assertFalse(saved["checks"][0]["semantic"]["passed"])
                self.assertEqual(saved["status"], "failed")


class TimeoutEvidence(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="round1-timeout-evidence-", dir=base))

    def test_verifier_timeout_keeps_previous_checks_and_partial_output(self):
        output = self.path / "verifier"
        output.mkdir()
        record = {"git_head_at_start": "controlled-fixture", "checks": []}
        script = "import sys,time;print('PARTIAL_STDOUT',flush=True);print('PARTIAL_STDERR',file=sys.stderr,flush=True);time.sleep(2)"
        plan = [("doctor", ["-m", "contextlab", "doctor", "--json"], 0), ("controlled-timeout", ["-u", "-c", script], 0), ("must-not-run", ["-c", "raise RuntimeError('unexpected execution')"], 0)]
        code = verifier.run_plan(plan, output, record, output / "verification.json", timeout_override=0.25)
        saved = json.loads((output / "verification.json").read_text())
        self.assertEqual(code, 4)
        self.assertTrue(saved["checks"][0]["passed"])
        timed = saved["checks"][1]
        self.assertEqual(timed["status"], "timed_out")
        self.assertEqual(timed["outcome"], "timeout_uncertain")
        self.assertIsNone(timed["exit_code"])
        self.assertFalse(timed["auto_retry"])
        self.assertEqual((ROOT / timed["stdout"]).read_bytes(), b'PARTIAL_STDOUT\n')
        self.assertEqual((ROOT / timed["stderr"]).read_bytes(), b'PARTIAL_STDERR\n')
        self.assertEqual(saved["unexecuted_steps"], ["must-not-run"])
        self.assertGreaterEqual(timed["wall_seconds"], 0.2)

    @unittest.skipUnless(shutil.which("uv"), "setup regression needs an already installed uv")
    def test_setup_timeout_keeps_failed_step_and_partial_output_without_install(self):
        root = self.path / "setup"
        root.mkdir()
        sentinel = root / "sentinel.txt"
        sentinel.write_text("DO_NOT_CHANGE")
        real_step = evidence_run.recorded_step
        def controlled_step(record, record_path, output, task_root, name, command, **kwargs):
            if name == "uv-version":
                command = [sys.executable, "-c", "print('uv controlled-fixture')"]
            elif name == "base-python":
                command = [sys.executable, "-c", "print('[3,12,13]')"]
            elif name == "create-empty-venv":
                command = [sys.executable, "-u", "-c", "import sys,time;print('SETUP_PARTIAL_OUT',flush=True);print('SETUP_PARTIAL_ERR',file=sys.stderr,flush=True);time.sleep(2)"]
                kwargs["timeout"] = 0.25
            else:
                self.fail("no install or subsequent step is authorized in timeout regression")
            return real_step(record, record_path, output, task_root, name, command, **kwargs)
        with patch.object(setup, "ROOT", root), patch.object(setup, "recorded_step", side_effect=controlled_step), patch.object(setup, "LOCK", ROOT / "requirements/ml-macos-arm64-py312.lock"), contextlib.redirect_stdout(io.StringIO()):
            code = setup.main(["install", "--python", sys.executable, "--venv", ".venv-controlled-timeout", "--offline"])
        saved = json.loads(next((root / ".local/clean-setup").glob("*/install-record.json")).read_text())
        self.assertEqual(code, 4)
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(len(saved["steps"]), 3)
        timed = saved["steps"][-1]
        self.assertEqual(timed["status"], "timed_out")
        self.assertEqual((root / timed["stdout"]).read_bytes(), b'SETUP_PARTIAL_OUT\n')
        self.assertEqual((root / timed["stderr"]).read_bytes(), b'SETUP_PARTIAL_ERR\n')
        self.assertFalse(timed["auto_retry"])
        self.assertFalse((root / ".venv-controlled-timeout").exists())
        self.assertEqual(sentinel.read_text(), "DO_NOT_CHANGE")


if __name__ == "__main__":
    unittest.main()
