"""One evolving supply chain shared by all fourteen chapter entry points."""
from dataclasses import asdict, replace
import datetime
import json
import math
import platform
import sqlite3
import sys
import time

from .retrieval import CapabilityUnavailable, Retriever, heuristic_rerank, lexical
from .store import ROOT, CORPUS, IDENTITIES, INGESTION_EVENTS, ACCESS_POLICY, Scope, Workspace, canonical, digest, eligible_sources, load_sources, validate_sources

STAGES = ["evidence-inventory", "corpus", "lexical", "dense", "hybrid-rerank", "pack", "claims", "structured", "temporal", "memory", "graph", "boundaries", "evaluate", "capstone"]
CASE = "CASE-SYN-104"
INVOICE = "INV-SYN-4817"
QUERY = "CASE-SYN-104 INV-SYN-4817 returns-v3 purchase case checks customer report fulfillment unknown"
REQUIRED = ["SYN-POLICY-RETURNS-V3", "SYN-PURCHASE-4817", "SYN-CASE-104", "SYN-REPORT-104", "SYN-FULFILLMENT-104"]


class CaseEvidenceUnavailable(ValueError):
    """An exact authorized case/policy record is absent or ambiguous.

    Encoder integrity, malformed input and runtime failures are different errors.
    """


def input_hashes():
    paths = [CORPUS, IDENTITIES, INGESTION_EVENTS, ACCESS_POLICY, ROOT / "fixtures/case-syn-104.json", ROOT / "fixtures/queries.json", ROOT / "fixtures/claim-support.json", ROOT / "fixtures/encoder-spec.json", ROOT / "data/provenance.json", ROOT / "contracts/chapters.json"]
    paths += [ROOT / "requirements" / name for name in ["core.txt", "ml-observed.txt", "ml-macos-arm64-py312.lock"] if (ROOT / "requirements" / name).is_file()]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}


def code_hashes():
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted((ROOT / "contextlab").glob("*.py"))}


def projection_hash(workspace, scope):
    return digest(canonical({"sources": workspace.sources(), "tombstones": sorted(workspace.tombstones()), "eligible_chunks": workspace.chunks(scope)}))


def pack_context(rows, budget):
    if budget < len(canonical({"evidence": []}).encode()):
        raise ValueError("byte budget is smaller than the empty pack serialization")
    pack, excluded = {"evidence": []}, []
    for row in rows:
        entry = {key: row[key] for key in ["chunk_id", "ref", "source_id", "source_sha256", "char_start", "char_end", "text", "trust"]}
        proposal = {"evidence": pack["evidence"] + [entry]}
        cost = len(canonical(proposal).encode())
        if cost <= budget:
            pack = proposal
        else:
            excluded.append({"chunk_id": row["chunk_id"], "reason": "whole evidence span does not fit serialized UTF-8 byte budget"})
    return {"pack": pack, "budget_unit": "utf8_bytes", "budget": budget, "serialized_cost": len(canonical(pack).encode()), "serialization": "canonical JSON; ensure_ascii=False; sorted keys; compact separators", "scope": "evidence object only; not complete backend prompt or model-token upper bound", "excluded": excluded}


def validate_tool_output(output, scope, case_id=CASE, invoice_id=INVOICE):
    expected = {"tenant", "case_id", "invoice_id", "purchase_check_complete", "case_check_complete", "fulfillment_status", "source_refs"}
    if set(output) != expected:
        raise ValueError("tool output has missing or unexpected fields")
    if (output["tenant"], output["case_id"], output["invoice_id"]) != (scope.tenant, case_id, invoice_id):
        raise ValueError("tool result does not match exact requested tenant/case/invoice scope")
    if type(output["purchase_check_complete"]) is not bool or type(output["case_check_complete"]) is not bool:
        raise ValueError("check states must be JSON booleans")
    if output["fulfillment_status"] not in {"unknown", "verified"}:
        raise ValueError("invalid fulfillment enum")
    if not isinstance(output["source_refs"], list) or not all(isinstance(ref, str) for ref in output["source_refs"]):
        raise ValueError("source_refs must be a string list")


