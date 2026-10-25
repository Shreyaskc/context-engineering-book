"""One bounded local inference probe; not an answer-quality evaluation."""
import datetime
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

from inventory import api

MODEL = "gemma4:12b-mlx"
PROMPT = (
    "Synthetic case CASE-SYN-104, invoice INV-SYN-4817: purchase lists two blue mugs "
    "at GBP 12.50 each. Customer reports one red mug. Fulfillment is unknown. "
    "Synthetic returns-v3 requires purchase and case checks and never authorizes "
    "automatic refund. Neither check is complete. "
    "In one short sentence state the pending checks and refund status."
)


def main():
    receipt = {"schema_version": 1, "purpose": "local inference plumbing only", "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "python": platform.python_version(), "system": platform.system(), "architecture": platform.machine(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "input": PROMPT, "input_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(), "input_utf8_bytes": len(PROMPT.encode()), "input_byte_measure_scope": "prompt string before backend rendering; not a model-token estimate", "omitted_response_fields": ["thinking", "context"], "counted_review_cycle": False}
    if platform.system() != "Darwin":
        receipt.update(status="unavailable", reason="Preparation probes must run on the connected Mac")
        return receipt, 3
    try:
        receipt["ollama_version"] = api("version")
        models = api("tags").get("models", [])
        local = next((m for m in models if m.get("name") == MODEL), None)
        if local is None:
            receipt.update(status="unavailable", reason="Required local model tag absent; no pull attempted")
            return receipt, 3
        if api("ps").get("models"):
            receipt.update(status="unavailable", reason="An existing model is loaded; avoid interfering with another lab")
            return receipt, 3
        show = api("show", {"model": MODEL})
        if show.get("remote_host") or show.get("remote_model"):
            receipt.update(status="unavailable", reason="Remote model routing is outside this probe")
            return receipt, 3
        receipt["model"] = {"name": MODEL, "manifest_digest": local.get("digest"), "template_sha256": hashlib.sha256(show.get("template", "").encode()).hexdigest(), "details": show.get("details"), "renderer": show.get("renderer")}
        request = {"model": MODEL, "prompt": PROMPT, "stream": False, "think": False, "keep_alive": 0, "options": {"temperature": 0, "seed": 7, "num_predict": 64, "num_ctx": 2048}}
        receipt["request"] = request
        started = time.monotonic()
        data = api("generate", request)
        receipt["wall_seconds"] = time.monotonic() - started
        receipt["output"] = {k: data[k] for k in ["model", "created_at", "response", "done", "done_reason", "total_duration", "load_duration", "prompt_eval_count", "prompt_eval_cached_count", "prompt_eval_duration", "eval_count", "eval_duration"] if k in data}
        receipt["output_sha256"] = hashlib.sha256(data.get("response", "").encode()).hexdigest()
        receipt["usage_scope"] = "backend-reported counts, separate from input bytes; missing fields remain unknown"
        receipt["duration_unit"] = "nanoseconds for backend durations; seconds for wall_seconds"
        receipt["ps_after"] = api("ps")
        receipt["status"] = "observed" if data.get("done") and data.get("response") else "failed"
        return receipt, 0 if receipt["status"] == "observed" else 4
    except Exception as exc:
        receipt.update(status="failed_or_uncertain", error_type=type(exc).__name__, error=str(exc), reason="Check server state before retrying an uncertain inference request")
        return receipt, 4


if __name__ == "__main__":
    result, code = main()
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(code)
