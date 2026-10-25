# Primary references checked during baseline preparation

Checked 2026-10-25. Documentation describes capabilities; local probe evidence
determines which capabilities actually work on the installed versions.

- [UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online%2Bretail):
  source, historical retailer, schema, dataset citation and CC BY 4.0.
- [Dataset DOI](https://doi.org/10.24432/C5BW33).
- [CC BY 4.0 terms](https://creativecommons.org/licenses/by/4.0/).
- [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2):
  sentence encoder, masked mean pooling, normalization, 384 dimensions, 256
  word-piece input limit, declared Apache-2.0 license.
- [Pinned MiniLM revision metadata](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2/revision/1110a243fdf4706b3f48f1d95db1a4f5529b4d41?blobs=true):
  upstream revision, license declaration, LFS weight checksum and Git blob identities;
  selected local assets matched, without a weight download.
- [Ollama generate API](https://docs.ollama.com/api/generate): local generation
  request fields, keep-alive and runtime response fields.
- [Ollama model details](https://docs.ollama.com/api-reference/show-model-details):
  model metadata, template and effective renderer information where available.
- [Ollama usage](https://docs.ollama.com/api/usage): prompt/output counters and
  nanosecond duration units.

No model-license text, tokenizer, weights, or historical raw data is redistributed.

Additional implementation-facing primary references:

- [SQLite FTS5](https://www.sqlite.org/fts5.html): native BM25 direction and scoped
  index behavior. The code-facing explanations here are independently written.
- [Ollama v0.34.0 API](https://github.com/ollama/ollama/blob/v0.34.0/docs/api.md):
  pinned API schema-format support and usage fields used by the local probes.
- [Ollama Gemma 4 MLX background](https://ollama.com/blog/faster-gemma-4-mlx-mtp):
  backend context only; its benchmark results are not this lab's measurements.
- [SPDX MIT](https://spdx.org/licenses/MIT.html): identifier/text reference for
  user-owned lab licensing, separate from upstream data/model/dependency terms.

Private book research notes and manuscript prose are not copied into the labs.
