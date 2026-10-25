"""Resolve official wheels and install a fresh project-local, hash-locked ML env."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from evidence_run import checkpoint, recorded_step, utc_now

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements/ml-macos-arm64-py312.lock"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["lock", "install"])
    parser.add_argument("--python", required=True, help="existing base Python 3.12; never downloaded")
    parser.add_argument("--venv", default=".venv-ml-clean")
    parser.add_argument("--offline", action="store_true", default=os.environ.get("UV_OFFLINE", "").lower() in {"1", "true"}, help="use only already cached official wheels; no network")
    args = parser.parse_args(argv)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("This lock/setup is tested only on the connected arm64 Mac")
    target = (ROOT / args.venv).resolve()
    if not target.is_relative_to(ROOT) or not target.name.startswith(".venv-"):
        raise ValueError("target must be an isolated .venv-* directory inside this project")
    if args.mode == "install" and target.exists():
        raise ValueError("clean installation requires a new absent environment; use a new target name")
    base = Path(args.python).resolve(strict=True)
    uv = shutil.which("uv")
    if not uv:
        raise ValueError("existing uv is required; no installer is run automatically")
    run_id = args.mode + "-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    private = ROOT / ".local/clean-setup" / run_id
    private.mkdir(parents=True, exist_ok=False)
    config = private / "empty-uv.toml"
    config.write_text("")
    cache = ROOT / ".local/uv-clean-cache"
    # No inherited package indexes, credentials, proxy configuration, PYTHONPATH,
    # user site packages, or configured book environment. Downloads use official PyPI.
    env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": str(private / "tmp"), "PYTHONDONTWRITEBYTECODE": "1", "UV_PYTHON_DOWNLOADS": "never", "UV_KEYRING_PROVIDER": "disabled", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "MACOSX_DEPLOYMENT_TARGET": "14.0", **({"UV_OFFLINE": "1"} if args.offline else {})}
    Path(env["TMPDIR"]).mkdir(exist_ok=True)
    record = {"schema_version": 1, "mode": args.mode, "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "platform": {"system": platform.system(), "architecture": platform.machine(), "minimum_wheel_macos": "14.0"}, "official_index": "https://pypi.org/simple", "cache_scope": "project-local new clean cache; not the preconfigured archive runtime", "target": str(target), "target_existed_before_creation": target.exists(), "offline": args.offline, "steps": [], "counted_review_cycle": False}
    record_path = private / (args.mode + "-record.json")
    def save():
        checkpoint(record_path, record)
    def run(name, command):
        step, stdout, stderr = recorded_step(record, record_path, private, ROOT, name, command, timeout=300, env=env, collection="steps")
        print(json.dumps({"step": name, "exit_code": step["exit_code"], "status": step["status"]}), flush=True)
        if not step["passed"]:
            raise RuntimeError("clean setup step failed: " + name + "; inspect retained output and uncertain-timeout status before any deliberate retry")
        return stdout
    uv_options = ["--cache-dir", str(cache), "--config-file", str(config), "--no-python-downloads", "--no-progress", "--keyring-provider", "disabled"]
    if args.offline:
        uv_options.append("--offline")
    try:
        record["uv_version"] = run("uv-version", [uv, "--version"]).decode().strip()
        record["uv_executable"] = str(uv)
        version = json.loads(run("base-python", [base, "-B", "-I", "-c", "import json,sys;print(json.dumps(list(sys.version_info[:3])))"]))
        if version[:2] != [3, 12]:
            raise ValueError("this platform lock requires an existing Python 3.12 interpreter")
        record["python_version"] = version
        if args.mode == "lock":
            run("compile-lock", [uv, "pip", "compile", "requirements/ml-observed.txt", "--python", str(base), "--python-platform", "aarch64-apple-darwin", "--generate-hashes", "--only-binary", ":all:", "--no-sources", "--default-index", "https://pypi.org/simple", "--emit-index-url", "--emit-index-annotation", "--custom-compile-command", "python3 scripts/setup_clean_ml.py lock --python /path/to/existing/python3.12", "--output-file", str(LOCK)] + uv_options)
        else:
            if not LOCK.is_file():
                raise ValueError("complete committed hash lock is required before installation")
            run("create-empty-venv", [base, "-B", "-I", "-m", "venv", "--without-pip", target])
            python = target / "bin/python"
            inspection = "import importlib.metadata as m,json,sys,site;print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,'user_site_enabled':site.ENABLE_USER_SITE,'sys_path':sys.path,'packages':sorted((d.metadata['Name'],d.version) for d in m.distributions())}))"
            before = json.loads(run("before-install", [python, "-B", "-I", "-c", inspection]))
            if before["packages"] or before["user_site_enabled"]:
                raise ValueError("environment was not empty/isolated before installation")
            record["before_install"] = before
            run("install-locked-wheels", [uv, "pip", "install", "--python", str(python), "--requirements", str(LOCK), "--require-hashes", "--only-binary", ":all:", "--strict", "--exact", "--link-mode", "copy", "--no-sources", "--default-index", "https://pypi.org/simple"] + uv_options)
            run("dependency-check", [uv, "pip", "check", "--python", str(python), "--cache-dir", str(cache), "--config-file", str(config), "--offline"])
            record["after_install"] = json.loads(run("after-install", [python, "-B", "-I", "-c", inspection]))
            roots = json.loads(run("import-roots", [python, "-B", "-I", "-c", "import torch,transformers,tokenizers,numpy,safetensors,huggingface_hub,json;print(json.dumps({m.__name__:m.__file__ for m in [torch,transformers,tokenizers,numpy,safetensors,huggingface_hub]}))"]))
            if not all(Path(path).resolve().is_relative_to(target) for path in roots.values()):
                raise ValueError("ML import escaped the fresh environment")
            if any("archive-v0" in path or ".venv-ml/" in path for path in record["after_install"]["sys_path"]):
                raise ValueError("an existing cached runtime leaked into sys.path")
            record["import_roots"] = roots
            record["installed_freeze"] = run("installed-freeze", [uv, "pip", "freeze", "--python", str(python), "--cache-dir", str(cache), "--config-file", str(config), "--offline"]).decode()
        record["lock_sha256"] = hashlib.sha256(LOCK.read_bytes()).hexdigest()
        record["status"] = "passed"
        record["ended_at_utc"] = utc_now()
    except Exception as exc:
        record.update(status="failed", ended_at_utc=utc_now(), error_type=type(exc).__name__, error=str(exc))
        save()
        print(json.dumps({"status": "failed", "reason": str(exc), "record": str(record_path.relative_to(ROOT))}), flush=True)
        return 4
    save()
    print(json.dumps({"status": "passed", "mode": args.mode, "record": str(record_path.relative_to(ROOT)), "lock_sha256": record["lock_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
