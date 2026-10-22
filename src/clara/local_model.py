"""Ollama privé : présence, serveur, modèle et génération vérifiés séparément."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Redirection de l'API locale refusée")


class LocalModel:
    def __init__(self, config, folder: Path):
        self.config, self.folder = config, folder
        self.process = self.log = None
        self.status = {"state": "absent", "executable": False, "server": False, "model": False}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def report(self, state, message, callback=None, **fields):
        self.status.update(state=state, message=message, **fields)
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / "ollama-status.tmp"
        tmp.write_text(json.dumps(self.status, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.folder / "ollama-status.json")
        if callback:
            callback(message)
        return state == "pret", message

    def executable(self):
        candidates = [shutil.which("ollama"), str(self.folder / "ollama/ollama.exe"),
                      str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs/Ollama/ollama.exe")]
        return next((p for p in candidates if p and Path(p).is_file()), None)

    def install(self, callback):
        if os.name != "nt":
            raise RuntimeError("Installation automatique réservée à Windows x64")
        import platform
        if platform.machine().lower() not in {"amd64", "x86_64"}:
            raise RuntimeError("Installation automatique réservée à Windows x64")
        self.report("telechargement", "Ollama absent — téléchargement de la distribution officielle…", callback)
        archive = self.folder / "ollama-download.zip"
        staging = self.folder / "ollama-staging"
        url = "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
        last = [-1]
        def progress(blocks, size, total):
            percent = int(blocks * size * 100 / total) if total > 0 else -1
            if percent // 10 > last[0]:
                last[0] = percent // 10
                callback(f"Téléchargement Ollama : {min(percent, 100)} %")
        try:
            urllib.request.urlretrieve(url, archive, progress)
            staging.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as z:
                for entry in z.infolist():
                    if not (staging / entry.filename).resolve().is_relative_to(staging.resolve()):
                        raise ValueError("Archive Ollama invalide")
                z.extractall(staging)
            if not (staging / "ollama.exe").is_file():
                raise ValueError("Exécutable absent de l'archive")
            destination = self.folder / "ollama"
            if destination.exists():
                shutil.rmtree(destination)
            staging.rename(destination)
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging)

    def request(self, endpoint, body=None, timeout=10):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.config['ollama_port']}/api/{endpoint}",
            None if body is None else json.dumps(body).encode(), {"Content-Type": "application/json"})
        return self.opener.open(req, timeout=timeout)

    def has_model(self):
        with self.request("tags") as response:
            tags = json.load(response)
        return self.config["ollama_model"] in {m["name"] for m in tags.get("models", [])}

    def pull(self, callback):
        self.report("telechargement", "Téléchargement du modèle " + self.config["ollama_model"] + "…", callback)
        complete = False
        last = None
        with self.request("pull", {"model": self.config["ollama_model"], "stream": True}, timeout=120) as response:
            for line in response:
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(event["error"])
                state = event.get("status", "")
                complete = state == "success"
                percent = int(event.get("completed", 0) * 100 / event["total"]) if event.get("total") else None
                message = state + (f" {percent} %" if percent is not None else "")
                if message != last:
                    self.report("telechargement", "Modèle : " + message, callback)
                    last = message
        if not complete or not self.has_model():
            raise RuntimeError("Téléchargement incomplet ou modèle absent après acquisition")

    def start(self, prepare=False, callback=None) -> tuple[bool, str]:
        callback = callback or (lambda message: None)
        try:
            name = self.config["ollama_model"]
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+", name) or "cloud" in name.lower():
                raise ValueError("Nom de modèle local invalide (nom:version requis)")
            executable = self.executable()
            if not executable and prepare:
                self.install(callback)
                executable = self.executable()
            if not executable:
                return self.report("absent", "Ollama absent ; commandes locales disponibles.", callback)
            self.status["executable"] = True
            port = self.config["ollama_port"]
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError("Port Ollama dédié occupé ; instance existante non réutilisée") from exc
            self.folder.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update(OLLAMA_HOST=f"127.0.0.1:{port}", OLLAMA_NO_CLOUD="1",
                       OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1")
            self.log = (self.folder / "ollama.log").open("ab")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.process = subprocess.Popen([executable, "serve"], env=env, stdout=self.log,
                                            stderr=self.log, creationflags=flags)
            for _ in range(100):
                if self.process.poll() is not None:
                    raise RuntimeError("L'instance Ollama dédiée s'est arrêtée")
                try:
                    with self.request("version", timeout=.5) as response:
                        version = json.load(response)["version"]
                    self.status.update(server=True, version=version)
                    break
                except Exception:
                    time.sleep(.1)
            if not self.status["server"]:
                raise RuntimeError("Serveur Ollama non joignable")
            if not self.has_model():
                if not prepare:
                    self.close()
                    return self.report("absent", "Modèle Ollama absent ; commandes locales disponibles. Relance start-clara.cmd pour le préparer.", callback)
                self.pull(callback)
            self.status["model"] = True
            # Listing a model does not prove it can load or generate on this PC.
            self.report("verification", "Ollama : vérification d'une génération locale…", callback)
            with self.request("generate", {"model": name, "prompt": "Réponds OK", "stream": False,
                                           "keep_alive": "2m", "options": {"num_predict": 8, "num_ctx": 4096}}, timeout=120) as response:
                result = json.load(response)
            if result.get("done") is not True or not result.get("response", "").strip():
                raise RuntimeError("Le modèle n'a pas produit de réponse de contrôle")
            return self.report("pret", f"Ollama prêt : {name}, génération locale vérifiée.", callback)
        except Exception as exc:
            self.close()
            return self.report("erreur", f"Ollama en erreur : {exc}. Commandes locales disponibles.", callback)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.log:
            self.log.close()
        self.process, self.log = None, None
