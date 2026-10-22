"""Parcours Windows automatique dans des fixtures dédiées, sans voix, Ollama optionnel."""
from __future__ import annotations
import argparse
import json
import os
import queue
import socket
import threading
import time
import traceback
from pathlib import Path
from uuid import uuid4

from .config import data_dir, load
from .contracts import ClaraError
from .engine import Engine
from .planner import Planner
from .setup import create_fixture
from .test_evidence import capture_step, write_artifacts

VERSION = 1


def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def create_journey_fixture(root):
    if root.exists():
        raise ValueError("Le parcours exige un nouveau dossier dédié.")
    create_fixture(root)
    nested = root / "sous-dossier/niveau-deux"
    nested.mkdir()
    (nested / "exemple.txt").write_text("Document du parcours automatique Clara.\n", encoding="utf-8")


class GuardedAdapter:
    """Ne cible que la fenêtre initiale et les chemins générés pour ce parcours."""
    def __init__(self, adapter, root):
        self.adapter, self.root = adapter, root.resolve()
        self.directories = {self.root, self.root / "sous-dossier", self.root / "sous-dossier/niveau-deux"}
        self.files = {self.root / "rapport ancien.pdf", self.root / "rapport recent.pdf",
                      self.root / "sous-dossier/niveau-deux/exemple.txt"}
        self.pinned = None
        self.stop_armed = False
        self.prepared, self.release = threading.Event(), threading.Event()
        self.open_calls = 0
        last_error = None
        deadline = time.monotonic() + 10
        while True:
            try:
                context = adapter.context()
                if Path(context["current_directory"]["path"]).resolve() == self.root:
                    self.pinned = dict(context["window"], path=str(self.root))
                    break
            except Exception as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                adapter.close()
                raise ClaraError("FIXTURE_WINDOW_MISSING", "Fenêtre d'essai unique non observée ; parcours arrêté.") from last_error
            time.sleep(.1)

    def check_path(self, path, allowed):
        path = Path(path)
        if path.is_symlink() or path.resolve() not in allowed:
            raise ClaraError("FIXTURE_ONLY", "Cible hors du parcours d'essai ; aucune action.")
        # Ne pas suivre un sous-dossier remplacé par un lien.
        for parent in path.parents:
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ClaraError("FIXTURE_ONLY", "Lien dans le parcours d'essai ; aucune action.")

    def context(self):
        context = self.adapter.context()
        if context["window"]["window_id"] != self.pinned["window_id"]:
            raise ClaraError("FIXTURE_WINDOW_CHANGED", "La fenêtre active a changé ; parcours arrêté.")
        self.check_path(Path(context["current_directory"]["path"]), self.directories)
        return context

    def ensure_context(self, expected):
        self.context()
        self.adapter.ensure_context(expected)

    def prepare_navigation(self, context, path):
        self.check_path(path, self.directories)
        self.ensure_context(context)
        return self.adapter.prepare_navigation(context, path)

    def observe_navigation(self, context, path):
        self.check_path(path, self.directories)
        result = self.adapter.observe_navigation(context, path)
        self.context()
        return result

    def prepare_open(self, context, path):
        self.check_path(path, self.files)
        self.ensure_context(context)
        native = self.adapter.prepare_open(context, path)
        if self.stop_armed:
            self.prepared.set()
            if not self.release.wait(5):
                raise ClaraError("STOP_TEST_TIMEOUT", "Arrêt de test non reçu ; ouverture refusée.")
        def open_file():
            self.open_calls += 1
            return native()
        return open_file

    def observe_open(self, ref):
        self.check_path(Path(ref["path"]), self.files)
        return self.adapter.observe_open(ref)

    def windows(self):
        return [self.pinned]

    def prepare_activate(self, ref):
        if ref["window_id"] != self.pinned["window_id"]:
            raise ClaraError("FIXTURE_ONLY", "Activation d'une autre fenêtre refusée.")
        return self.adapter.prepare_activate(ref)

    def observe_activate(self, ref):
        observation = self.adapter.observe_activate(ref)
        self.context()
        return observation

    def close(self):
        self.release.set()
        self.adapter.close()


