"""Scoped lexical, genuine local dense retrieval, RRF and labeled heuristics."""
from contextlib import closing
import hashlib
import importlib.metadata
import json
import math
import os
import re
import sqlite3
from pathlib import Path

from .store import ROOT, canonical, digest


class CapabilityUnavailable(RuntimeError):
    pass


def lexical(chunks, query, k=5):
    terms = re.findall(r"[^\W_]+", query, re.UNICODE)
    if not terms or not chunks:
        return []
    # Build FTS statistics from eligible content only. Hidden tenants/teams cannot
    # influence BM25 scores through a shared-corpus document-frequency side channel.
    with closing(sqlite3.connect(":memory:")) as db, db:
        db.execute("CREATE VIRTUAL TABLE scoped_fts USING fts5(chunk_id UNINDEXED, text)")
        db.executemany("INSERT INTO scoped_fts VALUES (?, ?)", [(c["chunk_id"], c["text"]) for c in chunks])
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        rows = db.execute("SELECT chunk_id, bm25(scoped_fts) AS score FROM scoped_fts WHERE scoped_fts MATCH ? ORDER BY score, chunk_id LIMIT ?", (expression, k)).fetchall()
    lookup = {c["chunk_id"]: c for c in chunks}
    return [dict(lookup[cid], score=-score, score_definition="negative SQLite FTS5 bm25; scoped corpus only", rank=i+1, method="lexical_fts5") for i, (cid, score) in enumerate(rows)]


