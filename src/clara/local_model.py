"""Instance Ollama dédiée, locale et cloud désactivé avant son lancement."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


class LocalModel:
    def __init__(self, config, folder: Path):
        self.config, self.folder = config, folder
        self.process = None
        self.log = None

    def start(self) -> tuple[bool, str]:
        executable = shutil.which("ollama")
        if not executable:
            return False, "Ollama absent ; commandes simples disponibles."
        port = self.config["ollama_port"]
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                return False, "Port Ollama dédié occupé ; instance existante non réutilisée."
        name = self.config["ollama_model"]
        if not name or "cloud" in name.lower() or "/" in name or "@" in name:
            return False, "Nom de modèle distant ou invalide refusé."
        self.folder.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(OLLAMA_HOST=f"127.0.0.1:{port}", OLLAMA_NO_CLOUD="1",
                   OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1")
        # Preserve the user's model store; never change the shared server's settings.
        self.log = (self.folder / "ollama.log").open("ab")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen([executable, "serve"], env=env, stdout=self.log,
                                        stderr=self.log, creationflags=flags)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(50):
            if self.process.poll() is not None:
                self.close()
                return False, "L'instance Ollama dédiée n'a pas démarré."
            try:
                with opener.open(f"http://127.0.0.1:{port}/api/tags", timeout=.5) as response:
                    tags = json.load(response)
                if name not in {m["name"] for m in tags.get("models", [])}:
                    self.close()
                    return False, "Modèle local absent ; aucun téléchargement pendant les commandes."
                return True, "Ollama dédié démarré avec cloud désactivé."
            except Exception:
                time.sleep(.1)
        self.close()
        return False, "Ollama dédié n'est pas prêt."

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
