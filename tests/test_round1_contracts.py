"""Round 1 public-lab regressions. Controlled cases do not claim model quality."""
import contextlib
import copy
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from contextlab import __main__ as cli
from contextlab.exercises import exercise_contract, run_exercise
from contextlab.pipeline import Pipeline, case_state, make_memory, memory_usable
from contextlab.store import ROOT, Scope, Workspace
import contextlab.store as store

sys.path.insert(0, str(ROOT / "scripts"))
from verify_on_mac import check_semantics


def put(result, path, value):
    for key in path[:-1]:
        result = result[key]
    result[path[-1]] = value


class ExerciseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        cls.path = Path(tempfile.mkdtemp(prefix="round1-exercises-", dir=base))
        cls.results = {}
        for number in range(1, 15):
            if number in {4, 5}:
                continue
            workspace = Workspace(cls.path / str(number)).initialize()
            cls.results[number] = run_exercise(number, Pipeline(workspace))
        common = {"scope": asdict(Scope()), "canonical_fixture_mutated": False, "status": "observed_expected_failure_and_correction"}
        # Encoder count/RRF arithmetic fixtures only; no pretend semantic vectors.
        cls.results[4] = dict(common, chapter=4, broken={"truncated": True, "untruncated_encoder_tokens": 403}, corrected={"truncated": False, "untruncated_encoder_tokens": 12})
        cls.results[5] = dict(common, chapter=5, broken={"comparable_units": False}, corrected={"method": "RRF offset 60", "ranking": [{"method": "hybrid_rrf", "score": 1/61, "contributions": [{"rrf_contribution": 1/61}]}]})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.path)

    def test_all_canonical_contracts_and_actual_core_cli(self):
        for number, result in self.results.items():
            with self.subTest(number=number):
                self.assertTrue(exercise_contract(number, result)["passed"])
        for number in [4, 5]:
            with self.subTest(unavailable=number), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(["exercise", "run", str(number), "--workspace", str(self.path / f"unavailable-{number}"), "--json"]), 3)
                self.assertEqual(json.loads(output.getvalue())["status"], "unavailable")

    def test_every_advertised_broken_and_corrected_outcome_can_fail(self):
        mutations = {
            1: [(('broken_rejected',), False), (('corrected_validated',), False)],
            2: [(('broken','refund_rule_present'), True), (('corrected','refund_rule_present'), False), (('broken','first_fragment'), 'x'*500)],
            3: [(('broken_rejected',), False), (('corrected','invoice_id'), 'INV-SYN-4818'), (('corrected','case_id'), 'wrong'), (('corrected','purchase_check_complete'), True), (('corrected','case_check_complete'), True)],
            4: [(('broken','truncated'), False), (('corrected','truncated'), True), (('broken','untruncated_encoder_tokens'), 12), (('corrected','untruncated_encoder_tokens'), 400)],
            5: [(('broken','comparable_units'), True), (('corrected','method'), 'raw-score-sum'), (('corrected','ranking'), [])],
            6: [(('broken','status'), 'observed'), (('broken','answer'), 'unsupported'), (('corrected','status'), 'insufficient_evidence'), (('corrected','business_actions'), ['refund']), (('corrected','context_serialized_utf8_bytes'), 999999)],
            7: [(('broken','citation_structurally_valid'), False), (('broken','fixture_support_label'), True), (('corrected','citation_structurally_valid'), False), (('corrected','fixture_support_label'), False)],
            8: [(('broken_rejected',), False), (('corrected','invoice_id'), 'INV-SYN-4818'), (('corrected','purchase_check_complete'), True)],
            9: [(('temporal','independent_observation_exercise'), []), (('temporal','then_only_refs'), []), (('temporal','now_only_refs'), []), (('temporal','live_projection_deletion_exercise','removed_refs'), [])],
            10: [(('broken','usable'), True), (('corrected','usable'), False)],
            11: [(('unsupported_edge_returned',), True), (('corrected',), []), (('corrected',), [{'source_refs':['SYN-PURCHASE-4817@1'],'relation':'delivered_color'}])],
            12: [(('boundaries','status'), 'failed'), (('boundaries','tests'), []), (('boundaries','tests'), [{'query':str(i),'forbidden_source_hits':1,'returned_source_ids':[]} for i in range(3)]), (('boundaries','tests'), [{'query':str(i),'forbidden_source_hits':0,'returned_source_ids':['SYN-HARBOR-CASE']} for i in range(3)])],
            13: [(('broken','status'), 'verified_existing_artifact'), (('broken','changes'), []), (('corrected','status'), 'reexecution_mismatch'), (('corrected','replay_stable_sha256'), 'wrong')],
            14: [(('broken','status'), 'observed'), (('broken','answer'), 'unsupported'), (('deletion','removed_refs'), []), (('corrected','status'), 'insufficient_evidence')],
        }
        serial = 0
        for number, variants in mutations.items():
            for path, value in variants:
                serial += 1
                with self.subTest(number=number, path=path):
                    result = copy.deepcopy(self.results[number])
                    put(result, path, value)
                    self.assertFalse(exercise_contract(number, result)["passed"])
                    # A stale producer success flag must not fool either wrapper.
                    with patch.object(cli, "run_exercise", return_value=result), contextlib.redirect_stdout(io.StringIO()) as out:
                        code = cli.main(["exercise", "run", str(number), "--workspace", str(self.path / f"wrapper-{serial}"), "--json"])
                    self.assertEqual(code, 4)
                    wrapper = json.loads(out.getvalue())
                    self.assertEqual(wrapper["status"], "exercise_contract_failed")
                    name = f"real-model-exercise-{number:02}" if number in {4, 5} else f"exercise-{number:02}"
                    self.assertFalse(check_semantics(name, out.getvalue().encode(), self.path, "controlled-stub")["passed"])

    def test_each_temporal_exclusion_and_inclusion_is_checked(self):
        for index in range(4):
            result = copy.deepcopy(self.results[9])
            row = result["temporal"]["independent_observation_exercise"][index]
            row["observation_eligible"] = not row["observation_eligible"]
            with self.subTest(index=index):
                self.assertFalse(exercise_contract(9, result)["passed"])

    def test_unsupported_clock_retains_insufficient_correction_and_fails(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(["exercise", "run", "06", "--branch", "northstar-v4", "--as-of", "2026-02-01T09:45:00Z", "--workspace", str(self.path / "no-policy"), "--json"])
        data = json.loads(output.getvalue())
        self.assertEqual(code, 4)
        self.assertEqual(data["result"]["corrected"]["status"], "insufficient_evidence")
        self.assertFalse(data["result"]["contract"]["passed"])


class EvidenceClassificationAndMemory(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="round1-state-", dir=base))
        self.workspace = Workspace(self.path).initialize()

    def tearDown(self):
        shutil.rmtree(self.path)

    def test_encoder_integrity_error_propagates_from_pack_and_capstone(self):
        pipeline = Pipeline(self.workspace)
        for stage in [pipeline.stage_6, pipeline.stage_14]:
            with self.subTest(stage=stage.__name__), patch.object(pipeline.retriever, "search", side_effect=ValueError("encoder asset differs from pinned MiniLM provenance specification")):
                with self.assertRaisesRegex(ValueError, "encoder asset differs"):
                    stage()

    def test_truly_missing_policy_remains_insufficient_evidence(self):
        scope = replace(Scope(), branch="northstar-v4", as_of="2026-02-01T09:45:00Z")
        self.assertEqual(Pipeline(self.workspace, scope).stage_14()["status"], "insufficient_evidence")

    def test_memory_requires_complete_exact_unique_string_dependencies(self):
        scope = Scope()
        memory = make_memory(case_state(self.workspace, scope), scope)
        refs = memory["source_refs"]
        self.assertTrue(memory_usable(memory, self.workspace, scope))
        self.assertTrue(memory_usable(dict(memory, source_refs=list(reversed(refs))), self.workspace, scope))
        invalid = [[], refs+[refs[0]], refs+['SYN-HARBOR-CASE@1'], refs+['SYN-REVISION-NOTE@1'], tuple(refs), None, [1], 'not-an-array']
        invalid += [[ref for ref in refs if ref != omitted] for omitted in refs]
        for value in invalid:
            with self.subTest(dependencies=value):
                self.assertFalse(memory_usable(dict(memory, source_refs=value), self.workspace, scope))

    def test_symlinked_local_root_and_child_escape_preserve_disposable_sentinels(self):
        fake_root = self.path / "disposable-root"
        fake_root.mkdir()
        outside = self.path / "outside-owned-fixture"
        outside.mkdir()
        marked = outside / "marked"
        marked.mkdir()
        (marked / ".contextlab-workspace").write_text("contextlab-v1\n")
        sentinel = marked / "sentinel.txt"
        sentinel.write_text("DO_NOT_CHANGE")
        (fake_root / ".local").symlink_to(outside, target_is_directory=True)
        with patch.object(store, "ROOT", fake_root), self.assertRaisesRegex(ValueError, "symlink"):
            store.Workspace(fake_root / ".local/marked").initialize(reset=True)
        self.assertEqual(sentinel.read_text(), "DO_NOT_CHANGE")
        (fake_root / ".local").unlink()
        (fake_root / ".local").mkdir()
        (fake_root / ".local/escape").symlink_to(marked, target_is_directory=True)
        with patch.object(store, "ROOT", fake_root), self.assertRaises(ValueError):
            store.Workspace(fake_root / ".local/escape").initialize(reset=True)
        self.assertEqual(sentinel.read_text(), "DO_NOT_CHANGE")


if __name__ == "__main__":
    unittest.main()
