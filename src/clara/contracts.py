"""Validation des contrats publiés, puis de leurs relations sémantiques."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads(files("clara").joinpath("resources/contracts_v1.1.schema.json").read_text(encoding="utf-8"))
AVAILABLE = frozenset({"explorer.navigate", "explorer.parent", "files.search",
                       "files.filter", "files.select_recent", "files.open", "window.list",
                       "window.activate"})


def uid() -> str:
    return uuid4().hex


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClaraError(Exception):
    def __init__(self, code: str, message: str, layer: str = "RESOLUTION"):
        super().__init__(message)
        self.code, self.layer = code, layer


def validate(name: str, value: dict) -> None:
    schema = {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise ClaraError("PLAN_INVALID", f"Contrat {name} invalide.", "INTENT")


def validate_plan(proposal: dict) -> list[dict]:
    validate("ModelProposal", proposal)
    if proposal["kind"] != "PLAN":
        raise ClaraError("UNRECOGNIZED", "Reformule la demande.", "INTENT")
    previous = set()
    for step in proposal["steps"]:
        sid, intent = step["step_id"], step["intent_id"]
        if sid in previous or not set(step["depends_on"]) <= previous:
            raise ClaraError("PLAN_INVALID", "Dépendances absentes, cycliques ou répétées.", "INTENT")
        if intent not in AVAILABLE:
            raise ClaraError("CAPABILITY_UNAVAILABLE", "Cette fonction est indisponible dans ce prototype.", "INTENT")
        def check_refs(value):
            if isinstance(value, dict):
                if "source_step" in value and value["source_step"] not in step["depends_on"]:
                    raise ClaraError("PLAN_INVALID", "Référence de résultat sans dépendance.", "INTENT")
                for child in value.values():
                    check_refs(child)
            elif isinstance(value, list):
                for child in value:
                    check_refs(child)
        check_refs(step["arguments"])
        previous.add(sid)
    return proposal["steps"]


def target(path: Path, kind: str | None = None) -> dict:
    stat = path.stat()
    return {"target_id": uid(), "kind": kind or ("directory" if path.is_dir() else "file"),
            "path": str(path), "window_id": None, "tab_id": None,
            "identity_token": f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}",
            "observed_at": utc()}


def revalidate(ref: dict) -> Path:
    path = Path(ref["path"])
    try:
        fresh = target(path, ref["kind"])
    except OSError as exc:
        raise ClaraError("TARGET_NOT_FOUND", "La cible n'existe plus.") from exc
    if fresh["identity_token"] != ref["identity_token"]:
        raise ClaraError("TARGET_CHANGED", "La cible a changé depuis sa sélection.")
    return path


def result_set(refs: list[dict], scope: str, extension=None, query=None,
               complete=True, inaccessible=None, order="name_asc") -> dict:
    return {"result_set_id": uid(), "targets": refs,
            "filters": {"extension": extension, "query": query}, "order": order,
            "scope": scope, "complete": complete, "inaccessible_roots": inaccessible or [],
            "observed_at": utc()}


def observed(refs: list[dict], summary: str, results=None) -> dict:
    return {"targets": refs, "result_set": results, "summary": summary}


def action_result(action_id: str, observation=None, error: ClaraError | None = None,
                  status=None) -> dict:
    value = {"action_id": action_id, "status": status or ("FAILED" if error else "SUCCEEDED"),
             "observed_result": observation,
             "error": None if error is None else {"code": error.code, "layer": error.layer,
                   "message": str(error), "retryable": False},
             "operation_id": None, "undo_record_id": None, "observed_at": utc()}
    validate("ActionResult", value)
    return value
