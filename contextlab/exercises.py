"""Deliberately broken cases and concrete corrections using the shared pipeline."""
import copy
from dataclasses import asdict
import math

from .pipeline import CASE, Pipeline, case_state, fixture_support, make_memory, memory_usable, query_graph, build_graph, reduce_tool_output, replay
from .retrieval import CapabilityUnavailable, heuristic_rerank, rrf
from .store import AS_OF, chunk_source, instant, validate_sources


def contract_scope_supported(scope):
    try:
        return all(scope.get(k) == v for k, v in {"principal": "service-reader", "tenant": "northstar-retail", "team": "service-operations", "branch": "northstar-v3"}.items()) and instant(scope["as_of"]) == instant(AS_OF) and instant(scope.get("knowledge_at") or scope["as_of"]) == instant(AS_OF)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _exercise_contract(number, result):
    """Recompute finite exercise predicates from observations, never from its status."""
    checks = []
    def check(name, observed, expected):
        checks.append({"name": name, "observed": observed, "expected": expected, "passed": type(observed) is type(expected) and observed == expected})
    def get(*keys):
        value = result
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value
    def assessment(value):
        return isinstance(value, dict) and value.get("status") == "observed" and isinstance(value.get("answer"), str) and bool(value["answer"]) and value.get("business_actions") == [] and value.get("state", {}).get("fulfillment_status") == "unknown" and value.get("state", {}).get("automatic_refund_authorized") is False and value.get("context_serialized_utf8_bytes", math.inf) <= value.get("context_budget_utf8_bytes", -1)
    check("canonical_exercise_scope", contract_scope_supported(result.get("scope", {})), True)
    check("canonical_fixture_unchanged", result.get("canonical_fixture_mutated"), False)
    if number == 1:
        check("unattributed_envelope_rejected", get("broken_rejected"), True)
        check("corrected_envelopes_validated", get("corrected_validated"), True)
    elif number == 2:
        check("fragment_omits_refund_rule", get("broken", "refund_rule_present"), False)
        check("complete_policy_keeps_refund_rule", get("corrected", "refund_rule_present"), True)
        check("fragment_is_shorter", isinstance(get("broken", "first_fragment"), str) and isinstance(get("corrected", "whole_policy"), str) and len(get("broken", "first_fragment")) < len(get("corrected", "whole_policy")), True)
    elif number in {3, 8}:
        check("wrong_scope_or_forged_check_rejected", get("broken_rejected"), True)
        check("corrected_invoice", get("corrected", "invoice_id"), "INV-SYN-4817")
        check("corrected_case", get("corrected", "case_id"), CASE)
        check("purchase_still_pending", get("corrected", "purchase_check_complete"), False)
        check("case_still_pending", get("corrected", "case_check_complete"), False)
    elif number == 4:
        check("long_input_truncated", get("broken", "truncated"), True)
        check("short_input_not_truncated", get("corrected", "truncated"), False)
        check("long_count_exceeds_limit", type(get("broken", "untruncated_encoder_tokens")) is int and get("broken", "untruncated_encoder_tokens") > 256, True)
        check("short_count_within_limit", type(get("corrected", "untruncated_encoder_tokens")) is int and 0 < get("corrected", "untruncated_encoder_tokens") <= 256, True)
    elif number == 5:
        check("raw_score_units_incomparable", get("broken", "comparable_units"), False)
        check("rank_fusion_named", get("corrected", "method"), "RRF offset 60")
        rows = get("corrected", "ranking")
        valid = isinstance(rows, list) and bool(rows)
        for row in rows if isinstance(rows, list) else []:
            try:
                contributions = row["contributions"]
                valid = valid and row["method"] == "hybrid_rrf" and bool(contributions) and all(math.isfinite(c["rrf_contribution"]) and c["rrf_contribution"] > 0 for c in contributions) and math.isclose(row["score"], sum(c["rrf_contribution"] for c in contributions), rel_tol=0, abs_tol=1e-12)
            except (KeyError, TypeError, ValueError):
                valid = False
        check("fusion_has_checked_rank_contributions", bool(valid), True)
    elif number == 6:
        check("underbudget_refuses", get("broken", "status"), "insufficient_evidence")
        check("underbudget_answer_absent", get("broken", "answer"), None)
        check("corrected_bundle_and_budget_sufficient", assessment(get("corrected")), True)
    elif number == 7:
        check("broken_locator_valid", get("broken", "citation_structurally_valid"), True)
        check("unsupported_claim_not_supported", get("broken", "fixture_support_label"), False)
        check("corrected_locator_valid", get("corrected", "citation_structurally_valid"), True)
        check("corrected_claim_supported", get("corrected", "fixture_support_label"), True)
    elif number == 9:
        temporal = get("temporal") or {}
        expected = [("2026-04-14T09:10:00Z", False), ("2026-04-14T09:22:00Z", False), ("2026-04-14T09:26:00Z", False), ("2026-04-14T09:30:00Z", True)]
        observed = [(r.get("query_at"), r.get("observation_eligible")) for r in temporal.get("independent_observation_exercise", []) if isinstance(r, dict)]
        check("publication_ingestion_index_boundaries", observed, expected)
        check("historical_deleted_note_visible_only_then", "SYN-DELETED-NOTE@1" in temporal.get("then_only_refs", []), True)
        check("corrected_revision_visible_now", "SYN-REVISION-NOTE@2" in temporal.get("now_only_refs", []), True)
        check("scratch_deletion_removed_refs", bool(temporal.get("live_projection_deletion_exercise", {}).get("removed_refs")), True)
    elif number == 10:
        check("invented_memory_unusable", get("broken", "usable"), False)
        check("rebuilt_memory_usable", get("corrected", "usable"), True)
    elif number == 11:
        check("unsupported_edge_not_returned", get("unsupported_edge_returned"), False)
        rows = get("corrected")
        check("corrected_edges_sourced_without_delivery_claim", isinstance(rows, list) and bool(rows) and all(r.get("source_refs") and r.get("relation") != "delivered_color" for r in rows), True)
    elif number == 12:
        boundary = get("boundaries") or {}
        rows = boundary.get("tests", [])
        forbidden = {"SYN-HARBOR-CASE", "SYN-HARBOR-INVOICE", "SYN-HARBOR-POLICY", "SYN-INJECTION-TRAP", "SYN-INVENTORY-COUNT", "SYN-WAREHOUSE-CHECK", "SYN-INVENTORY-EXCEPTION"}
        check("boundary_report_observed", boundary.get("status"), "observed")
        check("three_query_cases_checked", isinstance(rows, list) and len({r.get("query") for r in rows}) == 3, True)
        check("no_forbidden_sources_returned", isinstance(rows, list) and bool(rows) and all(r.get("forbidden_source_hits") == 0 and not forbidden.intersection(r.get("returned_source_ids", [])) for r in rows), True)
    elif number == 13:
        check("changed_artifact_detected", get("broken", "status"), "drift_detected")
        check("artifact_change_named", "artifact_changed" in (get("broken", "changes") or []), True)
        check("corrected_reexecution_matches", get("corrected", "status"), "reexecuted_stable_fields_match")
        check("corrected_stable_hashes_equal", isinstance(get("corrected", "original_stable_sha256"), str) and get("corrected", "original_stable_sha256") == get("corrected", "replay_stable_sha256"), True)
    elif number == 14:
        check("deleted_report_prevents_answer", get("broken", "status"), "insufficient_evidence")
        check("deleted_report_answer_absent", get("broken", "answer"), None)
        check("report_projection_actually_deleted", "SYN-REPORT-104@1" in (get("deletion", "removed_refs") or []), True)
        check("explicit_reset_restores_assessment", assessment(get("corrected")), True)
    else:
        check("known_exercise", False, True)
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "scope": "finite canonical exercise predicates; not production or general semantic proof"}


