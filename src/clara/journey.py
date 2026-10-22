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
    for name in ("unique/_projets/sous-dossier", "ambigu/_projets", "ambigu/projets-2026", "Équipe été/Compte-rendus"):
        (root / name).mkdir(parents=True)
    (root / "unique/_projets/sous-dossier/notes.txt").write_text("Texte contrôlé Clara.\n", encoding="utf-8")
    manifest = []
    from .semantic import digest
    for path in sorted(root.rglob("*")):
        manifest.append({"path": str(path.relative_to(root)), "kind": "directory" if path.is_dir() else "file",
                         "mtime_ns": path.stat().st_mtime_ns,
                         "sha256": digest(path) if path.is_file() else None})
    (root / "fixture-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


class GuardedAdapter:
    """Ne cible que la fenêtre initiale et les chemins générés pour ce parcours."""
    def __init__(self, adapter, root, cold_start=False):
        self.adapter, self.root = adapter, root.resolve()
        self.directories = {self.root, self.root / "sous-dossier", self.root / "sous-dossier/niveau-deux"}
        self.files = {self.root / "rapport ancien.pdf", self.root / "rapport recent.pdf",
                      self.root / "sous-dossier/niveau-deux/exemple.txt"}
        self.directories.update(p.resolve() for p in self.root.rglob("*") if p.is_dir() and not p.is_symlink())
        self.files.update(p.resolve() for p in self.root.rglob("*") if p.is_file() and p.suffix in {".txt", ".pdf"} and not p.is_symlink())
        self.pinned = None
        self.stop_armed = False
        self.prepared, self.release = threading.Event(), threading.Event()
        self.open_calls = 0
        self.cold_start = cold_start
        self.initial_windows = []
        if cold_start:
            self.initial_windows = adapter.windows()
            return
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
        if self.pinned is None:
            raise ClaraError("FIXTURE_WINDOW_MISSING", "Fenêtre d'essai pas encore créée.")
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
        if self.cold_start and self.pinned is None:
            if Path(path).resolve() != self.root or context.get("window"):
                raise ClaraError("FIXTURE_ONLY", "Le démarrage doit ouvrir la racine d'essai.")
            return self.adapter.prepare_navigation(context, path)
        self.ensure_context(context)
        return self.adapter.prepare_navigation(context, path)

    def observe_navigation(self, context, path):
        self.check_path(path, self.directories)
        result = self.adapter.observe_navigation(context, path)
        if self.cold_start and self.pinned is None:
            self.pinned = dict(result[0]["window"], path=str(self.root))
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
        return [self.pinned] if self.pinned else []

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


def run_journey(config, root, output, adapter_factory, backend="windows", capture=None, planner=None, with_ollama=False,
                extended=False, cold_start=False, panel=None):
    report = {"version": VERSION, "mode": "commands_without_speech", "backend": backend, "status": "RUNNING",
              "run_id": uuid4().hex, "fixture": str(root), "screenshots_requested": capture is not None, "started_at": time.time(), "steps": [],
              "limits": "Microphone/transcription/voix non testés. Captures = preuves visuelles, pas assertions automatiques. Ouverture : titre de fenêtre, pas contenu du document." + (" Ollama demandé." if with_ollama else " Ollama non testé.")}
    save_report(output, report)
    config = dict(config, folder_aliases={"essai": str(root)}, open_extensions=["txt", "pdf"], jev_enabled=False)
    holder, engine = {}, None
    planner = planner or Planner(config)
    planner.config = dict(planner.config, jev_enabled=False)
    from .semantic import digest
    from importlib.resources import files
    import hashlib
    from .catalogue import catalogue
    report["metadata"] = {"catalogue_sha256": hashlib.sha256(json.dumps(catalogue(config.get('catalogue_path'))[0], sort_keys=True).encode()).hexdigest(),
                          "source_sha256": {p.name: digest(p) for p in Path(__file__).parent.glob("*.py")},
                          "settings": {k: config[k] for k in ("semantic_enabled", "semantic_threshold", "semantic_margin", "name_threshold", "name_margin", "jev_enabled", "ollama_model")},
                          "corpus_manifest": json.loads(files("clara").joinpath("resources/comprehension_manifest.json").read_text()),
                          "semantic_model": planner.semantic.encoder.identity if getattr(getattr(planner, 'semantic', None), 'encoder', None) else "not_loaded"}
    report["cold_start"] = {"requested": cold_start, "no_initial_explorer": "NOT_TESTED"}
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
        report["ollama_natural"] = {"status": "PENDING", "backend": backend, "forced": False}
        if extended:
            local_probe = Planner(dict(config, jev_enabled=False), False, semantic=planner.semantic)
            candidates = ["emmène-moi un étage plus haut", "retrouve le contenant immédiat de cet emplacement",
                          "je veux sortir de ce répertoire pour consulter celui qui l'englobe"]
            rejected = []
            for phrase in candidates:
                try:
                    local_probe.interpret(phrase, {})
                except ClaraError as exc:
                    if exc.code == "CAPABILITY_UNAVAILABLE":
                        rejected.append(phrase)
            report["ollama_natural"]["locally_rejected_candidates"] = rejected
            if rejected:
                scenarios[6] = ("parent via Ollama", rejected[0], root / "sous-dossier", None)
            else:
                scenarios[6] = ("parent imbriqué", "remonte au dossier parent", root / "sous-dossier", None)
                report["ollama_natural"]["status"] = "NOT_EXERCISED"
    expected_intents = [
        ["explorer.navigate"], ["explorer.navigate"], ["explorer.navigate"], ["files.search"],
        ["files.open"], ["window.activate"], ["explorer.parent"], ["explorer.parent"],
        ["files.filter"], ["files.select_recent", "files.open"], ["window.activate"],
        ["files.open"], ["window.activate"], ["files.filter", "files.select_recent", "files.open"]]
    if extended:
        extras = [
            ("réinitialisation", "ouvre le dossier essai", root, None, ["explorer.navigate"]),
            ("cas unique", "ouvre le dossier unique", root / "unique", None, ["explorer.navigate"]),
            ("nom approximatif", "ouvre le dossier projet", root / "unique/_projets", None, ["explorer.navigate"]),
            ("sous-dossier nommé", "ouvre le dossier sous dossier", root / "unique/_projets/sous-dossier", None, ["explorer.navigate"]),
            ("texte des fixtures", "ouvre le fichier note.txt", root / "unique/_projets/sous-dossier/notes.txt", None, ["files.open"]),
            ("retour après notes", "retour à l'explorateur", None, None, ["window.activate"]),
            ("reset après texte", "ouvre le dossier essai", root, None, ["explorer.navigate"]),
            ("cas ambigu", "ouvre le dossier ambigu", root / "ambigu", None, ["explorer.navigate"]),
            ("clarification noms", "ouvre le dossier projet", root / "ambigu/_projets", "_projets", ["explorer.navigate"]),
            ("reset après choix", "ouvre le dossier essai", root, None, ["explorer.navigate"]),
            ("accents", "ouvre le dossier equipe ete", root / "Équipe été", None, ["explorer.navigate"]),
            ("séparateurs et pluriel", "ouvre le dossier compte rendu", root / "Équipe été/Compte-rendus", None, ["explorer.navigate"]),
            ("reset final", "ouvre le dossier essai", root, None, ["explorer.navigate"]),
            ("cible absente", "ouvre le fichier introuvable.txt", None, "ERROR:TARGET_NOT_FOUND", ["files.open"]),
            ("fenêtres après échec prévu", "liste les fenêtres explorateur", None, None, ["window.list"])]
        scenarios += [extra[:4] for extra in extras]
        expected_intents += [extra[4] for extra in extras]
    def evidence(entry):
        guard = holder.get("adapter")
        hwnd = guard.pinned["window_id"] if guard and guard.pinned else None
        stems = ["exemple"] if entry["name"] == "ouverture du texte" else (
            ["rapport recent"] if entry["name"] in {"plus récent contextuel", "ambiguïté et choix"} else
            ["notes"] if entry["name"] == "texte des fixtures" else [])
        capture_step(report, entry, output, capture, hwnd, stems)
        if panel:
            entry["panel_capture"] = panel.capture(output, report["run_id"], len(report["steps"]))

    def factory():
        holder["adapter"] = GuardedAdapter(adapter_factory(), root, cold_start=cold_start)
        report["cold_start"]["no_initial_explorer"] = not bool(holder["adapter"].initial_windows) if cold_start else "NOT_TESTED"
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
        if cold_start:
            scenarios[0] = ("ouverture initiale", f"ouvre le dossier {root}", root, None)
        skip_until_reset = False
        reset_labels = {"réinitialisation", "reset après texte", "reset après choix", "reset final", "fenêtres après échec prévu"}
        for scenario_index, (label, command, expected_path, choice) in enumerate(scenarios):
            if skip_until_reset:
                if label not in reset_labels:
                    report["steps"].append({"name": label, "command": command, "status": "SKIPPED", "reason": "étape dépendante d'un scénario échoué"})
                    continue
                engine.stop()
                # Réactiver uniquement la fenêtre épinglée avant de repartir
                # d'un dossier connu, notamment après une ouverture inconnue.
                recovery = {"before": label, "events": [], "status": "RUNNING"}
                report.setdefault("recoveries", []).append(recovery)
                engine.submit("retour à l'explorateur")
                recovery_id = None
                recovery_deadline = time.monotonic() + 10
                while True:
                    if time.monotonic() > recovery_deadline:
                        raise TimeoutError("Réinitialisation du contexte non observée")
                    try:
                        event = engine.events.get(timeout=.05)
                    except queue.Empty:
                        continue
                    recovery['events'].append(event)
                    if event['kind'] == 'plan':
                        recovery_id = event['request_id']
                    if recovery_id and event.get('request_id') == recovery_id:
                        if event['kind'] in {'error', 'fatal'}:
                            raise RuntimeError(event['message'])
                        if event['kind'] == 'done':
                            recovery['status'] = 'PASSED'
                            break
                skip_until_reset = False
            try:
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
                        if event["kind"] == "directory" and panel:
                            panel.set_directory(event.get("path"))
                        if event["kind"] == "plan":
                            interpretation = {"origin": event.get("origin"), "steps": event["steps"], "request_id": event["request_id"], "trace": event.get("trace", [])}
                            entry["interpretations"].append(interpretation)
                            actual = [step["intent_id"] for step in event["steps"]]
                            if actual != entry["expected_intents"]:
                                engine.stop()
                                raise RuntimeError("Intentions reconnues différentes des intentions attendues")
                            if label == "dossier principal" and interpretation["origin"] not in {"LOCAL_SIMILARITY", "LOCAL_SEMANTIC"}:
                                raise RuntimeError("Le parcours n'a pas exercé la similarité locale")
                            if label == "parent via Ollama" and interpretation["origin"] != "LOCAL_MODEL":
                                raise RuntimeError("Le parcours n'a pas exercé le repli Ollama")
                        if event["kind"] in {"error", "fatal"}:
                            if choice == "ERROR:" + event.get("code", ""):
                                entry["expected_error_observed"] = event["code"]
                                break
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
                if entry.get("expected_error_observed"):
                    entry["observed"] = {"error_code": entry["expected_error_observed"], "success_announced": False}
                elif choice == "STOP":
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
                if label == "parent via Ollama":
                    report["ollama_natural"]["status"] = "PASSED" if backend == "windows" else "SIMULATED"
                if panel:
                    entry["panel_path"] = panel.path
                    if expected_path and expected_path.is_dir() and panel.path != str(expected_path):
                        raise RuntimeError("Le chemin du panneau ne correspond pas au dossier observé.")
                entry["finished_at"] = time.time()
                evidence(entry)
                save_report(output, report)
            except Exception:
                if not extended:
                    raise
                # Un changement de fenêtre ou une cible hors fixtures arrête
                # tout le parcours ; aucune récupération vers une fenêtre tierce.
                if any(e.get("code", "").startswith("FIXTURE_") for e in entry["events"]):
                    raise
                engine.stop()
                if entry["status"] in {"RUNNING", "PASSED"}:
                    entry["status"] = "FAILED"
                entry["traceback"] = traceback.format_exc()
                entry["finished_at"] = time.time()
                evidence(entry)
                save_report(output, report)
                skip_until_reset = True
        report["status"] = "PASSED" if all(s["status"] == "PASSED" for s in report["steps"]) else "FAILED"
        if report['status'] == 'PASSED' and report.get("ollama_natural", {}).get("status") == "NOT_EXERCISED":
            report["status"] = "INCOMPLETE"
        if report['status'] == 'PASSED' and cold_start and not report['cold_start']['no_initial_explorer']:
            report['status'] = 'INCOMPLETE'
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
        encoder = getattr(getattr(planner, 'semantic', None), 'encoder', None)
        report['metadata']['semantic_model'] = encoder.identity if encoder else 'UNAVAILABLE'
        from .diagnostics import versions
        report['metadata']['packages'] = versions()
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
    parser.add_argument("--extended", action="store_true", help="Noms approximatifs, erreurs prévues, corpus et panneau")
    parser.add_argument("--unique-output", action="store_true", help="Conserver un dossier de résultats par exécution")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.unique_output:
        output = output.parent / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]) / output.name
    local = None
    single = socket.socket()
    try:
        if os.name != "nt":
            raise RuntimeError("Windows interactif requis ; aucun test Windows effectué.")
        try:
            single.bind(("127.0.0.1", 11436))
        except OSError as exc:
            raise RuntimeError("Ferme Clara et les autres parcours avant de lancer ce test.") from exc
        config = dict(load(args.config), jev_enabled=False)
        planner = Planner(config)
        if args.with_ollama:
            from .local_model import LocalModel
            local = LocalModel(config, data_dir())
            ready, message = local.start(callback=lambda message: print(message, flush=True))
            if not ready:
                raise RuntimeError(message)
            planner = Planner(config, True)
        capture = None
        panel = None
        if args.extended:
            from .test_evidence import JourneyPanel
            panel = JourneyPanel()
        if args.screenshots:
            from .test_evidence import WindowCapture
            capture = WindowCapture()
        root = data_dir() / "autotest-fixtures" / uuid4().hex
        root.parent.mkdir(parents=True, exist_ok=True)
        create_journey_fixture(root)
        if not args.extended:
            os.startfile(str(root), "open")
        from .windows import WindowsAdapter
        report = run_journey(config, root, output, WindowsAdapter, capture=capture,
                             planner=planner, with_ollama=args.with_ollama,
                             extended=args.extended, cold_start=args.extended, panel=panel)
        if args.extended:
            from .comprehension_test import evaluate
            report["corpus"] = evaluate(config, 'confirmation')
            report["fixture_manifest"] = json.loads((root / "fixture-manifest.json").read_text(encoding="utf-8"))
            if report["corpus"]["status"] != "PASSED" and report["status"] == "PASSED":
                report["status"] = "INCOMPLETE"
            save_report(output, report)
            write_artifacts(output, report)
        report['ollama_readiness'] = local.status if local else {'state': 'NOT_REQUESTED'}
        save_report(output, report)
        write_artifacts(output, report)
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
