# Clean ML reproducibility and bounded capstone generation

The original baseline reused a configured cached runtime. That remains historical
evidence and is not called a clean setup. The subsequent clean gate created an
absent project-local environment from an existing Python 3.12.13 interpreter,
verified zero initial distributions and disabled user-site access, and installed
34 official PyPI packages from the complete hash lock with wheel-only,
hash-required, strict dependency checks and copy mode. ML imports resolved inside
the new environment; no foreign cache runtime appeared on its Python path.
See clean-install.json (private observation not distributed) and the independently
declared [dependency-license metadata](../data/dependency-licenses.json).

## Exact setup commands

An already installed uv must be available on PATH before the setup command.
Setup records its actual version and does not invoke a uv/Python installer.

This tested lock targets **macOS 14+, arm64, Python 3.12**. It is not a universal
lock. Core examples remain dependency-free on Python 3.12+ with SQLite FTS5.
Use an already-installed compatible base interpreter; neither Python nor global
packages are installed/upgraded by the script.

```sh
BASE_PYTHON=/path/to/existing/python3.12
python3 scripts/setup_clean_ml.py install --python "$BASE_PYTHON"
```

The target `.venv-ml-clean` must be absent. The script refuses to reuse an existing
environment and never copies `.pth` links from the configured baseline. It uses a
separate project-local package cache, the explicit official PyPI index, the
committed `requirements/ml-macos-arm64-py312.lock`, and no inherited package index,
credentials, or `PYTHONPATH`. All install steps and failures retain exact argument
arrays, exit codes, stdout/stderr hashes and lock identity in ignored local records.

Maintainers can resolve the lock explicitly with:

```sh
python3 scripts/setup_clean_ml.py lock --python "$BASE_PYTHON"
```

Resolution is not repeated during normal installation. The first resolution
failed because uv's macOS platform default was 13.0 and the pinned Torch wheel
requires macOS 14+. That failure is preserved. The corrected target is explicitly
14.0, compatible with this Mac; this did not upgrade the OS or global software.
No source distributions were built. Missing wheels or hash/dependency errors
remain failures, not instructions to switch indexes or bypass hash checks.

## Frozen-source verification

```sh
MODEL_DIR=/path/to/already-verified/minilm/snapshot
GEMMA_TOKENIZER=/path/to/existing/gemma/tokenizer.json
python3 scripts/verify_on_mac.py --output .local/frozen-core
CONTEXTLAB_MINILM_DIR="$MODEL_DIR" .venv-ml-clean/bin/python scripts/verify_on_mac.py --model-dir "$MODEL_DIR" --tokenizer-file "$GEMMA_TOKENIZER" --ollama-probes --output .local/frozen-clean-ml
```

The model path must match the pinned repository/revision and asset hashes. No
model pull/download occurs. The extended verification runs prerequisites, tests,
all core and genuine-embedding stages, deliberate failure/correction exercises,
the frozen retrieval comparison, replay re-execution, tokenizer/content probes,
a bounded original generation probe, and the existing capstone's context-backed
generation experiment. Model validation failures are separately preserved and are
non-passing. The wrapper independently requires all intended cases and their
semantic predicates; an exit code alone cannot pass the gate. Review closure
remains with the parent.

## Context-backed Gemma experiment

The standalone command is:

```sh
.venv-ml-clean/bin/python scripts/verify_capstone_generation.py --model-dir "$MODEL_DIR" --output .local/capstone-generation-fresh
```

It uses the existing authorized, time-filtered Northstar pipeline: genuine dense
plus FTS5/RRF retrieval, exact case-record assembly, and a 6000-UTF-8-byte evidence
pack. Three fixed cases test canonical January 15, April 14 at 09:22 (publication
without ingestion/index readiness), and April 14 at 09:30 (index ready). The
independent training observation never becomes case fulfillment evidence.

Each request selects the already-installed `gemma4:12b-mlx`, requests no thinking,
uses a JSON claim/citation schema, temperature 0/seed 7, a 4096-token requested
context, and a 768-token output cap. Requests are local, bounded, and request
unload afterward. An existing loaded model causes refusal to interfere. No tools,
payments, refunds, approvals, business writes or cloud inference are invoked.

The model is asked for **extractive** claims: copy whole supplied evidence spans,
with source ref and character offsets. Records retain exact packed context and
source hashes, scope/clocks, prompt/schema/request, literal response text, runtime
token usage and validation results. Hidden reasoning is neither inspected nor
saved. Bytes remain distinct from model tokens; full tokenizer/template preflight
accuracy remains unverified.

Validation distinguishes eligible in-pack locators, verbatim span matching, and
finite full-source fixture support labels. This is a narrow extractive oracle,
not universal entailment or arbitrary answer quality. Unsupported text, an invalid
locator, absent future information, duplicate/missing claim types, or an uncovered
paraphrase causes the application to withhold the unvalidated model answer. The
literal output is preserved; a failure is never rewritten into success.