def run_journey(config, root, output, adapter_factory, backend="windows", capture=None, planner=None, with_ollama=False):
    report = {"version": VERSION, "mode": "commands_without_speech", "backend": backend, "status": "RUNNING",
              "run_id": uuid4().hex, "fixture": str(root), "screenshots_requested": capture is not None, "started_at": time.time(), "steps": [],
              "limits": "Microphone/transcription/voix non testés. Captures = preuves visuelles, pas assertions automatiques. Ouverture : titre de fenêtre, pas contenu du document." + (" Ollama demandé." if with_ollama else " Ollama non testé.")}
    save_report(output, report)
    config = dict(config, folder_aliases={"essai": str(root)}, open_extensions=["txt", "pdf"])
    holder, engine = {}, None
    planner = planner or Planner(config)
    scenarios = [
        ("dossier principal", "affiche ce dossier essai", root, None),
        ("sous-dossier", "ouvre le dossier sous-dossier", root / "sous-dossier", None),
        ("dossier imbriqué", "ouvre le dossier niveau-deux", root / "sous-dossier/niveau-deux", None),
        ("recherche", "cherche le fichier exemple", root / "sous-dossier/niveau-deux/exemple.txt", None),
        ("ouverture du texte", "ouvre le fichier exemple", root / "sous-dossier/niveau-deux/exemple.txt", None),
        ("retour Explorateur", "retour à l'explorateur", None, None),
        ("parent imbriqué", "remonte au dossier parent", root / "sous-dossier", None),
        ("retour principal", "remonte au dossier parent", root, None),
        ("filtre PDF", "montre-moi les PDF", None, None),
        ("plus récent contextuel", "ouvre le plus récent", root / "rapport recent.pdf", None),
        ("retour après PDF", "retour à l'explorateur", None, None),
        ("ambiguïté et choix", "ouvre rapport", root / "rapport recent.pdf", "rapport recent.pdf"),
        ("retour avant stop", "retour à l'explorateur", None, None),
        ("stop avant ouverture", "montre-moi les PDF puis ouvre le plus récent", None, "STOP")]
    if with_ollama:
        scenarios[6] = ("parent via Ollama", "emmène-moi un étage plus haut", root / "sous-dossier", None)
    expected_intents = [
        ["explorer.navigate"], ["explorer.navigate"], ["explorer.navigate"], ["files.search"],
        ["files.open"], ["window.activate"], ["explorer.parent"], ["explorer.parent"],
        ["files.filter"], ["files.select_recent", "files.open"], ["window.activate"],
        ["files.open"], ["window.activate"], ["files.filter", "files.select_recent", "files.open"]]
    def evidence(entry):
        guard = holder.get("adapter")
        hwnd = guard.pinned["window_id"] if guard and guard.pinned else None
        stems = ["exemple"] if entry["name"] == "ouverture du texte" else (
            ["rapport recent"] if entry["name"] in {"plus récent contextuel", "ambiguïté et choix"} else [])
        capture_step(report, entry, output, capture, hwnd, stems)

    def factory():
        holder["adapter"] = GuardedAdapter(adapter_factory(), root)
        return holder["adapter"]
    try:
        report["understanding"] = []
        for text, expected, error in [
            ("va dans F", "explorer.navigate", None),
            ("affiche donc le disque F", "explorer.navigate", None),
            ("ne va pas dans F", None, "UNRECOGNIZED"),
            ("va dans F ou G", None, "INCOMPLETE")]:
            expected_arguments = {"target": {"path": "F:\\"}} if expected == "explorer.navigate" else None
            case = {"text": text, "expected_intent": expected, "expected_arguments": expected_arguments, "expected_error": error}
            try:
                steps, origin = planner.interpret(text, {})
                case.update(steps=steps, origin=origin, status="PASSED" if not error and steps[0]["intent_id"] == expected and steps[0]["arguments"] == expected_arguments else "FAILED")
            except ClaraError as exc:
                case.update(error_code=exc.code, message=str(exc), status="PASSED" if error == exc.code else "FAILED")
            report["understanding"].append(case)
            save_report(output, report)
            if case["status"] != "PASSED":
                raise RuntimeError("Contrôle de compréhension échoué : " + text)
        engine = Engine(config, planner, factory, root / "journey-history.sqlite")
        if not engine.ready.wait(12) or engine.failed:
            raise RuntimeError("Coordinateur ou fenêtre d'essai indisponible.")
        engine.submit(config["wake_phrases"][0])
        for scenario_index, (label, command, expected_path, choice) in enumerate(scenarios):
            entry = {"name": label, "command": command, "expected_path": str(expected_path) if expected_path else None,
                     "expected": "choix entre deux PDF" if choice and choice != "STOP" else
                                 "deux étapes de lecture puis stop sans ouverture" if choice == "STOP" else "SUCCEEDED",
                     "expected_intents": expected_intents[scenario_index],
                     "status": "RUNNING", "started_at": time.time(), "events": [], "interpretations": []}
            report["steps"].append(entry)
            save_report(output, report)
            adapter = holder["adapter"]
            if choice == "STOP":
                adapter.stop_armed = True
                before = adapter.open_calls
            engine.submit(command)
            deadline, stopped, asked = time.monotonic() + 20, False, False
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Résultat non observé après 20 secondes : " + label)
                if choice == "STOP" and adapter.prepared.is_set() and not stopped:
                    engine.submit("stop")
                    adapter.release.set()
                    stopped = True
                try:
                    event = engine.events.get(timeout=.05)
                except queue.Empty:
                    event = None
                if event:
                    entry["events"].append(event)
                    if event["kind"] == "plan":
                        interpretation = {"origin": event.get("origin"), "steps": event["steps"], "request_id": event["request_id"]}
                        entry["interpretations"].append(interpretation)
                        actual = [step["intent_id"] for step in event["steps"]]
                        if actual != entry["expected_intents"]:
                            engine.stop()
                            raise RuntimeError("Intentions reconnues différentes des intentions attendues")
                        if label == "dossier principal" and interpretation["origin"] != "LOCAL_SIMILARITY":
                            raise RuntimeError("Le parcours n'a pas exercé la similarité locale")
                        if label == "parent via Ollama" and interpretation["origin"] != "LOCAL_MODEL":
                            raise RuntimeError("Le parcours n'a pas exercé le repli Ollama")
                    if event["kind"] in {"error", "fatal"}:
                        raise RuntimeError(event["message"])
                    if event["kind"] == "question":
                        if not choice or choice == "STOP" or len(event["candidates"]) != 2:
                            raise RuntimeError("Question inattendue ; aucune réponse arbitraire.")
                        matches = [c for c in event["candidates"] if c["name"] == choice]
                        if len(matches) != 1:
                            raise RuntimeError("Candidat d'essai attendu absent.")
                        asked = True
                        engine.submit(str(matches[0]["number"]), event["dialogue_id"])
                    if event["kind"] == "result" and event["result"]["status"] != "SUCCEEDED":
                        entry["status"] = event["result"]["status"]
                        raise RuntimeError(event["message"])
                    if event["kind"] == "done":
                        break
                if stopped and engine.jobs.unfinished_tasks == 0 and engine.events.empty():
                    break
            results = [e["result"]["observed_result"] for e in entry["events"] if e["kind"] == "result"]
            if choice == "STOP":
                if not stopped or adapter.open_calls != before or len(results) != 2:
                    raise RuntimeError("Stop n'a pas empêché l'ouverture attendue.")
                entry["observed"] = {"stop_accepted": True, "open_calls_after_stop": adapter.open_calls - before, "completed_read_steps": len(results)}
            elif not results or (expected_path and not any(Path(t["path"]).resolve() == expected_path.resolve() for t in results[-1]["targets"])):
                raise RuntimeError("Le résultat observé ne correspond pas à la cible attendue.")
            elif choice and not asked:
                raise RuntimeError("L'ambiguïté attendue n'a pas été présentée.")
            if label == "filtre PDF" and {Path(t["path"]).name for t in results[-1]["targets"]} != {"rapport ancien.pdf", "rapport recent.pdf"}:
                raise RuntimeError("Le filtre PDF ne contient pas exactement les deux fixtures.")
            entry["status"] = "PASSED"
            entry["finished_at"] = time.time()
            evidence(entry)
            save_report(output, report)
        report["status"] = "PASSED"
    except Exception:
        report["status"] = "FAILED"
        report["traceback"] = traceback.format_exc()
        if report["steps"] and report["steps"][-1]["status"] == "RUNNING":
            report["steps"][-1]["status"] = "FAILED"
        if report["steps"]:
            report["steps"][-1]["finished_at"] = time.time()
            evidence(report["steps"][-1])
        for label, command, _, _ in scenarios[len(report["steps"]):]:
            report["steps"].append({"name": label, "command": command, "status": "SKIPPED"})
    finally:
        if engine:
            if "adapter" in holder:
                holder["adapter"].release.set()
            engine.close()
        if (root / "journey-history.sqlite").is_file():
            from .diagnostics import journal_snapshot
            try:
                report["recent_journal"] = journal_snapshot(root / "journey-history.sqlite")
            except Exception:
                report["journal_error"] = traceback.format_exc()
        report["finished_at"] = time.time()
        report["evidence_status"] = "NOT_REQUESTED" if capture is None else (
            "COMPLETE" if all(s.get("screenshot", {}).get("status") == "SAVED" for s in report["steps"] if s["status"] != "SKIPPED") else "PARTIAL")
        save_report(output, report)
        write_artifacts(output, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    parser.add_argument("--output", type=Path, default=data_dir() / "journey.json")
    parser.add_argument("--screenshots", action="store_true", help="Captures des fenêtres d'essai après étapes et échecs")
    parser.add_argument("--with-ollama", action="store_true", help="Exercer aussi un vrai repli local, sans téléchargement")
    args = parser.parse_args()
    output = args.output.resolve()
    local = None
    single = socket.socket()
    try:
        if os.name != "nt":
            raise RuntimeError("Windows interactif requis ; aucun test Windows effectué.")
        try:
            single.bind(("127.0.0.1", 11436))
        except OSError as exc:
            raise RuntimeError("Ferme Clara et les autres parcours avant de lancer ce test.") from exc
        config = load(args.config)
        planner = Planner(config)
        if args.with_ollama:
            from .local_model import LocalModel
            local = LocalModel(config, data_dir())
            ready, message = local.start(callback=lambda message: print(message, flush=True))
            if not ready:
                raise RuntimeError(message)
            planner = Planner(config, True)
        capture = None
        if args.screenshots:
            from .test_evidence import WindowCapture
            capture = WindowCapture()
        root = data_dir() / "autotest-fixtures" / uuid4().hex
        root.parent.mkdir(parents=True, exist_ok=True)
        create_journey_fixture(root)
        os.startfile(str(root), "open")
        from .windows import WindowsAdapter
        report = run_journey(config, root, output, WindowsAdapter, capture=capture,
                             planner=planner, with_ollama=args.with_ollama)
    except Exception:
        report = {"version": VERSION, "run_id": uuid4().hex, "status": "INCOMPLETE", "steps": [],
                  "traceback": traceback.format_exc(), "backend": "windows" if os.name == "nt" else "not_tested"}
        save_report(output, report)
        write_artifacts(output, report)
    finally:
        if local:
            local.close()
        single.close()
    print("Parcours sans voix : " + report["status"], flush=True)
    print("Rapport : " + str(output) + " ; archive : " + str(output.with_suffix('.zip')), flush=True)
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
