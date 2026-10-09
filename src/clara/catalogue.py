"""Catalogue statique : formulations -> commandes, jamais vers des cibles résolues."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def catalogue():
    data = json.loads(files("clara").joinpath("resources/formulations_fr.json").read_text(encoding="utf-8"))
    if data["version"] != 1:
        raise ValueError("Version du catalogue statique inconnue.")
    entries = []
    for entry in data["entries"]:
        for template in entry["phrases"]:
            tokens = re.findall(r"\{(\w+)\}", template)
            if len(tokens) != len(set(tokens)) or set(tokens) - {"query", "extension"}:
                raise ValueError("Paramètres du catalogue invalides.")
            if set(re.findall(r"\{(\w+)\}", entry["command"])) != set(tokens):
                raise ValueError("Paramètres de commande incohérents.")
            pattern = re.escape(template)
            for token in tokens:
                expression = ".+" if token == "query" else "|".join(
                    re.escape(k) for k in sorted(data["extensions"], key=len, reverse=True))
                pattern = pattern.replace(re.escape("{" + token + "}"), f"(?P<{token}>{expression})")
            entries.append((re.compile(pattern), entry["command"]))
    # Les formulations les plus spécifiques précèdent les cibles libres.
    entries.sort(key=lambda item: len(item[0].pattern.replace("(?P<query>.+)", "")), reverse=True)
    return data, entries


def canonicalize(text: str) -> str:
    """Attend un texte déjà normalisé ; correspondances complètes, sans similarité."""
    data, entries = catalogue()
    cleaned = text.removeprefix("clara, ").removeprefix("clara ")
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