def reduce_tool_output(output, workspace, scope):
    validate_tool_output(output, scope)
    authoritative = case_state(workspace, scope)
    if set(output["source_refs"]) != set(authoritative["source_refs"]):
        raise ValueError("tool source refs do not match currently eligible exact case evidence")
    for field in ["purchase_check_complete", "case_check_complete", "fulfillment_status"]:
        if output[field] != authoritative[field]:
            raise ValueError("tool output cannot promote unsupported verified state: " + field)
    return authoritative


def case_state(workspace, scope):
    sources = workspace.eligible(scope)
    policy_id = "returns-v4" if scope.branch == "northstar-v4" else "returns-v3"
    policy = [s for s in sources if s["kind"] == "policy" and s["record"].get("policy_id") == policy_id]
    lookup = {}
    for kind in ["purchase", "case", "report", "fulfillment"]:
        rows = [s for s in sources if s["kind"] == kind and s["record"].get("case_id") == CASE and s["record"].get("invoice_id") == INVOICE]
        if len(rows) != 1:
            raise CaseEvidenceUnavailable("missing or ambiguous exact scoped " + kind + " evidence")
        lookup[kind] = rows[0]
    if len(policy) != 1:
        raise CaseEvidenceUnavailable("missing or ambiguous branch-specific policy")
    lookup["policy"] = policy[0]
    record = lookup["purchase"]["record"]
    report = lookup["report"]["record"]
    output = {"tenant": scope.tenant, "case_id": CASE, "invoice_id": INVOICE, "purchase_check_complete": record["purchase_check_complete"], "case_check_complete": lookup["case"]["record"]["case_check_complete"], "fulfillment_status": lookup["fulfillment"]["record"]["fulfillment_status"], "source_refs": [s["ref"] for s in lookup.values()]}
    validate_tool_output(output, scope)
    # This reducer does not promote tool text or a reported claim to a completed check.
    return dict(output, purchase={key: record[key] for key in ["description", "quantity", "unit_price_minor", "currency"]}, customer_report={"description": report["reported_description"], "quantity": report["reported_quantity"], "status": "reported_claim"}, policy_id=policy_id, required_checks=lookup["policy"]["record"]["required_checks"], automatic_refund_authorized=lookup["policy"]["record"]["automatic_refund_authorized"])


def citation_status(workspace, scope, citation):
    source = next((s for s in workspace.eligible(scope) if s["ref"] == citation.get("ref")), None)
    if source is None:
        return False
    start, end = citation.get("char_start"), citation.get("char_end")
    return type(start) is int and type(end) is int and 0 <= start < end <= len(source["content"]) and citation.get("quote") == source["content"][start:end]


def fixture_support(workspace, scope, claim_key, citation):
    structural = citation_status(workspace, scope, citation)
    source = next((s for s in workspace.eligible(scope) if s["ref"] == citation.get("ref")), None)
    # These are finite curated support labels for exact full-source fixture claims.
    # Arbitrary natural-language claims and partial spans are not adjudicated here.
    labels = json.loads((ROOT / "fixtures/claim-support.json").read_text())["labels"]
    label = labels.get(claim_key, {})
    supported = bool(structural and source and label.get("ref") == source["ref"] and label.get("source_sha256") == source["sha256"] and citation["char_start"] == 0 and citation["char_end"] == len(source["content"]))
    return {"claim_key": claim_key, "citation_structurally_valid": structural, "fixture_support_label": supported, "support_scope": "curated full-source fixture label, not general semantic entailment", "citation": citation}


def make_memory(state, scope):
    summary = assessment_text(state)
    from .store import instant
    expiry = (instant(scope.as_of) + datetime.timedelta(days=7)).isoformat()
    return {"summary": summary, "source_refs": state["source_refs"], "tenant": scope.tenant, "team": scope.team, "principal": scope.principal, "branch": scope.branch, "as_of": scope.as_of, "expires_at": expiry, "trust": "derived_fixture_summary", "lossy": True, "omitted_fields": ["full source wording", "source ordering", "individual source time fields; recheck sources before reuse"], "correction": "rebuild from currently eligible exact scoped source records", "admission_purpose": "single synthetic case teaching exercise"}


