# Clara Vibe OS — état du projet

Mise à jour : 2026-10-08

## État vérifié
- Spécification fonctionnelle consolidée en V1.1.
- Périmètre V1 centré sur l’Explorateur Windows, avec architecture fonctionnelle extensible vers Firefox, ChatGPT, Notepad++ et Fork.
- Exigences non fonctionnelles et critères d’acceptation ajoutés.

## Changements
- Spécification fonctionnelle V1.1 ajoutée au dépôt sous `docs/Clara_Specifications_fonctionnelles_V1.1.md` (commit `493c66a`).
- Activation configurable (« Bonjour Clara » / « Salut Clara » comme valeurs initiales), session temporaire et commande de fin configurable.
- Démarrage automatique en arrière-plan ; mécanisme exact à décider en conception technique.
- Retour sonore « ding » après prise en compte d’un énoncé ; erreur = message vocal bref + notification visuelle.
- Cible de réactivité 1–2 s, limite haute 5 s pour commande simple.
- Robustesse : erreur sans plantage, reprise propre après crash/redémarrage, aucune reprise automatique des commandes inachevées.
- Consommation faible en veille, fonctionnement V1 local sans API externe.
- Critères d’acceptation mains libres et procédure de mise à jour manuelle via Git/GitHub/Fork.

## Contrôles
- Présence et lecture du fichier Markdown vérifiées sur la branche `main` après commit.
- DOCX rendu en 12 pages et vérifié visuellement.
- Mise en page corrigée sur l’exemple multi-étapes ; aucun chevauchement ou texte coupé observé.

## Blocages
- Aucun blocage fonctionnel majeur identifié à ce stade.
- Choix techniques (STT, interprétation, automatisation Windows, architecture de processus/service, cache, historique/undo) encore à définir.

## Prochaine action
- Rédiger la spécification technique à partir de la V1.1 fonctionnelle, en commençant par l’architecture globale et le prototype Explorateur.
