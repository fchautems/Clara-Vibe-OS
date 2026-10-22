"""Option TypeSafe explicite ; aucune donnée Windows ou clé dans les traces."""
import json
import math
import os
import urllib.request

from .catalogue import catalogue
from .semantic import extract_slots

CRITERIA = {
    "explorer.navigate": "Aller dans un dossier ou un lecteur Windows",
    "explorer.parent": "Remonter au dossier parent du dossier courant",
    "files.search": "Rechercher des fichiers par leur nom dans le dossier courant",
    "files.filter": "Afficher les fichiers du dossier courant d'un format demandé",
    "files.select_recent": "Ouvrir le plus récent des fichiers de la liste actuelle",
    "files.open": "Ouvrir un fichier ou document nommé",
    "window.list": "Lister les fenêtres Explorateur ouvertes",
    "window.activate": "Ramener une fenêtre Explorateur au premier plan",
    "unknown": "Autre demande, action interdite ou information insuffisante"}


def classify(text, config):
    if not config.get("jev_enabled", False):
        return None, {"status": "DISABLED"}
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None, {"status": "UNAVAILABLE", "reason": "TYPESAFE_API_KEY absente"}
    data, _ = catalogue(config.get("catalogue_path"))
    slot = extract_slots(text, data)
    if slot is None:
        return None, {"status": "INCOMPLETE"}
    body = {"model": config["jev_model"], "state": slot["text"], "questions": {
        "intent": {"type": "choice", "instructions": "Quelle action Windows est demandée ?", "criteria": CRITERIA}}}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Redirection Jev refusée")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request("https://api.typesafe.ai/v1/systemone", json.dumps(body).encode(),
                                         {"Content-Type": "application/json", "Authorization": "Bearer " + key})
        with opener.open(request, timeout=config["jev_timeout_seconds"]) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Réponse trop grande")
        answer = json.loads(raw)["answers"]["intent"]
        choice, probabilities, confidence = answer["choice"], answer["probabilities"], answer["confidence"]
        if set(probabilities) != set(CRITERIA) or choice not in CRITERIA:
            raise ValueError("Choix non autorisé")
        values = list(probabilities.values()) + [confidence]
        if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError("Scores invalides")
        if abs(sum(probabilities.values()) - 1) > .01:
            raise ValueError("Distribution invalide")
        competitors = max(v for k, v in probabilities.items() if k != choice)
        if choice == "unknown" or confidence < config["jev_threshold"] or probabilities[choice] - competitors < config["jev_margin"]:
            return None, {"status": "LOW_CONFIDENCE"}
        for entry in data["entries"]:
            kind = next((k for k in ("query", "drive", "extension") if "{" + k + "}" in entry["command"]), "none")
            if entry.get("intent_id") == choice and kind == slot["kind"] and "puis" not in entry["command"]:
                params = {} if kind == "none" else {kind: slot["value"]}
                return entry["command"].format(**params), {"status": "ACCEPTED", "intent": choice, "confidence": confidence}
        return None, {"status": "INCOMPLETE"}
    except Exception as exc:
        return None, {"status": "ERROR", "reason": type(exc).__name__}