def memory_usable(memory, workspace, scope):
    from .store import instant
    if not isinstance(memory, dict):
        return False
    dependencies = memory.get("source_refs")
    if not isinstance(dependencies, list) or not dependencies or not all(isinstance(ref, str) for ref in dependencies):
        return False
    if len(dependencies) != len(set(dependencies)):
        return False
    refs = {s["ref"] for s in workspace.eligible(scope)}
    try:
        state = case_state(workspace, scope)
        expected_summary = assessment_text(state)
        expected_dependencies = set(state["source_refs"])
        valid_time = instant(memory["as_of"]) <= instant(scope.as_of) < instant(memory["expires_at"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return False
    return memory.get("summary") == expected_summary and all(memory.get(k) == getattr(scope, k) for k in ["tenant", "team", "principal", "branch"]) and valid_time and set(dependencies) == expected_dependencies and expected_dependencies.issubset(refs)


def assessment_text(state):
    purchase, report = state["purchase"], state["customer_report"]
    minor = purchase["unit_price_minor"]
    checks = ", ".join(check for check in state["required_checks"] if not state.get(check + "_check_complete", False))
    refund = "authorized" if state["automatic_refund_authorized"] else "not authorized"
    check_text = "Required checks remain pending: " + checks if checks else "Required checks are complete"
    return f'{state["invoice_id"]} lists {purchase["quantity"]} {purchase["description"]}(s) at {purchase["currency"]} {minor//100}.{minor%100:02} each. The customer reports {report["quantity"]} {report["description"]}(s). Fulfillment is {state["fulfillment_status"]}. {check_text}. Automatic refund is {refund}.'


def build_graph(workspace, scope):
    sources = {s["source_id"]: s for s in workspace.eligible(scope)}
    edges = []
    specifications = [("SYN-PURCHASE-4817", INVOICE, "lists_purchase", "purchase"), ("SYN-REPORT-104", CASE, "customer_reports", "report"), ("SYN-FULFILLMENT-104", CASE, "fulfillment_status", "fulfillment"), ("SYN-CASE-104", CASE, "references_invoice", "case")]
    for sid, subject, relation, target in specifications:
        if sid in sources:
            source = sources[sid]
            record = source["record"]
            if target == "purchase":
                target = {key: record[key] for key in ["description", "quantity", "unit_price_minor", "currency"]}
            elif target == "report":
                target = {key: record[key] for key in ["reported_description", "reported_quantity", "verified"]}
            else:
                target = record.get("fulfillment_status", record.get("invoice_id"))
            edges.append({"subject": subject, "relation": relation, "object": target, "source_refs": [source["ref"]], "trust": source["trust"], "tenant": source["tenant"]})
    if all(sid in sources for sid in ["SYN-PURCHASE-4817", "SYN-REPORT-104"]):
        edges.append({"subject": CASE, "relation": "possible_report_purchase_discrepancy", "object": "requires_review", "source_refs": [sources[sid]["ref"] for sid in ["SYN-PURCHASE-4817", "SYN-REPORT-104"]], "trust": "inferred_not_verified", "tenant": scope.tenant})
    return {"edges": edges, "as_of": scope.as_of, "note": "No delivered-color edge is licensed by this evidence; every traversed contributing ref must remain eligible."}


def query_graph(graph, workspace, scope, subject):
    from .store import instant
    if instant(scope.as_of) < instant(graph["as_of"]):
        return []
    refs = {s["ref"] for s in workspace.eligible(scope)}
    fixture_supported = {canonical(edge) for edge in build_graph(workspace, scope)["edges"]}
    return [edge for edge in graph["edges"] if edge["subject"] == subject and edge["tenant"] == scope.tenant and bool(edge["source_refs"]) and set(edge["source_refs"]).issubset(refs) and canonical(edge) in fixture_supported]


def retrieval_metrics(ids, relevant, k=5):
    """Binary source gains; deduplicate before cutoff; ideal uses all unique labels.

    DCG@5 = sum(gain at rank i / log2(i+1)); IDCG includes up to five
    relevant sources. No labels means null recall/nDCG and MRR 0.
    """
    ids = list(dict.fromkeys(ids))[:k]
    labels = set(relevant)
    found = [1 if sid in labels else 0 for sid in ids]
    dcg = sum(gain / math.log2(i+2) for i, gain in enumerate(found))
    ideal = sum(1 / math.log2(i+2) for i in range(min(k, len(labels))))
    return {"recall_at_5": len(labels.intersection(ids)) / len(labels) if labels else None, "mrr_at_5": next((1/(i+1) for i, gain in enumerate(found) if gain), 0.0), "ndcg_at_5": dcg / ideal if ideal else None}


def evaluate(workspace, scope, retriever, include_dense):
    fixture = json.loads((ROOT / "fixtures/queries.json").read_text())
    if asdict(scope) != fixture["scope"]:
        raise ValueError("benchmark labels are valid only for the frozen fixture scope and clock")
    methods = ["lexical"] + (["dense", "hybrid"] if include_dense else [])
    rows = []
    for query in fixture["queries"]:
        results = {}
        for method in methods:
            started = time.perf_counter()
            candidates = retriever.search(query["query"], method, 15)
            elapsed = time.perf_counter() - started
            ids = list(dict.fromkeys(c["source_id"] for c in candidates))[:5]
            results[method] = dict(retrieval_metrics(ids, query["relevant"]), ranked_source_ids=ids, latency_seconds=elapsed)
        rows.append(dict(query, results=results))
    aggregates = {}
    for split in ["dev", "heldout"]:
        selection = [row for row in rows if row["split"] == split]
        aggregates[split] = {"queries": len(selection), "methods": {method: {metric: sum(row["results"][method][metric] for row in selection) / len(selection) for metric in ["recall_at_5", "mrr_at_5", "ndcg_at_5"]} for method in methods}}
    comparisons = {}
    for method in methods[1:]:
        counts = {"wins": 0, "losses": 0, "ties": 0}
        for row in rows:
            delta = row["results"][method]["ndcg_at_5"] - row["results"]["lexical"]["ndcg_at_5"]
            counts["ties" if abs(delta) <= 1e-12 else "wins" if delta > 0 else "losses"] += 1
        comparisons[method + "_vs_lexical"] = dict(counts, criterion="per-query nDCG@5; tie tolerance 1e-12; 20 synthetic queries")
    return {"status": "observed", "label_sha256": digest((ROOT / "fixtures/queries.json").read_bytes()), "methods": methods, "aggregates": aggregates, "comparisons": comparisons, "queries": rows, "unavailable": [] if include_dense else ["dense", "hybrid"], "limitations": ["small manually labeled synthetic corpus; not a general retrieval-quality claim", "held-out partition was measured; do not tune on it and continue calling it unseen", "no learned reranker, semantic-entailment model, or answer-quality benchmark"]}


class Pipeline:
    def __init__(self, workspace, scope=Scope(), track="core", model_dir=None, budget=3600):
        scope.validate()
        self.workspace, self.scope, self.track = workspace, scope, track
        self.retriever = Retriever(workspace, scope, model_dir)
        self.budget = budget
        self.include_dense = track == "local-model"

    def assembly_rows(self):
        # Exact case/purchase/policy selection is explicit, separate from search ranking.
        state = case_state(self.workspace, self.scope)
        refs = set(state["source_refs"])
        chunks = self.workspace.chunks(self.scope)
        required = [dict(c, rank=i+1, method="exact_scoped_record_assembly", score=1.0) for i, c in enumerate(chunks) if c["ref"] in refs]
        optional = self.retriever.search(QUERY, "hybrid" if self.include_dense else "lexical", 10)
        required_ids = {row["chunk_id"] for row in required}
        return required + [row for row in optional if row["chunk_id"] not in required_ids]

    def run(self, number):
        if not 1 <= number <= 14:
            raise ValueError("chapter must be 1 through 14")
        started = time.perf_counter()
        output = getattr(self, "stage_" + str(number))()
        path = self.workspace.artifact(f"{number:02}-{STAGES[number-1]}", output)
        receipt = {"schema_version": 1, "stage": STAGES[number-1], "chapter": number, "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "scope": asdict(self.scope), "snapshot": self.workspace.metadata(), "track": self.track, "settings": {"budget_unit": "utf8_bytes", "evidence_budget": self.budget}, "command_argv": sys.argv, "versions": {"python": platform.python_version(), "system": platform.system(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version}, "input_sha256": input_hashes(), "code_sha256": code_hashes(), "projection_sha256": projection_hash(self.workspace, self.scope), "encoder": self.retriever.encoder.metadata if self.retriever.encoder else None, "artifact": str(path.relative_to(self.workspace.path)), "artifact_sha256": digest(path.read_bytes()), "wall_seconds": time.perf_counter()-started, "status": output.get("status", "observed"), "counted_review_cycle": False, "model_runtime_usage": None, "usage_note": "No generation is performed by the deterministic pipeline. Optional Ollama probe records actual generation usage separately."}
        receipt_path = self.workspace.path / "receipts" / f"{number:02}-{STAGES[number-1]}.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return {"stage": STAGES[number-1], "status": receipt["status"], "artifact": receipt["artifact"], "artifact_sha256": receipt["artifact_sha256"], "receipt": str(receipt_path.relative_to(self.workspace.path)), "result": output}

    def stage_1(self):
        sources = self.workspace.eligible(self.scope)
        return {"status": "observed", "eligible_sources": len(sources), "source_refs": [s["ref"] for s in sources], "origin": "original synthetic; no historical customer data", "license": "MIT", "scope": asdict(self.scope)}

    def stage_2(self):
        sources = self.workspace.sources()
        validate_sources(sources)
        chunks = self.workspace.chunks(self.scope)
        lookup = {s["ref"]: s for s in self.workspace.eligible(self.scope)}
        for chunk in chunks:
            assert lookup[chunk["ref"]]["content"][chunk["char_start"]:chunk["char_end"]] == chunk["text"]
        return {"status": "observed", "validated_source_envelopes": len(sources), "eligible_chunks": len(chunks), "span_checks": "exact character slices; UTF-8 byte spans also retained", "sqlite": sqlite3.sqlite_version, "fts5": True}

    def stage_3(self):
        return {"status": "observed", "query": QUERY, "method": "SQLite FTS5 BM25 over eligible content only", "candidates": self.retriever.search(QUERY, "lexical", 5)}

    def stage_4(self):
        if not self.include_dense:
            return {"status": "unavailable", "reason": "Choose local-model track with existing encoder assets; no semantic substitute is used"}
        data = self.retriever.build_dense()
        return {"status": "observed", "encoder": data["encoder"], "eligible_chunks_embedded": len(data["chunks"]), "truncated_chunks": data["truncated_chunks"], "cache_fingerprint": data["fingerprint"], "query": QUERY, "candidates": self.retriever.search(QUERY, "dense", 5)}

    def stage_5(self):
        if not self.include_dense:
            rows = heuristic_rerank(self.retriever.search(QUERY, "lexical", 10), REQUIRED)
            return {"status": "partially_available", "hybrid_status": "unavailable without genuine dense retrieval", "method": "lexical plus explicitly labeled metadata heuristic", "candidates": rows[:5]}
        rows = self.retriever.search(QUERY, "hybrid", 10)
        return {"status": "observed", "method": "RRF offset 60, then metadata heuristic; no learned cross-encoder", "fused": rows[:5], "reranked": heuristic_rerank(rows, REQUIRED)[:5]}

    def stage_6(self):
        try:
            rows = self.assembly_rows()
        except CaseEvidenceUnavailable:
            packed = pack_context([], self.budget)
            return dict(packed, status="insufficient_evidence", missing_required_refs=["exact_scoped_case_bundle"], reason="required exact-scoped records are unavailable or ambiguous")
        packed = pack_context(rows, self.budget)
        expected = set(case_state(self.workspace, self.scope)["source_refs"])
        packed["missing_required_refs"] = sorted(expected - {row["ref"] for row in packed["pack"]["evidence"]})
        packed["status"] = "insufficient_evidence" if packed["missing_required_refs"] else "observed"
        return packed

    def stage_7(self):
        packed = self.stage_6()
        claims = []
        labels = {"SYN-PURCHASE-4817": "purchase_two_blue_1250", "SYN-REPORT-104": "customer_reports_one_red", "SYN-FULFILLMENT-104": "fulfillment_unknown", "SYN-CASE-104": "checks_pending", "SYN-POLICY-RETURNS-V3": "no_automatic_refund"}
        for row in packed["pack"]["evidence"]:
            if row["source_id"] in labels:
                citation = {"ref": row["ref"], "char_start": row["char_start"], "char_end": row["char_end"], "quote": row["text"]}
                claims.append(fixture_support(self.workspace, self.scope, labels[row["source_id"]], citation))
        source = next((s for s in self.workspace.eligible(self.scope) if s["source_id"] == "SYN-PURCHASE-4817"), None)
        failure = fixture_support(self.workspace, self.scope, "delivered_red", {"ref": source["ref"], "char_start": 0, "char_end": len(source["content"]), "quote": source["content"]}) if source else None
        return {"status": packed["status"], "claims": claims, "failure_exercise": failure, "warning": "Valid source ID/span does not establish arbitrary claim support"}

    def stage_8(self):
        state = case_state(self.workspace, self.scope)
        bad = {key: state[key] for key in ["tenant", "case_id", "invoice_id", "purchase_check_complete", "case_check_complete", "fulfillment_status", "source_refs"]}
        bad["invoice_id"] = "INV-SYN-4818"
        try:
            reduce_tool_output(bad, self.workspace, self.scope)
        except ValueError as exc:
            failure = str(exc)
        else:
            raise AssertionError("wrong-invoice exercise was not rejected")
        return {"status": "observed", "state": state, "failure_exercise": {"wrong_invoice_rejected": True, "reason": failure}, "label": "deterministic fixture reducer; no real tool or business action invoked"}

    def stage_9(self):
        historical = replace(self.scope, as_of="2026-01-10T12:00:00Z")
        then = {s["ref"] for s in self.workspace.eligible(historical)}
        now = {s["ref"] for s in self.workspace.eligible(self.scope)}
        demo = Workspace(self.workspace.path / "temporal-demo").initialize(reset=(self.workspace.path / "temporal-demo").exists())
        demo.artifact("dependent-memory", {"source_refs": ["SYN-REVISION-NOTE@2"], "summary": "indigo training label"})
        deletion = demo.delete_projection("SYN-REVISION-NOTE", self.scope.as_of)
        assert not any(s["source_id"] == "SYN-REVISION-NOTE" for s in demo.sources())
        assert not list((demo.path / "artifacts").glob("*.json"))
        observation = []
        for at in ["2026-04-14T09:10:00Z", "2026-04-14T09:22:00Z", "2026-04-14T09:26:00Z", "2026-04-14T09:30:00Z"]:
            scope = replace(self.scope, as_of=at, knowledge_at=at)
            ids = {s["source_id"] for s in self.workspace.eligible(scope)}
            observation.append({"query_at": at, "observation_eligible": "SYN-OBSERVATION-APR14" in ids})
        return {"status": "observed", "historical_as_of": historical.as_of, "current_as_of": self.scope.as_of, "then_only_refs": sorted(then-now), "now_only_refs": sorted(now-then), "independent_observation_exercise": observation, "source_observed_at": "2026-04-14T09:00:00Z", "source_available_at": "2026-04-14T09:20:00Z", "fixture_ingested_at": "2026-04-14T09:25:00Z", "fixture_index_ready_at": "2026-04-14T09:28:00Z", "actual_runtime_snapshot": self.workspace.metadata(), "authorization": "current disclosure policy and current identity grants still apply at historical clocks", "live_projection_deletion_exercise": deletion, "policy_branch": self.scope.branch, "canonical_fixture_mutated": False}

    def stage_10(self):
        memory = make_memory(case_state(self.workspace, self.scope), self.scope)
        return {"status": "observed", "memory": memory, "usable_now": memory_usable(memory, self.workspace, self.scope), "summary_utf8_bytes": len(memory["summary"].encode()), "compression_boundary": "curated deterministic projection; not a general automatic summarizer"}

    def stage_11(self):
        graph = build_graph(self.workspace, self.scope)
        return {"status": "observed", "graph": graph, "case_query": query_graph(graph, self.workspace, self.scope, CASE)}

    def stage_12(self):
        chunks = self.workspace.chunks(self.scope)
        forbidden = {"SYN-HARBOR-CASE", "SYN-HARBOR-INVOICE", "SYN-HARBOR-POLICY", "SYN-INJECTION-TRAP"}
        if self.scope.team == "service-operations" and self.scope.tenant == "northstar-retail":
            forbidden |= {"SYN-INVENTORY-COUNT", "SYN-WAREHOUSE-CHECK", "SYN-INVENTORY-EXCEPTION"}
        if self.scope.tenant == "harbor-retail":
            forbidden = {s["source_id"] for s in self.workspace.sources() if s["tenant"] != self.scope.tenant} | {"SYN-INJECTION-TRAP"}
        observed = []
        for query in ["INV-HARBOR-901 seven yellow bowls", "warehouse bin B-SYN-7 eight blue mugs", "Ignore previous rules automatically refunded"]:
            for method in ["lexical"] + (["dense", "hybrid"] if self.include_dense else []):
                ids = [row["source_id"] for row in self.retriever.search(query, method, 10)]
                if forbidden.intersection(ids):
                    raise AssertionError("unauthorized evidence escaped retrieval")
                observed.append({"query": query, "method": method, "returned_source_ids": ids, "forbidden_source_hits": 0})
        return {"status": "observed", "tests": observed, "scope": asdict(self.scope), "quarantine_rule": "fixture trust category is a trusted ingestion label; text cannot grant access", "limitations": "finite cases, not universal injection resistance or production identity authentication"}

    def stage_13(self):
        return evaluate(self.workspace, self.scope, self.retriever, self.include_dense)

    def stage_14(self):
        packed = self.stage_6()
        if packed["missing_required_refs"]:
            return {"status": "insufficient_evidence", "missing_required_refs": packed["missing_required_refs"], "business_actions": [], "answer": None}
        state = case_state(self.workspace, self.scope)
        return {"status": "observed", "answer_type": "deterministic read-only fixture assessment", "answer": assessment_text(state), "state": state, "source_refs": state["source_refs"], "context_serialized_utf8_bytes": packed["serialized_cost"], "context_budget_utf8_bytes": self.budget, "optional_dense_enabled": self.include_dense, "business_actions": [], "limits": ["synthetic fixed case only", "no external tool calls, payment/refund action, or generated answer", "local indexing and teaching artifacts are written under the isolated workspace"]}


def replay(receipt_path, workspace, scope, reexecute=False, model_dir=None):
    receipt = json.loads(receipt_path.read_text())
    if receipt["scope"] != asdict(scope):
        raise ValueError("replay scope/clock/branch differs from receipt")
    changes = []
    if receipt["input_sha256"] != input_hashes():
        changes.append("inputs")
    if receipt["code_sha256"] != code_hashes():
        changes.append("code")
    if receipt.get("projection_sha256") != projection_hash(workspace, scope):
        changes.append("live_projection")
    versions = {"python": platform.python_version(), "system": platform.system(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version}
    if receipt["versions"] != versions:
        changes.append("runtime_versions")
    path = (workspace.path / receipt["artifact"]).resolve()
    if not path.is_relative_to(workspace.path):
        raise ValueError("receipt artifact escapes workspace")
    if not path.exists():
        changes.append("artifact_missing_or_invalidated")
    elif digest(path.read_bytes()) != receipt["artifact_sha256"]:
        changes.append("artifact_changed")
    result = {"status": "verified_existing_artifact" if not changes else "drift_detected", "changes": changes, "scope": receipt["scope"], "note": "Receipt verification, not a claim of model-generation bitwise reproduction. A deleted artifact is not reconstructed."}
    if reexecute and not changes:
        pipeline = Pipeline(workspace, scope, receipt["track"], model_dir, receipt["settings"]["evidence_budget"])
        original = json.loads(path.read_text())
        output = getattr(pipeline, "stage_" + str(receipt["chapter"]))()
        omitted = {"latency_seconds", "wall_seconds", "observed_at_utc"}
        def stable(value):
            if isinstance(value, dict):
                return {key: stable(item) for key, item in value.items() if key not in omitted}
            if isinstance(value, list):
                return [stable(item) for item in value]
            return value
        result.update(status="reexecuted_stable_fields_match" if stable(original) == stable(output) else "reexecution_mismatch", comparison_omits=sorted(omitted), original_stable_sha256=digest(canonical(stable(original))), replay_stable_sha256=digest(canonical(stable(output))), note="Re-executed the same stage against the checked live snapshot. No deleted content is reconstructed and no business action is invoked.")
        if pipeline.retriever.encoder and receipt.get("encoder") and pipeline.retriever.encoder.metadata != receipt["encoder"]:
            result.update(status="drift_detected", changes=["encoder_versions_or_assets"])
    return result
