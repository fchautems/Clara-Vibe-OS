"""Essai réel explicite sur le dossier de fixtures, sans microphone ni modèle."""
import json
import os
import time
from pathlib import Path

from clara.config import data_dir, load
from clara.contracts import observed, target, validate
from clara.setup import create_fixture
from clara.windows import WindowsAdapter


def main():
    if os.name != "nt":
        raise SystemExit("Cet essai requiert Windows interactif.")
    fixture = data_dir() / "fixtures"
    create_fixture(fixture)
    os.startfile(str(fixture), "open")
    adapter = WindowsAdapter()
    observations = []
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                context = adapter.context()
                if Path(context["current_directory"]["path"]) == fixture:
                    break
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Fenêtre de fixtures non observée ou onglets ambigus.")
            time.sleep(.1)
        validate("ContextSnapshot", context)
        folder = fixture / "sous-dossier"
        adapter.prepare_navigation(context, folder)()
        context, observation = adapter.observe_navigation(context, folder)
        observations.append(observation)
        adapter.prepare_navigation(context, fixture)()
        context, observation = adapter.observe_navigation(context, fixture)
        observations.append(observation)
        ref = target(fixture / "rapport recent.pdf")
        adapter.prepare_open(context, Path(ref["path"]))()
        observations.append(adapter.observe_open(ref))
        print(json.dumps({"status": "OBSERVED", "observations": observations}, ensure_ascii=False, indent=2))
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
