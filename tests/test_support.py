import json
import threading
import unittest
from unittest.mock import patch

from clara.config import defaults
from clara.contracts import ClaraError
from clara.planner import Planner, deterministic, normal, plan
from clara.support import help_requested, help_message, support_catalogue
from test_core import Fixture


class SupportCatalogue(unittest.TestCase):
    def test_unavailable_requests_never_reach_model(self):
        planner = Planner(defaults(), True)
        examples = {"ouvre Firefox": "application.launch", "peux-tu lancer l'application inconnue": "application.launch",
                    "copie ce fichier": "files.copy", "déplace ce fichier dans documents": "files.move",
                    "renomme notes": "files.rename", "supprime notes": "files.delete", "annule": "history.undo",
                    "annule la dernière action": "history.undo"}
        with patch.object(planner, "_model") as model:
            for text, intent in examples.items():
                with self.subTest(text=text), self.assertRaises(ClaraError) as raised:
                    planner.interpret(text, {})
                self.assertEqual(raised.exception.code, "CAPABILITY_UNAVAILABLE")
                self.assertEqual(raised.exception.intent_id, intent)
            model.assert_not_called()

    def test_explicit_file_or_folder_is_not_confused_with_application(self):
        for text, expected in [("ouvre le fichier Firefox", "files.open"), ("ouvre Firefox.pdf", "files.open"),
                               ("ouvre le dossier Firefox", "explorer.navigate"), ("cherche copie.txt", "files.search")]:
            steps, _ = Planner(defaults()).interpret(text, {})
            self.assertEqual(steps[0]["intent_id"], expected)

    def test_sequence_with_unavailable_action_is_rejected_entirely(self):
        for phrase in ["ouvre notes puis copie ce fichier", "montre les PDF puis supprime rapport"]:
            self.assertEqual(deterministic(phrase)["kind"], "UNAVAILABLE")

    def test_negations_are_not_classified_as_affirmative_requests(self):
        self.assertEqual(deterministic("ne supprime pas notes")["kind"], "UNKNOWN")

    def test_all_help_phrases_and_polite_variant(self):
        for text in support_catalogue()["help_phrases"] + ["Clara, quelles sont tes commandes, s'il te plaît ?"]:
            self.assertTrue(help_requested(normal(text)), text)
        self.assertFalse(help_requested("ouvre le fichier aide.txt"))
        self.assertFalse(help_requested("cherche aide"))

    def test_help_uses_configured_sleep_phrase(self):
        config = dict(defaults(), sleep_phrases=["à bientôt Clara"])
        self.assertIn("à bientôt Clara", help_message(config))
        self.assertNotIn("bonne nuit", help_message(config))

    def test_malformed_model_unavailable_response_is_rejected(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, "_model", return_value={"kind": "UNAVAILABLE"}), self.assertRaises(ClaraError) as raised:
            planner.interpret("formulation nouvelle", {})
        self.assertEqual(raised.exception.code, "PLAN_INVALID")


class SupportExecution(Fixture):
    def test_help_without_explorer_context_or_ollama(self):
        engine = self.start()
        with patch.object(self.adapter, "context", side_effect=RuntimeError("no Explorer")) as context:
            engine.submit("qu'est-ce que tu sais faire")
            self.assertIn("stop", self.event("help")["message"])
            context.assert_not_called()
        self.assertEqual(self.adapter.opened, [])

    def test_help_does_not_open_session_in_standby(self):
        engine = self.start()
        engine.sleep()
        engine.submit("aide")
        self.event("ignored")
        self.assertFalse(engine.session)

    def test_help_preserves_pending_choice(self):
        engine = self.start()
        engine.submit("ouvre rapport")
        question = self.event("question")
        token = engine.dialogue_token()
        engine.submit("aide", token)
        self.event("help")
        self.assertEqual(engine.dialogue_token(), token)
        self.assertFalse(engine.current.cancelled)
        engine.submit("un", token)
        self.assertEqual(self.event("result")["result"]["status"], "SUCCEEDED")

    def test_stale_help_response_does_not_change_dialogue(self):
        engine = self.start()
        engine.submit("ouvre rapport")
        self.event("question")
        token = engine.dialogue_token()
        engine.submit("aide", "stale-token")
        self.event("error")
        self.assertEqual(engine.dialogue_token(), token)

    def test_help_during_preparation_does_not_replace_or_pause_request(self):
        started, release = threading.Event(), threading.Event()
        planner = Planner(self.config, True)
        def delayed(*args):
            started.set()
            release.wait(2)
            return plan([("files.open", {"target": {"query": "notes"}})])
        with patch.object(planner, "_model", side_effect=delayed):
            engine = self.start(planner)
            engine.submit("formulation nouvelle")
            self.assertTrue(started.wait(2))
            try:
                engine.submit("aide")
                self.event("help")
                self.assertFalse(engine.current.paused)
                self.assertIsNone(engine.dialogue)
            finally:
                release.set()
            self.assertEqual(self.event("result")["result"]["status"], "SUCCEEDED")

    def test_unavailable_request_is_logged_and_does_not_open_file(self):
        engine = self.start()
        engine.submit("ouvre Firefox")
        error = self.event("error")
        self.assertEqual(error["code"], "CAPABILITY_UNAVAILABLE")
        self.assertIn("application", error["message"])
        self.assertEqual(self.adapter.opened, [])
        engine.close()
        self.engine = None
        import sqlite3
        with sqlite3.connect(self.folder / "history.sqlite") as db:
            payload = json.loads(db.execute("SELECT payload FROM events WHERE kind='request_error'").fetchone()[0])
        self.assertEqual(payload["intent_id"], "application.launch")
        self.assertEqual(payload["text"], "ouvre Firefox")


if __name__ == "__main__":
    unittest.main()
