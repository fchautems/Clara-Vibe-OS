from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time

from .audio import capture_worker, stt_worker, voice_worker
from .planner import normal


class AudioRuntime:
    def __init__(self, config, engine):
        self.config, self.engine = config, engine
        self.ctx = mp.get_context("spawn")
        self.active, self.speaking = self.ctx.Event(), self.ctx.Event()
        self.shutdown, self.interrupt = self.ctx.Event(), self.ctx.Event()
        self.controls = self.ctx.Queue(maxsize=64)
        self.utterances, self.jobs = self.ctx.Queue(maxsize=2), self.ctx.Queue(maxsize=2)
        self.results, self.diagnostics = self.ctx.Queue(maxsize=16), self.ctx.Queue(maxsize=64)
        self.voices = self.ctx.Queue(maxsize=8)
        self.epoch = 0
        self.voice_epoch = self.ctx.Value("I", 0)
        self.captures = {}
        self.lock = threading.Lock()
        self.processes = [
            self.ctx.Process(target=capture_worker, args=(config, self.active, self.speaking, self.shutdown,
                              self.controls, self.utterances, self.diagnostics), daemon=True),
            self.ctx.Process(target=stt_worker, args=(config, self.shutdown, self.jobs, self.results, self.active), daemon=True),
            self.ctx.Process(target=voice_worker, args=(self.shutdown, self.voices, self.speaking,
                              self.interrupt, self.diagnostics, self.voice_epoch), daemon=True)]
        for p in self.processes:
            p.start()
        # Control listener is independent of UI, model and Windows execution.
        threading.Thread(target=self._controls, daemon=True, name="clara-priority-controls").start()
        threading.Thread(target=self._transcriptions, daemon=True, name="clara-stt-results").start()

    def cancel_capture(self):
        with self.lock:
            self.epoch += 1
            self.voice_epoch.value = self.epoch
        self.interrupt.set()
        self.engine.capturing = False

    def _controls(self):
        while not self.shutdown.is_set():
            try:
                kind, at = self.controls.get(timeout=.1)
            except queue.Empty:
                continue
            if kind == "stop":
                self.cancel_capture()
                self.engine.stop()
                self.engine.emit("control_timing", recognized_at=at, accepted_at=time.monotonic())
            elif kind == "sleep":
                self.cancel_capture()
                self.active.clear()
                self.engine.sleep()
            elif kind == "wake":
                if not self.engine.session:
                    self.engine.activate()
                    if self.engine.session:
                        self.active.set()
            elif kind == "capture_start":
                self.engine.capturing = self.engine.session
                with self.lock:
                    self.captures[at] = (self.epoch, self.engine.dialogue_token(), self.engine.session_id)
                    while len(self.captures) > 8:
                        self.captures.pop(next(iter(self.captures)))
            elif kind == "capture_end":
                self.engine.capturing = False

    def _transcriptions(self):
        while not self.shutdown.is_set():
            self.active.set() if self.engine.session else self.active.clear()
            try:
                job = self.utterances.get_nowait()
                with self.lock:
                    token = self.captures.pop(job["began"], None)
                # If the capture-start message has not yet arrived, wait briefly;
                # do not attach a reply to a question created after speech began.
                if token is None:
                    for _ in range(10):
                        time.sleep(.01)
                        with self.lock:
                            token = self.captures.pop(job["began"], None)
                        if token is not None:
                            break
                if token is None:
                    self.engine.emit("error", "Métadonnées de capture absentes ; énoncé abandonné.")
                else:
                    job.update(epoch=token[0], dialogue_id=token[1],
                               session_id=token[2] or self.engine.session_id)
                    if self.config["feedback_ding"]:
                        try:
                            import winsound
                            winsound.MessageBeep(winsound.MB_OK)
                        except ImportError:
                            pass
                    try:
                        self.jobs.put_nowait(job)
                    except queue.Full:
                        self.engine.emit("error", "Transcription saturée ; énoncé abandonné.")
            except queue.Empty:
                pass
            try:
                result = self.results.get(timeout=.05)
            except queue.Empty:
                continue
            with self.lock:
                valid = result["epoch"] == self.epoch
            if not valid or not self.engine.session or result["session_id"] != self.engine.session_id:
                self.engine.emit("ignored", "Transcription tardive abandonnée.")
                continue
            if "error" in result:
                self.engine.emit("error", "Transcription indisponible : " + result["error"])
                continue
            text = result["text"]
            for phrase in self.config["wake_phrases"]:
                n, p = normal(text), normal(phrase)
                if n.startswith(p + " "):
                    text = n[len(p) + 1:]
                    break
            self.engine.emit("transcript", text, stt_finished_at=result["stt_finished_at"],
                             last_speech_at=result["last_speech_at"], acquired_at=result["acquired_at"])
            if text:
                if normal(text) == "stop" or normal(text) in [normal(p) for p in self.config["sleep_phrases"]]:
                    self.cancel_capture()
                self.engine.submit(text, result["dialogue_id"], result["last_speech_at"])

    def say(self, text):
        try:
            self.voices.put_nowait((self.epoch, text[:1500]))
        except queue.Full:
            self.engine.emit("error", "Retours vocaux saturés ; consulte le panneau.")

    def close(self):
        self.cancel_capture()
        self.shutdown.set()
        for p in self.processes:
            p.join(timeout=1)
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)
