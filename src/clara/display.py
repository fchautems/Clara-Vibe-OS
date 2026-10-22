"""Même affichage du chemin pour l'application et son banc sans voix."""


def set_directory(label, path):
    label.setText("Dossier : " + (path or "non observable"))
