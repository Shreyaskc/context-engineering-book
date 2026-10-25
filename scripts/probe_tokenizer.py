"""Measure local content tokens without claiming backend prompt-template accuracy."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer-file", required=True, help="existing tokenizer.json")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        raise RuntimeError("Preparation probes must execute on the connected Mac")
    from tokenizers import Tokenizer
    path = Path(args.tokenizer_file).resolve(strict=True)
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    tokenizer = Tokenizer.from_file(str(path))
    rows = []
    for text in ["CASE-SYN-104: two blue mugs at GBP 12.50 each.", "Fulfillment is unknown. No automatic refund.", "Café — £25.00 ☕"]:
        rows.append({"text": text, "characters": len(text), "utf8_bytes": len(text.encode()), "content_token_ids_without_added_specials": tokenizer.encode(text, add_special_tokens=False).ids, "tokens_with_tokenizer_postprocessor": len(tokenizer.encode(text, add_special_tokens=True).ids)})
    print(json.dumps({"schema_version": 1, "status": "observed", "system": platform.system(), "architecture": platform.machine(), "python": platform.python_version(), "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "tokenizers_version": importlib.metadata.version("tokenizers"), "tokenizer_sha256": digest, "measure_scope": "local content tokenization only; backend renderer/template and full prompt budget unverified", "rows": rows, "counted_review_cycle": False}, indent=2, ensure_ascii=False, sort_keys=True))
