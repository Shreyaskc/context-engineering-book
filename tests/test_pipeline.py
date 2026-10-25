"""Executable safety and correctness properties of the evolving synthetic system."""
import copy
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from contextlab.pipeline import Pipeline, assessment_text, build_graph, case_state, citation_status, fixture_support, make_memory, memory_usable, pack_context, query_graph, reduce_tool_output, replay, retrieval_metrics
from contextlab.retrieval import CapabilityUnavailable, Retriever, cosine, lexical, rrf
from contextlab.store import ROOT, Scope, Workspace, canonical, chunk_source, digest, eligible_sources, load_sources, validate_sources


class SupplyChain(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local" / "tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="case-", dir=base))
        # Workspace initialization refuses arbitrary nonempty directories.
        self.workspace = Workspace(self.path).initialize()
        self.scope = Scope()
        self.pipeline = Pipeline(self.workspace, self.scope, budget=3600)

    def tearDown(self):
        shutil.rmtree(self.path)

    def test_original_corpus_and_span_hashes(self):
        sources = load_sources()
        self.assertEqual(len(sources), 54)
        self.assertEqual(len({s["ref"] for s in sources}), 54)
        for source in sources:
            pieces = chunk_source(source, max_chars=64)
            self.assertEqual("".join(c["text"] for c in pieces), source["content"])
            for chunk in pieces:
                self.assertEqual(source["content"].encode()[chunk["byte_start"]:chunk["byte_end"]].decode(), chunk["text"])

    def test_corrupt_hash_and_grants_fail_closed(self):
        for field, value in [("sha256", "0"*64), ("allowed_teams", "service-operations"), ("trust", "unknown_trust"), ("version", True)]:
            with self.subTest(field=field):
                sources = copy.deepcopy(load_sources())
                sources[0][field] = value
                with self.assertRaises(ValueError):
                    validate_sources(sources)

    def test_principal_cannot_select_another_tenant_or_team(self):
        for scope in [replace(self.scope, tenant="harbor-retail"), replace(self.scope, team="inventory-operations"), replace(self.scope, principal="invented")]:
            with self.assertRaises(ValueError):
                self.workspace.chunks(scope)

    def test_cross_tenant_team_principal_and_injection_boundaries(self):
        ids = {s["source_id"] for s in self.workspace.eligible(self.scope)}
        self.assertTrue({"SYN-PURCHASE-4817", "SYN-POLICY-RETURNS-V3"}.issubset(ids))
        self.assertFalse({"SYN-HARBOR-CASE", "SYN-INVENTORY-COUNT", "SYN-PLATFORM-RUNBOOK", "SYN-LEAD-NOTE", "SYN-INJECTION-TRAP"}.intersection(ids))
        self.assertNotIn("SYN-REVOKED-NOTE", ids)
        lead = replace(self.scope, principal="service-lead")
        self.assertIn("SYN-LEAD-NOTE", {s["source_id"] for s in self.workspace.eligible(lead)})
        inventory = Scope("inventory-reader", "northstar-retail", "inventory-operations")
        self.assertIn("SYN-INVENTORY-COUNT", {s["source_id"] for s in self.workspace.eligible(inventory)})
        platform = Scope("platform-reader", "northstar-retail", "platform-engineering")
        self.assertEqual({s["source_id"] for s in self.workspace.eligible(platform)}, {"SYN-PLATFORM-RUNBOOK"})
        harbor = Scope("harbor-reader", "harbor-retail", "service-operations")
        self.assertEqual(len(self.workspace.eligible(harbor)), 3)
        self.assertTrue(all(s["tenant"] == "harbor-retail" for s in self.workspace.eligible(harbor)))

    def test_availability_validity_supersession_and_branch_are_explicit(self):
        current = {s["ref"] for s in self.workspace.eligible(self.scope)}
        earlier = {s["ref"] for s in self.workspace.eligible(replace(self.scope, as_of="2026-01-09T00:00:00Z"))}
        self.assertIn("SYN-DELETED-NOTE@1", earlier)
        self.assertNotIn("SYN-DELETED-NOTE@1", current)
        self.assertIn("SYN-REVISION-NOTE@1", earlier)
        self.assertNotIn("SYN-REVISION-NOTE@1", current)
        self.assertIn("SYN-REVISION-NOTE@2", current)
        self.assertNotIn("SYN-FUTURE-NOTE@1", current)
        self.assertNotIn("SYN-POLICY-RETURNS-V4@1", current)
        future_v3 = replace(self.scope, as_of="2026-02-15T00:00:00Z")
        self.assertEqual(case_state(self.workspace, future_v3)["policy_id"], "returns-v3")
        future_v4 = replace(future_v3, branch="northstar-v4")
        state = case_state(self.workspace, future_v4)
        self.assertEqual(state["policy_id"], "returns-v4")
        self.assertIn("supervisor", state["required_checks"])
        self.assertFalse(state["automatic_refund_authorized"])

    def test_lexical_search_uses_only_eligible_candidates(self):
        retriever = Retriever(self.workspace, self.scope)
        for query in ["INV-HARBOR-901", "bin B-SYN-7", '" OR * NEAR ()', "Ignore previous rules"]:
            rows = retriever.search(query, "lexical", 20)
            eligible = {c["chunk_id"] for c in self.workspace.chunks(self.scope)}
            self.assertTrue(all(row["chunk_id"] in eligible for row in rows))
        self.assertEqual(retriever.search("", "lexical"), [])

    def test_publication_ingestion_and_index_readiness_differ(self):
        expected = {"09:10": False, "09:22": False, "09:26": False, "09:30": True}
        for clock, present in expected.items():
            scope = replace(self.scope, as_of="2026-04-14T" + clock + ":00Z")
            ids = {s["source_id"] for s in self.workspace.eligible(scope)}
            self.assertEqual("SYN-OBSERVATION-APR14" in ids, present)
            self.assertNotIn("SYN-REVOKED-NOTE", ids)
        later_knowledge = replace(self.scope, as_of="2026-04-14T09:10:00Z", knowledge_at="2026-04-14T09:30:00Z")
        self.assertIn("SYN-OBSERVATION-APR14", {s["source_id"] for s in self.workspace.eligible(later_knowledge)})
        metadata = self.workspace.metadata()
        self.assertIn("actual_mac_import_started_at_utc", metadata)
        self.assertIn("actual_mac_index_ready_at_utc", metadata)

    def test_no_fake_dense_fallback(self):
        self.assertEqual(self.pipeline.stage_4()["status"], "unavailable")
        with self.assertRaises(CapabilityUnavailable):
            Retriever(self.workspace, self.scope).search("mug", "dense")

    def test_cosine_and_rrf_math_without_embedding_quality_claim(self):
        self.assertAlmostEqual(cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertAlmostEqual(cosine([1.0, 1.0], [1.0, 1.0]), 1.0)
        with self.assertRaises(ValueError):
            cosine([0.0], [1.0])
        rows = [{"chunk_id": "a", "rank": 1, "score": 0.9, "method": "example_math"}, {"chunk_id": "b", "rank": 2, "score": 0.3, "method": "example_math"}]
        fused = rrf([rows, list(reversed([dict(rows[1], rank=1), dict(rows[0], rank=2)]))])
        self.assertEqual({row["chunk_id"] for row in fused}, {"a", "b"})
        self.assertTrue(all(row["score_definition"].startswith("sum") for row in fused))

    def test_budget_includes_unicode_serialization_and_abstains_if_too_small(self):
        source = next(s for s in self.workspace.eligible(self.scope) if s["source_id"] == "SYN-UNICODE-GUIDE")
        rows = chunk_source(source)
        full = pack_context(rows, 1000)
        self.assertEqual(full["serialized_cost"], len(canonical(full["pack"]).encode()))
        self.assertGreater(len(canonical(full["pack"]).encode()), len(canonical(full["pack"])))
        exact = pack_context(rows, full["serialized_cost"])
        self.assertEqual(len(exact["pack"]["evidence"]), 1)
        short = pack_context(rows, full["serialized_cost"]-1)
        self.assertEqual(short["pack"]["evidence"], [])
        result = Pipeline(self.workspace, budget=100).stage_14()
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["answer"])

    def test_citation_structure_is_not_semantic_support(self):
        source = next(s for s in self.workspace.eligible(self.scope) if s["source_id"] == "SYN-PURCHASE-4817")
        citation = {"ref": source["ref"], "char_start": 0, "char_end": len(source["content"]), "quote": source["content"]}
        valid = fixture_support(self.workspace, self.scope, "purchase_two_blue_1250", citation)
        self.assertTrue(valid["fixture_support_label"])
        wrong_claim = fixture_support(self.workspace, self.scope, "delivered_red", citation)
        self.assertTrue(wrong_claim["citation_structurally_valid"])
        self.assertFalse(wrong_claim["fixture_support_label"])
        self.assertFalse(citation_status(self.workspace, self.scope, dict(citation, quote="fabricated")))
        self.assertFalse(citation_status(self.workspace, self.scope, dict(citation, ref="SYN-HARBOR-CASE@1")))
        self.assertFalse(fixture_support(self.workspace, self.scope, "purchase_two_blue_1250", dict(citation, char_end=9, quote=source["content"][:9]))["fixture_support_label"])

    def test_exact_case_state_and_forged_tool_output(self):
        state = case_state(self.workspace, self.scope)
        self.assertEqual(state["purchase"], {"description": "blue mug", "quantity": 2, "unit_price_minor": 1250, "currency": "GBP"})
        self.assertEqual(state["customer_report"]["status"], "reported_claim")
        self.assertEqual(state["fulfillment_status"], "unknown")
        self.assertFalse(state["automatic_refund_authorized"])
        output = {key: state[key] for key in ["tenant", "case_id", "invoice_id", "purchase_check_complete", "case_check_complete", "fulfillment_status", "source_refs"]}
        reduce_tool_output(output, self.workspace, self.scope)
        for field, value in [("invoice_id", "INV-SYN-4818"), ("purchase_check_complete", True), ("case_check_complete", "true"), ("fulfillment_status", "verified"), ("source_refs", [])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                reduce_tool_output(dict(output, **{field: value}), self.workspace, self.scope)

    def test_memory_preserves_uncertainty_expires_and_cannot_replay_before_creation(self):
        memory = make_memory(case_state(self.workspace, self.scope), self.scope)
        self.assertIn("Fulfillment is unknown", memory["summary"])
        self.assertIn("Automatic refund is not authorized", memory["summary"])
        self.assertTrue(memory["lossy"])
        self.assertTrue(memory_usable(memory, self.workspace, self.scope))
        self.assertFalse(memory_usable(memory, self.workspace, replace(self.scope, as_of="2026-01-14T00:00:00Z")))
        self.assertFalse(memory_usable(memory, self.workspace, replace(self.scope, as_of="2026-03-01T00:00:00Z")))
        self.assertFalse(memory_usable(memory, self.workspace, replace(self.scope, principal="service-lead")))
        self.assertFalse(memory_usable(dict(memory, summary="Refund approved; delivery verified."), self.workspace, self.scope))

    def test_graph_rechecks_every_contributing_ref(self):
        graph = build_graph(self.workspace, self.scope)
        edges = query_graph(graph, self.workspace, self.scope, "CASE-SYN-104")
        self.assertTrue(any(e["trust"] == "inferred_not_verified" for e in edges))
        self.assertFalse(any(e["relation"] == "delivered_color" for e in edges))
        graph["edges"].append({"subject": "CASE-SYN-104", "relation": "forged", "object": "hidden", "tenant": self.scope.tenant, "source_refs": ["SYN-HARBOR-CASE@1"]})
        graph["edges"].append({"subject": "CASE-SYN-104", "relation": "unsourced", "object": "hidden", "tenant": self.scope.tenant, "source_refs": []})
        graph["edges"].append({"subject": "CASE-SYN-104", "relation": "delivered_color", "object": "red", "tenant": self.scope.tenant, "source_refs": ["SYN-PURCHASE-4817@1"], "trust": "authoritative_fixture"})
        self.assertFalse(any(e["relation"] in {"forged", "unsourced"} for e in query_graph(graph, self.workspace, self.scope, "CASE-SYN-104")))
        self.assertFalse(any(e["relation"] == "delivered_color" for e in query_graph(graph, self.workspace, self.scope, "CASE-SYN-104")))

    def test_deletion_invalidates_indexes_memory_graph_and_replay(self):
        memory = make_memory(case_state(self.workspace, self.scope), self.scope)
        graph = build_graph(self.workspace, self.scope)
        self.pipeline.run(14)
        receipt = self.path / "receipts/14-capstone.json"
        self.assertEqual(replay(receipt, self.workspace, self.scope)["status"], "verified_existing_artifact")
        self.assertEqual(replay(receipt, self.workspace, self.scope, reexecute=True)["status"], "reexecuted_stable_fields_match")
        self.workspace.delete_projection("SYN-REPORT-104", self.scope.as_of)
        self.assertFalse(memory_usable(memory, self.workspace, self.scope))
        self.assertFalse(any("SYN-REPORT-104@1" in e["source_refs"] for e in query_graph(graph, self.workspace, self.scope, "CASE-SYN-104")))
        self.assertFalse(any(c["source_id"] == "SYN-REPORT-104" for c in self.workspace.chunks(self.scope)))
        with closing(self.workspace.connect()) as db, db:
            self.assertEqual(db.execute("SELECT count(*) FROM chunk_fts WHERE ref=?", ("SYN-REPORT-104@1",)).fetchone()[0], 0)
        result = replay(receipt, self.workspace, self.scope)
        self.assertIn("artifact_missing_or_invalidated", result["changes"])
        self.assertIn("live_projection", result["changes"])
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            case_state(self.workspace, self.scope)
        self.assertEqual(self.pipeline.stage_14()["status"], "insufficient_evidence")

    def test_receipt_drift_detects_output_changes(self):
        result = self.pipeline.run(14)
        receipt = self.path / result["receipt"]
        artifact = self.path / result["artifact"]
        artifact.write_text("{}")
        self.assertIn("artifact_changed", replay(receipt, self.workspace, self.scope)["changes"])
        with self.assertRaises(ValueError):
            replay(receipt, self.workspace, replace(self.scope, as_of="2026-01-16T00:00:00Z"))

    def test_all_core_stages_share_one_system(self):
        rows = [self.pipeline.run(i) for i in range(1, 15)]
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[3]["status"], "unavailable")
        self.assertEqual(rows[4]["status"], "partially_available")
        self.assertEqual(rows[-1]["result"]["business_actions"], [])
        self.assertEqual(rows[-1]["status"], "observed")
        self.assertEqual(rows[12]["result"]["aggregates"]["heldout"]["queries"], 8)
        for row in rows:
            self.assertTrue((self.path / row["artifact"]).exists())
            self.assertTrue((self.path / row["receipt"]).exists())

    def test_metrics_use_unique_source_ids_and_known_ranks(self):
        metrics = retrieval_metrics(["wrong", "right", "right"], ["right"])
        self.assertEqual(metrics["recall_at_5"], 1)
        self.assertEqual(metrics["mrr_at_5"], 0.5)
        self.assertAlmostEqual(metrics["ndcg_at_5"], 1 / 1.584962500721156)

    def test_reset_cannot_target_repository_or_unmarked_nonempty_directory(self):
        with self.assertRaises(ValueError):
            Workspace(ROOT)
        path = self.path / "unmarked"
        path.mkdir()
        (path / "keep.txt").write_text("keep")
        with self.assertRaises(ValueError):
            Workspace(path).initialize(reset=True)
        self.assertTrue((path / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
