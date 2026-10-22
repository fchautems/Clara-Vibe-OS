"""Tests de routage et de classement, encodeur/inférences explicitement simulés."""
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clara.catalogue import catalogue, migrate
from clara.config import defaults, load
from clara.contracts import ClaraError, target
from clara.journey import create_journey_fixture, run_journey
from clara.names import rank
from clara.planner import Planner, deterministic
from clara.resolver import Choices, Resolver
from clara.semantic import SemanticMatcher, extract_slots
from test_journey import InteractiveFake


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.config = dict(defaults(), semantic_model=str(self.folder / 'model'), catalogue_path=None)

    def test_catalogue_count_and_coverage(self):
        data, _ = catalogue()
        self.assertGreaterEqual(sum(len(e['phrases']) for e in data['entries']), 200)
        for intent in {e['intent_id'] for e in data['entries']}:
            self.assertGreaterEqual(sum(len(e['phrases']) for e in data['entries'] if e['intent_id'] == intent), 15)

    def test_migration_preserves_user_and_backup(self):
        path = self.folder / 'phrases.json'
        old = json.loads(json.dumps(catalogue()[0]))
        old.pop('bundle_revision')
        old['entries'][0]['phrases'] = ['ma commande personnelle']
        path.write_text(json.dumps(old))
        migrate(path)
        merged = json.loads(path.read_text())
        self.assertIn('ma commande personnelle', merged['entries'][0]['phrases'])
        self.assertEqual(json.loads(path.with_name(path.name + '.before-v3.bak').read_text()), old)
        before = path.read_bytes()
        migrate(path)
        self.assertEqual(path.read_bytes(), before)

    def test_catalogue_edit_is_visible_without_restart(self):
        path = self.folder / 'phrases.json'
        migrate(path)
        catalogue(str(path))
        data = json.loads(path.read_text())
        data['entries'][0]['phrases'].append('reviens au cran precedent immediatement')
        path.write_text(json.dumps(data))
        self.assertIsNotNone(deterministic('reviens au cran precedent immediatement', catalogue_path=str(path)))

    def test_slot_parameters_are_literal_and_typed(self):
        data, _ = catalogue()
        for text, kind, value in [('consulte le fichier rapport 2026.pdf', 'query', 'rapport 2026.pdf'),
                                  ('rejoins le disque g', 'drive', 'g'), ('isole les pdf', 'extension', 'pdf')]:
            slot = extract_slots(text, data)
            self.assertEqual((slot['kind'], slot['value']), (kind, value))
        self.assertIsNone(extract_slots('consulte le fichier notes puis invente une action', data))

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'numpy optionnel absent')
    def test_same_intent_examples_do_not_compete_and_threshold_is_used(self):
        import numpy as np
        data = dict(catalogue()[0], entries=[
            {'command': 'remonte au dossier parent', 'intent_id': 'explorer.parent', 'phrases': ['alpha', 'alpha bis']},
            {'command': 'liste les fenetres explorateur', 'intent_id': 'window.list', 'phrases': ['beta']}])
        encoder = Mock(identity={'revision': 'SIMULATED'})
        def encode(texts):
            result = np.zeros((len(texts), 384), dtype='float32')
            for i, text in enumerate(texts):
                result[i, 1 if text in ['beta', 'liste les fenetres explorateur'] else 0] = 1
            return result
        encoder.encode.side_effect = encode
        matcher = SemanticMatcher(self.config, encoder)
        with patch('clara.semantic.catalogue', return_value=(data, [])):
            command, trace = matcher.match('phrase nouvelle')
            self.assertEqual(command, 'remonte au dossier parent')
            self.assertEqual(len(trace['candidates']), 2)
            self.assertEqual(trace['margin'], 1)
            key = matcher.key
            data['entries'][0]['phrases'].append('alpha ter')
            matcher.match('phrase nouvelle')
            self.assertNotEqual(matcher.key, key)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'numpy optionnel absent')
    def test_close_distinct_intents_fall_through(self):
        import numpy as np
        encoder = Mock(identity={'revision': 'SIMULATED'})
        encoder.encode.side_effect = lambda texts: np.tile(np.eye(1, 384)[0], (len(texts), 1))
        command, trace = SemanticMatcher(self.config, encoder).match('une demande nouvelle')
        self.assertIsNone(command)
        self.assertEqual(trace['status'], 'LOW_CONFIDENCE')

    def test_semantic_route_does_not_call_other_engines(self):
        matcher = Mock()
        matcher.match.return_value = ('ouvre le dossier projets', {'status': 'ACCEPTED'})
        planner = Planner(self.config, True, semantic=matcher)
        with patch('clara.planner.similar_command') as lexical, patch('clara.jev.classify') as jev, patch.object(planner, '_model') as model:
            steps, origin = planner.interpret('partons vers le dossier projets', {})
            self.assertEqual(origin, 'LOCAL_SEMANTIC')
            self.assertEqual(steps[0]['arguments']['target']['query'], 'projets')
            lexical.assert_not_called(); jev.assert_not_called(); model.assert_not_called()

    def test_literal_absolute_path_preserves_accents_and_case(self):
        path = self.folder / 'Équipe été'
        path.mkdir()
        steps, _ = Planner(self.config).interpret('ouvre le dossier ' + str(path), {})
        self.assertEqual(steps[0]['arguments']['target']['path'], str(path))

    def test_location_ou_is_not_an_alternative(self):
        matcher = Mock()
        matcher.match.return_value = ('cherche le fichier rapport', {'status': 'ACCEPTED'})
        for text in ['je voudrais savoir où est le fichier rapport', 'je voudrais savoir ou est le fichier rapport']:
            steps, _ = Planner(self.config, semantic=matcher).interpret(text, {})
            self.assertEqual(steps[0]['intent_id'], 'files.search')

    def test_direct_route_bypasses_encoder(self):
        matcher = Mock()
        Planner(self.config, True, matcher).interpret('va dans F', {})
        matcher.match.assert_not_called()

    def test_forced_ollama_fallback_is_labelled(self):
        matcher = Mock()
        matcher.match.return_value = (None, {'status': 'LOW_CONFIDENCE', 'simulated': True})
        planner = Planner(self.config, True, matcher)
        with patch.object(planner, '_model', return_value=deterministic('remonte')) as model:
            _, origin = planner.interpret('une demande inedite', {})
            self.assertEqual(origin, 'LOCAL_MODEL')
            self.assertIn('LOCAL_SEMANTIC', [t['engine'] for t in planner.last_trace])
            model.assert_called_once()

    def test_hallucinated_model_parameter_refused(self):
        planner = Planner(dict(self.config, semantic_enabled=False), True)
        with patch.object(planner, '_model', return_value=deterministic('ouvre le fichier secret.txt')):
            with self.assertRaises(ClaraError) as error:
                planner.interpret('demande nouvelle', {})
            self.assertEqual(error.exception.code, 'PLAN_INVALID')

    def test_negation_alternative_and_unknown_sequence_never_reach_encoder(self):
        matcher = Mock()
        planner = Planner(self.config, True, matcher)
        with patch.object(planner, '_model') as model:
            for phrase in ['ne va pas dans F', 'ouvre plus le fichier notes', 'va dans F ou G', 'ouvre le dossier projets puis invente une action']:
                with self.assertRaises(ClaraError):
                    planner.interpret(phrase, {})
            matcher.match.assert_not_called(); model.assert_not_called()

    def test_drive_folder_dependency(self):
        steps, _ = Planner(self.config).interpret('va dans F dans le dossier projet', {})
        self.assertEqual(steps[0]['arguments']['target'], {'path': 'F:\\'})
        self.assertEqual(steps[1]['arguments']['target'], {'query': 'projet'})
        self.assertEqual(steps[1]['depends_on'], ['s1'])

    def test_missing_models_keep_local_and_never_download(self):
        planner = Planner(self.config)
        with patch('urllib.request.OpenerDirector.open') as request:
            planner.interpret('va dans F', {})
            with self.assertRaises(ClaraError):
                planner.interpret('une phrase nouvelle incomprise', {})
            request.assert_not_called()

    def test_jev_disabled_makes_no_request(self):
        from clara.jev import classify
        with patch('urllib.request.OpenerDirector.open') as request:
            self.assertEqual(classify('phrase nouvelle', self.config)[1]['status'], 'DISABLED')
            request.assert_not_called()

    def test_jev_timeout_is_safe_and_ollama_remains_last(self):
        from clara.jev import classify
        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'TEST_SECRET'}), patch('urllib.request.OpenerDirector.open', side_effect=TimeoutError):
            command, trace = classify('requete nouvelle', dict(self.config, jev_enabled=True))
            self.assertIsNone(command)
            self.assertEqual(trace['status'], 'ERROR')
        planner = Planner(dict(self.config, jev_enabled=True, semantic_enabled=False), True)
        with patch('clara.jev.classify', return_value=(None, {'status': 'ERROR'})), patch.object(planner, '_model', return_value=deterministic('remonte')):
            _, origin = planner.interpret('requete nouvelle', {})
            self.assertEqual(origin, 'LOCAL_MODEL')

    def test_corpus_hashes_and_coverage_are_frozen(self):
        from clara.semantic import digest
        from importlib.resources import files
        resources = files('clara').joinpath('resources')
        manifest = json.loads(resources.joinpath('comprehension_manifest.json').read_text())
        for name, expected in manifest.items():
            self.assertEqual(digest(resources.joinpath(name)), expected)
        for name, minimum in [('calibration', 40), ('evaluation', 120), ('confirmation', 120)]:
            cases = json.loads(resources.joinpath(f'comprehension_{name}_fr.json').read_text())['cases']
            self.assertGreaterEqual(len(cases), minimum)

    def test_jev_typed_answer_and_redacted_parameter(self):
        import io
        from clara.jev import classify, CRITERIA
        probabilities = {k: float(k == 'explorer.navigate') for k in CRITERIA}
        response = {'answers': {'intent': {'choice': 'explorer.navigate', 'confidence': 1., 'probabilities': probabilities}}}
        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'TEST_SECRET'}), patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(response).encode())) as request:
            command, trace = classify('je souhaite consulter le dossier personnel', dict(self.config, jev_enabled=True))
            self.assertEqual(command, 'ouvre le dossier personnel')
            self.assertNotIn('personnel', request.call_args.args[0].data.decode())
            self.assertNotIn('TEST_SECRET', json.dumps(trace))

    def test_names_and_ambiguity(self):
        root = self.folder / 'fixtures'
        create_journey_fixture(root)
        resolver = Resolver(self.config)
        ref = resolver.selector({'query': 'projet'}, root / 'unique', {}, {}, directories=True)
        self.assertEqual(Path(ref['path']).name, '_projets')
        with self.assertRaises(Choices) as choices:
            resolver.selector({'query': 'projet'}, root / 'ambigu', {}, {}, directories=True)
        self.assertEqual(len(choices.exception.targets), 2)
        ref = resolver.selector({'query': 'projets 2026'}, root / 'ambigu', {}, {}, directories=True)
        self.assertEqual(Path(ref['path']).name, 'projets-2026')
        with self.assertRaises(ClaraError):
            resolver.selector({'query': 'projets 2027'}, root / 'ambigu', {}, {}, directories=True)

    def test_extensions_and_minor_typo(self):
        for name in ['rapport.pdf', 'rapport.txt', 'factures.txt']:
            (self.folder / name).write_text('test')
        resolver = Resolver(self.config)
        ref = resolver.selector({'query': 'rapport.pdf'}, self.folder, {}, {})
        self.assertEqual(Path(ref['path']).suffix, '.pdf')
        ref = resolver.selector({'query': 'facturres.txt'}, self.folder, {}, {})
        self.assertEqual(Path(ref['path']).name, 'factures.txt')
        with self.assertRaises(ClaraError):
            resolver.selector({'query': 'rapport.docx'}, self.folder, {}, {})

    def test_spoken_extension_preserves_requested_type(self):
        for text in ['ouvre le rapport PDF', 'ouvre le fichier rapport PDF']:
            steps, _ = Planner(self.config).interpret(text, {})
            self.assertEqual(steps[0]['arguments']['target']['query'], 'rapport.pdf')
        for name in ['rapport.pdf', 'rapport.txt']:
            (self.folder / name).write_text('test')
        ref = Resolver(self.config).selector({'query': 'rapport.pdf'}, self.folder, {}, {})
        self.assertEqual(Path(ref['path']).suffix, '.pdf')

    def test_extended_journey_and_failure_recovery_simulated(self):
        root = self.folder / 'fixtures'
        create_journey_fixture(root)
        report = run_journey(self.config, root, self.folder / 'journey.json', lambda: InteractiveFake(root),
                             backend='simulated', extended=True)
        self.assertEqual(report['status'], 'PASSED', report.get('traceback'))
        self.assertEqual(len(report['steps']), 29)
        self.assertEqual(report['steps'][-2]['expected_error_observed'], 'TARGET_NOT_FOUND')
        self.assertEqual(report['steps'][-1]['status'], 'PASSED')

    def test_cold_start_simulated_does_not_need_context(self):
        from test_reliability import ColdExplorer
        root = self.folder / 'fixtures'
        create_journey_fixture(root)
        class ColdInteractive(InteractiveFake, ColdExplorer):
            def __init__(self):
                InteractiveFake.__init__(self, root)
                self.exists = False
                self.navigation_calls = 0
            def context(self):
                if not self.exists:
                    raise ClaraError('CONTEXT_AMBIGUOUS', 'fermé')
                return InteractiveFake.context(self)
            def prepare_navigation(self, context, path):
                return ColdExplorer.prepare_navigation(self, context, path)
            def windows(self):
                return super().windows() if self.exists else []
        report = run_journey(self.config, root, self.folder / 'cold.json', ColdInteractive,
                             backend='simulated', cold_start=True)
        self.assertEqual(report['status'], 'PASSED', report.get('traceback'))
        self.assertTrue(report['cold_start']['no_initial_explorer'])

    def test_extended_independent_scenarios_continue_after_unknown(self):
        root = self.folder / 'fixtures'
        create_journey_fixture(root)
        adapter = InteractiveFake(root)
        adapter.observe_open = Mock(side_effect=OSError('observation indisponible'))
        report = run_journey(self.config, root, self.folder / 'journey.json', lambda: adapter,
                             backend='simulated', extended=True)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['steps'][4]['status'], 'UNKNOWN')
        named = {s['name']: s for s in report['steps']}
        self.assertEqual(named['nom approximatif']['status'], 'PASSED')
        self.assertEqual(named['fenêtres après échec prévu']['status'], 'PASSED')

    def test_many_unrelated_files_do_not_hide_named_target(self):
        for i in range(140):
            (self.folder / f'unrelated-{i}.txt').write_text('test')
        wanted = self.folder / 'factures.txt'
        wanted.write_text('test')
        ref = Resolver(self.config).selector({'query': 'facture.txt'}, self.folder, {}, {})
        self.assertEqual(Path(ref['path']), wanted)
