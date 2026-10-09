import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from clara.config import defaults, save
from clara.diagnostics import LIMIT, bounded_probe, collect, journal_snapshot, native_probe, write_bundle
from test_core import Fixture


class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bundle_keeps_useful_logs_but_does_not_copy_audio_or_personal_files(self):
        save(self.folder / "config.json", defaults())
        (self.folder / "measurements.jsonl").write_text('{"kind":"error","message":"bug"}\n')
        (self.folder / "secret.pdf").write_bytes(b"personal document")
        (self.folder / "audio.wav").write_bytes(b"raw audio")
        destination = self.folder / "diagnostic.zip"
        write_bundle(destination, self.folder, "application en cours", probes={"sapi": {"status": "WARNING"}})
        with zipfile.ZipFile(destination) as z:
            self.assertNotIn("secret.pdf", z.namelist())
            self.assertNotIn("audio.wav", z.namelist())
            report = json.loads(z.read("diagnostic.json"))
            self.assertEqual(report["checks"]["config"], "OK")
            self.assertEqual(report["probes"]["sapi"]["status"], "WARNING")
            self.assertIn("catalogue.py", report["source_sha256"])
            self.assertIn(b"bug", z.read("measurements.jsonl"))

    def test_missing_config_still_produces_explanatory_report(self):
        contents = collect(self.folder, "installation failed")
        report = json.loads(contents["diagnostic.json"])
        self.assertEqual(report["checks"]["config"], "ERROR")
        self.assertTrue(report["collection_errors"])
        self.assertFalse((self.folder / "config.json").exists())

    def test_invalid_config_is_preserved_and_exported(self):
        (self.folder / "config.json").write_text("{broken")
        contents = collect(self.folder, "failure")
        self.assertEqual(contents["config-invalid.txt"], "{broken")
        self.assertEqual((self.folder / "config.json").read_text(), "{broken")

    def test_log_tail_is_bounded_and_contains_latest_error(self):
        (self.folder / "ollama.log").write_bytes(b"x" * (LIMIT * 2) + b"latest error")
        value = collect(self.folder, "failure")["ollama.log"]
        self.assertEqual(len(value), LIMIT)
        self.assertTrue(value.endswith("latest error"))

    def test_sqlite_snapshot_is_read_only_bounded_and_does_not_mark_pending_actions(self):
        path = self.folder / "history.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript("CREATE TABLE events(id INTEGER PRIMARY KEY,timestamp TEXT,kind TEXT,payload TEXT); CREATE TABLE actions(action_id TEXT,request_id TEXT,step_id TEXT,payload TEXT,result TEXT);")
            db.executemany("INSERT INTO events VALUES (?, 'date', 'test', '{}')", [(i,) for i in range(150)])
            db.execute("INSERT INTO actions VALUES ('a','r','s','{}',NULL)")
        snapshot = journal_snapshot(path)
        self.assertEqual(len(snapshot["events"]), 100)
        self.assertIsNone(snapshot["actions"][0][-1])
        with sqlite3.connect(path) as db:
            self.assertIsNone(db.execute("SELECT result FROM actions").fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 150)

    def test_corrupt_journal_does_not_prevent_report(self):
        (self.folder / "history.sqlite").write_bytes(b"broken database")
        report = json.loads(collect(self.folder, "failure")["diagnostic.json"])
        self.assertTrue(any("DatabaseError" in e for e in report["collection_errors"]))

    def test_probe_timeout_is_explicit_and_bounded(self):
        with patch("clara.diagnostics.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 20)) as run:
            result = bounded_probe("microphone", {})
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(run.call_args.kwargs["timeout"], 20)

    @unittest.skipIf(os.name == "nt", "Contrôle du mode non Windows")
    def test_linux_does_not_claim_native_success(self):
        self.assertEqual(native_probe("microphone", {})["status"], "NOT_TESTED")

    def test_failed_export_keeps_previous_zip_intact(self):
        path = self.folder / "diagnostic.zip"
        write_bundle(path, self.folder, "previous")
        previous = path.read_bytes()
        with patch("clara.diagnostics.collect", side_effect=RuntimeError("failure")), self.assertRaises(RuntimeError):
            write_bundle(path, self.folder, "new")
        self.assertEqual(path.read_bytes(), previous)
        self.assertFalse(path.with_suffix(".zip.tmp").exists())

    def test_launcher_install_failure_exports_stage_and_traceback(self):
        source = Path(__file__).parents[1] / "scripts/launch.py"
        spec = importlib.util.spec_from_file_location("clara_test_launch", source)
        launch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launch)
        root = self.folder / "repository"
        (root / ".venv/Scripts").mkdir(parents=True)
        (root / ".venv/Scripts/python.exe").touch()
        data = self.folder / "data"
        process = MagicMock()
        process.__enter__.return_value = process
        process.stdout = ["installation error: wheel unavailable\n"]
        process.wait.return_value = 1
        cwd = Path.cwd()
        try:
            with patch.object(launch, "ROOT", root), patch.object(launch, "user_folder", return_value=data), \
                 patch.object(sys, "platform", "win32"), patch.object(sys, "argv", ["launch.py"]), \
                 patch.object(launch.subprocess, "Popen", return_value=process):
                self.assertEqual(launch.main(), 1)
            with zipfile.ZipFile(root / "diagnostic-clara.zip") as z:
                self.assertEqual(json.loads(z.read("diagnostic.json"))["stage"], "échec : installation")
                self.assertIn(b"wheel unavailable", z.read("launcher.log"))
                self.assertIn(b"Traceback", z.read("launcher.log"))
        finally:
            os.chdir(cwd)

    @unittest.skipIf(os.name == "nt", "Le lancement non Windows échoue sans préparation")
    def test_bootstrap_report_works_without_site_packages(self):
        source = Path(__file__).parents[1]
        root = self.folder / "repository"
        (root / "scripts").mkdir(parents=True)
        (root / "src/clara").mkdir(parents=True)
        shutil.copy(source / "scripts/launch.py", root / "scripts/launch.py")
        for name in ["__init__.py", "config.py", "diagnostics.py"]:
            shutil.copy(source / "src/clara" / name, root / "src/clara" / name)
        env = dict(os.environ, LOCALAPPDATA=str(self.folder / "appdata"))
        result = subprocess.run([sys.executable, "-S", str(root / "scripts/launch.py")],
                                env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        with zipfile.ZipFile(root / "diagnostic-clara.zip") as z:
            report = json.loads(z.read("diagnostic.json"))
            self.assertEqual(report["stage"], "échec : initialisation")
            self.assertIn(b"RuntimeError", z.read("launcher.log"))


class EngineDiagnostics(Fixture):
    def test_original_native_exception_is_preserved_in_report_history(self):
        def fail():
            raise OSError("original Windows diagnostic")
        self.adapter.prepare_open = lambda context, path: fail
        engine = self.start()
        engine.submit("ouvre notes")
        event = self.event("result")
        self.assertEqual(event["result"]["status"], "UNKNOWN")
        snapshot = journal_snapshot(self.folder / "history.sqlite")
        errors = [json.loads(row[2]) for row in snapshot["events"] if row[1] == "native_error"]
        self.assertTrue(any("original Windows diagnostic" in e["traceback"] for e in errors))


if __name__ == "__main__":
    unittest.main()
