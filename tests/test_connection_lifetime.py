"""Real SQLite ownership/transaction regressions; closure is checked before GC."""
from contextlib import closing, redirect_stdout
import gc
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import warnings

from contextlab.__main__ import main
from contextlab.readiness import examples
from contextlab.retrieval import lexical
from contextlab.store import ROOT, Scope, Workspace

REAL_CONNECT = sqlite3.connect


class ObservedConnection(sqlite3.Connection):
    """Run actual SQL and retain an observable close/transaction-exit order."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []
        self.closed_explicitly = False
        self.fail_sql_prefix = None

    def __enter__(self):
        self.events.append("transaction_enter")
        return super().__enter__()

    def __exit__(self, *exception):
        self.events.append("transaction_exit_begin")
        try:
            return super().__exit__(*exception)
        finally:
            self.events.append({"transaction_exit_end": True, "in_transaction": self.in_transaction})

    def execute(self, sql, *args, **kwargs):
        if self.fail_sql_prefix and sql.startswith(self.fail_sql_prefix):
            # The error is raised by SQLite, after any preceding real writes.
            return super().execute("SELECT * FROM c_b2_deliberately_missing_table")
        return super().execute(sql, *args, **kwargs)

    def close(self):
        if not self.closed_explicitly:
            self.events.append({"close": True, "in_transaction": self.in_transaction})
        super().close()
        self.closed_explicitly = True


class ConnectionLifetime(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="connection-life-", dir=base))
        self.workspace = Workspace(self.path)
        self.connections = []  # Strong refs deliberately prevent GC from closing anything.
        self.fail_sql_prefix = None

    def tearDown(self):
        evidence = ROOT / ".local/connection-lifetime-evidence" / self.path.name
        evidence.mkdir(parents=True)
        (evidence / "observations.json").write_text(json.dumps({
            "test": self.id(), "connections": len(self.connections),
            "closed_before_test_cleanup": sum(db.closed_explicitly for db in self.connections),
            "events": [db.events for db in self.connections],
        }, indent=2) + "\n")
        for db in self.connections:
            if not db.closed_explicitly:
                db.close()
        shutil.rmtree(self.path)

    def connect(self, *args, **kwargs):
        db = REAL_CONNECT(*args, factory=ObservedConnection, **kwargs)
        db.fail_sql_prefix = self.fail_sql_prefix
        self.connections.append(db)
        return db

    def assert_closed(self, connections=None):
        connections = self.connections if connections is None else connections
        self.assertTrue(connections, "test must observe at least one real connection")
        for db in connections:
            self.assertTrue(db.closed_explicitly, db.events)
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")
            exits = [i for i, e in enumerate(db.events) if isinstance(e, dict) and e.get("transaction_exit_end")]
            closes = [i for i, e in enumerate(db.events) if isinstance(e, dict) and e.get("close")]
            self.assertEqual(len(closes), 1)
            self.assertTrue(exits)
            self.assertLess(exits[-1], closes[0], "transaction must exit before close")
            self.assertFalse(db.events[exits[-1]]["in_transaction"])
            self.assertFalse(db.events[closes[0]]["in_transaction"])

    def scalar(self, sql):
        with closing(REAL_CONNECT(self.workspace.db)) as db, db:
            return db.execute(sql).fetchone()[0]

    def test_initialize_commits_and_closes_before_return(self):
        with patch("sqlite3.connect", self.connect):
            self.workspace.initialize()
            self.assert_closed()
        self.assertEqual(self.scalar("SELECT count(*) FROM sources"), 54)
        self.assertGreater(self.scalar("SELECT count(*) FROM chunks"), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM metadata"), 5)

    def test_initialize_exception_rolls_back_inserted_sources_and_closes(self):
        self.fail_sql_prefix = "INSERT INTO chunks"
        with patch("sqlite3.connect", self.connect):
            with self.assertRaises(sqlite3.OperationalError):
                self.workspace.initialize()
            self.assert_closed()
        # executescript creates the schema before the subsequent insert transaction.
        self.assertEqual(self.scalar("SELECT count(*) FROM sources"), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM chunks"), 0)

    def test_workspace_reads_materialize_results_then_close(self):
        self.workspace.initialize()
        with patch("sqlite3.connect", self.connect):
            self.assertIsInstance(self.workspace.sources(), list)
            self.assert_closed()
            self.assertEqual(self.workspace.tombstones(), set())
            self.assert_closed()
            self.assertIsInstance(self.workspace.metadata(), dict)
            self.assert_closed()
            self.assertIsInstance(self.workspace.chunks(Scope()), list)
            self.assert_closed()

    def test_each_workspace_read_closes_on_real_sql_error(self):
        self.workspace.initialize()
        for method, prefix in [(self.workspace.sources, "SELECT envelope"),
                               (self.workspace.tombstones, "SELECT source_id"),
                               (self.workspace.metadata, "SELECT key"),
                               (lambda: self.workspace.chunks(Scope()), "SELECT body")]:
            with self.subTest(prefix=prefix):
                self.fail_sql_prefix = prefix
                start = len(self.connections)
                with patch("sqlite3.connect", self.connect):
                    with self.assertRaises(sqlite3.OperationalError):
                        method()
                    self.assert_closed(self.connections[start:])

    def test_row_decode_exception_also_closes_before_propagating(self):
        self.workspace.initialize()
        for table, column, method in [("sources", "envelope", self.workspace.sources),
                                      ("chunks", "body", lambda: self.workspace.chunks(Scope()))]:
            with self.subTest(table=table):
                with closing(REAL_CONNECT(self.workspace.db)) as db, db:
                    original = db.execute(f"SELECT rowid, {column} FROM {table} LIMIT 1").fetchone()
                    db.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", ("{", original[0]))
                start = len(self.connections)
                try:
                    with patch("sqlite3.connect", self.connect):
                        with self.assertRaises(json.JSONDecodeError):
                            method()
                        self.assert_closed(self.connections[start:])
                finally:
                    with closing(REAL_CONNECT(self.workspace.db)) as db, db:
                        db.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", (original[1], original[0]))

    def test_delete_commits_all_projection_changes_before_close(self):
        self.workspace.initialize()
        with patch("sqlite3.connect", self.connect):
            result = self.workspace.delete_projection("SYN-REPORT-104", Scope().as_of)
            self.assert_closed()
        self.assertEqual(result["removed_refs"], ["SYN-REPORT-104@1"])
        for table in ["sources", "chunks", "chunk_fts"]:
            self.assertEqual(self.scalar(f"SELECT count(*) FROM {table} WHERE ref='SYN-REPORT-104@1'"), 0)
        self.assertEqual(self.scalar("SELECT count(*) FROM tombstones WHERE source_id='SYN-REPORT-104'"), 1)

    def test_delete_failure_rolls_back_actual_deletes_and_preserves_artifacts(self):
        self.workspace.initialize()
        counts = {t: self.scalar(f"SELECT count(*) FROM {t}") for t in ["sources", "chunks", "chunk_fts"]}
        artifact = self.workspace.artifact("retained-on-rollback", {"sentinel": True})
        self.fail_sql_prefix = "INSERT OR REPLACE INTO tombstones"
        with patch("sqlite3.connect", self.connect):
            with self.assertRaises(sqlite3.OperationalError):
                self.workspace.delete_projection("SYN-REPORT-104", Scope().as_of)
            self.assert_closed()
        self.assertEqual({t: self.scalar(f"SELECT count(*) FROM {t}") for t in counts}, counts)
        self.assertEqual(self.scalar("SELECT count(*) FROM tombstones"), 0)
        self.assertTrue(artifact.is_file())

    def test_lexical_readiness_doctor_close_on_success_with_identical_outputs(self):
        chunks = [{"chunk_id": "one", "text": "blue mug"}, {"chunk_id": "two", "text": "red plate"}]
        expected = (lexical(chunks, "mug"), examples())
        with redirect_stdout(io.StringIO()) as before:
            self.assertEqual(main(["doctor", "--json"]), 0)
        with patch("sqlite3.connect", self.connect):
            self.assertEqual(lexical(chunks, "mug"), expected[0]); self.assert_closed()
            self.assertEqual(examples(), expected[1]); self.assert_closed()
            with redirect_stdout(io.StringIO()) as after:
                self.assertEqual(main(["doctor", "--json"]), 0)
            self.assert_closed()
        self.assertEqual(before.getvalue(), after.getvalue())

    def test_lexical_readiness_doctor_close_on_real_sql_exceptions(self):
        for fn, prefix in [(lambda: lexical([{"chunk_id": "one", "text": "mug"}], "mug"), "SELECT chunk_id"),
                           (examples, "SELECT text"),
                           (lambda: main(["doctor", "--json"]), "CREATE VIRTUAL TABLE check_fts")]:
            with self.subTest(prefix=prefix):
                self.fail_sql_prefix = prefix; start = len(self.connections)
                with patch("sqlite3.connect", self.connect), redirect_stdout(io.StringIO()):
                    if prefix.startswith("CREATE"):
                        self.assertEqual(fn(), 2)
                    else:
                        with self.assertRaises(sqlite3.OperationalError):
                            fn()
                    self.assert_closed(self.connections[start:])

    def test_raw_connect_api_remains_caller_owned_with_commit_and_rollback(self):
        self.workspace.initialize()
        with patch("sqlite3.connect", self.connect):
            db = self.workspace.connect()
            self.assertIsInstance(db, sqlite3.Connection)
            try:
                with db:
                    db.execute("INSERT INTO metadata VALUES ('persisted', 'yes')")
                self.assertFalse(db.closed_explicitly)
                self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='persisted'").fetchone()[0], "yes")
                with self.assertRaisesRegex(RuntimeError, "abort"):
                    with db:
                        db.execute("INSERT INTO metadata VALUES ('rolled-back', 'no')")
                        raise RuntimeError("abort")
            finally:
                db.close()
            self.assert_closed()
        self.assertEqual(self.scalar("SELECT count(*) FROM metadata WHERE key='persisted'"), 1)
        self.assertEqual(self.scalar("SELECT count(*) FROM metadata WHERE key='rolled-back'"), 0)

    def test_close_runs_after_a_real_commit_failure_and_rollback(self):
        self.workspace.initialize()
        with patch("sqlite3.connect", self.connect):
            with self.assertRaises(sqlite3.IntegrityError):
                with closing(self.workspace.connect()) as db, db:
                    db.execute("PRAGMA foreign_keys=ON")
                    db.executescript("CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);")
                    db.execute("INSERT INTO child VALUES (1)")
            self.assert_closed()
        self.assertEqual(self.scalar("SELECT count(*) FROM child"), 0)

    def test_existing_pipeline_fixture_and_direct_test_caller_close(self):
        from test_pipeline import SupplyChain
        result = unittest.TestResult()
        with patch("sqlite3.connect", self.connect):
            SupplyChain("test_deletion_invalidates_indexes_memory_graph_and_replay").run(result)
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
            self.assert_closed()

    def test_repeated_reads_and_lexical_leave_zero_live_connections(self):
        self.workspace.initialize()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            with patch("sqlite3.connect", self.connect):
                for _ in range(50):
                    self.workspace.sources(); self.workspace.tombstones(); self.workspace.metadata()
                    lexical(self.workspace.chunks(Scope()), "mug")
                    self.assert_closed()
                self.assertEqual(len(self.connections), 350)
            # Additional GC diagnostic only; all closures above were already asserted.
            gc.collect()
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])


if __name__ == "__main__":
    unittest.main()
