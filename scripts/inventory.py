"""Read-only, allowlisted local observations. No downloads or model execution."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME_DIR = Path.home()
MODELS = ("gemma4:12b-mlx", "gemma4:26b-mlx")
MINILM = "models--sentence-transformers--all-MiniLM-L6-v2"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def command(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        return {"argv": argv, "exit_code": p.returncode, "stdout": p.stdout.strip()[:2000], "stderr": p.stderr.strip()[:2000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": argv, "error_type": type(exc).__name__, "error": str(exc)}


def api(endpoint, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/" + endpoint, data, {"Content-Type": "application/json"})
    with OPENER.open(req, timeout=20) as response:
        return json.load(response)


def inventory(use_ollama):
    out = {"schema_version": 1, "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "script_sha256": sha(Path(__file__)), "system": platform.system(), "architecture": platform.machine(), "python": platform.python_version()}
    out["hardware"] = {k: command(["sysctl", "-n", v]) for k, v in {"model": "hw.model", "chip": "machdep.cpu.brand_string", "memory_bytes": "hw.memsize", "logical_cpus": "hw.ncpu", "physical_cpus": "hw.physicalcpu"}.items()}
    out["macos"] = command(["sw_vers", "-productVersion"])
    out["tools"] = {tool: command([tool, "--version"]) if shutil.which(tool) else {"available": False} for tool in ["git", "uv", "ollama"]}
    out["runtime_packages"] = {}
    for package in ["numpy", "torch", "transformers", "tokenizers", "sentence-transformers", "sentencepiece", "tiktoken", "mlx", "mlx-lm", "safetensors", "huggingface-hub"]:
        try:
            out["runtime_packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            out["runtime_packages"][package] = None
    out["local_embedding_assets"] = []
    root = HOME_DIR / ".cache/huggingface/hub" / MINILM / "snapshots"
    for snapshot in sorted(root.glob("*")):
        assets = {}
        for name in ["model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json", "modules.json", "1_Pooling/config.json", "sentence_bert_config.json", "README.md"]:
            p = snapshot / name
            assets[name] = {"exists": p.is_file(), "size_bytes": p.stat().st_size, "sha256": sha(p)} if p.is_file() else {"exists": False}
        out["local_embedding_assets"].append({"model": "sentence-transformers/all-MiniLM-L6-v2", "snapshot": snapshot.name, "assets": assets})
    out["ollama_manifests"] = []
    model_root = HOME_DIR / ".ollama/models"
    for model in MODELS:
        name, tag = model.split(":")
        manifest = model_root / "manifests/registry.ollama.ai/library" / name / tag
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text())
        selected = {}
        for layer in data.get("layers", []):
            if layer.get("name") in ["tokenizer.json", "tokenizer_config.json", "config.json"] or layer.get("mediaType", "").endswith(".license"):
                blob = model_root / "blobs" / layer["digest"].replace(":", "-")
                item = {"manifest_digest": layer["digest"], "exists": blob.is_file()}
                if blob.is_file():
                    item.update(size_bytes=blob.stat().st_size, sha256=sha(blob))
                if layer.get("name") == "tokenizer_config.json" and blob.is_file():
                    cfg = json.loads(blob.read_text())
                    item.update(tokenizer_class=cfg.get("tokenizer_class"), chat_template_present=bool(cfg.get("chat_template")))
                selected[layer.get("name", "license")] = item
        out["ollama_manifests"].append({"model": model, "manifest_sha256": sha(manifest), "selected_assets": selected, "weight_tensors_rehashed": False})
    if use_ollama:
        out["ollama_api"] = {}
        for endpoint in ["version", "tags", "ps"]:
            try:
                data = api(endpoint)
                if endpoint == "tags":
                    data = {"models": [{k: m[k] for k in ["name", "digest", "size", "details", "capabilities"] if k in m} for m in data.get("models", []) if m.get("name") in MODELS]}
                out["ollama_api"][endpoint] = data
            except Exception as exc:
                out["ollama_api"][endpoint] = {"error_type": type(exc).__name__, "error": str(exc)}
        out["ollama_api"]["show"] = {}
        for model in MODELS:
            try:
                data = api("show", {"model": model, "verbose": False})
                selected = {k: data[k] for k in ["details", "capabilities", "parameters", "renderer", "parser", "template_source", "thinking"] if k in data}
                selected["template_sha256"] = hashlib.sha256(data.get("template", "").encode()).hexdigest()
                selected["template_characters"] = len(data.get("template", ""))
                selected["model_info_scalars"] = {k: v for k, v in data.get("model_info", {}).items() if not isinstance(v, (dict, list))}
                out["ollama_api"]["show"][model] = selected
            except Exception as exc:
                out["ollama_api"]["show"][model] = {"error_type": type(exc).__name__, "error": str(exc)}
    out["input_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / "fixtures/case-syn-104.json", ROOT / "contracts/chapters.json", ROOT / "data/provenance.json"]}
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", action="store_true", help="read only the existing loopback server")
    args = parser.parse_args()
    print(json.dumps(inventory(args.ollama), indent=2, sort_keys=True))
