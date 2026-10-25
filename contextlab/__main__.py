"""The contextlab CLI: shared stages, clean lab workspaces, no business actions."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import sys

from . import __version__
from .pipeline import Pipeline, STAGES, replay
from .retrieval import CapabilityUnavailable
from .readiness import examples
from .exercises import finalize_exercise, run_exercise
from .store import ROOT, Scope, Workspace, canonical, digest


def common(parser):
    parser.add_argument("--workspace", default=".local/lab")
    parser.add_argument("--principal", default="service-reader")
    parser.add_argument("--tenant", default="northstar-retail")
    parser.add_argument("--team", default="service-operations")
    parser.add_argument("--as-of", default="2026-01-15T12:00:00Z")
    parser.add_argument("--knowledge-at", help="synthetic system knowledge/index cutoff; defaults to as-of")
    parser.add_argument("--branch", choices=["northstar-v3", "northstar-v4"], default="northstar-v3")
    parser.add_argument("--json", action="store_true", help="JSON is always emitted; flag retained for explicit examples")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m contextlab", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    readiness = commands.add_parser("readiness")
    readiness.add_argument("--json", action="store_true")
    for command in ["lab", "stage", "exercise"]:
        command_parser = commands.add_parser(command)
        run = command_parser.add_subparsers(dest="action", required=True).add_parser("run")
        run.add_argument("target", help="chapter 01..14 or all" if command == "lab" else "chapter 01..14" if command == "exercise" else "stage name")
        common(run)
        run.add_argument("--track", choices=["core", "local-model"], default="core")
        run.add_argument("--model-dir", help="existing local MiniLM snapshot; never downloaded")
        run.add_argument("--budget", type=int, default=3600, help="UTF-8 bytes of serialized evidence object")
        run.add_argument("--reset", action="store_true", help="replace only a marked workspace under .local")
    rp = commands.add_parser("replay")
    common(rp)
    rp.add_argument("--receipt", required=True)
    rp.add_argument("--reexecute", action="store_true")
    rp.add_argument("--model-dir", help="existing local encoder, required if replayed stage uses dense retrieval")
    deletion = commands.add_parser("delete")
    common(deletion)
    deletion.add_argument("--source-id", required=True)
    scenario = commands.add_parser("scenario")
    branch = scenario.add_subparsers(dest="action", required=True).add_parser("branch")
    branch.add_argument("from_branch", choices=["northstar-v3"])
    branch.add_argument("to_branch", choices=["northstar-v4"])
    common(branch)
    args = parser.parse_args(argv)
    try:
        if args.command == "readiness":
            result = examples()
        elif args.command == "doctor":
            with sqlite3.connect(":memory:") as db:
                db.execute("CREATE VIRTUAL TABLE check_fts USING fts5(text)")
            result = {"status": "ready_core", "package": "contextlab", "version": __version__, "python": platform.python_version(), "system": platform.system(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version, "fts5": True, "core_third_party_dependencies": [], "optional_dense": "existing local MiniLM snapshot and ML dependencies required", "stages": STAGES, "review_cycles_completed": 0}
        else:
            scope = Scope(args.principal, args.tenant, args.team, args.as_of, args.branch, args.knowledge_at)
            scope.validate()
            path = Path(args.workspace)
            workspace = Workspace(path if path.is_absolute() else ROOT / path)
            if args.command in {"lab", "stage", "exercise"}:
                workspace.initialize(reset=args.reset)
                pipeline = Pipeline(workspace, scope, args.track, args.model_dir, args.budget)
                targets = list(range(1, 15)) if args.command == "lab" and args.target == "all" else [int(args.target)] if args.command in {"lab", "exercise"} else [STAGES.index(args.target)+1]
                if args.command == "exercise":
                    output = finalize_exercise(targets[0], run_exercise(targets[0], pipeline))
                    path = workspace.artifact(f"exercise-{targets[0]:02}", output)
                    result = {"status": output["status"], "artifact": str(path.relative_to(workspace.path)), "result": output, "review_cycles_completed": 0}
                    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                    return 0 if output["contract"]["passed"] else 4
                rows = [pipeline.run(n) for n in targets]
                result = {"status": "observed", "track": args.track, "stages": rows, "review_cycles_completed": 0}
                if any(row["status"] == "insufficient_evidence" for row in rows):
                    result["status"] = "insufficient_evidence"
                elif any(row["status"] in {"unavailable", "partially_available"} for row in rows):
                    result["status"] = "completed_with_unavailable_optional_stages"
            elif args.command == "scenario":
                workspace.initialize()
                config = {"from": args.from_branch, "branch": args.to_branch, "policy_id": "returns-v4", "as_of": "2026-02-15T12:00:00Z", "activation": "pass this branch and as-of explicitly to later commands", "canonical_fixture_mutated": False}
                path = workspace.path / "scenario-northstar-v4.json"
                path.write_text(canonical(config) + "\n")
                result = {"status": "branch_defined", "scenario": config}
            elif args.command == "delete":
                workspace.initialize()
                if args.source_id not in {s["source_id"] for s in workspace.eligible(scope)}:
                    raise ValueError("source is absent or ineligible for this scope; deletion refused")
                result = dict(workspace.delete_projection(args.source_id, scope.as_of), status="projection_deleted")
            else:
                receipt = Path(args.receipt).resolve()
                if not receipt.is_relative_to(workspace.path / "receipts"):
                    raise ValueError("receipt must belong to this marked workspace's receipts directory")
                result = replay(receipt, workspace, scope, args.reexecute, args.model_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if result["status"] in {"insufficient_evidence", "drift_detected", "reexecution_mismatch"}:
            return 4
        if args.command == "lab" and args.target in {"04", "4", "05", "5"} and result["status"] == "completed_with_unavailable_optional_stages":
            return 3
        if args.command == "stage" and result["status"] == "completed_with_unavailable_optional_stages":
            return 3
        return 0
    except CapabilityUnavailable as exc:
        print(json.dumps({"status": "unavailable", "reason": str(exc), "downloads_attempted": False}))
        return 3
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"status": "invalid_or_failed", "error_type": type(exc).__name__, "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
