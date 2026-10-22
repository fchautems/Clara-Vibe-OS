"""Preuves visuelles du parcours : fenêtres autorisées, jamais le bureau entier."""
from __future__ import annotations
import hashlib
import zipfile
from pathlib import Path


class WindowCapture:
    def __init__(self):
        import win32gui
        from PySide6.QtGui import QGuiApplication
        self.gui = win32gui
        self.app = QGuiApplication.instance() or QGuiApplication([])

    def __call__(self, destination, explorer_hwnd, document_stems):
        from .planner import normal
        hwnd = self.gui.GetForegroundWindow()
        title = self.gui.GetWindowText(hwnd)
        is_explorer = self.gui.GetClassName(hwnd) in {"CabinetWClass", "ExploreWClass"}
        allowed = str(hwnd) == str(explorer_hwnd) if is_explorer else any(
            name and name in normal(title) for name in document_stems)
        if not allowed or not self.gui.IsWindowVisible(hwnd) or self.gui.IsIconic(hwnd):
            return {"status": "SKIPPED", "reason": "Fenêtre au premier plan hors du parcours ou non visible."}
        self.app.processEvents()
        screen = self.app.primaryScreen()
        if screen is None:
            raise RuntimeError("Écran interactif indisponible")
        image = screen.grabWindow(hwnd)
        if image.isNull() or not image.save(str(destination), "PNG"):
            raise RuntimeError("Capture de fenêtre indisponible")
        return {"status": "SAVED", "window_id": str(hwnd), "title": title,
                "width": image.width(), "height": image.height(),
                "sha256": hashlib.sha256(Path(destination).read_bytes()).hexdigest()}


def capture_step(report, entry, output, capture, explorer_hwnd, document_stems):
    if capture is None:
        entry['screenshot'] = {'status': 'DISABLED'}
        return
    folder = output.parent / (output.stem + '-captures') / report['run_id']
    try:
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{len(report['steps']):02d}-{entry['status'].lower()}.png"
        evidence = capture(destination, explorer_hwnd, document_stems)
        if evidence.get('status') == 'SAVED':
            if not destination.is_file() or destination.is_symlink():
                raise RuntimeError('Fichier de capture absent ou invalide')
            evidence['path'] = str(destination.relative_to(output.parent))
        entry['screenshot'] = evidence
    except Exception as exc:
        entry['screenshot'] = {'status': 'ERROR', 'reason': str(exc)}


def write_artifacts(output, report):
    """Résumé et ZIP dédiés, rapport JSON complet et PNG de cette exécution."""
    summary = [f"Clara — tests sans voix : {report['status']}",
               f"Backend : {report.get('backend', 'non testé')}",
               f"Captures : {report.get('evidence_status', 'non effectuées')}",
               report.get('limits', ''), '']
    for case in report.get('understanding', []):
        summary.append(f"Compréhension {case['status']} : {case['text']}")
    for step in report.get('steps', []):
        origins = ', '.join(p.get('origin', '?') for p in step.get('interpretations', []))
        summary.append(f"{step['status']} — {step['name']} | {step['command']} | {origins}")
        evidence = step.get('screenshot', {})
        if evidence:
            summary.append(f"  Capture : {evidence.get('path', evidence.get('reason', evidence.get('status')))}")
    if report.get('traceback'):
        summary.extend(['', report['traceback']])
    text_path = output.with_suffix('.txt')
    text_path.write_text('\n'.join(summary) + '\n', encoding='utf-8')
    destination = output.with_suffix('.zip')
    temporary = destination.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(output, output.name)
            archive.write(text_path, text_path.name)
            for step in report.get('steps', []):
                ref = step.get('screenshot', {}).get('path')
                if not ref:
                    continue
                path = output.parent / ref
                allowed = output.parent / (output.stem + '-captures') / report['run_id']
                if path.is_symlink() or not path.resolve().is_relative_to(allowed.resolve()):
                    continue
                archive.write(path, str(path.relative_to(output.parent)))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
