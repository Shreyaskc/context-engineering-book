# Setup and dependency strategy

## Beginner baseline

Use a local terminal and Python 3.12+. Confirm `python3 --version` and
`git --version`, change into this repository, then run the README checks.
An isolated environment is optional for the standard-library baseline:

```sh
python3 -m venv .venv
.venv/bin/python scripts/check_baseline.py
.venv/bin/python -m unittest discover -s tests -v
```

No package installation is needed. SQLite, JSON, argparse, hashing, and unittest
come with Python. No paid API, account, credentials, public port, or security
setting change is part of setup. Local inventory uses a fixed loopback address
only and disables proxy routing for those requests.

## Optional local models

The baseline probes are intentionally separate:

```sh
python3 scripts/inventory.py --ollama
python3 scripts/smoke_generation.py
python3 scripts/smoke_embedding.py --model-dir /path/to/local/minilm/snapshot
```

Generation uses the already-installed `gemma4:12b-mlx` tag on
`127.0.0.1:11434`; it checks the local tags before requesting inference, caps
output/context, and requests unload afterward. It never pulls a model or changes
server settings. Do not start/replace the existing server just to run this probe.
Do not select the larger model by default on a memory-constrained system.

The embedding probe requires PyTorch, Transformers, tokenizers, safetensors,
NumPy, and their dependencies in a separate environment. It reads local files
only, disables remote code, uses CPU with two threads, applies attention-masked
mean pooling and L2 normalization, and caps MiniLM input at 256 tokens. No
sentence-transformers package is required for that explicitly documented pipeline.
The [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
documents the encoder and pooling approach. These real vectors are not hashes.

`requirements/ml-observed.txt` pins direct versions observed in the preparation
probe. It is not a complete lock and is not the beginner installation route yet.
The preparation reused compatible existing cached package distributions under
an ignored local diagnostic environment. This verifies that local assets can
execute; it does not verify a clean install. No dependencies or models were
downloaded for this baseline.

The subsequent clean setup uses the complete hash-locked closure in
`requirements/ml-macos-arm64-py312.lock`, targeting macOS 14+ arm64 and Python
3.12. A new empty environment with 34 official packages passed dependency and
import-isolation checks. See [reproducibility-gates.md](reproducibility-gates.md)
for the exact tested commands and preserved initial resolution failure. Core
and ML specifications remain separate; no global software changes are required.

## Troubleshooting

| Symptom | Meaning / recovery |
|---|---|
| `no such module: fts5` | This Python's SQLite lacks FTS5. Report the gap and use an already-installed compatible interpreter; do not silently install or change system Python. |
| `Operation not permitted` from hardware or loopback read | Execution sandbox restriction; record the denied probe. Use an authorized local read; do not alter macOS security settings. |
| Ollama unavailable / local tag absent | Optional capability unavailable. Record it; no automatic install, pull, upgrade, or fallback to cloud. |
| Cached weights/tokenizer missing | Report exact missing file, revision, license and size before any download proposal. |
| Default Python cannot import ML libraries | Use an isolated compatible interpreter; do not mutate either existing book environment. |
| Tokenizer count differs from runtime | Check template/protocol/special tokens; disable exact-budget claim until reconciled. |
| Memory pressure or timeout | Keep explicit output/context limits; record failure and partial/uncertain outcome. Do not infer completion or retry blindly. |
| Raw UCI data is missing | Baseline is synthetic-only; future real-data derivation needs verified checksums and minimization. |

Local `.local/` observations can contain paths and operational metadata. They are
ignored and are not publication artifacts. Keep any external caches read-only.

The shared optional pipeline uses `python3 -m contextlab lab run all --track local-model --model-dir /path/to/existing/snapshot --workspace .local/models --reset --json`. Missing assets fail with exit 3; a mismatched asset hash is rejected. Core optional-model unit tests are skipped unless `CONTEXTLAB_MINILM_DIR` is set. Detailed exercises and observed behavior are in the lab and reproduction guides.
