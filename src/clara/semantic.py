"""Encodeur ONNX CPU hors ligne ; intentions et paramètres restent distincts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .catalogue import catalogue, clean

REPOSITORY = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_FILE = "onnx/model_quint8_avx2.onnx"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Encoder:
    def __init__(self, folder):
        folder = Path(folder)
        manifest = json.loads((folder / "clara-download.json").read_text(encoding="utf-8"))
        if manifest.get("revision") != REVISION or manifest.get("repo") != REPOSITORY:
            raise ValueError("Révision du moteur sémantique non reconnue")
        for name in (MODEL_FILE, "tokenizer.json"):
            if manifest.get("sha256", {}).get(name) != digest(folder / name):
                raise ValueError("Fichier du moteur absent ou altéré : " + name)
        import onnxruntime as ort
        ort.disable_telemetry_events()
        from tokenizers import Tokenizer
        self.identity = manifest
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=0, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(folder / MODEL_FILE), sess_options=options,
                                           providers=["CPUExecutionProvider"])

    def encode(self, texts):
        import numpy as np
        batches = []
        for start in range(0, len(texts), 16):
            tokens = self.tokenizer.encode_batch(texts[start:start + 16])
            feed = {"input_ids": np.asarray([t.ids for t in tokens], dtype=np.int64),
                    "attention_mask": np.asarray([t.attention_mask for t in tokens], dtype=np.int64),
                    "token_type_ids": np.asarray([t.type_ids for t in tokens], dtype=np.int64)}
            output = self.session.run(None, {i.name: feed[i.name] for i in self.session.get_inputs()})[0]
            mask = feed["attention_mask"][..., None]
            pooled = (output * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            batches.append(pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12))
        return np.concatenate(batches).astype("float32")


def extract_slots(text, data):
    """Ne capture que des valeurs textuelles explicites, jamais celles d'un exemple."""
    text = clean(text, data)
    if re.search(r"\b(?:puis|ensuite|et)\b", text):
        return None
    anchors = list(re.finditer(r"\b(dossier|fichier|document)\s+(?:(?:nomme|appele)\s+)?", text))
    match = anchors[-1] if anchors else None
    tail = text[match.end():] if match else ""
    relative = re.search(r"\b(?:parent|recent|dernier|au-dessus|courant|englobant|contenant|qui contient|modifie|en date)\b", text)
    explicitly_named = match and re.search(r"\b(?:nomme|appele)\b", match[0])
    if match and tail and (explicitly_named or not relative):
        query = tail.strip(' "')
        # Une demande de filtre contient une extension, pas un nom libre.
        if query not in data["extensions"]:
            return {"kind": "query", "value": query, "text": text[:match.end()] + "cible", "anchor": match[1]}
    drive = re.search(r"\b([a-z])(?::[\\/]?)?$", text)
    if drive:
        return {"kind": "drive", "value": drive[1], "text": text[:drive.start(1)] + "lecteur"}
    for extension in sorted(data["extensions"], key=len, reverse=True):
        if re.search(r"\b" + re.escape(extension) + r"\b", text):
            return {"kind": "extension", "value": data["extensions"][extension],
                    "text": re.sub(r"\b" + re.escape(extension) + r"\b", "format", text)}
    return {"kind": "none", "value": None, "text": text}


def compatible_intents(text, slot):
    """Contraintes typées : la similarité ne transforme pas un fichier en dossier.

    Les repères explicites sont des contraintes de sens, pas des scores ajoutés.
    Le score minimal reste obligatoire après ces contrôles.
    """
    if slot['kind'] == 'query':
        if slot.get('anchor') == 'dossier':
            if re.search(r'\b(?:cherche|recherche|localise|repere)\b', text):
                return set()  # recherche de dossiers hors périmètre actuel
            return {'explorer.navigate'}
        if re.search(r'\b(?:cherche|recherche|retrouve|trouve|localise|repere|ou est)\b', text):
            return {'files.search'}
        if re.search(r'\b(?:ouvre|ouvrir|consulte|consulter|lis|lire|affiche|afficher|voir|presente|presenter|montre|montrer|apparaitre)\b', text):
            return {'files.open'}
        return {'files.open', 'files.search'}
    if slot['kind'] == 'none':
        if re.search(r'\b(?:explorateur|fenetre)\b', text) and 'premier plan' in text:
            return {'window.activate'}
        if re.search(r'\b(?:recent|recente|dernier|derniere|en date)\b', text):
            return {'files.select_recent'}
        if re.search(r'\b(?:parent|englobant|contenant|contient|superieur|dessus|remonter|remonte|recule|sortir)\b', text):
            return {'explorer.parent'}
        if re.search(r'\b(?:fenetres|explorateurs)\b', text) or (
                re.search(r'\b(?:quels|quelles|combien|chaque|toutes|tous)\b', text) and 'fenetre' in text):
            return {'window.list'}
        if re.search(r"\b(?:explorateur|fenetre)\b", text):
            return {'window.activate'}
    return None


