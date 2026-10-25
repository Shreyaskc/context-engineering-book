# Reproduction and evidence

All reported examples, tests, tokenizer/embedding probes and inference ran on the
connected Mac. `scripts/verify_on_mac.py` refuses another operating system and
records real subprocess execution; it is not one of the twenty independent reviews.

```sh
python3 scripts/verify_on_mac.py --output .local/verification-core
```

The harness runs doctor, readiness, invariant checks, unit tests, all core stages,
all failure exercises (04/05 explicitly unavailable in core), capstone re-execution,
and explicit v4 branching/assessment. Each command has its exact argument array,
exit code and expected code, stdout/stderr files and hashes, elapsed time, source
hashes and starting commit. It never downloads, installs, changes security settings,
opens public ports, or calls a paid API.

For the optional model track, use an already-configured compatible interpreter:

```sh
MODEL_DIR=/path/to/existing/minilm/snapshot
CONTEXTLAB_MINILM_DIR="$MODEL_DIR" python3 scripts/verify_on_mac.py --model-dir "$MODEL_DIR" --output .local/verification-models
```

That adds all genuine dense/hybrid stages, real truncation/fusion exercises, real
model unit tests, and evaluation re-execution. The model environment must already
exist; the harness does not prepare it or silently switch interpreters.

Each stage writes `artifacts/NN-name.json` and `receipts/NN-name.json` under its
marked workspace. Receipts contain code hashes, fixture/label/model-spec/policy
hashes, live-projection hash, actual import/index timestamps, explicit clock/scope,
versions, command, requested UTF-8 byte limit, output hash, timing, and encoder
metadata where used. `model_runtime_usage` is null because the pipeline performs
no generation; null is not a zero-token inference measurement.

```sh
python3 -m contextlab replay --workspace .local/lab --receipt .local/lab/receipts/14-capstone.json --json
python3 -m contextlab replay --workspace .local/lab --receipt .local/lab/receipts/14-capstone.json --reexecute --json
```

Replay checks code, input, runtime, scope/clock, live projection and artifact
integrity. Re-execution compares stable output fields while naming omitted timing
keys. Optional model re-execution needs the same existing model directory and
compatible runtime. No deleted/missing artifact is reconstructed. This is not
proof of portable bitwise model generation, nor a universal replay framework.

The separate `inventory.py`, `smoke_embedding.py`, `probe_tokenizer.py`, and bounded
`smoke_generation.py` emit real local observations. Gemma generation records
backend prompt/output counters separately from bytes. Thinking text and large
context-token arrays are omitted. The inference probe is not an answer-quality test.

All operational evidence is ignored under `.local/`, including private absolute
paths in exact command records. Publish only an explicitly sanitized subset after
review. Source code, tests, dependency specs, source/provenance contracts and lab
docs are tracked locally. Before publication inspect the full tree and Git history;
`.gitignore` does not remove anything already committed.
