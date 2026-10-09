"""Acquisition explicite des modèles, distincte du chemin d'une commande."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from .config import data_dir, load


def create_fixture(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    # Two small real PDFs, readable by an associated PDF application.
    def pdf(label):
        content = f"BT /F1 18 Tf 72 720 Td ({label}) Tj ET".encode("ascii")
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
                   b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
                   b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        data = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = len(data)
        data.extend(b"xref\n0 6\n0000000000 65535 f \n")
        for offset in offsets[1:]:
            data.extend(f"{offset:010d} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return data
    for name, stamp in [("rapport ancien.pdf", 1700000000), ("rapport recent.pdf", 1700000100)]:
        path = folder / name
        if not path.exists():
            path.write_bytes(pdf("Clara - " + name.replace(".pdf", "")))
            os.utime(path, (stamp, stamp))
    for name in ["notes.txt", "stop.txt"]:
        p = folder / name
        if not p.exists():
            p.write_text("Document d'essai Clara.\n", encoding="utf-8")
    (folder / "sous-dossier").mkdir(exist_ok=True)


def main():
    config = load(data_dir() / "config.json")
    vosk_path = Path(config["vosk_model"])
    if not vosk_path.is_dir():
        vosk_path.parent.mkdir(parents=True, exist_ok=True)
        archive = vosk_path.parent / "vosk.download.zip"
        print("Téléchargement du modèle léger français Vosk…", flush=True)
        urllib.request.urlretrieve("https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip", archive)
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                destination = (vosk_path.parent / entry.filename).resolve()
                if not destination.is_relative_to(vosk_path.parent.resolve()):
                    raise ValueError("Archive modèle invalide")
            z.extractall(vosk_path.parent)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (vosk_path / "clara-download.json").write_text(json.dumps({"source": "alphacephei.com/vosk/models",
                    "model": "vosk-model-small-fr-0.22", "sha256": digest}), encoding="utf-8")
        archive.unlink()
    from vosk import Model, SetLogLevel
    from .audio import validate_phrases
    SetLogLevel(-1)
    validate_phrases(Model(str(vosk_path)), config)
    whisper = Path(config["whisper_model"])
    if not (whisper / "model.bin").exists():
        from huggingface_hub import HfApi, snapshot_download
        repo = "Systran/faster-whisper-small"
        revision = HfApi().model_info(repo).sha
        print("Téléchargement du modèle de transcription français/multilingue…", flush=True)
        snapshot_download(repo, revision=revision, local_dir=str(whisper),
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
        (whisper / "clara-download.json").write_text(json.dumps({"repo": repo, "revision": revision}), encoding="utf-8")
    executable = shutil.which("ollama")
    if executable:
        print("Vérification/acquisition du modèle local Ollama…", flush=True)
        subprocess.run([executable, "pull", config["ollama_model"]], check=True)
    else:
        print("Ollama absent : le chemin déterministe reste utilisable ; formulations libres indisponibles.")
    create_fixture(data_dir() / "fixtures")
    print("Préparation terminée. Les modèles ne seront pas téléchargés pendant les commandes.")


if __name__ == "__main__":
    main()
