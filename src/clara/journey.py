"""Parcours Windows automatique dans des fixtures dédiées, sans voix ni Ollama."""
from __future__ import annotations
import argparse
import json
import os
import queue
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


def run_journey(config, root, output, adapter_factory, backend="windows"):
    report = {"version": VERSION, "mode": "commands_without_speech", "backend": backend, "status": "RUNNING",
              "fixture": str(root), "started_at": time.time(), "steps": [],
              "limits": "Voix/Ollama non testés. Ouverture : fenêtre associée, pas contenu du document."}
    save_report(output, report)
    config = dict(config, folder_aliases={"essai": str(root)}, open_extensions=["txt", "pdf"])
    holder, engine = {}, None
    scenarios = [
        ("dossier principal", "ouvre le dossier essai", root, None),
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
    def factory():
        holder["adapter"] = GuardedAdapter(adapter_factory(), root)
        return holder["adapter"]
    try:
        engine = Engine(config, Planner(config), factory, root / "journey-history.sqlite")
        if not engine.ready.wait(12) or engine.failed:
            raise RuntimeError("Coordinateur ou fenêtre d'essai indisponible.")
        engine.submit(config["wake_phrases"][0])
        for label, command, expected_path, choice in scenarios:
            entry = {"name": label, "command": command, "expected_path": str(expected_path) if expected_path else None,
                     "expected": "choix entre deux PDF" if choice and choice != "STOP" else
                                 "deux étapes de lecture puis stop sans ouverture" if choice == "STOP" else "SUCCEEDED",
                     "status": "RUNNING", "started_at": time.time(), "events": []}
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
            save_report(output, report)
        report["status"] = "PASSED"
    except Exception:
        report["status"] = "FAILED"
        report["traceback"] = traceback.format_exc()
        if report["steps"] and report["steps"][-1]["status"] == "RUNNING":
            report["steps"][-1]["status"] = "FAILED"
        if report["steps"]:
            report["steps"][-1]["finished_at"] = time.time()
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
        save_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=data_dir() / "config.json")
    args = parser.parse_args()
    output = data_dir() / "journey.json"
    if os.name != "nt":
        save_report(output, {"version": VERSION, "status": "NOT_TESTED", "detail": "Windows interactif requis."})
        return 1
    root = data_dir() / "autotest-fixtures" / uuid4().hex
    root.parent.mkdir(parents=True, exist_ok=True)
    create_journey_fixture(root)
    os.startfile(str(root), "open")
    from .windows import WindowsAdapter
    report = run_journey(load(args.config), root, output, WindowsAdapter)
    print("Parcours automatique : " + report["status"], flush=True)
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
