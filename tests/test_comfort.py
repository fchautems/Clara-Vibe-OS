import threading
from unittest.mock import patch

from clara.contracts import ClaraError
from clara.planner import normal
from clara.support import comfort_requested, support_catalogue
from test_core import Fixture


class ComfortExecution(Fixture):
    def test_phrases_and_politeness_match_without_file_name_confusion(self):
        for kind, phrases in support_catalogue()['comfort_phrases'].items():
            for phrase in phrases:
                self.assertEqual(comfort_requested(normal(phrase)), kind)
        self.assertEqual(comfort_requested(normal('Clara, répète, s’il te plaît')), 'repeat')
        self.assertEqual(comfort_requested(normal('où suis-je ?')), 'location')
        self.assertIsNone(comfort_requested(normal('ouvre le fichier répète.txt')))

    def test_repeat_does_not_call_windows_or_planner(self):
        engine = self.start()
        engine.submit('aide')
        help_event = self.event('help')
        with patch.object(self.adapter, 'context') as context, patch.object(engine.planner, 'interpret') as planner:
            engine.submit('répète')
            self.assertEqual(self.event('info')['message'], help_event['message'])
            context.assert_not_called()
            planner.assert_not_called()
        self.assertEqual(self.adapter.opened, [])

    def test_repeat_preserves_numbered_choices_even_after_help(self):
        engine = self.start()
        engine.submit('ouvre rapport')
        question = self.event('question')
        token = engine.dialogue_token()
        engine.submit('aide', token)
        self.event('help')
        engine.submit('répète les choix', token)
        repeated = self.event('info')
        self.assertEqual(repeated['message'], question['message'])
        self.assertEqual(repeated['candidates'], question['candidates'])
        self.assertEqual(engine.dialogue_token(), token)
        engine.submit('un', token)
        self.assertEqual(self.event('result')['result']['status'], 'SUCCEEDED')

    def test_repeat_never_reexecutes_completed_action(self):
        engine = self.start()
        engine.submit('ouvre notes')
        result = self.event('result')
        self.event('done')
        engine.submit('répète')
        self.assertEqual(self.event('info')['message'], result['message'])
        self.assertEqual(len(self.adapter.opened), 1)

    def test_standby_and_new_session_clear_previous_response(self):
        engine = self.start()
        engine.submit('aide')
        self.event('help')
        engine.sleep()
        engine.submit('répète')
        self.event('ignored')
        engine.activate()
        engine.submit('répète')
        self.assertIn('pas encore', self.event('info')['message'])

    def test_stale_token_is_refused_without_changing_choices(self):
        engine = self.start()
        engine.submit('ouvre rapport')
        self.event('question')
        token = engine.dialogue_token()
        for phrase in ['répète', 'où suis-je']:
            engine.submit(phrase, 'stale')
            self.event('error')
            self.assertEqual(engine.dialogue_token(), token)
        self.assertEqual(self.adapter.opened, [])

    def test_location_is_read_fresh_without_planner_or_opening(self):
        engine = self.start()
        with patch.object(engine.planner, 'interpret') as planner:
            engine.submit('où suis-je')
            self.assertIn(str(self.folder), self.event('info')['message'])
            other = self.folder / 'autre'
            other.mkdir()
            self.adapter.folder = other
            engine.submit('où suis-je')
            self.assertIn(str(other), self.event('info')['message'])
            planner.assert_not_called()
        self.assertEqual(self.adapter.opened, [])

    def test_location_failure_is_explicit_and_worker_survives(self):
        engine = self.start()
        with patch.object(self.adapter, 'context', side_effect=ClaraError('NO_CONTEXT', 'Aucun Explorateur actif.')):
            engine.submit('où suis-je')
            self.assertIn('Aucun Explorateur', self.event('info')['message'])
        engine.submit('ouvre notes')
        self.assertEqual(self.event('result')['result']['status'], 'SUCCEEDED')

    def test_location_during_choice_preserves_dialogue(self):
        engine = self.start()
        engine.submit('ouvre rapport')
        self.event('question')
        token = engine.dialogue_token()
        engine.submit('où suis-je', token)
        self.assertIn(str(self.folder), self.event('info')['message'])
        self.assertEqual(engine.dialogue_token(), token)
        self.assertFalse(engine.current.cancelled)

    def test_stop_discards_location_result_observed_late(self):
        engine = self.start()
        started, release = threading.Event(), threading.Event()
        context = self.adapter.context
        def delayed():
            started.set()
            release.wait(2)
            return context()
        with patch.object(self.adapter, 'context', side_effect=delayed):
            engine.submit('où suis-je')
            self.assertTrue(started.wait(2))
            engine.stop()
            release.set()
            engine.jobs.join()
        events = []
        while not engine.events.empty():
            events.append(engine.events.get_nowait())
        self.assertFalse(any(event['kind'] == 'info' for event in events))

    def test_location_during_execution_does_not_pause_or_replace(self):
        engine = self.start()
        started, release = threading.Event(), threading.Event()
        def delay():
            started.set()
            release.wait(2)
        self.adapter.before_call = delay
        engine.submit('ouvre notes')
        self.assertTrue(started.wait(2))
        try:
            engine.submit('où suis-je')
            self.assertIn('en cours', self.event('info')['message'])
            self.assertFalse(engine.current.paused)
            self.assertIsNone(engine.dialogue)
        finally:
            release.set()
        self.assertEqual(self.event('result')['result']['status'], 'SUCCEEDED')

    def test_negated_repeat_does_not_replay_response(self):
        engine = self.start()
        engine.submit('ne répète pas')
        self.event('error')
        self.assertEqual(self.adapter.opened, [])
