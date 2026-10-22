"""Preuves et rapports avec captures simulées ; aucun screenshot Windows ici."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clara.config import defaults
from clara.journey import create_journey_fixture, run_journey
from clara.planner import Planner, deterministic
from clara.test_evidence import capture_step, write_artifacts, WindowCapture
from test_journey import InteractiveFake


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.root = self.folder / 'fixture'
        create_journey_fixture(self.root)
        self.output = self.folder / 'journey.json'
    def tearDown(self):
        self.tmp.cleanup()
    def capture(self, destination, hwnd, stems):
        destination.write_bytes(b'FAKE_SCREENSHOT_NOT_A_REAL_PNG')
        return {'status': 'SAVED', 'window_id': str(hwnd), 'simulated': True}
    def run_case(self, capture=None, **kwargs):
        adapter = InteractiveFake(self.root)
        return run_journey(defaults(), self.root, self.output, lambda: adapter,
                           backend='simulated', capture=capture, **kwargs)
    def test_report_contains_interpretation_parameters_and_complete_bundle(self):
        report = self.run_case(self.capture)
        self.assertEqual(report['status'], 'PASSED', report.get('traceback'))
        self.assertEqual(report['evidence_status'], 'COMPLETE')
        self.assertEqual(len(report['understanding']), 4)
        first = report['steps'][0]['interpretations'][0]
        self.assertEqual(first['origin'], 'LOCAL_SIMILARITY')
        self.assertEqual(first['steps'][0]['arguments']['target']['query'], 'essai')
        with zipfile.ZipFile(self.output.with_suffix('.zip')) as archive:
            names = archive.namelist()
            self.assertEqual(len([n for n in names if n.endswith('.png')]), 14)
            self.assertEqual(json.loads(archive.read('journey.json'))['backend'], 'simulated')
            self.assertIn('LOCAL_SIMILARITY', archive.read('journey.txt').decode())
    def test_capture_error_does_not_turn_successful_actions_into_failure(self):
        def failed(*args):
            raise OSError('capture unavailable')
        report = self.run_case(failed)
        self.assertEqual(report['status'], 'PASSED')
        self.assertEqual(report['evidence_status'], 'PARTIAL')
        self.assertEqual(report['steps'][0]['screenshot']['status'], 'ERROR')
    def test_unknown_action_also_captured_and_not_reported_successful(self):
        adapter = InteractiveFake(self.root)
        def failed(ref):
            raise OSError('observation unavailable')
        adapter.observe_open = failed
        report = run_journey(defaults(), self.root, self.output, lambda: adapter,
                             backend='simulated', capture=self.capture)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['steps'][4]['status'], 'UNKNOWN')
        self.assertEqual(report['steps'][4]['screenshot']['status'], 'SAVED')
        self.assertTrue(all(s['status'] == 'SKIPPED' for s in report['steps'][5:]))
    def test_ollama_option_exercises_model_and_records_origin(self):
        planner = Planner(defaults(), True)
        with patch.object(planner, '_model', return_value=deterministic('remonte')) as model:
            report = self.run_case(planner=planner, with_ollama=True)
            self.assertEqual(report['status'], 'PASSED', report.get('traceback'))
            self.assertEqual(report['steps'][6]['interpretations'][0]['origin'], 'LOCAL_MODEL')
            model.assert_called_once()
    def test_capture_disabled_is_explicit(self):
        report = self.run_case()
        self.assertEqual(report['evidence_status'], 'NOT_REQUESTED')
        self.assertTrue(all(s['screenshot']['status'] == 'DISABLED' for s in report['steps']))
    def test_missing_capture_file_is_error(self):
        report = {'run_id': 'test', 'steps': [{}]}
        entry = report['steps'][0]; entry['status'] = 'FAILED'
        capture_step(report, entry, self.output, lambda *args: {'status': 'SAVED'}, '42', [])
        self.assertEqual(entry['screenshot']['status'], 'ERROR')
    def test_capture_refuses_unrelated_foreground_window(self):
        from unittest.mock import Mock
        capture = object.__new__(WindowCapture)
        capture.gui = Mock()
        capture.gui.GetForegroundWindow.return_value = 99
        capture.gui.GetWindowText.return_value = 'Unrelated document'
        capture.gui.GetClassName.return_value = 'OtherApplication'
        capture.app = Mock()
        result = capture(self.folder / 'forbidden.png', '42', ['exemple'])
        self.assertEqual(result['status'], 'SKIPPED')
        capture.app.primaryScreen.assert_not_called()
        self.assertFalse((self.folder / 'forbidden.png').exists())
    def test_zip_does_not_include_outside_file(self):
        outside = self.folder / 'personal.png'; outside.write_bytes(b'private')
        report = {'run_id': 'test', 'status': 'FAILED', 'steps': [
            {'status': 'FAILED', 'name': 'case', 'command': 'test', 'screenshot': {'path': 'personal.png'}}]}
        self.output.write_text(json.dumps(report))
        write_artifacts(self.output, report)
        with zipfile.ZipFile(self.output.with_suffix('.zip')) as archive:
            self.assertNotIn('personal.png', archive.namelist())