class LocalEncoder:
    """all-MiniLM-L6-v2: no prefixes, 256 tokens including specials, mean/L2."""
    def __init__(self, model_dir):
        if not model_dir:
            raise CapabilityUnavailable("dense retrieval requires an existing local MiniLM snapshot; no download attempted")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise CapabilityUnavailable("optional local encoder dependencies are unavailable") from exc
        path = Path(model_dir).resolve()
        names = ["model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json", "1_Pooling/config.json", "sentence_bert_config.json"]
        assets = {}
        for name in names:
            file = path / name
            if not file.is_file():
                raise CapabilityUnavailable("local encoder asset missing: " + name)
            with file.open("rb") as stream:
                assets[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        spec = json.loads((ROOT / "fixtures/encoder-spec.json").read_text())
        if any(spec["asset_sha256"].get(name) != value for name, value in assets.items()):
            raise ValueError("encoder asset differs from pinned MiniLM provenance specification")
        config = json.loads((path / "config.json").read_text())
        pooling = json.loads((path / "1_Pooling/config.json").read_text())
        sequence = json.loads((path / "sentence_bert_config.json").read_text())
        if config.get("hidden_size") != 384 or sequence.get("max_seq_length") != 256 or not pooling.get("pooling_mode_mean_tokens"):
            raise ValueError("unsupported encoder pipeline: expected local MiniLM mean-pooling/384-D/256-token configuration")
        self.torch = torch
        torch.set_num_threads(2)
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, use_safetensors=True).to("cpu").eval()
        self.metadata = {"model": spec["repository"], "revision": spec["revision"], "license": "Apache-2.0 (model card; retain its terms)", "asset_sha256": assets, "dimensions": 384, "query_prefix": "", "document_prefix": "", "max_tokens_including_specials": 256, "pooling": "attention-masked mean followed by L2 normalization", "device": "cpu", "threads": 2, "versions": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "tokenizers", "safetensors", "numpy", "huggingface-hub"]}}

    def encode(self, texts):
        torch = self.torch
        all_vectors, counts = [], []
        for start in range(0, len(texts), 16):
            batch_texts = texts[start:start+16]
            counts.extend(len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False)) for text in batch_texts)
            batch = self.tokenizer(batch_texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
            with torch.no_grad():
                hidden = self.model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                means = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                vectors = torch.nn.functional.normalize(means, p=2, dim=1)
            all_vectors.extend(vectors.tolist())
        return all_vectors, counts


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("vector dimensions differ")
    numerator = math.fsum(a*b for a, b in zip(left, right))
    denominator = math.sqrt(math.fsum(a*a for a in left) * math.fsum(b*b for b in right))
    if not denominator or not math.isfinite(numerator / denominator):
        raise ValueError("invalid vector")
    return numerator / denominator


class Retriever:
    def __init__(self, workspace, scope, model_dir=None):
        self.workspace, self.scope, self.model_dir = workspace, scope, model_dir
        self.encoder = None
        self._dense = None

    def build_dense(self):
        # Only eligible chunks enter this scope-specific vector cache.
        chunks = self.workspace.chunks(self.scope)
        self.encoder = self.encoder or LocalEncoder(self.model_dir)
        fingerprint = digest(canonical({"chunks": chunks, "scope": self.scope.__dict__, "encoder": self.encoder.metadata}))
        path = self.workspace.path / "dense.json"
        if path.exists():
            cached = json.loads(path.read_text())
            if cached.get("fingerprint") == fingerprint:
                self._dense = cached
                return cached
        vectors, counts = self.encoder.encode([c["text"] for c in chunks])
        data = {"fingerprint": fingerprint, "encoder": self.encoder.metadata, "scope": self.scope.__dict__, "chunks": chunks, "vectors": vectors, "untruncated_token_counts": counts, "truncated_chunks": [c["chunk_id"] for c, n in zip(chunks, counts) if n > 256]}
        path.write_text(canonical(data))
        self._dense = data
        return data

    def search(self, query, method="lexical", k=5):
        chunks = self.workspace.chunks(self.scope)
        if method == "lexical":
            return lexical(chunks, query, k)
        if method == "dense":
            data = self.build_dense() if self._dense is None else self._dense
            # Recheck eligibility even when a prior vector cache is available.
            allowed = {c["chunk_id"]: c for c in chunks}
            query_vectors, counts = self.encoder.encode([query])
            rows = [(c["chunk_id"], cosine(vector, query_vectors[0])) for c, vector in zip(data["chunks"], data["vectors"]) if c["chunk_id"] in allowed and c["source_sha256"] == allowed[c["chunk_id"]]["source_sha256"]]
            rows.sort(key=lambda item: (-item[1], item[0]))
            return [dict(allowed[cid], score=score, rank=i+1, method="dense_exact_cosine", score_definition="cosine of real MiniLM vectors; Python standard-library exact search", query_encoder_tokens=counts[0], query_truncated=counts[0] > 256) for i, (cid, score) in enumerate(rows[:k])]
        if method == "hybrid":
            return rrf([self.search(query, "lexical", 15), self.search(query, "dense", 15)], k=k)
        raise ValueError("unknown retrieval method")


def rrf(rankings, k=5, offset=60):
    merged = {}
    for ranking in rankings:
        for row in ranking:
            item = merged.setdefault(row["chunk_id"], dict(row, score=0.0, contributions=[]))
            contribution = 1.0 / (offset + row["rank"])
            item["score"] += contribution
            item["contributions"].append({"method": row["method"], "rank": row["rank"], "raw_score": row["score"], "rrf_contribution": contribution})
    rows = sorted(merged.values(), key=lambda row: (-row["score"], row["chunk_id"]))[:k]
    return [dict(row, rank=i+1, method="hybrid_rrf", score_definition=f"sum 1/({offset}+rank); tie by chunk_id") for i, row in enumerate(rows)]


def heuristic_rerank(rows, required_source_ids):
    """Explicit metadata heuristic, not a trained cross-encoder."""
    ranked = sorted(rows, key=lambda row: (row["source_id"] not in required_source_ids, row["trust"] != "authoritative_fixture", row["rank"], row["chunk_id"]))
    return [dict(row, previous_rank=row["rank"], rank=i+1, reranker="metadata heuristic: required case source, authoritative trust, prior rank; not learned") for i, row in enumerate(ranked)]
