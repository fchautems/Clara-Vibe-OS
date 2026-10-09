"""Lancement unique avec journal et rapport automatique même après un échec."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clara.diagnostics import user_folder, write_bundle

def main():
    os.chdir(ROOT)
    folder = user_folder()
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / "launcher.log"
    report_path = ROOT / "diagnostic-clara.zip"
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    stage, probes, code = "initialisation", {}, 1
    halt = threading.Event()
    exporter = None
    config_path = folder / "config.json"
    if "--config" in sys.argv[1:]:
        index = sys.argv.index("--config")
        if index + 1 < len(sys.argv):
            config_path = Path(sys.argv[index + 1]).resolve()
    def export():
        try:
            write_bundle(report_path, folder, stage, probes=probes, launcher_log=log_path, config_path=config_path)
            return True
        except Exception:
            print("Export du diagnostic échoué :\n" + traceback.format_exc(), file=sys.stderr, flush=True)
            return False
    def periodically():
        while not halt.wait(30):
            export()
    with log_path.open("w", encoding="utf-8") as log:
        def run(arguments):
            log.write("\nETAPE : " + stage + "\n")
            log.flush()
            with subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env=environment, text=True, encoding="utf-8", errors="replace") as process:
                try:
                    for line in process.stdout:
                        print(line, end="", flush=True)
                        log.write(line)
                        log.flush()
                    result = process.wait()
                except BaseException:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                    raise
            if result:
                raise RuntimeError(f"Échec de {stage}, code {result}")
        try:
            export()
            exporter = threading.Thread(target=periodically, daemon=True)
            exporter.start()
            if sys.platform != "win32":
                raise RuntimeError("Le lancement vocal nécessite Windows.")
            python = ROOT / ".venv/Scripts/python.exe"
            stage = "environnement Python"
            if not python.is_file():
                run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
            stage = "installation"
            marker = ROOT / ".venv/clara-installed.txt"
            if not marker.exists():
                run([str(python), "-m", "pip", "install", "-r", "requirements-windows.lock"])
                run([str(python), "-m", "pip", "install", "--no-deps", "-e", "."])
                marker.write_text("0.1.0")
            stage = "préparation des modèles"
            ready = folder / "setup-complete.json"
            if not ready.exists():
                run([str(python), "-m", "clara.setup"])
                ready.write_text(json.dumps({"version": "0.1.0"}))
            stage = "diagnostic de disponibilité"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            for name in ["imports", "microphone", "sapi", "explorer"]:
                result = None
                try:
                    result = subprocess.run([str(python), "-c",
                                            "import json,sys; from clara.diagnostics import bounded_probe; "
                                            "print(json.dumps(bounded_probe(sys.argv[1],json.load(sys.stdin))))", name],
                                            input=json.dumps(config), capture_output=True, text=True,
                                            encoding="utf-8", errors="replace", env=environment, timeout=25)
                    probes[name] = json.loads(result.stdout)
                except Exception:
                    probes[name] = {"status": "ERROR", "traceback": traceback.format_exc()}
                    if result is not None:
                        probes[name].update(stdout=result.stdout[-262144:], stderr=result.stderr[-262144:])
                print(f"Diagnostic {name} : {probes[name].get('status', 'ERROR')}", flush=True)
            stage = "application en cours"
            export()
            run([str(python), "-m", "clara.app", "--fixture", *sys.argv[1:]])
            stage, code = "fermeture normale", 0
        except (Exception, KeyboardInterrupt):
            stage = "échec : " + stage
            log.write(traceback.format_exc())
            log.flush()
        finally:
            halt.set()
            if exporter:
                exporter.join()
            log.flush()
            exported = export()
    print(f"Rapport à transmettre : {report_path}" if exported else f"Rapport indisponible ; journal : {log_path}", flush=True)
    return code

if __name__ == "__main__":
    raise SystemExit(main())
