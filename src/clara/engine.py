from __future__ import annotations

import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ClaraError, action_result, observed, revalidate, uid, utc, validate
from .planner import normal
from .resolver import Choices, Resolver
from .storage import Journal


@dataclass
class Ticket:
    text: str
    request_id: str = field(default_factory=uid)
    sequence_id: str = field(default_factory=uid)
    generation: int = 0
    cancelled: bool = False
    paused: bool = False
    admitted: bool = False
    steps: list = field(default_factory=list)
    index: int = 0
    context: dict | None = None
    outputs: dict = field(default_factory=dict)
    choices: dict = field(default_factory=dict)
    wait: dict | None = None
    started_at: float = field(default_factory=time.monotonic)
    last_speech_at: float | None = None
    attempts: dict = field(default_factory=dict)


class Gate:
    """Stop/admission ordonnés sous un verrou court, sans Windows ni disque."""
    def __init__(self):
        self.lock = threading.RLock()
        self.admitted_ids = set()
        self.blocked = False

    def cancel(self, ticket):
        with self.lock:
            ticket.cancelled = True
            ticket.generation += 1
            ticket.paused = False

    def admit(self, ticket, generation, action_id):
        with self.lock:
            if self.blocked or ticket.cancelled or ticket.paused or ticket.generation != generation or action_id in self.admitted_ids:
                return False
            self.admitted_ids.add(action_id)
            ticket.admitted = True
            return True


