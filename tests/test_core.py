import json
import os
import queue
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from clara.config import defaults, load, save
from clara.contracts import ClaraError, action_result, observed, target, uid, utc, validate, validate_plan
from clara.engine import Engine, Gate, Ticket
from clara.planner import Planner, deterministic, plan
from clara.resolver import Choices, Resolver
from clara.storage import Journal
from clara.setup import create_fixture


class FakeWindows:
    def __init__(self, folder):
        self.folder = folder
        self.opened = []
        self.changed = False
        self.before_call = None
        self.after_call = None

    def context(self):
        return {"context_id": uid(), "application": "explorer", "capabilities": ["opening", "navigation"],
                "window": {"target_id": uid(), "kind": "window", "path": None, "window_id": "42",
                           "tab_id": None, "identity_token": "42", "observed_at": utc()},
                "current_directory": target(self.folder), "selected_targets": [], "result_sets": [], "observed_at": utc()}

    def ensure_context(self, context):
        if self.changed or Path(context["current_directory"]["path"]) != self.folder:
            raise ClaraError("WINDOW_CHANGED", "Le contexte a changé.")

    def prepare_open(self, context, path):
        if self.before_call:
            self.before_call()
        return lambda: self.opened.append(path)

    def observe_open(self, ref):
        if self.after_call:
            self.after_call()
        return observed([ref], "Ouverture observée par le simulateur.")

    def prepare_navigation(self, context, path):
        return lambda: setattr(self, "folder", path)

    def observe_navigation(self, context, path):
        fresh = self.context()
        return fresh, observed([fresh["current_directory"]], "Navigation observée.")

    def close(self):
        pass

    def windows(self):
        return [dict(self.context()["window"], path=str(self.folder))]

    def prepare_activate(self, ref):
        return lambda: setattr(self, "changed", False)

    def observe_activate(self, ref):
        return observed([ref], "Fenêtre active.")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        create_fixture(self.folder)
        self.config = defaults()
        self.adapter = FakeWindows(self.folder)
        self.engine = None

    def tearDown(self):
        if self.engine:
            self.engine.close()
        self.tmp.cleanup()

    def start(self, planner=None):
        self.engine = Engine(self.config, planner or Planner(self.config), lambda: self.adapter,
                             self.folder / "history.sqlite")
        self.assertTrue(self.engine.ready.wait(2))
        self.engine.activate()
        return self.engine

    def event(self, kind, timeout=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                item = self.engine.events.get(timeout=.05)
            except queue.Empty:
                continue
            if item["kind"] == kind:
                return item
        self.fail(f"Événement attendu absent : {kind}")


class Contracts(Fixture):
    def test_canonical_pdf_plan_and_closed_fields(self):
        p = deterministic("Montre-moi les PDF de ce dossier, puis ouvre le plus récent")
        self.assertEqual(len(validate_plan(p)), 3)
        p["authorization_id"] = "forged"
        with self.assertRaises(ClaraError):
            validate_plan(p)

    def test_unknown_intent_and_cycles_rejected(self):
        for p in [plan([("files.open", {"target": {"query": "notes"}})]),
                  plan([("history.undo", {"action_id": None})])]:
            if p["steps"][0]["intent_id"] == "files.open":
                p["steps"][0]["depends_on"] = ["s1"]
            with self.assertRaises(ClaraError):
                validate_plan(p)

    def test_source_reference_requires_dependency(self):
        p = plan([("files.filter", {"scope": "current_folder", "extension": "pdf"}),
                  ("files.open", {"source_step": "s1"})])
        p["steps"][1]["depends_on"] = []
        with self.assertRaises(ClaraError):
            validate_plan(p)

    def test_negations_never_reach_model(self):
        planner = Planner(self.config, True)
        with patch.object(planner, "_model") as model:
            for phrase in ["n'ouvre pas notes", "ne déplace pas ce fichier", "ouvre tout sauf notes"]:
                with self.assertRaises(ClaraError):
                    planner.interpret(phrase, {})
            model.assert_not_called()

    def test_result_requires_actual_observation(self):
        with self.assertRaises(ClaraError):
            action_result("a")
        value = action_result("a", observed([], "Observation."))
        validate("ActionResult", value)

    def test_model_cannot_invent_absolute_path(self):
        planner = Planner(self.config, True)
        p = plan([("files.open", {"target": {"path": "/invented/file.pdf"}})])
        with patch.object(planner, "_model", return_value=p), self.assertRaises(ClaraError):
            planner.interpret("peux-tu afficher mon document", {})


class Resolution(Fixture):
    def test_recent_is_within_exact_result_set(self):
        resolver = Resolver(self.config)
        value = resolver.listing(self.folder, "pdf")
        ref = resolver.recent(value)
        self.assertEqual(Path(ref["path"]).name, "rapport recent.pdf")

    def test_equal_dates_require_choice(self):
        os.utime(self.folder / "rapport ancien.pdf", (1700000100, 1700000100))
        resolver = Resolver(self.config)
        with self.assertRaises(Choices):
            resolver.recent(resolver.listing(self.folder, "pdf"))

    def test_file_changed_after_selection_is_rejected(self):
        resolver = Resolver(self.config)
        value = resolver.listing(self.folder, "pdf")
        (self.folder / "rapport recent.pdf").write_text("changed")
        with self.assertRaises(ClaraError):
            resolver.recent(value)

    def test_old_result_set_not_valid_in_new_folder(self):
        resolver = Resolver(self.config)
        value = resolver.listing(self.folder, "pdf")
        with self.assertRaises(ClaraError):
            resolver.get_set(value["result_set_id"], self.folder / "sous-dossier", {value["result_set_id"]: value})

    def test_result_limit_does_not_hide_incomplete_selection(self):
        self.config["max_results"] = 1
        with self.assertRaises(ClaraError):
            Resolver(self.config).listing(self.folder, "pdf")


class Execution(Fixture):
    def test_return_to_explorer_without_model(self):
        self.start().submit("retour à l'explorateur")
        self.event("done")

    def test_navigation_and_parent_sequence(self):
        e = self.start()
        e.submit("ouvre le dossier sous-dossier")
        self.event("done")
        self.assertEqual(self.adapter.folder, self.folder / "sous-dossier")
        e.submit("remonte au dossier parent")
        self.event("done")
        self.assertEqual(self.adapter.folder, self.folder)

    def test_complete_sequence(self):
        self.start().submit("montre-moi les PDF puis ouvre le plus récent")
        self.event("done")
        self.assertEqual(self.adapter.opened, [self.folder / "rapport recent.pdf"])

    def test_consecutive_commands_keep_result_context(self):
        e = self.start()
        e.submit("montre les PDF")
        self.event("done")
        e.submit("ouvre le plus récent")
        self.event("done")
        self.assertEqual(self.adapter.opened, [self.folder / "rapport recent.pdf"])

    def test_ambiguity_requires_number_and_rejects_stale_reply(self):
        e = self.start()
        e.submit("ouvre rapport")
        q = self.event("question")
        e.submit("un", "stale-dialogue")
        self.event("error")
        self.assertEqual(self.adapter.opened, [])
        e.submit("deux", q["dialogue_id"])
        self.event("done")
        self.assertEqual(self.adapter.opened, [self.folder / "rapport recent.pdf"])

    def test_stop_during_preparation_blocks_call(self):
        entered, release = threading.Event(), threading.Event()
        self.adapter.before_call = lambda: (entered.set(), release.wait(2))
        e = self.start()
        e.submit("ouvre notes")
        self.assertTrue(entered.wait(2))
        e.stop()
        release.set()
        self.assertTrue(e.jobs.join() is None)
        self.assertEqual(self.adapter.opened, [])

    def test_stop_after_admission_retains_result_but_no_following_step(self):
        entered, release = threading.Event(), threading.Event()
        self.adapter.after_call = lambda: (entered.set(), release.wait(2))
        class TwoOpens:
            def interpret(self, *args):
                return validate_plan(plan([("files.open", {"target": {"query": "notes"}}),
                                           ("files.open", {"target": {"query": "stop"}})])), "TEST"
        e = self.start(TwoOpens())
        e.submit("test")
        self.assertTrue(entered.wait(2))
        e.stop()
        release.set()
        self.event("result")
        e.jobs.join()
        self.assertEqual(self.adapter.opened, [self.folder / "notes.txt"])

    def test_stop_while_model_runs_rejects_late_plan(self):
        entered, release = threading.Event(), threading.Event()
        class SlowPlanner:
            def interpret(self, *args):
                entered.set()
                release.wait(2)
                return validate_plan(plan([("files.open", {"target": {"query": "notes"}})])), "TEST"
        e = self.start(SlowPlanner())
        e.submit("test")
        self.assertTrue(entered.wait(2))
        e.stop()
        release.set()
        e.jobs.join()
        self.assertEqual(self.adapter.opened, [])

    def test_stop_during_commit_blocks_call(self):
        entered, release = threading.Event(), threading.Event()
        original = Journal.prepare
        def delayed(journal, action):
            value = original(journal, action)
            entered.set()
            release.wait(2)
            return value
        with patch.object(Journal, "prepare", delayed):
            e = self.start()
            e.submit("ouvre notes")
            self.assertTrue(entered.wait(2))
            e.stop()
            release.set()
            e.jobs.join()
        self.assertEqual(self.adapter.opened, [])

    def test_target_changed_during_commit_blocks_call(self):
        original = Journal.prepare
        def change(journal, action):
            value = original(journal, action)
            (self.folder / "notes.txt").write_text("changed during commit")
            return value
        with patch.object(Journal, "prepare", change):
            self.start().submit("ouvre notes")
            self.event("error")
        self.assertEqual(self.adapter.opened, [])

    def test_context_changed_after_choice_blocks_call(self):
        e = self.start()
        e.submit("ouvre rapport")
        q = self.event("question")
        self.adapter.changed = True
        e.submit("un", q["dialogue_id"])
        self.event("error")
        self.assertEqual(self.adapter.opened, [])

    def test_new_request_pauses_before_replacement_question(self):
        entered, release = threading.Event(), threading.Event()
        self.adapter.before_call = lambda: (entered.set(), release.wait(2))
        e = self.start()
        e.submit("ouvre notes")
        self.assertTrue(entered.wait(2))
        old = e.current
        e.submit("ouvre stop")
        q = self.event("question")
        self.assertTrue(old.paused)
        release.set()
        e.jobs.join()
        self.assertEqual(self.adapter.opened, [])
        self.adapter.before_call = None
        e.submit("non", q["dialogue_id"])
        self.event("done")
        self.assertEqual(self.adapter.opened, [self.folder / "notes.txt"])

    def test_expired_choice_never_opens(self):
        e = self.start()
        e.submit("ouvre rapport")
        self.event("question")
        e.dialogue["expires"] = time.monotonic() - 1
        e.tick()
        self.assertIsNone(e.dialogue)
        self.assertEqual(self.adapter.opened, [])

    def test_idle_protects_capture_and_then_sleeps(self):
        e = self.start()
        e.last_interaction = time.monotonic() - 1000
        e.capturing = True
        e.tick()
        self.assertTrue(e.session)
        e.capturing = False
        e.tick()
        self.assertFalse(e.session)

    def test_locked_session_cannot_activate(self):
        e = self.start()
        e.sleep()
        e.suspended = True
        e.activate()
        self.assertFalse(e.session)

    def test_control_word_inside_filename_is_not_stop(self):
        e = self.start()
        e.submit("ouvre stop")
        self.event("done")
        self.assertEqual(self.adapter.opened, [self.folder / "stop.txt"])

    def test_executable_not_openable(self):
        (self.folder / "programme.exe").write_text("fixture")
        self.start().submit("ouvre programme")
        self.event("error")
        self.assertEqual(self.adapter.opened, [])

    def test_ui_saturation_never_blocks_stop_lock(self):
        e = self.start()
        for _ in range(150):
            e.emit("progress", "test")
        e.current = Ticket("test")
        old = e.current
        e.stop()
        self.assertTrue(old.cancelled)
        self.assertTrue(e.gate.blocked)


class Persistence(Fixture):
    def test_restart_marks_prepared_unknown_without_replay(self):
        path = self.folder / "journal.sqlite"
        journal = Journal(path)
        journal.db.execute("INSERT INTO actions VALUES ('a','r','s',1,'{}',NULL)")
        journal.db.commit()
        journal.close()
        journal = Journal(path)
        self.assertEqual(json.loads(journal.db.execute("SELECT result FROM actions").fetchone()[0])["status"], "UNKNOWN")
        journal.close()

    def test_invalid_config_preserves_previous_file(self):
        path = self.folder / "config.json"
        save(path, self.config)
        old = path.read_bytes()
        invalid = dict(self.config, session_idle_seconds=-1)
        with self.assertRaises(ValueError):
            save(path, invalid)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(load(path), self.config)

    def test_duplicate_action_is_not_new_effect(self):
        journal = Journal(self.folder / "journal.sqlite")
        action = {"action_id": "a", "request_id": "r", "step_id": "s", "sequence_id": "q", "generation": 0,
                  "intent_id": "files.open", "arguments": {"target": {"query": "notes"}}, "targets": [],
                  "context_id": "c", "authorization_id": None, "journal_commit_id": "j", "attempt_no": 1}
        self.assertTrue(journal.prepare(action))
        self.assertFalse(journal.prepare(action))
        with self.assertRaises(ValueError):
            journal.prepare(dict(action, action_id="b"))
        journal.close()


if __name__ == "__main__":
    unittest.main()
