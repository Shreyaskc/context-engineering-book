"""Offline MiniLM diagnostic using real weights, masked mean pooling, normalization."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path


def main(model_dir):
    if platform.system() != "Darwin":
        raise RuntimeError("Preparation probes must execute on the connected Mac")
    # Force offline operation before importing model libraries. No credential reads.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    import torch.nn.functional as functional
    from transformers import AutoModel, AutoTokenizer

    model_dir = Path(model_dir).resolve(strict=True)
    required = ["model.safetensors", "tokenizer.json", "tokenizer_config.json", "config.json", "1_Pooling/config.json", "sentence_bert_config.json"]
    hashes = {}
    for name in required:
        with (model_dir / name).open("rb") as handle:
            hashes[name] = hashlib.file_digest(handle, "sha256").hexdigest()
    encoder_limit = json.loads((model_dir / "sentence_bert_config.json").read_text())["max_seq_length"]
    pooling = json.loads((model_dir / "1_Pooling/config.json").read_text())
    if encoder_limit != 256 or not pooling.get("pooling_mode_mean_tokens"):
        raise ValueError("This probe requires the documented MiniLM mean-pooling pipeline")
    texts = ["What checks are required before a return?", "Synthetic returns-v3 requires purchase and case checks; no automatic refund is authorized.", "The garden contains yellow flowers."]
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
    model = AutoModel.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False, use_safetensors=True).to("cpu").eval()
    untruncated = [len(tokenizer.encode(text, add_special_tokens=True, truncation=False)) for text in texts]
    batch = tokenizer(texts, padding=True, truncation=True, max_length=encoder_limit, return_tensors="pt")
    with torch.no_grad():
        token_embeddings = model(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
        vectors = functional.normalize((token_embeddings * mask).sum(1) / mask.sum(1).clamp(min=1e-9), p=2, dim=1)
    assert tuple(vectors.shape) == (3, 384), "unexpected embedding dimensions"
    assert torch.isfinite(vectors).all().item(), "non-finite vectors"
    assert torch.allclose(vectors.norm(dim=1), torch.ones(3), atol=1e-5), "vectors not normalized"
    return {"schema_version": 1, "purpose": "encoder execution diagnostic; no retrieval-quality claim", "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "system": platform.system(), "architecture": platform.machine(), "python": platform.python_version(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "model": "sentence-transformers/all-MiniLM-L6-v2", "asset_sha256": hashes, "versions": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "tokenizers", "safetensors", "numpy", "huggingface-hub"]}, "inputs": texts, "input_sha256": hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest(), "settings": {"device": "cpu", "threads": 2, "max_encoder_tokens_including_specials": encoder_limit, "pooling": "attention-masked mean followed by L2 normalization", "local_files_only": True, "trust_remote_code": False}, "token_counts_including_specials_untruncated": untruncated, "token_counts_used": batch["attention_mask"].sum(dim=1).tolist(), "truncated": [n > encoder_limit for n in untruncated], "shape": list(vectors.shape), "l2_norms": vectors.norm(dim=1).tolist(), "cosine_to_query": (vectors[1:] @ vectors[0]).tolist(), "vector_payload_sha256": hashlib.sha256(vectors.contiguous().numpy().tobytes()).hexdigest(), "counted_review_cycle": False, "status": "observed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="existing local snapshot; no download")
    args = parser.parse_args()
    print(json.dumps(main(args.model_dir), indent=2, sort_keys=True))