class Engine:
    def __init__(self, config, planner, adapter_factory, journal_path):
        self.config, self.planner = config, planner
        self.adapter_factory, self.journal_path = adapter_factory, journal_path
        self.gate = Gate()
        self.events = queue.Queue(maxsize=128)
        self.urgent = queue.SimpleQueue()
        self.jobs = queue.Queue(maxsize=64)
        self.session = False
        self.suspended = False
        self.session_id = None
        self.current = None
        self.dialogue = None
        self.last_interaction = time.monotonic()
        self.capturing = False
        self.sets = {}
        self.latest = None
        self.closed = threading.Event()
        self.failed = False
        self.ready = threading.Event()
        self.worker = threading.Thread(target=self._worker, daemon=True, name="clara-coordinator")
        self.worker.start()

    def emit(self, kind, message="", **extra):
        event = {"kind": kind, "message": message, **extra}
        try:
            self.events.put_nowait(event)
        except queue.Full:
            if not self.gate.blocked:
                self.gate.blocked = True
                self.urgent.put({"kind": "fatal", "message": "Panneau saturé ; nouvelles actions bloquées. Résultats conservés dans le journal."})

    def activate(self):
        with self.gate.lock:
            if self.suspended or self.failed:
                return
            if self.session:
                self.last_interaction = time.monotonic()
                return
            self.session = True
            self.session_id = uid()
            self.last_interaction = time.monotonic()
        self.emit("session", "Session active.")

    def stop(self):
        recognized = time.monotonic()
        with self.gate.lock:
            if self.current:
                self.gate.cancel(self.current)
            self.current = None
            self.dialogue = None
            accepted = time.monotonic()
        self.emit("stop", "Séquence interrompue ; une étape déjà engagée peut terminer.",
                  recognized_at=recognized, accepted_at=accepted)

    def sleep(self, reason="Retour en veille."):
        self.stop()
        with self.gate.lock:
            self.session = False
            self.session_id = None
            self.latest = None
            self.sets.clear()
        self.emit("session", reason)

    def dialogue_token(self):
        with self.gate.lock:
            return self.dialogue["id"] if self.dialogue else None

    def submit(self, text: str, dialogue_id=None, last_speech_at=None):
        n = normal(text)
        if n in [normal(p) for p in self.config["wake_phrases"]]:
            self.activate()
            return
        if n == "stop":
            self.stop()
            return
        if n in [normal(p) for p in self.config["sleep_phrases"]]:
            self.sleep()
            return
        with self.gate.lock:
            if not self.session:
                self.emit("ignored", "En veille : prononce la phrase d'activation.")
                return
            self.last_interaction = time.monotonic()
            if self.dialogue:
                if dialogue_id != self.dialogue["id"]:
                    self.emit("error", "Réponse périmée ; réponds à la question actuelle.")
                    return
                self._reply(n)
                return
            if dialogue_id is not None:
                self.emit("error", "Ce dialogue est terminé.")
                return
            if self.current:
                self.current.paused = True
                self._question({"kind": "replace", "ticket": self.current, "new_text": text,
                                "last_speech_at": last_speech_at},
                               "Une demande est en cours. La remplacer ? Réponds oui ou non.")
                return
            ticket = Ticket(text, last_speech_at=last_speech_at)
            self.current = ticket
            self._enqueue(ticket)

    def _enqueue(self, ticket):
        try:
            self.jobs.put_nowait(ticket)
        except queue.Full:
            self.gate.cancel(ticket)
            if self.current is ticket:
                self.current = None
            self.emit("error", "File de travail saturée ; aucune nouvelle action.")

    def _question(self, data, message):
        data.update(id=uid(), expires=time.monotonic() + self.config["clarification_timeout_seconds"])
        self.dialogue = data
        self.emit("question", message, dialogue_id=data["id"],
                  candidates=[{"number": i + 1, "name": Path(r["path"]).name if r["path"] else r["window_id"]}
                              for i, r in enumerate(data.get("targets", []))])

    def _reply(self, text):
        d = self.dialogue
        if time.monotonic() >= d["expires"]:
            self._expire_dialogue()
            return
        t = d["ticket"]
        if d["kind"] == "replace":
            if text == "oui":
                self.gate.cancel(t)
                self.current, self.dialogue = None, None
                self.submit(d["new_text"], last_speech_at=d["last_speech_at"])
            elif text == "non":
                self.dialogue = None
                t.paused = False
                if t.wait:
                    self._question(t.wait, t.wait["message"])
                else:
                    self._enqueue(t)
            else:
                self.emit("question", "Réponds oui ou non.", dialogue_id=d["id"])
            return
        numbers = {"un": 1, "une": 1, "premier": 1, "deux": 2, "deuxieme": 2,
                   "trois": 3, "troisieme": 3, "quatre": 4, "cinq": 5}
        text = text.removeprefix("le ").removeprefix("numero ")
        number = int(text) if text.isdigit() else numbers.get(text)
        if number is None or not 1 <= number <= len(d["targets"]):
            self.emit("question", "Donne le numéro du choix, ou dis stop.", dialogue_id=d["id"])
            return
        t.choices[t.steps[t.index]["step_id"]] = d["targets"][number - 1]
        t.wait = None
        self.dialogue = None
        self._enqueue(t)

    def _expire_dialogue(self):
        d = self.dialogue
        self.dialogue = None
        if d["kind"] == "replace":
            # Old sequence stays paused; new request is abandoned, no surprise resume.
            self.emit("error", "Réponse expirée ; ancienne séquence suspendue. Dis stop puis reformule.")
        else:
            self.gate.cancel(d["ticket"])
            if self.current is d["ticket"]:
                self.current = None
            self.emit("error", "Choix expiré ; aucune ouverture.")

    def tick(self):
        with self.gate.lock:
            if self.dialogue and time.monotonic() >= self.dialogue["expires"]:
                self._expire_dialogue()
            protected = self.capturing or self.dialogue or (self.current and self.current.admitted)
            if self.session and not protected and time.monotonic() - self.last_interaction >= self.config["session_idle_seconds"]:
                self.sleep("Session expirée ; retour en veille.")

    def _worker(self):
        adapter, journal = None, None
        try:
            adapter = self.adapter_factory()
            journal = Journal(self.journal_path)
            self.ready.set()
            while not self.closed.is_set():
                try:
                    ticket = self.jobs.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    self._run(ticket, adapter, journal)
                except Choices as choices:
                    with self.gate.lock:
                        if not ticket.cancelled:
                            ticket.wait = {"kind": "choose", "ticket": ticket, "targets": choices.targets,
                                           "message": choices.question}
                            if not ticket.paused:
                                self._question(ticket.wait, choices.question)
                except Exception as exc:
                    err = exc if isinstance(exc, ClaraError) else ClaraError("INTERNAL_ERROR", "Erreur du composant ; aucune étape suivante.", "EXECUTION")
                    details = traceback.format_exc()
                    journal.event("request_error", {"request_id": ticket.request_id, "code": err.code, "message": str(err), "traceback": details})
                    self.emit("error", str(err), request_id=ticket.request_id, code=err.code, traceback=details)
                    with self.gate.lock:
                        self.gate.cancel(ticket)
                        if self.current is ticket:
                            self.current = None
                            self.dialogue = None
                finally:
                    self.jobs.task_done()
        except Exception as exc:
            self.failed = True
            self.session = False
            self.emit("fatal", str(exc), traceback=traceback.format_exc())
            self.ready.set()
        finally:
            if journal:
                journal.close()
            if adapter:
                adapter.close()

    def _run(self, t, adapter, journal):
        if t.cancelled or t.paused:
            return
        if not t.steps:
            context_error = None
            try:
                t.context = adapter.context()
            except ClaraError as exc:
                context_error = exc
                t.context = {"context_id": uid(), "application": None, "capabilities": [], "window": None,
                             "current_directory": None, "selected_targets": [], "result_sets": [], "observed_at": utc()}
            validate("ContextSnapshot", t.context)
            folder = Path(t.context["current_directory"]["path"]) if t.context["current_directory"] else None
            if self.latest and (self.latest not in self.sets or Path(self.sets[self.latest]["scope"]) != folder):
                self.latest = None
                self.sets.clear()
            steps, origin = self.planner.interpret(t.text, t.context, self.latest)
            if context_error and any(s["intent_id"] not in {"window.list", "window.activate"} for s in steps):
                raise context_error
            if t.cancelled:
                journal.event("late_plan", {"request_id": t.request_id})
                return
            t.steps = steps
            journal.event("interpretation", {"request_id": t.request_id, "text": t.text, "origin": origin, "steps": steps})
            self.emit("plan", t.text, steps=steps, request_id=t.request_id)
        resolver = Resolver(self.config)
        while t.index < len(t.steps):
            if t.cancelled or t.paused:
                return
            step = t.steps[t.index]
            # Revalidation also occurs after a clarification or replacement refusal.
            if step["intent_id"] not in {"window.list", "window.activate"}:
                adapter.ensure_context(t.context)
            observation, refs, native, observer = self._prepare(t, step, adapter, resolver)
            generation = t.generation
            aid = uid()
            action = {"action_id": aid, "request_id": t.request_id, "step_id": step["step_id"],
                      "sequence_id": t.sequence_id, "generation": generation, "intent_id": step["intent_id"],
                      "arguments": step["arguments"], "targets": refs, "context_id": t.context["context_id"],
                      "authorization_id": None, "journal_commit_id": uid(),
                      "attempt_no": t.attempts.get(step["step_id"], 1)}
            if not journal.prepare(action):
                raise ClaraError("DUPLICATE", "Étape déjà enregistrée ; aucun nouvel effet.", "STORAGE")
            if native:
                # Recheck after the last disk wait, before admission and native call.
                if step["intent_id"] != "window.activate":
                    adapter.ensure_context(t.context)
                for ref in refs:
                    if ref["kind"] != "window":
                        revalidate(ref)
            # No I/O between the gate and native call. Observations follow the call.
            if not self.gate.admit(t, generation, aid):
                journal.finish(action_result(aid, status="CANCELLED"))
                if t.paused:
                    t.attempts[step["step_id"]] = action["attempt_no"] + 1
                return
            call_at = time.monotonic()
            exception_trace = None
            try:
                if native:
                    native()
                if observer:
                    observation = observer()
                result = action_result(aid, observation)
            except Exception as exc:
                exception_trace = traceback.format_exc()
                error = exc if isinstance(exc, ClaraError) else ClaraError("WINDOWS_FAILED", "L'appel Windows a échoué ; résultat incertain.", "EXECUTION")
                result = action_result(aid, error=error, status="UNKNOWN" if native else "FAILED")
            finally:
                with self.gate.lock:
                    t.admitted = False
            journal.finish(result)
            if exception_trace:
                journal.event("native_error", {"action_id": aid, "request_id": t.request_id, "traceback": exception_trace})
            journal.event("timing", {"request_id": t.request_id, "step_id": step["step_id"],
                          "acquired_at": t.started_at, "last_speech_at": t.last_speech_at,
                          "action_started_at": call_at, "result_at": time.monotonic()})
            self.emit("result", (result["observed_result"] or {}).get("summary", (result["error"] or {}).get("message", "")),
                      result=result, request_id=t.request_id, action_started_at=call_at,
                      last_speech_at=t.last_speech_at)
            if result["status"] != "SUCCEEDED":
                raise ClaraError("STEP_FAILED", "Séquence arrêtée après résultat incertain ou échec.", "EXECUTION")
            t.outputs[step["step_id"]] = observation
            if observation["result_set"]:
                rs = observation["result_set"]
                with self.gate.lock:
                    if not t.cancelled:
                        self.sets[rs["result_set_id"]] = rs
                        self.latest = rs["result_set_id"]
                        while len(self.sets) > 16:
                            self.sets.pop(next(iter(self.sets)))
            t.index += 1
        with self.gate.lock:
            if self.current is t and not t.paused:
                self.current = None
        self.emit("done", "Demande terminée.", request_id=t.request_id)

    def _prepare(self, t, step, adapter, resolver):
        intent, args = step["intent_id"], step["arguments"]
        folder = Path(t.context["current_directory"]["path"]) if t.context["current_directory"] else Path.home()
        choice = t.choices.get(step["step_id"])
        if intent in {"files.filter", "files.search"}:
            if intent == "files.search" and args["scope"] != "current_folder":
                raise ClaraError("CAPABILITY_UNAVAILABLE", "Recherche limitée au dossier courant.")
            rs = resolver.listing(folder, args.get("extension"), args.get("query"))
            return observed(rs["targets"], f"{len(rs['targets'])} fichier(s) trouvé(s).", rs), rs["targets"], None, None
        if intent == "files.select_recent":
            rs = t.outputs[args["source_step"]]["result_set"] if "source_step" in args else resolver.get_set(args["result_set_id"], folder, self.sets)
            ref = choice or resolver.recent(rs)
            revalidate(ref)
            return observed([ref], f"Plus récent : {Path(ref['path']).name}"), [ref], None, None
        if intent in {"files.open", "explorer.navigate", "explorer.parent"}:
            if intent == "explorer.parent":
                from .contracts import target
                ref = target(folder.parent)
            else:
                selector = args.get("target") or {"source_step": args["source_step"]}
                ref = choice or resolver.selector(selector, folder, t.outputs, self.sets, intent == "explorer.navigate",
                                                  t.context["selected_targets"])
            path = revalidate(ref)
            if intent == "files.open":
                if ref["kind"] != "file" or path.suffix.lower().lstrip(".") not in self.config["open_extensions"]:
                    raise ClaraError("CAPABILITY_UNAVAILABLE", "Ce type de fichier n'est pas ouvrable dans le prototype.")
                return None, [ref], adapter.prepare_open(t.context, path), lambda: adapter.observe_open(ref)
            def nav_observer():
                fresh, observation = adapter.observe_navigation(t.context, path)
                t.context = fresh
                return observation
            return None, [ref], adapter.prepare_navigation(t.context, path), nav_observer
        if intent == "window.list":
            refs = adapter.windows()
            return observed(refs, f"{len(refs)} fenêtre(s) Explorateur."), refs, None, None
        if intent == "window.activate":
            refs = adapter.windows()
            selector = args["target"]
            matches = [r for r in refs if (selector.get("target_id") == r["target_id"]
                       or normal(selector.get("query", "!")) == "explorateur"
                       or normal(selector.get("query", "!")) in normal(Path(r["path"]).name))]
            if choice:
                ref = choice
            elif not matches:
                raise ClaraError("TARGET_NOT_FOUND", "Fenêtre Explorateur introuvable.")
            elif len(matches) > 1:
                if len(matches) > 5:
                    raise ClaraError("TOO_MANY_CANDIDATES", "Plus de cinq fenêtres ; précise le dossier.")
                raise Choices(matches, "Quelle fenêtre Explorateur ?")
            else:
                ref = matches[0]
            def activation_observer():
                observation = adapter.observe_activate(ref)
                t.context = adapter.context()
                return observation
            return None, [ref], adapter.prepare_activate(ref), activation_observer
        raise ClaraError("CAPABILITY_UNAVAILABLE", "Intention indisponible.")

    def close(self):
        self.stop()
        self.closed.set()
        self.worker.join(timeout=2)
