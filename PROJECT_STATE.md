# Clara Vibe OS — état du projet

Mise à jour : 2026-10-09

## État vérifié
- Prototype 0.1 implémenté sous `src/clara` : premier parcours vocal local pour l'Explorateur Windows. Code prêt pour essai sur le PC cible ; fonctionnement vocal/COM/UIA et performances réelles encore non validés.
- Périmètre autorisé : activation, session enchaînée, contexte, navigation/parent, recherche locale par nom, filtre, sélection du plus récent, ouverture, choix vocal, stop et retour en veille. Panneau et diagnostic local inclus.
- Lancement : `start-clara.cmd` ; guide `README.md`, périmètre/contrôles `docs/PROTOTYPE_01.md`, essai réel de fixtures `scripts/windows_smoke.py`.
- Dépendances fixées dans `requirements-windows.lock` ; Python 3.11 Windows x64 recommandé. Modèles téléchargés pendant préparation, jamais pendant une commande.
- Référence fonctionnelle V1.1 inchangée : `docs/Clara_Specifications_fonctionnelles_V1.1.md`, depuis `493c66a`.
- Technique V1.1 et JSON Schema : `docs/Clara_Vibe_OS_Specification_technique_V1.1.md`, `docs/contracts_v1.1.schema.json`. V1 archivée et revue conservée sans modification ; versionnement documentaire effectué dans `d8558a2`.
- Le prototype ne réalise pas toute la V1 : modifications de fichiers, undo, tâches longues, recherche globale, apprentissage sémantique, autres applications, UAC et démarrage automatique restent hors de cette tranche.

## Changements
- Processus audio Vosk léger, processus STT Faster-Whisper CPU INT8 et processus de voix française SAPI ; coordinateur et travailleur Windows distincts de la boucle PySide6.
- Commandes déterministes et modèle Ollama local candidat `qwen2.5:3b` ; propositions validées contre le schéma et leurs dépendances. Ollama absent produit un mode dégradé explicite avec commandes simples disponibles.
- Instance Ollama dédiée sur boucle locale, cloud désactivé avant lancement ; pas de modification des paramètres du serveur partagé.
- Résolution de fichiers réobservés, choix numéroté si ambiguïté, égalités de dates et ensembles périmés traités explicitement. Retour vocal à l'Explorateur après ouverture.
- Stop/admission ordonnés sous verrou court ; revalidation après commit et avant appel natif ; réponse incompatible suspendue avant question. Résultats tardifs enregistrés, aucune poursuite après stop.
- Journal SQLite WAL/FULL, clés de déduplication, résultats inconnus au redémarrage sans rejeu. Mesures locales de parole, acquisition, STT, début/résultat d'action, stop, RAM et CPU.
- Configurable sans changement de code ; petit panneau sans prise de focus nominale ; fixtures indépendantes des fichiers personnels. Voix SAPI choisie pour le prototype à la place du candidat Piper.
- Les neuf constats de la revue sont intégrés dans la conception technique V1.1 et suivis en section 24.3 ; leur validation native reste distincte des tests simulés.

## Contrôles
- 2026-10-09 : 40 tests automatisés réussis sur Linux. Contrats et relations, négations, chemin inventé, résultats observés, contexte/cible modifiés, séquences, choix périmés, stop pendant préparation/commit/modèle et après admission, remplacement/refus, expiration, veille, déduplication/reprise ; segmentation audio simulée, pauses, tampon maximal et capture pendant synthèse.
- Syntaxe compilée et entrée CLI vérifiée. Schéma embarqué identique au document versionné. Deux PDF de fixtures relus : une page et texte attendu chacun.
- Paquets directs disponibles pour Windows x64/Python 3.11 ; dépendances résolues depuis Linux et verrouillées. Wheel Python pur de srt construit ; marqueurs Windows et installation native encore à vérifier sur Windows.
- Modèle Vosk français réel chargé sur Linux ; mots salut/clara/bonjour/bonne/nuit/stop présents dans le vocabulaire. Aucun score de reconnaissance de la voix de Fréd mesuré.
- Workflow de tests du noyau prévu pour Linux et Windows ; son état d'exécution distant doit être vérifié séparément après commit.
- Documentation V1.1 rendue et inspectée en 26 pages ; schéma JSON et DDL du journal validés auparavant. Sources primaires des interfaces consultées.
- 2026-10-08 : audit Git historique jusqu'à `bea1074`, aucun écrasement constaté entre conversations. La révision documentaire a ensuite conservé la fonctionnelle et les documents historiques.
- Aucun essai microphone, voix SAPI, modèle d'intention réel ou Explorateur Windows exécuté ici. Aucun benchmark Clara ni preuve réseau/écho/compatibilité GPU.

## Blocages et points ouverts
- Cet environnement est Linux et n'a pas accès à la session Windows de Fréd. Essais interactifs, microphone, SAPI, COM/UIA et benchmarks doivent être exécutés sur son PC.
- Prototype à utiliser d'abord avec casque et une fenêtre Explorateur à un onglet ; onglets multiples refusés, suppression d'écho sur haut-parleurs non implémentée.
- SAPI française et modèles locaux doivent être disponibles pour accepter le parcours vocal complet. Les modes dégradés ne constituent pas cette acceptation.
- Le travailleur Windows est un thread, sans supervision/remplacement de processus pour un appel COM bloqué. Enveloppes IPC complètes et tous les contrats de la V1 restent à intégrer.
- L'ouverture observe une fenêtre au titre correspondant ; elle ne prouve pas le chargement intégral du document. UNKNOWN bloque la suite si l'observation manque.
- Latence : arbitrer le silence initial 2 s face à la cible 1–2 s depuis le dernier mot, après mesure. GPU, noms propres, bruit, pauses, ressources et qualité restent à mesurer.
- Les journaux du prototype n'ont pas de purge automatique. Le corpus complet de 140 cas et les seuils utiles restent un protocole d'acceptation ultérieur.
- Convention d'undo, opérations modificatrices/inverses, recherche globale et UAC restent des validations futures ; aucune exigence fonctionnelle finale n'est réduite.

## Prochaine action
- Mettre le dépôt à jour sur le PC Windows et lancer `start-clara.cmd` : préparation puis dossier d'essai ouvert automatiquement.
- Exécuter le parcours vocal README et les contre-exemples du protocole ; garder les résultats inconnus/échecs et mesures de délai complet.
- Corriger les problèmes observés, puis trancher moteurs, réglages de parole et budgets avant d'ajouter les modifications de fichiers.
