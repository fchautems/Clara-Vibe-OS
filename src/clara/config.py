from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ClaraVibeOS"


def defaults() -> dict:
    root = data_dir()
    return {"schema_version": "0.1", "wake_phrases": ["salut clara", "bonjour clara"],
            "sleep_phrases": ["bonne nuit clara"], "session_idle_seconds": 180,
            "end_silence_ms": 2000, "max_utterance_seconds": 60,
            "clarification_timeout_seconds": 60, "microphone": None,
            "speech_rms_threshold": 350, "vosk_model": str(root / "models/vosk-model-small-fr-0.22"),
            "whisper_model": str(root / "models/whisper-small"),
            "ollama_model": "qwen2.5:3b", "ollama_port": 11435,
            "ollama_timeout_seconds": 15, "max_results": 128,
            "folder_aliases": {"documents": str(Path.home() / "Documents"),
                               "téléchargements": str(Path.home() / "Downloads")},
            "open_extensions": ["pdf", "txt", "md", "png", "jpg", "jpeg", "csv",
                                "json", "docx", "xlsx", "pptx"], "feedback_ding": True}


def check(value: dict) -> dict:
    base = defaults()
    if set(value) != set(base) or value["schema_version"] != "0.1":
        raise ValueError("Configuration inconnue ou incomplète ; conserver la dernière version valide.")
    for key in ("wake_phrases", "sleep_phrases", "open_extensions"):
        if not isinstance(value[key], list) or not value[key] or not all(isinstance(x, str) and x.strip() for x in value[key]):
            raise ValueError(f"Réglage invalide : {key}")
    for key, low, high in (("session_idle_seconds", 10, 3600), ("end_silence_ms", 300, 5000),
                         ("max_utterance_seconds", 5, 60), ("clarification_timeout_seconds", 5, 120),
                         ("speech_rms_threshold", 1, 32767), ("ollama_port", 1024, 65535),
                         ("ollama_timeout_seconds", 1, 60), ("max_results", 1, 128)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError(f"Réglage invalide : {key}")
    if not isinstance(value["folder_aliases"], dict) or not all(
        isinstance(k, str) and k.strip() and isinstance(v, str) and Path(v).is_absolute()
        for k, v in value["folder_aliases"].items()
    ):
        raise ValueError("Les alias doivent désigner des chemins absolus.")
    for key in ("vosk_model", "whisper_model", "ollama_model"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"Réglage invalide : {key}")
    if value["microphone"] is not None and type(value["microphone"]) is not int:
        raise ValueError("microphone doit être un numéro de périphérique ou null.")
    if type(value["feedback_ding"]) is not bool:
        raise ValueError("feedback_ding doit être booléen.")
    return value


def load(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save(path, defaults())
    return check(json.loads(path.read_text(encoding="utf-8")))


def save(path: Path, value: dict) -> None:
    check(value)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
