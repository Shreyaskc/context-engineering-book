# Honest budget units

Three distinct measurements belong in receipts:

1. UTF-8 bytes of the exact serialized evidence or prompt, with its scope named.
2. Local tokenizer counts, with the tokenizer artifact hash, special-token mode,
   exact text/template, tokenizer-library version, and truncation settings.
3. Actual runtime usage returned by the inference backend, including missing
   fields as unknown and separate prompt/output counts when provided.

Characters, Python string length, bytes, and words are not model tokens. The core
teaching track uses `utf8_bytes`; it does not divide by four and call the result
tokens. Budget complete serialization, separators, IDs, and citation overhead.
Byte packing demonstrates resource allocation but does not establish that a
generation request fits a model context window.

## Optional accurate track and current evidence

The local MiniLM cache includes its real WordPiece tokenizer, model weights,
pooling configuration, and a sentence-transformer maximum sequence length of
256 tokens. The base BERT tokenizer/config advertises 512; the embedding track
must honor the **encoder pipeline's 256 limit**, including special tokens, and
record truncation. These counts apply to MiniLM, not to Gemma generation.

The installed Gemma Ollama manifests reference a 32,169,626-byte `tokenizer.json`
(SHA-256 `cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f`).
That is stronger evidence than counting with an unrelated tokenizer. The
`tokenizer_config.json` does not contain a `chat_template`; `/api/show` exposes a
short prompt template, and a backend renderer may add protocol tokens. Exact
end-to-end chat budgeting is therefore **not yet validated**. Local content-token
counts alone do not establish the final rendered request cost.

A future accurate adapter must identify the effective renderer/template, freeze
its source/hash, serialize messages and tool schemas exactly, and compare local
counts with runtime prompt counts across empty, ASCII, Unicode, multi-message,
system/tool, and boundary cases. Any discrepancy disables the accuracy claim.
If template evidence is incomplete, retain byte budgets and separately report
runtime usage. Do not use Gemma 2, Qwen, Llama, or tiktoken counts as Gemma 4 counts.

An advertised 262,144-token model context limit is model metadata, not proof of
the server's allocated context, practical memory capacity, or validated budget.
Generation probes request a small explicit context and output cap. A full pack
also reserves answer/protocol overhead; receipts distinguish requested limits,
preflight measures, and actual usage. Missing usage is not zero.

The official [Ollama usage reference](https://docs.ollama.com/api/usage) describes
the runtime prompt/output counters and nanosecond durations. Local server behavior
must still be observed for the pinned version.
