"""C-B3: retain real readers to prove ownership without garbage collection."""
import gc
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import inventory

REAL_OPEN = Path.open
REAL_DIGEST = hashlib.file_digest


class ReadFailure(io.BufferedReader):
    def readinto(self, buffer):
        self.bytes_read = super().readinto(buffer)
        raise OSError("injected read failure after actual binary read")


class InventoryReaderLifetime(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="inventory-readers-", dir=base))
        self.file = self.path / "fixture.bin"
        self.payload = bytes(range(256)) * 2049
        self.file.write_bytes(self.payload)
        self.streams = []  # Keep strong references until after closure assertions.
        self.record_open = lambda path, *args, **kwargs: self.opened(path, *args, **kwargs)

    def tearDown(self):
        evidence = ROOT / ".local/inventory-reader-evidence" / self.path.name
        evidence.mkdir(parents=True)
        (evidence / "observations.json").write_text(json.dumps({
            "test": self.id(), "real_readers_retained": len(self.streams),
            "closed_before_test_cleanup": [stream.closed for stream in self.streams],
        }, indent=2) + "\n")
        for stream in self.streams:
            stream.close()
        shutil.rmtree(self.path)

    def opened(self, path, *args, **kwargs):
        stream = REAL_OPEN(path, *args, **kwargs)
        if path == self.file:
            self.streams.append(stream)
        return stream

    def assert_readers_closed(self):
        self.assertTrue(self.streams, "must acquire at least one real binary reader")
        for stream in self.streams:
            self.assertTrue(stream.closed, "reader must close before return/raise is observed")
            self.assertTrue(stream.raw.closed, "underlying real file must also close")
            with self.assertRaises(ValueError):
                stream.fileno()

    def test_known_binary_digest_unchanged_and_reader_closed_before_return(self):
        with patch.object(Path, "open", self.record_open):
            result = inventory.sha(self.file)
            self.assertEqual(result, hashlib.sha256(self.payload).hexdigest())
            self.assert_readers_closed()

    def test_empty_file_digest_and_closure(self):
        self.file.write_bytes(b"")
        with patch.object(Path, "open", self.record_open):
            self.assertEqual(inventory.sha(self.file), hashlib.sha256(b"").hexdigest())
            self.assert_readers_closed()

    def test_real_read_failure_closes_before_exception_propagates(self):
        def failing_open(path, *args, **kwargs):
            if path != self.file:
                return REAL_OPEN(path, *args, **kwargs)
            stream = ReadFailure(io.FileIO(path, "r"))
            self.streams.append(stream)
            return stream
        with patch.object(Path, "open", failing_open):
            with self.assertRaisesRegex(OSError, "after actual binary read"):
                inventory.sha(self.file)
            self.assertGreater(self.streams[-1].bytes_read, 0)
            self.assert_readers_closed()

    def test_digest_finalization_failure_still_closes_real_reader(self):
        actual_hashes = []
        class FinalizationFailure:
            def hexdigest(self):
                raise RuntimeError("injected hex finalization failure")
        def failing_finalization(stream, algorithm):
            actual_hashes.append(REAL_DIGEST(stream, algorithm).hexdigest())
            return FinalizationFailure()
        with patch.object(Path, "open", self.record_open), patch.object(inventory.hashlib, "file_digest", failing_finalization):
            with self.assertRaisesRegex(RuntimeError, "hex finalization failure"):
                inventory.sha(self.file)
            self.assertEqual(actual_hashes, [hashlib.sha256(self.payload).hexdigest()])
            self.assert_readers_closed()

    def test_repeated_calls_leave_no_retained_real_readers_open(self):
        expected = hashlib.sha256(self.payload).hexdigest()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            with patch.object(Path, "open", self.record_open):
                for _ in range(128):
                    self.assertEqual(inventory.sha(self.file), expected)
                    self.assert_readers_closed()
            self.assertEqual(len(self.streams), 128)
            gc.collect()  # Additional diagnostic; closure was already asserted above.
        self.assertEqual([w for w in caught if issubclass(w.category, ResourceWarning)], [])

    def test_missing_path_preserves_open_error_without_acquiring_a_reader(self):
        self.file.unlink()
        with patch.object(Path, "open", self.record_open):
            with self.assertRaises(FileNotFoundError):
                inventory.sha(self.file)
        self.assertEqual(self.streams, [])


if __name__ == "__main__":
    unittest.main()
