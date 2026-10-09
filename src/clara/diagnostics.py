"""Rapport local exportable, stdlib seule même avant installation."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGES = ["jsonschema", "PySide6", "sounddevice", "numpy", "vosk", "faster-whisper", "psutil", "pywin32", "pywinauto"]
LIMIT = 262144

def user_folder():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ClaraVibeOS"

def tail(path):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - LIMIT))
        return stream.read(LIMIT).decode("utf-8", errors="replace")

def journal_snapshot(path):
    # Ne jamais instancier Journal : son constructeur modifie l'état de reprise.
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=.25)
    try:
        db.execute("PRAGMA query_only=ON")
        events = db.execute("SELECT timestamp,kind,payload FROM events ORDER BY id DESC LIMIT 100").fetchall()
        actions = db.execute("SELECT action_id,request_id,step_id,payload,result FROM actions ORDER BY rowid DESC LIMIT 100").fetchall()
        return {"events": events[::-1], "actions": actions[::-1], "limit_per_table": 100}
    finally:
        db.close()

def versions():
    result = {}
    for name in PACKAGES:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "MISSING"
    return result

def native_probe(name, config):
    if name == "imports":
        import importlib
        result = {"python": sys.version, "packages": versions(), "errors": {}}
        if os.name == "nt":
            for module in ["jsonschema", "PySide6.QtWidgets", "sounddevice", "numpy", "vosk", "faster_whisper", "psutil", "win32com.client", "pywinauto"]:
                try:
                    importlib.import_module(module)
                except Exception:
                    result["errors"][module] = traceback.format_exc()
        result["status"] = "ERROR" if result["errors"] else "OK" if os.name == "nt" else "NOT_TESTED"
        return result
    if os.name != "nt":
        return {"status": "NOT_TESTED", "detail": "Session Windows requise."}
    if name == "microphone":
        import sounddevice as sd
        devices = [dict(d, index=i) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        sd.check_input_settings(device=config.get("microphone"), channels=1, dtype="int16", samplerate=16000)
        with sd.RawInputStream(device=config.get("microphone"), channels=1, dtype="int16", samplerate=16000):
            pass
        return {"status": "OK", "input_devices": devices, "detail": "Flux ouvert sans enregistrer ; reconnaissance non testée."}
    if name == "sapi":
        import pythoncom
        import win32com.client
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            languages = [v.GetAttribute("Language") for v in voice.GetVoices()]
            french = any(code.lower() in {"40c", "040c", "80c", "080c", "100c"} for lang in languages for code in lang.split(";"))
            return {"status": "OK" if french else "WARNING", "languages": languages,
                    "detail": "Voix française détectée ; synthèse non testée." if french else "Voix française SAPI absente."}
        finally:
            pythoncom.CoUninitialize()
    if name == "explorer":
        from .windows import WindowsAdapter, tab_count
        adapter = WindowsAdapter()
        try:
            windows = adapter.windows()
            counts = [adapter.probe.submit(tab_count, int(w["window_id"])).result(timeout=2) for w in windows[:5]]
            return {"status": "OK" if windows and all(n <= 1 for n in counts) else "WARNING",
                    "windows": windows, "tab_counts": counts,
                    "detail": "Observation seulement, aucune activation ; au plus 5 fenêtres sondées."}
        finally:
            adapter.close()
    raise ValueError("Sonde inconnue")

def bounded_probe(name, config):
    try:
        result = subprocess.run([sys.executable, "-m", "clara.diagnostics", "--probe", name],
                                input=json.dumps(config), text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=20)
        if result.returncode:
            return {"status": "ERROR", "returncode": result.returncode, "stderr": result.stderr[-LIMIT:]}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "detail": "Sonde interrompue après 20 s ; résultat inconnu."}
    except Exception:
        return {"status": "ERROR", "traceback": traceback.format_exc()}

def collect(folder, stage, probes=None, launcher_log=None, config_path=None):
    probes = probes or {}
    report = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "stage": stage,
              "system": {"os": platform.platform(), "launcher_python": sys.version, "architecture": platform.machine()},
              "application_packages": probes.get("imports", {}).get("packages", "NOT_TESTED"),
              "checks": {}, "probes": probes, "collection_errors": [],
              "limits": "Disponibilité seulement ; pas de benchmark, transcription ni action Windows validée."}
    contents = {}
    source = Path(__file__).parent
    report["source_sha256"] = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(source.rglob("*")) if p.suffix in {".py", ".json"}}
    try:
        config = json.loads((config_path or folder / "config.json").read_text(encoding="utf-8"))
        from .config import check
        check(config)
        report["checks"]["config"] = "OK"
        contents["config.json"] = json.dumps(config, ensure_ascii=False, indent=2)
        for key, required in [("vosk_model", ["am/final.mdl", "conf/model.conf"]), ("whisper_model", ["model.bin", "config.json", "tokenizer.json"])]:
            report["checks"][key] = {file: (Path(config[key]) / file).is_file() for file in required}
        report["checks"]["ollama_executable"] = "FOUND" if shutil.which("ollama") else "MISSING"
    except Exception:
        report["checks"]["config"] = "ERROR"
        report["collection_errors"].append(traceback.format_exc())
        if (config_path or folder / "config.json").is_file():
            contents["config-invalid.txt"] = tail(config_path or folder / "config.json")
    paths = {name: folder / name for name in ["measurements.jsonl", "ollama.log", "journey.json", "journey.log"]}
    if launcher_log:
        paths["launcher.log"] = launcher_log
    for name, path in paths.items():
        if path.is_file():
            try:
                contents[name] = tail(path)
            except Exception:
                report["collection_errors"].append(traceback.format_exc())
    if (folder / "history.sqlite").is_file():
        try:
            contents["history-recent.json"] = json.dumps(journal_snapshot(folder / "history.sqlite"), ensure_ascii=False, indent=2)
        except Exception:
            report["collection_errors"].append(traceback.format_exc())
    contents["diagnostic.json"] = json.dumps(report, ensure_ascii=False, indent=2)
    contents["LIRE-MOI.txt"] = (
        "Diagnostic Clara : " + stage + "\n\nEnvoyer ce ZIP dans la conversation pour analyse. Aucun envoi automatique.\n"
        "Configuration, versions, disponibilités, dernières traces et actions.\n"
        "Peut contenir noms de fichiers, chemins et transcriptions. Aucun audio ni fichier personnel copié.\n"
        "Traces : derniers 256 Kio par fichier ; historique : 100 dernières lignes par table.\n"
        "Un contrôle OK ne prouve pas la précision vocale ou le succès d'une commande.\n\n" + json.dumps(probes, ensure_ascii=False, indent=2))
    return contents

def write_bundle(destination, folder, stage, **kwargs):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in collect(folder, stage, **kwargs).items():
                archive.writestr(name, content)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, choices=["microphone", "sapi", "explorer", "imports"])
    args = parser.parse_args()
    try:
        result = native_probe(args.probe, json.load(sys.stdin))
    except Exception:
        result = {"status": "ERROR", "traceback": traceback.format_exc()}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
