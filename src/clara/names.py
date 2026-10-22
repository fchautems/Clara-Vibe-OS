"""Classement de noms observés ; aucune génération de chemin."""
import re
from difflib import SequenceMatcher
from pathlib import Path

from .planner import normal


def tokens(name):
    parts = re.findall(r"[^\W_]+", normal(name))
    return [p[:-1] if p.endswith("s") and len(p) > 3 and not p.endswith(("ss", "us")) else p for p in parts]


def rank(query, refs, config, directories=False):
    query = normal(query)
    suffix = Path(query).suffix.lower() if not directories else ""
    qbase = Path(query).stem if suffix else query
    qtokens = tokens(qbase)
    ranked = []
    for ref in refs:
        path = Path(ref["path"])
        if suffix and path.suffix.lower() != suffix:
            continue
        name = path.name if directories else path.stem
        ntokens = tokens(name)
        # Chiffres non demandés : conserver comme candidat de clarification,
        # chiffres contradictoires demandés : ne jamais les fusionner.
        qnumbers, nnumbers = re.findall(r"\d+", qbase), re.findall(r"\d+", name)
        if qnumbers and qnumbers != nnumbers:
            continue
        q, n = " ".join(qtokens), " ".join(ntokens)
        score = 1. if q == n else .92 if qtokens and set(qtokens).issubset(ntokens) else SequenceMatcher(None, q, n).ratio()
        if score >= config.get("name_threshold", .84):
            ranked.append((score, ref))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["path"]))
    trace = [{"path": ref["path"], "score": score} for score, ref in ranked[:5]]
    if not ranked:
        return [], trace
    best = ranked[0][0]
    # Inclusive margin: projet vs projets-2026 remains a question.
    near = [ref for score, ref in ranked if best - score <= config.get("name_margin", .08) + 1e-9]
    return near, trace
