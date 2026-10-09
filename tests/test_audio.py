import unittest

from clara.audio import Segmenter, validate_phrases
from clara.config import defaults


class AudioSegmentation(unittest.TestCase):
    def test_pause_does_not_execute_a_fragment(self):
        s = Segmenter(defaults())
        s.feed(b"a", 0, True, True)
        self.assertIsNone(s.feed(b"b", 1, False, True)[1])
        s.feed(b"c", 1.5, True, True)
        self.assertIsNone(s.feed(b"d", 2.5, False, True)[1])
        _, utterance = s.feed(b"e", 3.6, False, True)
        self.assertEqual(utterance["pcm"], b"abcde")
        self.assertEqual(utterance["last_speech_at"], 1.5)

    def test_only_one_final_at_end_of_silence(self):
        s = Segmenter(defaults())
        s.feed(b"a", 1, True, True)
        self.assertIsNotNone(s.feed(b"b", 3.1, False, True)[1])
        self.assertIsNone(s.feed(b"c", 3.2, False, True)[1])

    def test_oversize_audio_never_executes_tail_and_memory_is_bounded(self):
        s = Segmenter(dict(defaults(), max_utterance_seconds=5))
        for i in range(100):
            _, utterance = s.feed(b"x" * 3200, float(i), True, True)
            self.assertIsNone(utterance)
        self.assertEqual(s.chunks, [])
        self.assertLessEqual(len(s.preamble), 10)
        self.assertIsNone(s.feed(b"x", 102, False, True)[1])

    def test_audio_in_standby_not_sent_to_heavy_transcription(self):
        s = Segmenter(defaults())
        s.feed(b"a", 1, True, False)
        self.assertIsNone(s.feed(b"b", 3.1, False, False)[1])

    def test_wake_and_command_keep_full_utterance(self):
        s = Segmenter(defaults())
        s.feed(b"wake", 1, True, False)
        s.feed(b"command", 1.5, True, False)
        s.wake_pending = True
        _, utterance = s.feed(b"end", 3.6, False, False)
        self.assertEqual(utterance["pcm"], b"wakecommandend")

    def test_discard_after_stop_or_overflow_no_transcription(self):
        s = Segmenter(defaults())
        s.feed(b"a", 1, True, True)
        s.discard()
        self.assertIsNone(s.feed(b"b", 3.1, False, True)[1])
        s.feed(b"c", 4, True, True)
        self.assertIsNotNone(s.feed(b"d", 6.1, False, True)[1])

    def test_tts_not_recaptured_as_ordinary_command(self):
        s = Segmenter(defaults())
        s.feed(b"a", 1, True, True, True)
        self.assertIsNone(s.feed(b"b", 3.1, False, True, False)[1])

    def test_unavailable_wake_word_is_explicitly_rejected(self):
        class Model:
            def vosk_model_find_word(self, word):
                return -1 if word == "clara" else 1
        with self.assertRaises(ValueError):
            validate_phrases(Model(), defaults())


if __name__ == "__main__":
    unittest.main()
