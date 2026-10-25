"""Runnable prerequisite concepts, distinct from machine capability inventory."""
import json
import math
import sqlite3

from .retrieval import cosine
from .store import instant


def examples():
    parsed = json.loads('{"unknown": null, "known_zero": 0, "checked": false}')
    left, right = [3, 4], [6, 8]
    relevant, retrieved = {"policy", "purchase", "case"}, ["policy", "unrelated"]
    true_positives = len(relevant.intersection(retrieved))
    start, end = instant("2026-04-14T09:00:00Z"), instant("2026-04-14T10:00:00Z")
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE ranking USING fts5(text)")
        db.executemany("INSERT INTO ranking VALUES (?)", [("blue mug purchase",), ("red plate",), ("mug return",)])
        rows = db.execute("SELECT text, bm25(ranking) FROM ranking WHERE ranking MATCH 'mug' ORDER BY bm25(ranking), text").fetchall()
    return {
        "status": "observed",
        "shell_versus_python": {"shell_command": "python3 -m contextlab readiness --json", "python_expression": "2 + 2", "python_result": 2+2, "rule": "Run shell commands at the terminal prompt; Python expressions belong in a .py file or Python interpreter. Do not paste a shell command at a Python >>> prompt."},
        "json_none_zero": {"parsed": parsed, "unknown_is_none": parsed["unknown"] is None, "zero_is_none": parsed["known_zero"] is None, "zero_is_falsey": not parsed["known_zero"], "rule": "null becomes None, false becomes False, and zero remains a known number. Use is None to test missingness."},
        "utc_half_open": {"interval": "[2026-04-14T09:00:00Z, 2026-04-14T10:00:00Z)", "start_included": start <= start < end, "end_included": start <= end < end, "rule": "UTC timestamps are timezone-aware. A half-open interval includes its start and excludes its end."},
        "lexical_direction": {"sqlite_fts5_rows_in_native_best_first_order": [{"text": text, "native_bm25": score, "display_score_negative_bm25": -score} for text, score in rows], "rule": "SQLite FTS5 native bm25 sorts lower first. This lab displays negative bm25 and sorts higher first; never mix the directions."},
        "dot_and_cosine": {"left": left, "right": right, "dot_product": math.fsum(a*b for a, b in zip(left, right)), "cosine": cosine(left, right), "orthogonal_cosine": cosine([1, 0], [0, 1]), "rule": "These are math vectors, not semantic embeddings. Dot product depends on length; cosine divides by both lengths. Normalized-vector dot product equals cosine."},
        "precision_recall": {"retrieved": retrieved, "relevant": sorted(relevant), "true_positives": true_positives, "precision": true_positives / len(retrieved), "recall": true_positives / len(relevant), "rule": "Precision asks how much retrieved material is relevant; recall asks how much relevant material was retrieved."},
        "bytes_versus_tokens": {"text": "Café", "characters": len("Café"), "utf8_bytes": len("Café".encode()), "model_tokens": None, "model_tokens_status": "not measured; a compatible model tokenizer and prompt template are required", "rule": "Characters and bytes are measured units, not model tokens."},
    }
