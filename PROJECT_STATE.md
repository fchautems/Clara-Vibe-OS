# Clara Vibe OS — état du projet

Mise à jour : 2026-10-08

## État vérifié
- 2026-10-08 : revue critique des specs fonctionnelle V1.1 et technique V1 terminée ; rapport `Clara_Vibe_OS_Revue_critique_specs_V1.md` livré. Neuf points à préciser, dont quatre contrats du noyau. L’architecture est conservable ; les recommandations ne sont pas encore intégrées aux specs.
- 2026-10-08 : spécification technique V1 rédigée et livrée dans `Clara_Vibe_OS_Specification_technique_V1.docx` (17 pages, 25 sections). Statut : proposition à relire, sans implémentation ni performance mesurée.
- Le document technique n’est pas encore ajouté au dépôt ; la référence fonctionnelle V1.1 reste inchangée.
- Spécification fonctionnelle consolidée en V1.1.
- Périmètre V1 centré sur l’Explorateur Windows, avec architecture fonctionnelle extensible vers Firefox, ChatGPT, Notepad++ et Fork.
- Exigences non fonctionnelles et critères d’acceptation ajoutés.

## Changements
- 2026-10-08 : architecture Python locale, processus et contrats, sessions, pipeline vocal, contexte, cache validé, Explorateur, recherche, confirmations, stop, historique/undo et reprise détaillés dans la proposition technique.
- Matrice de couverture de toutes les sections V1.1 et liste des composants à valider ajoutées au document technique.
- Spécification fonctionnelle V1.1 ajoutée au dépôt sous `docs/Clara_Specifications_fonctionnelles_V1.1.md` (commit `493c66a`).
- Activation configurable (« Bonjour Clara » / « Salut Clara » comme valeurs initiales), session temporaire et commande de fin configurable.
- Démarrage automatique en arrière-plan ; mécanisme exact à décider en conception technique.
- Retour sonore « ding » après prise en compte d’un énoncé ; erreur = message vocal bref + notification visuelle.
- Cible de réactivité 1–2 s, limite haute 5 s pour commande simple.
- Robustesse : erreur sans plantage, reprise propre après crash/redémarrage, aucune reprise automatique des commandes inachevées.
- Consommation faible en veille, fonctionnement V1 local sans API externe.
- Critères d’acceptation mains libres et procédure de mise à jour manuelle via Git/GitHub/Fork.

## Contrôles
- 2026-10-08 : versions actuelles des deux documents relues ; cohérence, transitions, interruption, concurrence, journalisation, undo et critères d’acceptation examinés. Sources primaires vérifiées pour SQLite, Ollama, Vosk, Faster-Whisper et Windows. Aucun test Clara ni benchmark Windows exécuté dans cette revue.
- 2026-10-08 : document technique rendu en 17 pages et contrôlé visuellement ; exemple JSON analysé avec succès. Ces contrôles concernent le document, pas le fonctionnement de Clara.
- Documentation primaire consultée pour les capacités annoncées de Vosk, Faster-Whisper, Piper, Ollama, UI Automation et SQLite.
- Présence et lecture du fichier Markdown vérifiées sur la branche `main` après commit.
- DOCX rendu en 12 pages et vérifié visuellement.
- Mise en page corrigée sur l’exemple multi-étapes ; aucun chevauchement ou texte coupé observé.

## Blocages
- Contrats à compléter avant implémentation du noyau : admission des actions face à stop, nouvelle demande pendant une séquence, commit acquitté avant modification et déduplication, schémas typés et transitions. Le mode local d’Ollama doit être imposé avant activation du modèle.
- Inactivité avec tâches longues, portée d’undo, réessai après correction, critères mesurables et chemin UAC restent à préciser. Les propositions du rapport ne sont pas des exigences nouvelles validées.
- Proposition technique à relire avant implémentation ; moteurs, modèles, compatibilité GPU, écho audio, onglets Explorateur et ressources restent à valider.
- Arbitrage fonctionnel nécessaire sur la latence : 2–3 secondes de silence ne permettent pas 1–2 secondes depuis le dernier mot. Aucune définition de délai n’a été modifiée implicitement.

## Prochaine action
- Préparer une technique V1.1 à partir de la revue, arbitrer les choix produit (latence, périmètre d’undo et critères d’acceptation), puis versionner les documents. Valider ensuite l’Explorateur, l’audio et l’inférence locale par prototypes Windows avant le premier parcours vertical.
