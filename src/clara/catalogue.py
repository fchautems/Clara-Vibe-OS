"""Catalogue statique : formulations -> commandes, jamais vers des cibles résolues."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
from importlib.resources import files


def catalogue(path=None):
    fingerprint = None
    if path and Path(path).exists():
        info = Path(path).stat()
        fingerprint = (info.st_mtime_ns, info.st_size)
    return _catalogue(path, fingerprint)


@lru_cache(maxsize=8)
def _catalogue(path, fingerprint):
    source = Path(path) if path else files("clara").joinpath("resources/formulations_fr.json")
    if path and not source.exists():
        from .config import data_dir
        if source == data_dir() / "formulations_fr.json":
            source = files("clara").joinpath("resources/formulations_fr.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data["version"] != 1:
        raise ValueError("Version du catalogue statique inconnue.")
    entries = []
    for entry in data["entries"]:
        for template in entry["phrases"]:
            template = clean(template, data)
            tokens = re.findall(r"\{(\w+)\}", template)
            if len(tokens) != len(set(tokens)) or set(tokens) - {"query", "extension", "drive"}:
                raise ValueError("Paramètres du catalogue invalides.")
            if set(re.findall(r"\{(\w+)\}", entry["command"])) != set(tokens):
                raise ValueError("Paramètres de commande incohérents.")
            pattern = re.escape(template)
            for token in tokens:
                expression = ".+" if token == "query" else r"[a-z](?::[\\/]?)?" if token == "drive" else "|".join(
                    re.escape(k) for k in sorted(data["extensions"], key=len, reverse=True))
                pattern = pattern.replace(re.escape("{" + token + "}"), f"(?P<{token}>{expression})")
            entries.append((re.compile(pattern), entry["command"]))
    # Les formulations les plus spécifiques précèdent les cibles libres.
    entries.sort(key=lambda item: len(item[0].pattern.replace("(?P<query>.+)", "")), reverse=True)
    return data, entries


catalogue.cache_clear = _catalogue.cache_clear


def migrate(path):
    """Ajoute le catalogue livré sans remplacer les personnalisations existantes."""
    import copy
    import os
    bundled = json.loads(files("clara").joinpath("resources/formulations_fr.json").read_text(encoding="utf-8"))
    if not path.exists():
        merged = bundled
    else:
        original = path.read_text(encoding="utf-8")
        merged = json.loads(original)
        if merged.get("version") != 1:
            raise ValueError("Version du catalogue utilisateur inconnue")
        if merged.get("bundle_revision", 0) >= bundled.get("bundle_revision", 0):
            return
        backup = path.with_name(path.name + ".before-v3.bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        for entry in bundled["entries"]:
            current = next((e for e in merged["entries"] if e["command"] == entry["command"]), None)
            if current is None:
                merged["entries"].append(copy.deepcopy(entry))
            else:
                current["phrases"] = list(dict.fromkeys(current["phrases"] + entry["phrases"]))
                for key in ("intent_id", "parameters"):
                    current.setdefault(key, entry[key])
        for key in ('prefixes', 'suffixes'):
            merged[key] = list(dict.fromkeys(merged[key] + bundled[key]))
        for key in ('infinitives', 'extensions'):
            for name, value in bundled[key].items():
                merged[key].setdefault(name, value)
        merged["bundle_revision"] = bundled["bundle_revision"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    catalogue.cache_clear()


def clean(text, data):
    """Attend un texte déjà normalisé ; correspondances complètes, sans similarité."""
    cleaned = re.sub(r"^(?:(?:euh|heu|hum|bon|alors)[ ,]+)+", "", text)
    cleaned = cleaned.removeprefix("clara, ").removeprefix("clara ")
    for prefix in data["prefixes"]:
        if cleaned.startswith(prefix + " "):
            cleaned = cleaned[len(prefix) + 1:]
            verb, separator, rest = cleaned.partition(" ")
            if verb in data["infinitives"]:
                cleaned = data["infinitives"][verb] + separator + rest
            break
    for suffix in data["suffixes"]:
        if cleaned.endswith(" " + suffix):
            cleaned = cleaned[:-len(suffix) - 1].rstrip(" ,")
            break
    cleaned = re.sub(r"^(ouvre|affiche|montre|cherche|va) (?:donc|maintenant|ici|pour moi) ", r"\1 ", cleaned)
    return cleaned


def canonicalize(text: str, path=None) -> str:
    data, entries = catalogue(path)
    cleaned = clean(text, data)
    for pattern, command in entries:
        match = pattern.fullmatch(cleaned)
        if not match:
            continue
        parameters = match.groupdict()
        # Une partie de séquence ne doit jamais devenir un nom de cible appris.
        if "query" in parameters and re.search(r"\b(?:puis|ensuite)\b|\bet (?:ouvre|affiche|cherche|va)\b", parameters["query"]):
            continue
        if "extension" in parameters:
            parameters["extension"] = data["extensions"][parameters["extension"]]
        return command.format(**parameters)
    return cleaned


def similar_command(text, config):
    """Compare only action words; parameters are captured literally, never fuzzed.

    Typed anchors are mandatory for free names. No fuzzy untyped 'open X',
    conjunction, negation or multi-action sequence is accepted here.
    """
    data, _ = catalogue(config.get("catalogue_path"))
    text = clean(text, data)
    if not text:
        return None, False
    if re.search(r"\b(pas|jamais|sans|sauf|ne|non|ni|aucun|plus|ou|puis|ensuite|et)\b|\bn'", text):
        return None, False
    candidates = {}
    for entry in data["entries"]:
        for template in entry["phrases"] + [entry["command"]]:
            params = {}
            actual, expected = text, template
            if "{query}" in template:
                # The noun keeps opening, searching and navigation distinct.
                anchor = "dossier" if "dossier {query}" in template else "fichier" if "fichier {query}" in template else "document" if "document {query}" in template else None
                if not anchor or not template.endswith("{query}"):
                    continue
                match = re.fullmatch(r"(.+?\b" + anchor + r") (.+)", text)
                if not match:
                    continue
                actual, params["query"] = match.groups()
                expected = template.split(" {query}")[0]
            elif "{drive}" in template:
                match = re.fullmatch(r"(.+?) ([a-z])(?::[\\/]?)?", text)
                if not match:
                    continue
                actual, params["drive"] = match.groups()
                expected = template.split(" {drive}")[0]
            elif "{" in template:
                continue
            # Do not turn close/delete/move into open on edit distance alone.
            verb = actual.split()[0]
            allowed = {p.split()[0] for p in entry["phrases"] + [entry["command"]]}
            if verb not in allowed and not any(SequenceMatcher(None, verb, v).ratio() >= .85 for v in allowed):
                continue
            score = SequenceMatcher(None, actual, expected).ratio()
            command = entry["command"].format(**params)
            candidates[command] = max(score, candidates.get(command, 0))
    ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] < config.get("similarity_threshold", .86):
        return None, False
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < config.get("similarity_margin", .06):
        return None, True
    return ranked[0][0], False