class SemanticMatcher:
    def __init__(self, config, encoder=None):
        self.config = config
        self.encoder = encoder
        self.error = None
        self.key = None
        self.rows = []
        self.vectors = None
        self.utterance_vectors = {}

    def match(self, text):
        import numpy as np
        data, _ = catalogue(self.config.get("catalogue_path"))
        slot = extract_slots(text, data)
        if slot is None:
            return None, {"status": "INCOMPLETE", "reason": "séquence non résolue"}
        if self.encoder is None:
            self.encoder = Encoder(self.config["semantic_model"])
        key = hashlib.sha256(json.dumps({"catalogue": data, "encoder": self.encoder.identity,
                                        "algorithm": 1}, sort_keys=True).encode()).hexdigest()
        if key != self.key:
            rows = []
            for entry in data["entries"]:
                if entry.get("intent_id") not in {"explorer.navigate", "explorer.parent", "files.search", "files.filter",
                                                  "files.select_recent", "files.open", "window.list", "window.activate"}:
                    continue
                if "puis" in entry["command"]:
                    continue
                kind = next((p for p in ("query", "drive", "extension") if "{" + p + "}" in entry["command"]), "none")
                for phrase in entry["phrases"] + [entry["command"]]:
                    rendered = phrase.format(query="cible", drive="lecteur", extension="format")
                    rows.append({"text": rendered, "intent": entry["intent_id"], "command": entry["command"], "kind": kind})
            cache = Path(self.config["semantic_model"]) / ("index-" + key + ".npz")
            try:
                with np.load(cache, allow_pickle=False) as saved:
                    vectors = saved["vectors"]
                if vectors.shape != (len(rows), 384) or not np.isfinite(vectors).all():
                    raise ValueError("Index invalide")
            except (OSError, ValueError, KeyError):
                vectors = self.encoder.encode([r["text"] for r in rows])
                try:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    temporary = cache.with_suffix(".tmp")
                    with temporary.open("wb") as stream:
                        np.savez_compressed(stream, vectors=vectors)
                    temporary.replace(cache)
                except OSError:
                    pass  # Cache optional; inference remains possible on read-only storage.
            self.rows, self.vectors, self.key = rows, vectors, key
        if slot["text"] not in self.utterance_vectors:
            if len(self.utterance_vectors) >= 256:
                self.utterance_vectors.clear()
            self.utterance_vectors[slot["text"]] = self.encoder.encode([slot["text"]])[0]
        scores = self.vectors @ self.utterance_vectors[slot["text"]]
        allowed = compatible_intents(slot['text'], slot)
        grouped = {}
        for row, score in zip(self.rows, scores):
            if row["kind"] != slot["kind"] or (allowed is not None and row['intent'] not in allowed):
                continue
            if row["intent"] not in grouped or score > grouped[row["intent"]][0]:
                grouped[row["intent"]] = (float(score), row)
        ranked = sorted(grouped.values(), key=lambda pair: pair[0], reverse=True)
        trace = {"status": "LOW_CONFIDENCE", "catalogue_index": key,
                 "candidates": [{"intent": row["intent"], "score": score} for score, row in ranked[:4]]}
        if not ranked:
            return None, trace
        margin = ranked[0][0] - ranked[1][0] if len(ranked) > 1 else 1.
        trace["margin"] = margin
        if ranked[0][0] < self.config["semantic_threshold"] or margin < self.config["semantic_margin"]:
            return None, trace
        row = ranked[0][1]
        trace["status"] = "ACCEPTED"
        params = {} if slot["kind"] == "none" else {slot["kind"]: slot["value"]}
        return row["command"].format(**params), trace


def prepare(config, callback=print):
    """Acquisition explicite, révision figée, contrôle par véritable encodage."""
    folder = Path(config["semantic_model"])
    try:
        try:
            encoder = Encoder(folder)
        except Exception:
            callback("Moteur sémantique : téléchargement en cours…")
            from huggingface_hub import snapshot_download
            snapshot_download(REPOSITORY, revision=REVISION, local_dir=str(folder),
                              allow_patterns=[MODEL_FILE, "tokenizer.json"])
            manifest = {"repo": REPOSITORY, "revision": REVISION,
                        "sha256": {name: digest(folder / name) for name in (MODEL_FILE, "tokenizer.json")}}
            (folder / "clara-download.json").write_text(json.dumps(manifest), encoding="utf-8")
            encoder = Encoder(folder)
        SemanticMatcher(config, encoder).match("retour dans l'explorateur")
        callback("Moteur sémantique : prêt (encodage CPU vérifié).")
        return True
    except Exception as exc:
        callback("Moteur sémantique : erreur (" + type(exc).__name__ + ") ; commandes directes conservées.")
        return False