def exercise_contract(number, result):
    try:
        if not isinstance(result, dict):
            raise TypeError("exercise observations must be an object")
        return _exercise_contract(number, result)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"passed": False, "checks": [{"name": "well_formed_observations", "passed": False}], "error_type": type(exc).__name__, "reason": str(exc)}


def finalize_exercise(number, result):
    contract = exercise_contract(number, result)
    return dict(result, status="observed_expected_failure_and_correction" if contract["passed"] else "exercise_contract_failed", contract=contract)


def rejection(action):
    try:
        action()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("deliberately invalid exercise was accepted")


def run_exercise(number, pipeline):
    workspace, scope = pipeline.workspace, pipeline.scope
    result = {"chapter": number, "scope": asdict(scope), "canonical_fixture_mutated": False}
    if not contract_scope_supported(result["scope"]) and number != 6:
        return finalize_exercise(number, dict(result, reason="This finite exercise requires the canonical Service Operations v3 clock/scope; use lab commands for other scenarios."))
    sources = workspace.sources()
    if number == 1:
        broken = copy.deepcopy(sources)
        broken[0].pop("provenance")
        result.update(broken=rejection(lambda: validate_sources(broken)), corrected="original attributed source envelopes pass validation")
        result["broken_rejected"] = True
        result["corrected_validated"] = validate_sources(sources) is None
    elif number == 2:
        policy = next(s for s in sources if s["source_id"] == "SYN-POLICY-RETURNS-V3")
        short = chunk_source(policy, 64)[0]
        full = chunk_source(policy, 360)[0]
        result.update(broken={"first_fragment": short["text"], "refund_rule_present": "never authorizes an automatic refund" in short["text"]}, corrected={"whole_policy": full["text"], "refund_rule_present": "never authorizes an automatic refund" in full["text"]}, lesson="A valid span can omit an exception; preserve the policy unit rather than treating a fragment as complete support.")
    elif number in {3, 8}:
        state = case_state(workspace, scope)
        output = {key: state[key] for key in ["tenant", "case_id", "invoice_id", "purchase_check_complete", "case_check_complete", "fulfillment_status", "source_refs"]}
        broken = dict(output, invoice_id="INV-SYN-4818") if number == 3 else dict(output, purchase_check_complete=True)
        result.update(broken=rejection(lambda: reduce_tool_output(broken, workspace, scope)), corrected=reduce_tool_output(output, workspace, scope), lesson="Search similarity and plausible tool text do not establish exact scope or completed checks.")
        result["broken_rejected"] = True
    elif number == 4:
        if not pipeline.include_dense:
            raise CapabilityUnavailable("truncation exercise requires the genuine local-model track")
        pipeline.retriever.build_dense()
        encoder = pipeline.retriever.encoder
        _, long_counts = encoder.encode(["policy " * 400 + "The required exception appears only at the end."])
        _, short_counts = encoder.encode(["Preserve the exception together with its policy rule."])
        result.update(broken={"untruncated_encoder_tokens": long_counts[0], "encoder_limit": 256, "truncated": long_counts[0] > 256}, corrected={"untruncated_encoder_tokens": short_counts[0], "truncated": short_counts[0] > 256}, lesson="Split or select coherent source units before encoding; truncation counts do not measure semantic retrieval quality.")
    elif number == 5:
        if not pipeline.include_dense:
            raise CapabilityUnavailable("fusion exercise requires both lexical and genuine dense rankings")
        query = "returns-v3 purchase case checks"
        lexical = pipeline.retriever.search(query, "lexical", 10)
        dense = pipeline.retriever.search(query, "dense", 10)
        result.update(broken={"operation": "add raw BM25-derived score to cosine", "comparable_units": False, "lexical_score_range": [min(r["score"] for r in lexical), max(r["score"] for r in lexical)], "dense_score_range": [min(r["score"] for r in dense), max(r["score"] for r in dense)]}, corrected={"method": "RRF offset 60", "ranking": rrf([lexical, dense])}, lesson="The metadata reranker remains a separately labeled heuristic, not a cross-encoder.")
    elif number == 6:
        result.update(broken=Pipeline(workspace, scope, budget=100).stage_14(), corrected=Pipeline(workspace, scope, budget=3600).stage_14())
    elif number == 7:
        source = next(s for s in workspace.eligible(scope) if s["source_id"] == "SYN-PURCHASE-4817")
        citation = {"ref": source["ref"], "char_start": 0, "char_end": len(source["content"]), "quote": source["content"]}
        result.update(broken=fixture_support(workspace, scope, "delivered_red", citation), corrected=fixture_support(workspace, scope, "purchase_two_blue_1250", citation))
    elif number == 9:
        result.update(temporal=pipeline.stage_9(), lesson="At 09:22 publication has occurred but ingestion and index readiness have not. Current disclosure grants still apply.")
    elif number == 10:
        memory = make_memory(case_state(workspace, scope), scope)
        bad = dict(memory, summary="The customer received red goods and a refund is approved.")
        result.update(broken={"summary": bad["summary"], "usable": memory_usable(bad, workspace, scope)}, corrected={"summary": memory["summary"], "usable": memory_usable(memory, workspace, scope)}, support_scope="deterministic fixture-summary validation, not general summarization entailment")
    elif number == 11:
        graph = build_graph(workspace, scope)
        graph["edges"].append({"subject": CASE, "relation": "delivered_color", "object": "red", "source_refs": ["SYN-PURCHASE-4817@1"], "trust": "authoritative_fixture", "tenant": scope.tenant})
        corrected = query_graph(graph, workspace, scope, CASE)
        result.update(broken="Injected a delivered-color edge citing a purchase record", corrected=corrected, unsupported_edge_returned=any(e["relation"] == "delivered_color" for e in corrected), support_scope="curated fixture graph projection with per-fact authorization; not universal entailment")
    elif number == 12:
        result.update(boundaries=pipeline.stage_12())
    elif number == 13:
        row = pipeline.run(14)
        path = workspace.path / row["artifact"]
        original = path.read_bytes()
        path.write_text("{}")
        broken = replay(workspace.path / row["receipt"], workspace, scope)
        path.write_bytes(original)
        corrected = replay(workspace.path / row["receipt"], workspace, scope, reexecute=True, model_dir=pipeline.retriever.model_dir)
        result.update(broken=broken, corrected=corrected)
    elif number == 14:
        result["deletion"] = workspace.delete_projection("SYN-REPORT-104", scope.as_of)
        broken = Pipeline(workspace, scope).stage_14()
        workspace.initialize(reset=True)
        corrected = Pipeline(workspace, scope).stage_14()
        result.update(broken=broken, corrected=corrected, correction_scope="explicit reset of an isolated synthetic teaching projection; not restoration of erased real customer data")
    else:
        raise ValueError("exercise chapter must be 1 through 14")
    return finalize_exercise(number, result)
