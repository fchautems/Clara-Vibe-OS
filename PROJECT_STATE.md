# Clara Vibe OS — état du projet

Mise à jour : 2026-10-09

## État vérifié
- Spécification fonctionnelle V1.1 : `docs/Clara_Specifications_fonctionnelles_V1.1.md`, inchangée depuis le commit `493c66a`.
- Spécification technique V1.1 : `docs/Clara_Vibe_OS_Specification_technique_V1.1.md`. Les neuf constats de la revue sont intégrés et suivis en section 24.3 ; les validations restantes sont explicites.
- Contrats du premier incrément : `docs/contracts_v1.1.schema.json` (JSON Schema draft 2020-12, 20 définitions, 16 intentions). Ils décrivent la conception ; aucun producteur ni adaptateur Clara n'est encore implémenté.
- Technique V1 archivée sous `docs/Clara_Vibe_OS_Specification_technique_V1.md` ; rapport de revue conservé sans modification sous `docs/Clara_Vibe_OS_Revue_critique_specs_V1.md`.
- Version Word V1.1 livrée (26 pages, 26 sections), avec historique de la V1 conservé.
- Périmètre V1 : Explorateur Windows, Python et traitement local ; architecture extensible vers Firefox, ChatGPT, Notepad++ et Fork. Les critères fonctionnels finaux restent ceux de la V1.1.

## Changements
- Admission des actions ordonnée avec stop ; une étape en file n'est pas engagée. Après stop, aucune étape suivante n'est admise ; une étape déjà admise peut finir.
- Demande incompatible : suspension avant question, dialogue unique et réponses liées à leur demande et génération.
- Journal : COMMIT acquitté avant modification, identifiants et clés de déduplication persistants ; après crash, résultat incertain sans rejeu automatique.
- Contrats fermés, variantes de réponse, arguments par intention, résultats observés, transitions et limites initiales documentés.
- Inactivité distincte des tâches longues ; convention d'undo proposée et cible reformulée ; réessai après correction uniquement sur demande explicite.
- Mode local Ollama imposé avant activation ; chemin UAC déclaré et validé par capacité.
- Protocole initial proposé de 140 cas, scénarios d'interruption et de reprise, mesures de délai complet et traçabilité des neuf constats. Les valeurs initiales ne constituent pas des performances mesurées.

## Contrôles
- 2026-10-09 : Word V1.1 rendu et contrôlé visuellement sur ses 26 pages.
- JSON Schema validé, références internes résolues, exemple de plan validé ; cas de rejet vérifiés pour métadonnées du modèle, champs inconnus, génération absente et résultats STARTED/SUCCEEDED sans donnée exigée.
- DDL du journal exécuté sur SQLite en mémoire, clés étrangères activées. Ce contrôle ne prouve pas la durabilité ni l'atomicité d'un effet Windows.
- Sources primaires SQLite WAL, threading UI Automation et mode local Ollama vérifiées pour la révision.
- 2026-10-08 : revue critique terminée ; neuf constats dont quatre contrats du noyau. Technique V1 rendue et vérifiée en 17 pages ; fonctionnelle V1.1 vérifiée en 12 pages.
- 2026-10-08 : audit de l'historique jusqu'à `bea1074`, aucun écrasement observé ; contributions des deux conversations successives sans perte constatée. Avant cette révision, `main` était à `27b2728` et la technique/revue restaient hors dépôt.
- Aucun essai Clara, benchmark vocal ni test d'intégration Windows exécuté. Les contrôles ci-dessus portent sur les documents et leurs contrats.

## Points ouverts
- Latence : arbitrer les 2–3 secondes de silence face à la cible 1–2 secondes depuis le dernier mot ; aucune exigence fonctionnelle n'est modifiée implicitement.
- Valider la convention d'undo en usage ; fixer seuil de réussite utile et budgets CPU/RAM/GPU après premières mesures.
- Choisir et vérifier moteurs/modèles, phrases hors vocabulaire, compatibilité GPU, écho audio et interruption pendant la voix.
- Vérifier observation des onglets Explorateur, recherche globale, opérations modificatrices et inverses, puis UAC avant d'annoncer ces capacités disponibles.
- Contrats formalisés à vérifier dans l'implémentation, notamment courses stop/admission, acquittement perdu, réponses périmées et reprise après effet sans résultat.

## Prochaine action
- Préparer puis exécuter sur le PC Windows un premier prototype vertical : activation, commande vocale, contexte Explorateur, filtrage/ouverture observée, stop et retour en veille.
- Mesurer transcription, compréhension, délai complet, ressources et fonctionnement local ; utiliser ces résultats pour trancher les choix ouverts avant les modifications de fichiers et leurs inverses.

