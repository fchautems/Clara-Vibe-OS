from __future__ import annotations

from pathlib import Path

from .contracts import ClaraError, revalidate, result_set, target
from .planner import normal


class Choices(Exception):
    def __init__(self, targets: list[dict], question="Lequel ?"):
        self.targets, self.question = targets, question


class Resolver:
    def __init__(self, config):
        self.config = config

    def listing(self, folder: Path, extension=None, query=None, directories=False) -> dict:
        if not folder.is_dir():
            raise ClaraError("TARGET_NOT_FOUND", "Dossier introuvable.")
        refs, skipped = [], []
        try:
            for p in sorted(folder.iterdir(), key=lambda x: normal(x.name)):
                if p.is_symlink():
                    continue  # No traversal or execution through an unobserved link.
                if directories != p.is_dir():
                    continue
                if extension and p.suffix.lower() != "." + extension.lower():
                    continue
                if query and normal(query) not in normal(p.name):
                    continue
                try:
                    refs.append(target(p))
                except OSError:
                    skipped.append(str(p))
                if len(refs) > self.config["max_results"]:
                    raise ClaraError("TOO_MANY_RESULTS", "Trop de résultats ; précise le nom ou l'extension.")
        except OSError as exc:
            raise ClaraError("ACCESS_DENIED", "Ce dossier n'est pas lisible.") from exc
        results = result_set(refs, str(folder), extension, query, not skipped, skipped)
        return results

    def unique(self, refs: list[dict]) -> dict:
        if not refs:
            raise ClaraError("TARGET_NOT_FOUND", "Aucun résultat dans le dossier courant.")
        if len(refs) > 1:
            if len(refs) > 5:
                raise ClaraError("TOO_MANY_CANDIDATES", "Plus de cinq candidats ; précise le nom.")
            raise Choices(refs)
        revalidate(refs[0])
        return refs[0]

    def selector(self, selector: dict, folder: Path, outputs: dict, sets: dict, directories=False, selected=()) -> dict:
        if "source_step" in selector:
            return self.unique(outputs[selector["source_step"]]["targets"])
        if "result_set_id" in selector:
            return self.unique(self.get_set(selector["result_set_id"], folder, sets)["targets"])
        if "target_id" in selector:
            refs = {r["target_id"]: r for r in list(selected) + [r for s in sets.values() for r in s["targets"]]
                    if r["target_id"] == selector["target_id"]}
            return self.unique(list(refs.values()))
        if "scope" in selector:
            return target(folder)
        if "path" in selector:
            p = Path(selector["path"])
            if not p.is_absolute():
                raise ClaraError("PLAN_INVALID", "Un chemin explicite doit être absolu.")
        else:
            query = selector["query"]
            aliases = {normal(k): v for k, v in self.config["folder_aliases"].items()}
            if directories and normal(query) in aliases:
                p = Path(aliases[normal(query)])
            else:
                refs = self.listing(folder, query=query, directories=directories)["targets"]
                exact = [r for r in refs if normal(Path(r["path"]).name) == normal(query)
                         or normal(Path(r["path"]).stem) == normal(query)]
                return self.unique(exact or refs)
        if p.is_symlink():
            raise ClaraError("CAPABILITY_UNAVAILABLE", "Les liens ne sont pas pris en charge dans ce prototype.")
        if not p.exists() or p.is_dir() != directories:
            raise ClaraError("TARGET_NOT_FOUND", "La cible n'existe pas ou n'a pas le type demandé.")
        return target(p)

    def get_set(self, sid: str, folder: Path, sets: dict) -> dict:
        value = sets.get(sid)
        if not value or Path(value["scope"]) != folder:
            raise ClaraError("CONTEXT_EXPIRED", "La liste de résultats ne correspond plus au dossier courant.")
        if not value["complete"]:
            raise ClaraError("INCOMPLETE_SCOPE", "Recherche incomplète ; impossible de choisir le plus récent.")
        return value

    def recent(self, results: dict) -> dict:
        if not results["complete"]:
            raise ClaraError("INCOMPLETE_SCOPE", "Recherche incomplète.")
        candidates = []
        for ref in results["targets"]:
            p = revalidate(ref)
            candidates.append((p.stat().st_mtime_ns, ref))
        if not candidates:
            raise ClaraError("TARGET_NOT_FOUND", "Aucun fichier dans cet ensemble.")
        newest = max(t for t, _ in candidates)
        return self.unique([r for t, r in candidates if t == newest])
