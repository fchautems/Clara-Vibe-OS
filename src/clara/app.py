from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import queue
import sys
import time
from pathlib import Path

from .config import data_dir, load
from .engine import Engine
from .local_model import LocalModel
from .planner import Planner
from .windows import WindowsAdapter


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Clara Vibe OS — prototype Explorateur")
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    parser.add_argument("--text-only", action="store_true", help="Diagnostic Windows sans microphone")
    parser.add_argument("--fixture", action="store_true", help="Ouvrir le dossier d'essai isolé")
    args = parser.parse_args()
    if os.name != "nt":
        parser.exit(2, "L'application vocale requiert Windows. Tests du noyau : python -m unittest discover -s tests\n")
    try:
        config = load(args.config)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QLineEdit
    from .runtime import AudioRuntime
    # A port bound for this process lifetime prevents two Clara instances per user.
    import socket
    single = socket.socket()
    try:
        single.bind(("127.0.0.1", 11436))
    except OSError:
        parser.exit(2, "Une instance Clara est déjà active, ou son port est occupé.\n")
    local = LocalModel(config, data_dir())
    ready, model_message = local.start()
    app = QApplication(sys.argv[:1])
    engine = Engine(config, Planner(config, ready), WindowsAdapter, data_dir() / "history.sqlite")
    audio = None if args.text_only else AudioRuntime(config, engine)
    root = QWidget()
    root.setWindowTitle("Clara Vibe OS — prototype 0.1")
    if not args.text_only:
        root.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        root.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    root.resize(600, 430)
    layout = QVBoxLayout(root)
    state = QLabel("Démarrage — utilise un casque. Les essais haut-parleurs restent à valider.")
    layout.addWidget(state)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.document().setMaximumBlockCount(500)
    layout.addWidget(view)
    stop = QPushButton("Stop")
    stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    def stop_all():
        if audio:
            audio.cancel_capture()
        engine.stop()
    stop.clicked.connect(stop_all)
    layout.addWidget(stop)
    if args.text_only:
        line = QLineEdit()
        line.setPlaceholderText("Mode diagnostic : saisir une commande ou un choix")
        def submit_line():
            engine.submit(line.text(), engine.dialogue_token())
            line.clear()
        line.returnPressed.connect(submit_line)
        layout.addWidget(line)
        engine.activate()
    view.appendPlainText(model_message)
    # Runtime telemetry is separate from action journal, never sent to the model.
    telemetry = (data_dir() / "measurements.jsonl").open("a", encoding="utf-8")
    telemetry.write(json.dumps({"wall_time": time.time(), "kind": "startup", "python": sys.version,
                                "ollama_ready": ready, "ollama_message": model_message,
                                "text_only": args.text_only}, ensure_ascii=False) + "\n")
    telemetry.flush()
    import psutil
    process = psutil.Process()
    last_resources = 0.
    def poll():
        nonlocal last_resources
        engine.tick()
        if audio:
            while True:
                try:
                    kind, message = audio.diagnostics.get_nowait()
                except queue.Empty:
                    break
                telemetry.write(json.dumps({"wall_time": time.time(), "kind": kind, "message": message}, ensure_ascii=False) + "\n")
                telemetry.flush()
                if kind.endswith("_traceback"):
                    continue
                state.setText(message)
                view.appendPlainText(message)
                if kind == "audio_fatal":
                    audio.cancel_capture()
                    audio.active.clear()
                    engine.sleep("Microphone suspendu ; redémarrage requis après correction.")
        while True:
            try:
                event = engine.urgent.get_nowait()
            except queue.Empty:
                try:
                    event = engine.events.get_nowait()
                except queue.Empty:
                    break
            message = event["message"]
            if message:
                view.appendPlainText(message)
            if event["kind"] == "session":
                state.setText(message)
                if audio and not engine.session:
                    audio.cancel_capture()
            if event["kind"] == "question":
                choices = "; ".join(f"{c['number']} : {c['name']}" for c in event.get("candidates", []))
                view.appendPlainText(choices)
                if audio and event["dialogue_id"] == engine.dialogue_token():
                    audio.say(message + " " + choices)
            elif event["kind"] in {"error", "fatal"} and audio:
                audio.say(message)
            result = event.get("result", {}).get("observed_result")
            if result and result.get("result_set"):
                for i, ref in enumerate(result["targets"], 1):
                    view.appendPlainText(f"{i} : {Path(ref['path']).name}")
            elif result and result["targets"] and all(r["kind"] == "window" for r in result["targets"]):
                names = "; ".join(f"{i} : {Path(ref['path']).name}" for i, ref in enumerate(result["targets"], 1))
                view.appendPlainText(names)
                if audio:
                    audio.say(message + " " + names)
            if event["kind"] in {"transcript", "result", "control_timing", "stop", "error", "fatal", "question", "session"}:
                telemetry.write(json.dumps({"wall_time": time.time(), **event}, ensure_ascii=False) + "\n")
                telemetry.flush()
        if time.monotonic() - last_resources >= 5:
            last_resources = time.monotonic()
            children = process.children(recursive=True)
            rss = process.memory_info().rss
            for child in children:
                try:
                    rss += child.memory_info().rss
                except psutil.Error:
                    pass
            telemetry.write(json.dumps({"wall_time": time.time(), "kind": "resources",
                                       "session_active": engine.session, "rss_bytes": rss,
                                       "system_cpu_percent": psutil.cpu_percent()}) + "\n")
            telemetry.flush()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(50)
    root.show()
    # Session lock notification: discard pending commands, wake phrase required on unlock.
    from PySide6.QtCore import QAbstractNativeEventFilter
    import ctypes
    from ctypes import wintypes
    class SessionEvents(QAbstractNativeEventFilter):
        def nativeEventFilter(self, event_type, message):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x02B1 and msg.wParam in (7, 8):  # WM_WTSSESSION_CHANGE
                engine.suspended = msg.wParam == 7
                if audio:
                    audio.cancel_capture()
                    audio.active.clear()
                engine.sleep("Session Windows verrouillée." if msg.wParam == 7 else "Windows déverrouillé ; Clara en veille.")
            return False, 0
    session_filter = SessionEvents()
    app.installNativeEventFilter(session_filter)
    register = ctypes.windll.wtsapi32.WTSRegisterSessionNotification
    register.argtypes = [wintypes.HWND, wintypes.DWORD]
    register.restype = wintypes.BOOL
    register(int(root.winId()), 0)
    if args.fixture:
        fixture = data_dir() / "fixtures"
        if not fixture.is_dir():
            from .setup import create_fixture
            create_fixture(fixture)
        QTimer.singleShot(1000, lambda: os.startfile(str(fixture), "open"))
    code = app.exec()
    timer.stop()
    if audio:
        audio.close()
    engine.close()
    local.close()
    telemetry.close()
    single.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
