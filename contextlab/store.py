"""Versioned source envelopes, span lineage, scoped eligibility and SQLite/FTS5."""
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "fixtures/corpus.jsonl"
IDENTITIES = ROOT / "fixtures/identities.json"
INGESTION_EVENTS = ROOT / "fixtures/ingestion-events.jsonl"
ACCESS_POLICY = ROOT / "fixtures/access-policy.json"
AS_OF = "2026-01-15T12:00:00Z"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps require an explicit timezone")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Scope:
    principal: str = "service-reader"
    tenant: str = "northstar-retail"
    team: str = "service-operations"
    as_of: str = AS_OF
    branch: str = "northstar-v3"
    knowledge_at: str | None = None

    def validate(self):
        identities = json.loads(IDENTITIES.read_text())
        identity = identities.get(self.principal)
        if not identity or self.tenant != identity["tenant"] or self.team not in identity["teams"]:
            raise ValueError("principal, tenant, and team do not match the fixture identity grant")
        instant(self.as_of)
        if self.knowledge_at is not None:
            instant(self.knowledge_at)
        if self.branch not in {"northstar-v3", "northstar-v4"}:
            raise ValueError("unknown explicit scenario branch")


def validate_sources(sources):
    seen = set()
    for source in sources:
        required = {"schema_version", "source_id", "version", "ref", "sha256", "content", "tenant", "allowed_teams", "allowed_principals", "origin", "license", "provenance", "available_at", "valid_from", "valid_until", "deleted_at", "supersedes", "branch", "trust", "kind", "record", "lineage"}
        if not isinstance(source, dict) or set(source) != required:
            raise ValueError("missing or unexpected source envelope fields")
        if source["schema_version"] != 1 or type(source["version"]) is not int or source["version"] < 1:
            raise ValueError("unsupported schema or immutable source version")
        if not isinstance(source["source_id"], str) or not re.fullmatch(r"SYN-[A-Z0-9-]+", source["source_id"]):
            raise ValueError("invalid synthetic source ID")
        if not isinstance(source["content"], str) or not source["content"]:
            raise ValueError("source content must be nonempty text")
        if source["tenant"] not in {"northstar-retail", "harbor-retail"} or source["branch"] not in {"common", "northstar-v3", "northstar-v4"}:
            raise ValueError("unknown tenant or scenario branch")
        if source["trust"] not in {"authoritative_fixture", "reported_claim", "untrusted_instruction"}:
            raise ValueError("unknown source trust category")
        if source["kind"] not in {"guide", "policy", "purchase", "case", "report", "fulfillment", "inventory", "adversarial"} or not isinstance(source["record"], dict):
            raise ValueError("invalid source kind or structured record")
        for field in ["allowed_teams", "allowed_principals", "supersedes"]:
            if not isinstance(source[field], list) or not all(isinstance(v, str) for v in source[field]) or len(set(source[field])) != len(source[field]):
                raise ValueError("grants and supersession refs must be unique string lists")
        if set(source["allowed_teams"]) - {"service-operations", "inventory-operations", "platform-engineering"}:
            raise ValueError("unknown team grant")
        if source["ref"] != f'{source["source_id"]}@{source["version"]}' or source["ref"] in seen:
            raise ValueError("invalid or duplicate immutable source ref")
        seen.add(source["ref"])
        if source["sha256"] != digest(source["content"]):
            raise ValueError("source content hash mismatch")
        if source["origin"] != "synthetic" or source["license"] != "MIT" or source["provenance"] != "original fictional teaching corpus; not UCI-derived":
            raise ValueError("baseline corpus must remain original, attributed synthetic data")
        if not source["allowed_teams"] and not source["allowed_principals"]:
            raise ValueError("empty grants must not imply public access")
        for field in ["available_at", "valid_from", "valid_until", "deleted_at"]:
            if source[field] is not None:
                if not isinstance(source[field], str):
                    raise ValueError("time fields must be RFC 3339 strings or permitted nulls")
                instant(source[field])
        if source["available_at"] is None or source["valid_from"] is None:
            raise ValueError("availability and valid-from timestamps are required")
        if source["valid_until"] and instant(source["valid_until"]) <= instant(source["valid_from"]):
            raise ValueError("validity interval must be nonempty")
        if source["lineage"] != {"parent_ref": None, "char_start": 0, "char_end": len(source["content"])}:
            raise ValueError("invalid source span lineage")


