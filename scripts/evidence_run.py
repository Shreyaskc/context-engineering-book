"""Durable subprocess receipts shared by verification and isolated setup.

No retries: a timeout can leave a server-side inference outcome uncertain.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def checkpoint(path, record):
    path = Path(path)
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _bytes(value):
    return value if isinstance(value, bytes) else (value or "").encode()


def recorded_step(record, record_path, output, root, name, command, *, timeout, expected=0, env=None, semantic=None, collection="checks"):
    """Checkpoint running/completed/failed steps, preserving partial bytes on timeout."""
    output, root = Path(output), Path(root)
    command = [str(value) for value in command]
    stdout, stderr = output / (name + ".stdout"), output / (name + ".stderr")
    allowed = {"CONTEXTLAB_MINILM_DIR", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "TOKENIZERS_PARALLELISM", "MACOSX_DEPLOYMENT_TARGET", "UV_OFFLINE", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE"}
    observed_env = dict(env) if env is not None else {key: os.environ[key] for key in sorted(allowed) if key in os.environ}
    step = {"name": name, "command_argv": command, "cwd": ".", "environment_mode": "explicit isolated environment" if env is not None else "inherited; only relevant non-secret variables retained", "environment": observed_env, "started_at_utc": utc_now(), "status": "running", "passed": False, "exit_code": None, "expected_exit_code": expected, "timeout_seconds": timeout, "timed_out": False, "auto_retry": False, "stdout": str(stdout.relative_to(root)), "stderr": str(stderr.relative_to(root))}
    record.setdefault(collection, []).append(step)
    record["status"] = "running"
    stdout.write_bytes(b"")
    stderr.write_bytes(b"")
    checkpoint(record_path, record)
    started = time.monotonic()
    out, err = b"", b""
    try:
        process = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=timeout)
        out, err = _bytes(process.stdout), _bytes(process.stderr)
        step.update(status="completed", exit_code=process.returncode, passed=process.returncode == expected)
    except subprocess.TimeoutExpired as exc:
        out, err = _bytes(exc.output), _bytes(exc.stderr)
        step.update(status="timed_out", timed_out=True, outcome="timeout_uncertain", error_type="TimeoutExpired", error="Command timed out; server-side completion may be unknown. Inspect state before any deliberate retry.")
    except OSError as exc:
        step.update(status="execution_failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        stdout.write_bytes(out)
        stderr.write_bytes(err)
        step.update(ended_at_utc=utc_now(), wall_seconds=time.monotonic()-started, stdout_sha256=hashlib.sha256(out).hexdigest(), stderr_sha256=hashlib.sha256(err).hexdigest())
    if step["status"] == "completed" and semantic is not None:
        try:
            assessment = semantic(out)
            if not isinstance(assessment, dict) or type(assessment.get("passed")) is not bool:
                raise ValueError("semantic checker must return a boolean passed field")
        except Exception as exc:
            assessment = {"passed": False, "error_type": type(exc).__name__, "reason": str(exc)}
        step["semantic"] = assessment
        step["passed"] = step["passed"] and assessment["passed"]
    checkpoint(record_path, record)
    return step, out, err
