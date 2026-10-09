"""Aide et capacités connues, sans résolution ni action Windows."""
import json
import re
from functools import lru_cache
from importlib.resources import files

from .catalogue import canonicalize


@lru_cache(maxsize=1)
def support_catalogue():
    return json.loads(files("clara").joinpath("resources/capabilities_fr.json").read_text(encoding="utf-8"))


def help_requested(normalized):
    return canonicalize(normalized) in support_catalogue()["help_phrases"]


def comfort_requested(normalized):
    text = canonicalize(normalized)
    for kind, phrases in support_catalogue()["comfort_phrases"].items():
        if text in phrases:
            return kind
    return None


def help_message(config=None):
    text = support_catalogue()["help_message"]
    if config:
        text = text.replace("Dis bonne nuit Clara pour terminer, si tu as conservé cette phrase dans tes réglages.",
                            "Pour terminer, dis : " + config["sleep_phrases"][0] + ".")
    return text


def known_unavailable(normalized):
    text = canonicalize(normalized)
    # Une séquence contenant une opération indisponible est refusée en entier.
    clauses = re.split(r"\s*(?:[,;]\s*)?\b(?:puis|ensuite|et ensuite)\b\s*", text)
    for capability in support_catalogue()["unavailable"]:
        if any(re.fullmatch(pattern, clause) for clause in clauses for pattern in capability["patterns"]):
            return capability["intent_id"]
    return None


def unavailable_message(intent_id):
    for capability in support_catalogue()["unavailable"]:
        if capability["intent_id"] == intent_id:
            return capability["message"]
    return "J'ai compris, mais cette fonction n'est pas encore disponible dans le prototype."