def load_sources(path=CORPUS):
    sources = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    validate_sources(sources)
    return sources


def ingestion_events():
    events = [json.loads(line) for line in INGESTION_EVENTS.read_text().splitlines() if line.strip()]
    for event in events:
        if instant(event["index_ready_at"]) < instant(event["ingested_at"]):
            raise ValueError("index readiness cannot precede ingestion")
    if len({e["ref"] for e in events}) != len(events):
        raise ValueError("duplicate ingestion event ref")
    return {event["ref"]: event for event in events}


def eligibility(source, scope, tombstones=(), events=None, current_policy=None):
    if source["tenant"] != scope.tenant:
        return "tenant"
    if scope.team not in source["allowed_teams"] and scope.principal not in source["allowed_principals"]:
        return "grant"
    current_policy = current_policy if current_policy is not None else json.loads(ACCESS_POLICY.read_text())
    denial = current_policy["source_denials"].get(source["source_id"], {})
    if scope.team in denial.get("teams", []) or scope.principal in denial.get("principals", []):
        return "current_disclosure_denial"
    if source["branch"] not in {"common", scope.branch}:
        return "branch"
    now = instant(scope.as_of)
    knowledge = instant(scope.knowledge_at or scope.as_of)
    if instant(source["available_at"]) > knowledge:
        return "not_yet_available"
    events = events if events is not None else ingestion_events()
    event = events.get(source["ref"])
    if event is None or instant(event["ingested_at"]) > knowledge:
        return "not_yet_ingested"
    if instant(event["index_ready_at"]) > knowledge:
        return "index_not_ready"
    if instant(source["valid_from"]) > now or source["valid_until"] and instant(source["valid_until"]) <= now:
        return "validity"
    if source["source_id"] in tombstones or source["deleted_at"] and instant(source["deleted_at"]) <= now:
        return "deleted"
    if source["trust"] == "untrusted_instruction":
        return "quarantined_untrusted_instruction"
    return None


def eligible_sources(sources, scope, tombstones=()):
    scope.validate()
    events = ingestion_events()
    policy = json.loads(ACCESS_POLICY.read_text())
    allowed = [s for s in sources if eligibility(s, scope, tombstones, events, policy) is None]
    superseded = {ref for source in allowed for ref in source["supersedes"]}
    return [s for s in allowed if s["ref"] not in superseded]


def chunk_source(source, max_chars=360):
    if max_chars < 32:
        raise ValueError("chunk size must be at least 32 characters")
    text = source["content"]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end]
        chunks.append({"chunk_id": f'{source["ref"]}#c{len(chunks)+1:03}', "ref": source["ref"], "source_id": source["source_id"], "source_sha256": source["sha256"], "text": chunk, "char_start": start, "char_end": end, "byte_start": len(text[:start].encode()), "byte_end": len(text[:end].encode()), "kind": source["kind"], "trust": source["trust"]})
        start = end
    return chunks


