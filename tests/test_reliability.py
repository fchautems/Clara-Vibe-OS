"""Tests automatisés Linux/Windows, interfaces natives simulées explicitement."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clara.catalogue import catalogue, similar_command
from clara.config import defaults, load
from clara.contracts import ClaraError
from clara.local_model import LocalModel
from clara.planner import Planner, deterministic, normal, plan
from clara.windows import WindowsAdapter
from test_core import Fixture, FakeWindows


class Understanding(unittest.TestCase):
    def test_calibration_corpus(self):
        cases = json.loads((Path(__file__).parent / 'data/similarity_fr.json').read_text())
        for case in cases:
            with self.subTest(phrase=case['text']):
                command, ambiguous = similar_command(case['text'], defaults())
                self.assertEqual(command, case['command'])
                self.assertFalse(ambiguous)

    def test_drive_variants_local(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, '_model') as model:
            for phrase in ['va dans F', 'ouvre le lecteur F', 'affiche le disque F',
                           'emmène-moi sur F', 'je voudrais aller dans F',
                           'euh ouvre le lecteur F', 'Clara, peux-tu ouvrir le lecteur F, s’il te plaît']:
                with self.subTest(phrase=phrase):
                    steps, origin = planner.interpret(phrase, {})
                    self.assertEqual(steps[0]['arguments']['target'], {'path': 'F:\\'})
                    self.assertEqual(origin, 'DETERMINISTIC')
            model.assert_not_called()

    def test_unseen_similarity_and_literal_parameters(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, '_model') as model:
            for phrase, intent, target in [
                ('affiche donc le disque F', 'explorer.navigate', {'path': 'F:\\'}),
                ('affiche ce dossier projets', 'explorer.navigate', {'query': 'projets'}),
                ('ouvree le dossier factures 2026', 'explorer.navigate', {'query': 'factures 2026'}),
                ('affiche ce fichier rapport.txt', 'files.open', {'query': 'rapport.txt'}),
            ]:
                with self.subTest(phrase=phrase):
                    steps, origin = planner.interpret(phrase, {})
                    self.assertIn(origin, {'LOCAL_SIMILARITY', 'DETERMINISTIC'})
                    self.assertEqual(steps[0]['intent_id'], intent)
                    self.assertEqual(steps[0]['arguments']['target'], target)
            model.assert_not_called()

    def test_negation_and_ambiguity_never_call_model(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, '_model') as model:
            for phrase in ['ne va pas dans F', 'ouvre le dossier projets ou archives',
                           'va dans F ou G', 'n’ouvre jamais le fichier notes',
                           'ouvre aucun fichier', 'affiche ce dossier sauf projets']:
                with self.subTest(phrase=phrase), self.assertRaises(ClaraError):
                    planner.interpret(phrase, {})
            model.assert_not_called()

    def test_different_meaning_not_fuzzed(self):
        for phrase in ['ferme le dossier projets', 'supprime le dossier projets',
                       'deplace le fichier notes', 'ouvre puis ferme le dossier projets']:
            with self.subTest(phrase=phrase):
                self.assertEqual(similar_command(phrase, defaults()), (None, False))

    def test_threshold_changes_acceptance(self):
        phrase = 'affiche ce dossier projets'
        self.assertIsNotNone(similar_command(phrase, defaults())[0])
        self.assertEqual(similar_command(phrase, dict(defaults(), similarity_threshold=.99)), (None, False))

    def test_close_scores_require_clarification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'commands.json'
            data = dict(catalogue()[0])
            data['entries'] = [
                {'command': 'ouvre le dossier {query}', 'phrases': ['affiche le dossier {query}']},
                {'command': 'cherche le fichier {query}', 'phrases': ['affiche ce dossier {query}']}]
            path.write_text(json.dumps(data))
            command, ambiguous = similar_command('affiche cee dossier projets', dict(defaults(), catalogue_path=str(path), similarity_margin=.2))
            self.assertIsNone(command)
            self.assertTrue(ambiguous)

    def test_editable_user_catalogue_and_config_migration(self):
        with tempfile.TemporaryDirectory() as folder, patch('clara.config.data_dir', return_value=Path(folder)):
            path = Path(folder) / 'config.json'
            old = defaults()
            for key in ['catalogue_path', 'similarity_threshold', 'similarity_margin']:
                del old[key]
            path.write_text(json.dumps(old))
            config = load(path)
            user = Path(config['catalogue_path'])
            data = json.loads(user.read_text())
            data['entries'].append({'command': 'remonte au dossier parent', 'phrases': ['niveau superieur']})
            user.write_text(json.dumps(data))
            catalogue.cache_clear()
            steps, _ = Planner(config).interpret('niveau supérieur', {})
            self.assertEqual(steps[0]['intent_id'], 'explorer.parent')
            self.assertEqual(json.loads(user.read_text()), data)

    def test_fallback_response_validated(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, '_model', return_value={'kind': 'PLAN', 'steps': [{'code': 'evil'}]}):
            with self.assertRaises(ClaraError):
                planner.interpret('fais quelque chose de nouveau', {})

    def test_actual_http_fallback_protocol(self):
        # Real HTTP on loopback against a fake server, NOT a real Ollama model.
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                payload = json.dumps({'done': True, 'response': json.dumps(deterministic('remonte'))}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            planner = Planner(dict(defaults(), ollama_port=server.server_port), True)
            steps, origin = planner.interpret('emmène-moi un étage plus haut', {})
            self.assertEqual(origin, 'LOCAL_MODEL')
            self.assertEqual(steps[0]['intent_id'], 'explorer.parent')
            self.assertEqual(len(calls), 1)
            planner.interpret('va dans F', {})
            self.assertEqual(len(calls), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class ColdExplorer(FakeWindows):
    def __init__(self, folder):
        super().__init__(folder)
        self.exists = False
        self.navigation_calls = 0
    def context(self):
        if not self.exists:
            raise ClaraError('CONTEXT_AMBIGUOUS', 'Explorateur fermé')
        return super().context()
    def prepare_navigation(self, context, path):
        def call():
            self.navigation_calls += 1
            self.exists = True
            self.folder = path
        return call


class Execution(Fixture):
    def test_closed_explorer_absolute_then_folder_then_file(self):
        nested = self.folder / 'sous-dossier' / 'imbrique'
        nested.mkdir(); (nested / 'exemple.txt').write_text('test')
        self.adapter = ColdExplorer(self.folder)
        engine = self.start()
        for phrase in [f'ouvre le dossier {self.folder}', 'ouvre le dossier sous-dossier',
                       'ouvre le dossier imbrique', 'ouvre le fichier exemple.txt']:
            engine.submit(phrase); self.event('done')
        self.assertEqual(self.adapter.opened, [nested / 'exemple.txt'])
        self.assertEqual(self.adapter.navigation_calls, 3)

    def test_closed_explorer_relative_request_does_not_guess(self):
        self.adapter = ColdExplorer(self.folder)
        self.start().submit('ouvre le dossier sous-dossier')
        self.event('error')
        self.assertEqual(self.adapter.navigation_calls, 0)

    def test_missing_destination_no_window_created(self):
        self.adapter = ColdExplorer(self.folder)
        self.start().submit(f'ouvre le dossier {self.folder}/absent')
        self.event('error')
        self.assertEqual(self.adapter.navigation_calls, 0)

    def test_failed_observation_never_success(self):
        self.adapter.observe_navigation = Mock(side_effect=ClaraError('OBSERVATION_UNKNOWN', 'Non confirmé', 'EXECUTION'))
        self.start().submit('ouvre le dossier sous-dossier')
        result = self.event('result')['result']
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertIsNone(result['observed_result'])
        self.event('error')

    def test_preparation_of_cold_window_has_no_side_effect(self):
        adapter = object.__new__(WindowsAdapter); adapter.shell = Mock()
        call = adapter.prepare_navigation({'window': None}, self.folder)
        adapter.shell.Explore.assert_not_called()
        call()
        adapter.shell.Explore.assert_called_once_with(str(self.folder))

    def test_native_focus_denial_not_success(self):
        adapter = object.__new__(WindowsAdapter); adapter.gui = Mock()
        adapter.gui.GetForegroundWindow.return_value = 99
        with self.assertRaises(ClaraError):
            adapter._foreground(42)
        adapter.gui.ShowWindow.assert_called_once_with(42, 9)

    def test_navigation_observer_checks_path_and_foreground(self):
        adapter = object.__new__(WindowsAdapter)
        adapter.com = Mock(); adapter._foreground = Mock()
        adapter._windows = Mock(return_value=[(42, self.folder, Mock())])
        adapter.context = self.adapter.context
        fresh, observation = adapter.observe_navigation({'window': None}, self.folder)
        adapter._foreground.assert_called_once_with(42)
        self.assertEqual(observation['targets'][0]['path'], str(self.folder))


class ModelPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = LocalModel(defaults(), Path(self.tmp.name))
    def tearDown(self):
        self.model.close(); self.tmp.cleanup()
    def response(self, obj):
        return io.BytesIO(json.dumps(obj).encode())
    def test_absence_is_not_ready(self):
        with patch.object(self.model, 'executable', return_value=None):
            self.assertFalse(self.model.start()[0])
            self.assertEqual(self.model.status['state'], 'absent')
    def test_install_failure_keeps_local_mode(self):
        with patch.object(self.model, 'executable', return_value=None), patch.object(self.model, 'install', side_effect=OSError('offline')):
            self.assertFalse(self.model.start(prepare=True)[0])
            self.assertEqual(self.model.status['state'], 'erreur')
    def test_pull_requires_completion_and_presence(self):
        with patch.object(self.model, 'request', return_value=io.BytesIO(b'{"status":"success"}\n')), patch.object(self.model, 'has_model', return_value=False):
            with self.assertRaises(RuntimeError):
                self.model.pull(lambda _: None)
    def test_pull_error_reported(self):
        with patch.object(self.model, 'request', return_value=io.BytesIO(b'{"error":"disk full"}\n')):
            with self.assertRaisesRegex(RuntimeError, 'disk full'):
                self.model.pull(lambda _: None)
    def test_server_and_model_not_enough_without_generation(self):
        self.run_start({'done': False}, False)
    def test_ready_requires_successful_generation(self):
        self.run_start({'done': True, 'response': 'OK'}, True)
    def run_start(self, result, expected):
        process = Mock(); process.poll.return_value = None
        with patch.object(self.model, 'executable', return_value='ollama'), \
             patch('clara.local_model.socket.socket'), \
             patch('clara.local_model.subprocess.Popen', return_value=process), \
             patch.object(self.model, 'has_model', return_value=True), \
             patch.object(self.model, 'request', side_effect=[self.response({'version': 'test'}), self.response(result)]):
            self.assertEqual(self.model.start()[0], expected)
            self.assertEqual(self.model.status['model'], True)
            self.assertEqual(self.model.status['state'], 'pret' if expected else 'erreur')
    def test_missing_model_is_not_complete(self):
        process = Mock(); process.poll.return_value = None
        with patch.object(self.model, 'executable', return_value='ollama'), \
             patch('clara.local_model.socket.socket'), \
             patch('clara.local_model.subprocess.Popen', return_value=process), \
             patch.object(self.model, 'has_model', return_value=False), \
             patch.object(self.model, 'request', return_value=self.response({'version': 'test'})):
            self.assertFalse(self.model.start()[0])
            self.assertEqual(self.model.status['state'], 'absent')
            self.assertFalse(self.model.status['model'])
    def test_occupied_port_never_reuses_foreign_server(self):
        sock = Mock(); sock.__enter__ = Mock(return_value=sock); sock.__exit__ = Mock()
        sock.bind.side_effect = OSError('occupied')
        with patch.object(self.model, 'executable', return_value='ollama'), patch('clara.local_model.socket.socket', return_value=sock), patch.object(self.model, 'request') as request:
            self.assertFalse(self.model.start()[0]); request.assert_not_called()
