"""Record Mac verification with semantic gates and durable timeout evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contextlab.exercises import exercise_contract
from contextlab.pipeline import STAGES, code_hashes, input_hashes
from evidence_run import checkpoint, recorded_step, utc_now
from verify_capstone_generation import assess_experiment_file


def build_checks(args, output):
    checks = [
        ("doctor", ["-m", "contextlab", "doctor", "--json"], 0),
        ("readiness", ["-m", "contextlab", "readiness", "--json"], 0),
        ("baseline", ["scripts/check_baseline.py"], 0),
        ("tests", ["-m", "unittest", "discover", "-s", "tests", "-v"], 0),
        ("core-all", ["-m", "contextlab", "lab", "run", "all", "--workspace", str(output / "core"), "--reset", "--json"], 0),
    ]
    for number in range(1, 15):
        checks.append((f"exercise-{number:02}", ["-m", "contextlab", "exercise", "run", str(number), "--workspace", str(output / f"exercise-{number:02}"), "--reset", "--json"], 3 if number in {4, 5} else 0))
    checks += [
        ("capstone-reexecute", ["-m", "contextlab", "replay", "--receipt", str(output / "core/receipts/14-capstone.json"), "--workspace", str(output / "core"), "--reexecute", "--json"], 0),
        ("v4-branch", ["-m", "contextlab", "scenario", "branch", "northstar-v3", "northstar-v4", "--workspace", str(output / "branch"), "--json"], 0),
        ("v4-capstone", ["-m", "contextlab", "lab", "run", "14", "--branch", "northstar-v4", "--as-of", "2026-02-15T12:00:00Z", "--workspace", str(output / "branch"), "--json"], 0),
    ]
    if args.model_dir:
        checks.append(("embedding-probe", ["scripts/smoke_embedding.py", "--model-dir", args.model_dir], 0))
        checks.append(("local-model-all", ["-m", "contextlab", "lab", "run", "all", "--track", "local-model", "--model-dir", args.model_dir, "--workspace", str(output / "models"), "--reset", "--json"], 0))
        for number in [4, 5]:
            checks.append((f"real-model-exercise-{number:02}", ["-m", "contextlab", "exercise", "run", str(number), "--track", "local-model", "--model-dir", args.model_dir, "--workspace", str(output / f"real-model-exercise-{number:02}"), "--reset", "--json"], 0))
        checks.append(("evaluation-reexecute", ["-m", "contextlab", "replay", "--receipt", str(output / "models/receipts/13-evaluate.json"), "--workspace", str(output / "models"), "--model-dir", args.model_dir, "--reexecute", "--json"], 0))
    if args.tokenizer_file:
        checks.append(("tokenizer-content-probe", ["scripts/probe_tokenizer.py", "--tokenizer-file", args.tokenizer_file], 0))
    if args.ollama_probes:
        if not args.model_dir:
            raise ValueError("capstone generation verification requires the genuine local encoder track")
        checks.append(("bounded-generation-probe", ["scripts/smoke_generation.py"], 0))
        checks.append(("authorized-context-generation", ["scripts/verify_capstone_generation.py", "--model-dir", args.model_dir, "--output", str(output / "capstone-generation")], 0))
    return checks


def check_semantics(name, stdout, output, commit):
    if name == "authorized-context-generation":
        return assess_experiment_file(output / "capstone-generation/experiment.json", commit)
    if name == "tests":
        return {"passed": True, "scope": "unittest process exit; individual assertions and test count are retained in stderr"}
    if name == "baseline":
        return {"passed": stdout.decode().strip() == "BASELINE_OK chapters=14 fixture=CASE-SYN-104"}
    data = json.loads(stdout)
    if name.startswith("exercise-") or name.startswith("real-model-exercise-"):
        number = int(name.rsplit("-", 1)[1])
        if name.startswith("exercise-") and number in {4, 5}:
            return {"passed": data.get("status") == "unavailable" and bool(data.get("reason")), "expected": "explicitly unavailable genuine-model exercise, exit 3"}
        result = data.get("result")
        if not isinstance(result, dict):
            return {"passed": False, "reason": "missing exercise observations"}
        contract = exercise_contract(number, result)
        contract["passed"] = contract["passed"] and data.get("status") == "observed_expected_failure_and_correction" and result.get("status") == "observed_expected_failure_and_correction"
        return contract
    if name in {"core-all", "local-model-all", "v4-capstone"}:
        rows = data.get("stages", [])
        expected_statuses = ["observed"] * (1 if name == "v4-capstone" else 14)
        if name == "core-all":
            expected_statuses[3:5] = ["unavailable", "partially_available"]
        workspace = output / {"core-all": "core", "local-model-all": "models", "v4-capstone": "branch"}[name]
        checked = []
        for row in rows:
            artifact = (workspace / row["artifact"]).resolve()
            receipt_path = (workspace / row["receipt"]).resolve()
            if not artifact.is_relative_to(workspace) or not receipt_path.is_relative_to(workspace):
                return {"passed": False, "reason": "artifact/receipt escapes workspace"}
            receipt = json.loads(receipt_path.read_text())
            checked.append(hashlib.sha256(artifact.read_bytes()).hexdigest() == row["artifact_sha256"] == receipt["artifact_sha256"] and receipt["code_sha256"] == code_hashes() and receipt["input_sha256"] == input_hashes())
        stages = [row.get("stage") for row in rows]
        expected_stages = ["capstone"] if name == "v4-capstone" else STAGES
        expected_top = "completed_with_unavailable_optional_stages" if name == "core-all" else "observed"
        return {"passed": data.get("status") == expected_top and stages == expected_stages and [r.get("status") for r in rows] == expected_statuses and bool(checked) and all(checked), "expected_stage_statuses": expected_statuses, "artifact_receipt_hashes_checked": len(checked)}
    if name.endswith("reexecute"):
        return {"passed": data.get("status") == "reexecuted_stable_fields_match" and data.get("changes") == [] and isinstance(data.get("original_stable_sha256"), str) and data.get("original_stable_sha256") == data.get("replay_stable_sha256")}
    if name == "v4-branch":
        return {"passed": data.get("status") == "branch_defined" and data.get("scenario", {}).get("canonical_fixture_mutated") is False}
    if name == "doctor":
        return {"passed": data.get("status") == "ready_core" and data.get("fts5") is True}
    if name == "readiness":
        return {"passed": data.get("status") == "observed" and data.get("json_none_zero", {}).get("unknown_is_none") is True and data.get("json_none_zero", {}).get("zero_is_none") is False and data.get("bytes_versus_tokens", {}).get("model_tokens") is None}
    if name == "embedding-probe":
        return {"passed": data.get("status") == "observed" and data.get("shape") == [3, 384] and all(abs(n-1) <= 1e-5 for n in data.get("l2_norms", [])) and len(data.get("l2_norms", [])) == 3}
    if name == "tokenizer-content-probe":
        return {"passed": data.get("status") == "observed" and len(data.get("rows", [])) == 3 and all(isinstance(r.get("content_token_ids_without_added_specials"), list) and r["content_token_ids_without_added_specials"] for r in data["rows"])}
    if name == "bounded-generation-probe":
        return {"passed": data.get("status") == "observed" and data.get("output", {}).get("done") is True and bool(data.get("output", {}).get("response")), "scope": "bounded execution only; context-backed semantic gate is separate"}
    return {"passed": False, "reason": "unknown semantic gate"}


def run_plan(checks, output, record, record_path, timeout_override=None):
    for index, (name, argv, expected) in enumerate(checks):
        timeout = timeout_override if timeout_override is not None else 390 if name == "authorized-context-generation" else 120
        step, out, err = recorded_step(record, record_path, output, ROOT, name, [sys.executable, "-B"] + argv, timeout=timeout, expected=expected, semantic=lambda value: check_semantics(name, value, output, record["git_head_at_start"]))
        if name == "tests":
            match = re.search(r"Ran (\d+) tests?", err.decode(errors="replace"))
            step["test_methods_reported"] = int(match.group(1)) if match else None
            skipped = re.search(r"skipped=(\d+)", err.decode(errors="replace"))
            step["skipped_methods_reported"] = int(skipped.group(1)) if skipped else 0
            checkpoint(record_path, record)
        if step["status"] in {"timed_out", "execution_failed"}:
            record["unexecuted_steps"] = [item[0] for item in checks[index+1:]]
            record["stopped_after"] = name
            break
    record["status"] = "passed" if len(record["checks"]) == len(checks) and all(c["passed"] for c in record["checks"]) else "failed"
    record["ended_at_utc"] = utc_now()
    checkpoint(record_path, record)
    return 0 if record["status"] == "passed" else 4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", help="existing MiniLM snapshot; no model download")
    parser.add_argument("--ollama-probes", action="store_true")
    parser.add_argument("--tokenizer-file", help="existing Gemma tokenizer.json")
    parser.add_argument("--output", default=".local/verification-core")
    args = parser.parse_args(argv)
    if platform.system() != "Darwin":
        raise RuntimeError("This verification must execute on the connected Mac")
    output = (ROOT / args.output).resolve()
    local = (ROOT / ".local").resolve()
    if not output.is_relative_to(local) or output == local:
        raise ValueError("verification output must be a child of .local")
    if output.exists() and any(output.iterdir()):
        raise ValueError("verification output must be fresh; earlier evidence is not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    record_path = output / "verification.json"
    record = {"schema_version": 2, "started_at_utc": utc_now(), "python": platform.python_version(), "system": platform.system(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version, "counted_review_cycle": False, "checks": [], "status": "initializing"}
    checkpoint(record_path, record)
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip()
        if Path(top).resolve() != ROOT:
            raise ValueError("verification requires this project's genuine Git checkout, not an archive inside another checkout")
        tracked = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
        record["source_sha256"] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(tracked)) if (ROOT/name).is_file()}
        record["git_head_at_start"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        record["git_status_at_start"] = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        checkpoint(record_path, record)
        checks = build_checks(args, output)
        code = run_plan(checks, output, record, record_path)
    except Exception as exc:
        record.update(status="failed", ended_at_utc=utc_now(), error_type=type(exc).__name__, error=str(exc))
        checkpoint(record_path, record)
        code = 4
    print(json.dumps({"status": record["status"], "checks": len(record["checks"]), "failed": [c["name"] for c in record["checks"] if not c["passed"]], "record": str(record_path.relative_to(ROOT)), "counted_review_cycles": 0}))
    return code


if __name__ == "__main__":
    sys.exit(main())
