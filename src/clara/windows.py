"""Shell STA et observation UI Automation MTA ; aucun objet COM partagé."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .contracts import ClaraError, observed, target, uid, utc
from .planner import normal


def tab_count(hwnd: int) -> int:
    import sys
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    try:
        sys.coinit_flags = pythoncom.COINIT_MULTITHREADED
        from pywinauto import Desktop
        return len(Desktop(backend="uia").window(handle=hwnd).descendants(control_type="TabItem"))
    finally:
        pythoncom.CoUninitialize()


class WindowsAdapter:
    def __init__(self):
        if os.name != "nt":
            raise ClaraError("WINDOWS_REQUIRED", "Ce mode nécessite une session Windows interactive.", "EXECUTION")
        import pythoncom
        import win32com.client
        import win32gui
        self.com, self.gui = pythoncom, win32gui
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        self.shell = win32com.client.Dispatch("Shell.Application")
        self.probe = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clara-uia-mta")

    def _windows(self):
        result = []
        for window in self.shell.Windows():
            try:
                hwnd = int(window.HWND)
                if self.gui.GetClassName(hwnd) not in {"CabinetWClass", "ExploreWClass"}:
                    continue
                folder = Path(window.Document.Folder.Self.Path)
                if folder.is_absolute() and folder.is_dir():
                    result.append((hwnd, folder, window))
            except Exception:
                continue
        return result

    def context(self):
        foreground = self.gui.GetForegroundWindow()
        matches = [w for w in self._windows() if w[0] == foreground]
        if len(matches) != 1:
            raise ClaraError("CONTEXT_AMBIGUOUS", "Active une fenêtre Explorateur unique avec un seul onglet.")
        hwnd, folder, window = matches[0]
        try:
            count = self.probe.submit(tab_count, hwnd).result(timeout=2)
        except Exception as exc:
            raise ClaraError("CAPABILITY_UNAVAILABLE", "Observation des onglets indisponible ; aucune action lancée.") from exc
        if count > 1:
            raise ClaraError("CONTEXT_AMBIGUOUS", "Plusieurs onglets : utilise une fenêtre Explorateur séparée pour cet essai.")
        selection = []
        try:
            for item in window.Document.SelectedItems():
                p = Path(item.Path)
                if p.exists() and not p.is_symlink():
                    selection.append(target(p))
        except Exception:
            pass
        ref = {"target_id": uid(), "kind": "window", "path": None, "window_id": str(hwnd),
               "tab_id": None, "identity_token": str(hwnd), "observed_at": utc()}
        return {"context_id": uid(), "application": "explorer", "capabilities": ["navigation", "opening"],
                "window": ref, "current_directory": target(folder), "selected_targets": selection,
                "result_sets": [], "observed_at": utc()}

    def ensure_context(self, expected: dict):
        fresh = self.context()
        if (fresh["window"]["window_id"] != expected["window"]["window_id"]
                or fresh["current_directory"]["path"] != expected["current_directory"]["path"]):
            raise ClaraError("WINDOW_CHANGED", "La fenêtre ou le dossier courant a changé.")

    def prepare_navigation(self, context, path: Path):
        self.ensure_context(context)
        matches = [x for x in self._windows() if str(x[0]) == context["window"]["window_id"]]
        if len(matches) != 1:
            raise ClaraError("WINDOW_CHANGED", "Fenêtre Explorateur non identifiable.")
        window = matches[0][2]
        # The returned callable is the native call itself; no lookup after admission.
        return lambda: window.Navigate2(str(path))

    def observe_navigation(self, context, path: Path):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.com.PumpWaitingMessages()
            fresh = self.context()
            if fresh["window"]["window_id"] == context["window"]["window_id"] and Path(fresh["current_directory"]["path"]) == path:
                return fresh, observed([fresh["current_directory"]], f"Dossier courant : {path.name}")
            time.sleep(.05)
        raise ClaraError("OBSERVATION_UNKNOWN", "Navigation envoyée ; résultat non confirmé.", "EXECUTION")

    def prepare_open(self, context, path: Path):
        self.ensure_context(context)
        # ShellExecute with the literal path; never cmd.exe, PowerShell or model code.
        return lambda: os.startfile(str(path), "open")

    def observe_open(self, ref: dict):
        name = normal(Path(ref["path"]).stem)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            hwnd = self.gui.GetForegroundWindow()
            title = normal(self.gui.GetWindowText(hwnd))
            if self.gui.GetClassName(hwnd) not in {"CabinetWClass", "ExploreWClass"} and name and name in title:
                return observed([ref], "Fenêtre associée observée ; chargement du document non garanti.")
            time.sleep(.05)
        raise ClaraError("OBSERVATION_UNKNOWN", "Ouverture transmise à Windows ; fenêtre du document non confirmée.", "EXECUTION")

    def windows(self):
        refs = []
        for hwnd, folder, _ in self._windows():
            if str(hwnd) not in {r["window_id"] for r in refs}:
                refs.append({"target_id": uid(), "kind": "window", "path": str(folder),
                             "window_id": str(hwnd), "tab_id": None,
                             "identity_token": str(hwnd), "observed_at": utc()})
        return refs

    def prepare_activate(self, ref):
        hwnd = int(ref["window_id"])
        if not self.gui.IsWindow(hwnd):
            raise ClaraError("WINDOW_CHANGED", "Cette fenêtre n'existe plus.")
        return lambda: self.gui.SetForegroundWindow(hwnd)

    def observe_activate(self, ref):
        if self.gui.GetForegroundWindow() != int(ref["window_id"]):
            raise ClaraError("OBSERVATION_UNKNOWN", "Activation de fenêtre non confirmée.", "EXECUTION")
        return observed([ref], "Fenêtre Explorateur active.")

    def close(self):
        self.probe.shutdown(wait=False, cancel_futures=True)
        self.shell = None
        self.com.CoUninitialize()
