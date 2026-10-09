import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clara.config import defaults
from clara.contracts import ClaraError
from clara.diagnostics import write_bundle
from clara.journey import GuardedAdapter, create_journey_fixture, run_journey
from test_core import FakeWindows


class InteractiveFake(FakeWindows):
    def __init__(self, folder):
        super().__init__(folder)
        self.document_active = False
    def context(self):
        if self.document_active:
            raise ClaraError("CONTEXT_AMBIGUOUS", "Document actif")
        return super().context()
    def prepare_open(self, context, path):
        native = super().prepare_open(context, path)
        def call():
            native()
            self.document_active = True
        return call
    def prepare_activate(self, ref):
        def call():
            self.document_active = False
            self.changed = False
        return call


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.root = self.folder / "new-fixtures"
        create_journey_fixture(self.root)
        self.output = self.folder / "journey.json"
    def tearDown(self):
        self.tmp.cleanup()

    def test_full_path_runs_actual_engine_with_simulated_windows_and_stop(self):
        adapter = InteractiveFake(self.root)
        report = run_journey(defaults(), self.root, self.output, lambda: adapter, "simulated")
        self.assertEqual(report["status"], "PASSED", report.get("traceback"))
        self.assertEqual(len(report["steps"]), 14)
        self.assertTrue(all(s["status"] == "PASSED" for s in report["steps"]))
        self.assertEqual(len(adapter.opened), 3)  # TXT, récent contextuel, choix du récent.
        self.assertEqual(report["steps"][-1]["observed"]["open_calls_after_stop"], 0)
        self.assertEqual(report["steps"][-1]["observed"]["completed_read_steps"], 2)
        self.assertFalse(adapter.document_active)
        self.assertEqual(json.loads(self.output.read_text())["backend"], "simulated")

    def test_unknown_open_is_preserved_and_remaining_steps_skipped(self):
        adapter = InteractiveFake(self.root)
        adapter.observe_open = lambda ref: (_ for _ in ()).throw(OSError("native observation missing"))
        report = run_journey(defaults(), self.root, self.output, lambda: adapter, "simulated")
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["steps"][4]["status"], "UNKNOWN")
        self.assertTrue(all(s["status"] == "SKIPPED" for s in report["steps"][5:]))
        self.assertIn("native observation missing", json.dumps(report["recent_journal"]))

    def test_guard_refuses_personal_file_and_parent_navigation(self):
        adapter = GuardedAdapter(InteractiveFake(self.root), self.root)
        outside = self.folder / "personal.txt"
        outside.write_text("private")
        context = adapter.context()
        with self.assertRaises(ClaraError):
            adapter.prepare_open(context, outside)
        with self.assertRaises(ClaraError):
            adapter.prepare_navigation(context, self.root.parent)
        self.assertEqual(outside.read_text(), "private")
        adapter.close()

    def test_guard_refuses_switch_to_other_window(self):
        base = InteractiveFake(self.root)
        adapter = GuardedAdapter(base, self.root)
        original = base.context
        def changed():
            ctx = original()
            ctx["window"]["window_id"] = "another-window"
            return ctx
        base.context = changed
        with self.assertRaises(ClaraError):
            adapter.context()
        adapter.close()

    def test_existing_fixture_is_not_reused_or_overwritten(self):
        (self.root / "notes.txt").write_text("modified by user")
        with self.assertRaises(ValueError):
            create_journey_fixture(self.root)
        self.assertEqual((self.root / "notes.txt").read_text(), "modified by user")

    def test_missing_window_produces_failure_with_no_actions(self):
        def failed():
            raise RuntimeError("window unavailable")
        report = run_journey(defaults(), self.root, self.output, failed, "simulated")
        self.assertEqual(report["status"], "FAILED")
        self.assertTrue(all(s["status"] == "SKIPPED" for s in report["steps"]))

    def test_zip_contains_journey_results(self):
        self.output.write_text(json.dumps({"status": "FAILED", "steps": [{"status": "UNKNOWN"}]}))
        archive = self.folder / "report.zip"
        write_bundle(archive, self.folder, "running")
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(json.loads(z.read("journey.json"))["steps"][0]["status"], "UNKNOWN")

    def launcher(self):
        path = Path(__file__).parents[1] / "scripts/launch.py"
        spec = importlib.util.spec_from_file_location("journey_test_launch", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_launcher_does_not_repeat_attempt_until_explicit_request(self):
        launch = self.launcher()
        (self.folder / "journey-version.json").write_text('{"version":1}')
        self.output.write_text('{"status":"FAILED"}')
        with patch.object(launch.subprocess, "run") as run:
            result = launch.run_self_test("python", self.folder / "config.json", self.folder, {})
            run.assert_not_called()
            self.assertFalse(result["ran_now"])

    def test_launcher_timeout_keeps_partial_results_and_marks_incomplete(self):
        launch = self.launcher()
        def timed_out(*args, **kwargs):
            self.output.write_text('{"status":"RUNNING","steps":[{"status":"PASSED"}]}')
            raise subprocess.TimeoutExpired("journey", 180)
        with patch.object(launch.subprocess, "run", side_effect=timed_out):
            result = launch.run_self_test("python", self.folder / "config.json", self.folder, {}, True)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(json.loads(self.output.read_text())["steps"][0]["status"], "PASSED")
        self.assertEqual(json.loads((self.folder / "journey-version.json").read_text())["status"], "INCOMPLETE")

    def test_missing_old_report_does_not_trigger_new_window_openings(self):
        launch = self.launcher()
        (self.folder / "journey-version.json").write_text('{"version":1,"status":"FAILED"}')
        with patch.object(launch.subprocess, "run") as run:
            self.assertFalse(launch.run_self_test("python", self.folder / "config.json", self.folder, {})["ran_now"])
            run.assert_not_called()

    def test_corrupt_child_report_is_marked_incomplete(self):
        launch = self.launcher()
        def corrupt(*args, **kwargs):
            self.output.write_text("broken JSON")
            return subprocess.CompletedProcess([], 1, "", "crash")
        with patch.object(launch.subprocess, "run", side_effect=corrupt):
            result = launch.run_self_test("python", self.folder / "config.json", self.folder, {}, True)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("traceback", json.loads(self.output.read_text()))


if __name__ == "__main__":
    unittest.main()
