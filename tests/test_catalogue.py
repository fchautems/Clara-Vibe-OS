import unittest
from unittest.mock import patch

from clara.catalogue import catalogue, canonicalize
from clara.config import defaults
from clara.contracts import ClaraError, validate_plan
from clara.planner import Planner, deterministic, normal


class StaticCatalogue(unittest.TestCase):
    def test_every_preloaded_formulation_produces_expected_valid_plan(self):
        data, _ = catalogue()
        for entry in data["entries"]:
            for template in entry["phrases"]:
                extensions = data["extensions"] if "{extension}" in template else ["pdf"]
                for extension in extensions:
                    phrase = template.format(query="rapport 2025", extension=extension)
                    command = entry["command"].format(query="rapport 2025", extension=data["extensions"][extension])
                    with self.subTest(phrase=phrase):
                        actual = deterministic(phrase, "previous-results")
                        self.assertEqual(actual, deterministic(command, "previous-results"))
                        validate_plan(actual)

    def test_polite_accents_and_punctuation_without_ollama(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, "_model") as model:
            for phrase in ["Clara, pourrais-tu afficher les documents PDF, s'il te plaît ?",
                           "Est-ce que tu peux afficher les documents PDF ?",
                           "J’aimerais afficher les documents PDF."]:
                steps, origin = planner.interpret(phrase, {})
                self.assertEqual(steps[0]["arguments"]["extension"], "pdf")
                self.assertEqual(origin, "DETERMINISTIC")
            model.assert_not_called()

    def test_parameter_values_are_not_cached_between_requests(self):
        planner = Planner(defaults())
        for name in ["rapport 2025", "facture septembre", "notes"]:
            steps, _ = planner.interpret("peux-tu afficher le fichier " + name, {})
            self.assertEqual(steps[0]["arguments"], {"target": {"query": name}})

    def test_named_document_does_not_keep_the_word_appele(self):
        steps, _ = Planner(defaults()).interpret("ouvre le document appelé rapport", {})
        self.assertEqual(steps[0]["arguments"]["target"]["query"], "rapport")

    def test_latest_requires_context_and_uses_current_result_set(self):
        planner = Planner(defaults())
        with self.assertRaises(ClaraError):
            planner.interpret("ouvre le dernier fichier", {})
        for sid in ["pdf-results", "text-results"]:
            steps, _ = planner.interpret("ouvre le dernier fichier", {}, sid)
            self.assertEqual(steps[0]["arguments"]["result_set_id"], sid)

    def test_negation_and_exceptions_never_use_catalogue_or_model(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, "_model") as model:
            for phrase in ["peux-tu ne pas afficher les documents PDF",
                           "montre les PDF sauf rapport", "n'ouvre jamais le dernier fichier"]:
                with self.subTest(phrase=phrase), self.assertRaises(ClaraError):
                    planner.interpret(phrase, {}, "results")
            model.assert_not_called()

    def test_unrecognized_formulation_still_reaches_local_model(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, "_model", return_value=deterministic("remonte")) as model:
            _, origin = planner.interpret("emmène-moi un étage plus haut", {})
            self.assertEqual(origin, "LOCAL_MODEL")
            model.assert_called_once()

    def test_partial_match_does_not_silently_execute_first_action(self):
        self.assertEqual(deterministic("affiche les documents PDF puis supprime rapport")["kind"], "UNAVAILABLE")
        self.assertIsNone(deterministic("affiche le fichier notes puis ouvre rapport"))

    def test_unrelated_words_and_file_names_are_not_rewritten(self):
        for phrase in ["ouvre notes s'il te plait.txt", "ouvre rapport PDF.txt", "ouvre Firefox"]:
            self.assertEqual(canonicalize(normal(phrase)), normal(phrase))


if __name__ == "__main__":
    unittest.main()
