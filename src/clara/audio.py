"""Capture légère et transcription lourde dans deux processus distincts."""
from __future__ import annotations

import json
import queue
import time
import traceback
from collections import deque

from .planner import normal


class Segmenter:
    """Fin de parole testable sans microphone, tampon borné même en cas de dépassement."""
    def __init__(self, config):
        self.silence = config["end_silence_ms"] / 1000
        self.limit = config["max_utterance_seconds"]
        self.preamble = deque(maxlen=10)
        self.started = None
        self.last_speech = 0.
        self.chunks = []
        self.invalid = False
        self.wake_pending = False

    def discard(self):
        self.invalid = True
        self.chunks.clear()

    def feed(self, block, now, speech, enabled, speaking=False):
        events, utterance = [], None
        self.preamble.append(block)
        if speech:
            self.last_speech = now
            if self.started is None:
                self.started = now
                self.chunks = list(self.preamble)[:-1]
                events.append(("capture_start", now))
        if self.started is not None:
            if speech and speaking:
                self.discard()  # Also discard if TTS finishes before the trailing silence.
            if now - self.started > self.limit and not self.invalid:
                self.discard()
                events.append(("too_long", now))
            if not self.invalid:
                self.chunks.append(block)
            if not speech and now - self.last_speech >= self.silence:
                events.append(("capture_end", now))
                if (enabled or self.wake_pending) and not speaking and not self.invalid:
                    utterance = {"pcm": b"".join(self.chunks), "began": self.started,
                                 "last_speech_at": self.last_speech, "acquired_at": now}
                self.started = None
                self.chunks.clear()
                self.invalid, self.wake_pending = False, False
        return events, utterance


def validate_phrases(model, config):
    phrases = config["wake_phrases"] + config["sleep_phrases"] + ["stop"]
    for phrase in phrases:
        for word in normal(phrase).split():
            if model.vosk_model_find_word(word) < 0:
                raise ValueError(f"Mot absent du modèle d'activation : {word}. Ancien réglage conservé.")


def capture_worker(config, active, speaking, shutdown, controls, utterances, diagnostics):
    try:
        import numpy as np
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(-1)
        model = Model(config["vosk_model"])
        validate_phrases(model, config)
        recognizer = KaldiRecognizer(model, 16000)
        frames = queue.Queue(maxsize=64)
        overflow = False
        def callback(indata, count, clock, status):
            nonlocal overflow
            if status:
                overflow = True
            try:
                frames.put_nowait(bytes(indata))
            except queue.Full:
                overflow = True
        segmenter = Segmenter(config)
        with sd.RawInputStream(samplerate=16000, blocksize=1600, device=config["microphone"],
                               channels=1, dtype="int16", callback=callback) as stream:
            diagnostics.put(("audio_ready", "Microphone actif. Utilise un casque pour ce prototype."))
            while not shutdown.is_set():
                try:
                    block = frames.get(timeout=.2)
                except queue.Empty:
                    if not stream.active:
                        raise RuntimeError("Microphone déconnecté ; écoute suspendue.")
                    continue
                now = time.monotonic()
                if overflow:
                    overflow = False
                    segmenter.discard()
                    diagnostics.put(("audio_error", "Capture saturée ; énoncé abandonné."))
                samples = np.frombuffer(block, dtype=np.int16).astype(np.float32)
                speech = float(np.sqrt(np.mean(samples * samples))) >= config["speech_rms_threshold"]
                if recognizer.AcceptWaveform(block):
                    text = normal(json.loads(recognizer.Result()).get("text", ""))
                    if text == "stop" and active.is_set():
                        controls.put(("stop", now))
                        segmenter.discard()
                    elif text in [normal(x) for x in config["sleep_phrases"]] and active.is_set():
                        controls.put(("sleep", now))
                        segmenter.discard()
                    else:
                        for phrase in config["wake_phrases"]:
                            phrase = normal(phrase)
                            if text == phrase or text.startswith(phrase + " "):
                                controls.put(("wake", now))
                                segmenter.wake_pending = text != phrase
                                if text == phrase:
                                    segmenter.discard()
                                break
                events, utterance = segmenter.feed(block, now, speech, active.is_set(), speaking.is_set())
                for event in events:
                    if event[0] == "too_long":
                        diagnostics.put(("audio_error", "Énoncé trop long ; reformule après une pause."))
                    else:
                        controls.put(event)
                if utterance:
                    try:
                        utterances.put_nowait(utterance)
                    except queue.Full:
                        diagnostics.put(("audio_error", "Transcription occupée ; demande abandonnée."))
    except Exception as exc:
        diagnostics.put(("audio_fatal", str(exc)))
        diagnostics.put(("audio_traceback", traceback.format_exc()))


def stt_worker(config, shutdown, jobs, results, active):
    model = None
    while not shutdown.is_set():
        try:
            job = jobs.get(timeout=.2)
        except queue.Empty:
            if not active.is_set() and model is not None:
                model = None
                import gc
                gc.collect()
            continue
        try:
            import numpy as np
            from faster_whisper import WhisperModel
            if model is None:
                model = WhisperModel(config["whisper_model"], device="cpu", compute_type="int8",
                                     cpu_threads=4, local_files_only=True)
            audio = np.frombuffer(job.pop("pcm"), dtype=np.int16).astype(np.float32) / 32768
            segments, _ = model.transcribe(audio, language="fr", beam_size=3,
                                          condition_on_previous_text=False, vad_filter=False)
            text = " ".join(s.text.strip() for s in segments).strip()
            results.put({**job, "text": text, "stt_finished_at": time.monotonic()})
        except Exception as exc:
            results.put({**{k: v for k, v in job.items() if k != "pcm"}, "error": str(exc), "traceback": traceback.format_exc()})


def voice_worker(shutdown, commands, speaking, interrupt, diagnostics, epoch):
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        french = [v for v in voice.GetVoices() if any(x.lower() in {"40c", "040c", "80c", "080c", "100c"}
                   for x in v.GetAttribute("Language").split(";"))]
        if not french:
            raise ValueError("Aucune voix française SAPI installée ; retours visuels seulement.")
        voice.Voice = french[0]
        diagnostics.put(("voice_ready", "Voix française locale disponible."))
        while not shutdown.is_set():
            try:
                generation, message = commands.get(timeout=.2)
            except queue.Empty:
                continue
            if generation != epoch.value:
                continue
            interrupt.clear()
            speaking.set()
            voice.Speak(message, 1)  # SVSFlagsAsync
            while not voice.WaitUntilDone(50):
                if interrupt.is_set() or shutdown.is_set():
                    voice.Speak("", 3)  # Async + purge
                    break
            speaking.clear()
        pythoncom.CoUninitialize()
    except Exception as exc:
        diagnostics.put(("voice_error", str(exc)))
        diagnostics.put(("voice_traceback", traceback.format_exc()))
    finally:
        speaking.clear()