class Workspace:
    def __init__(self, path):
        if (ROOT / ".local").is_symlink():
            raise ValueError("workspace .local root must not be a symlink")
        self.path = Path(path).resolve()
        base = (ROOT / ".local").resolve()
        if not self.path.is_relative_to(base) or self.path == base:
            raise ValueError("workspace must be a child of this repository's .local directory")
        self.db = self.path / "evidence.sqlite"

    def initialize(self, reset=False):
        if self.path.exists() and reset:
            if not (self.path / ".contextlab-workspace").is_file():
                raise ValueError("refusing reset without this lab's workspace marker")
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        if not (self.path / ".contextlab-workspace").exists():
            if any(self.path.iterdir()):
                raise ValueError("refusing to initialize a nonempty unmarked directory")
            (self.path / ".contextlab-workspace").write_text("contextlab-v1\n")
        (self.path / "artifacts").mkdir(exist_ok=True)
        (self.path / "receipts").mkdir(exist_ok=True)
        if not self.db.exists():
            sources = load_sources()
            actual_ingested = datetime.now(timezone.utc).isoformat()
            # Exit the transaction (commit/rollback) before closing the owned handle.
            with closing(self.connect()) as db, db:
                db.executescript("CREATE TABLE sources(ref TEXT PRIMARY KEY, envelope TEXT NOT NULL); CREATE TABLE chunks(chunk_id TEXT PRIMARY KEY, ref TEXT NOT NULL, body TEXT NOT NULL); CREATE TABLE tombstones(source_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL); CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE VIRTUAL TABLE chunk_fts USING fts5(chunk_id UNINDEXED, ref UNINDEXED, text);")
                for source in sources:
                    db.execute("INSERT INTO sources VALUES (?, ?)", (source["ref"], canonical(source)))
                    for chunk in chunk_source(source):
                        db.execute("INSERT INTO chunks VALUES (?, ?, ?)", (chunk["chunk_id"], chunk["ref"], canonical(chunk)))
                        db.execute("INSERT INTO chunk_fts VALUES (?, ?, ?)", (chunk["chunk_id"], chunk["ref"], chunk["text"]))
                metadata = {"actual_mac_import_started_at_utc": actual_ingested, "actual_mac_index_ready_at_utc": datetime.now(timezone.utc).isoformat(), "reconstruction_mode": "synthetic historical ingestion/index-event fixture; actual runtime import times are separate", "fixture_ingestion_events_sha256": digest(INGESTION_EVENTS.read_bytes()), "corpus_sha256": digest(CORPUS.read_bytes())}
                db.executemany("INSERT INTO metadata VALUES (?, ?)", metadata.items())
        return self

    def connect(self):
        """Return a caller-owned raw connection; its transaction context does not close it."""
        return sqlite3.connect(self.db)

    def sources(self):
        with closing(self.connect()) as db, db:
            return [json.loads(row[0]) for row in db.execute("SELECT envelope FROM sources ORDER BY ref")]

    def tombstones(self):
        with closing(self.connect()) as db, db:
            return {row[0] for row in db.execute("SELECT source_id FROM tombstones")}

    def metadata(self):
        with closing(self.connect()) as db, db:
            return dict(db.execute("SELECT key, value FROM metadata"))

    def eligible(self, scope):
        return eligible_sources(self.sources(), scope, self.tombstones())

    def chunks(self, scope):
        refs = [s["ref"] for s in self.eligible(scope)]
        if not refs:
            return []
        with closing(self.connect()) as db, db:
            rows = db.execute("SELECT body FROM chunks WHERE ref IN (" + ",".join("?" for _ in refs) + ") ORDER BY chunk_id", refs)
            return [json.loads(row[0]) for row in rows]

    def artifact(self, name, value):
        path = self.path / "artifacts" / (name + ".json")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def delete_projection(self, source_id, at):
        """Erase a source and all cached derivatives from this isolated live projection.

        Immutable synthetic authoring fixtures remain outside the projection.
        Receipts contain hashes, not source content, and are retained as audit evidence.
        """
        instant(at)
        with closing(self.connect()) as db, db:
            db.execute("PRAGMA secure_delete=ON")
            refs = [r[0] for r in db.execute("SELECT ref FROM sources") if r[0].rsplit("@", 1)[0] == source_id]
            for ref in refs:
                db.execute("DELETE FROM chunk_fts WHERE ref=?", (ref,))
                db.execute("DELETE FROM chunks WHERE ref=?", (ref,))
                db.execute("DELETE FROM sources WHERE ref=?", (ref,))
            db.execute("INSERT OR REPLACE INTO tombstones VALUES (?, ?)", (source_id, at))
            # SQLite secure_delete clears freed table content; the lab does not promise
            # forensic erasure of storage, OS caches, backups, or the authoring fixture.
            db.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")
        for path in (self.path / "artifacts").glob("*.json"):
            path.unlink()
        dense = self.path / "dense.json"
        if dense.exists():
            dense.unlink()
        return {"source_id": source_id, "removed_refs": refs, "invalidated": ["FTS5", "chunks", "dense", "candidate/pack/claim/state/memory/graph artifacts"], "scope": "isolated live projection; immutable synthetic fixture and external backups are not erased"}
