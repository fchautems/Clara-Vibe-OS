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
- 2026-10-09 : branche parallèle `feature/voice-comfort`, issue du main `cab89914` et non fusionnée. Commandes locales « répète » (dernière réponse ou question avec choix prioritaires) et « où suis-je ? » (lecture fraîche du contexte par le travailleur Windows). Aucune action native ni Ollama ; séquence/clarification conservées, veille respectée, tokens périmés refusés, réponses de localisation tardives invalidées par stop/session/dialogue. Réponse de session effacée en veille. Panneau, voix et télémétrie intégrés.
- 2026-10-09 : parcours automatique Windows de 14 étapes, au premier lancement uniquement, dans un nouveau dossier généré. Commandes traitées par Engine/Planner, contexte et navigation observés, TXT/PDF ouverts, recherche/filtre/plus récent, clarification numérique et stop injecté avant engagement. Garde limitée aux chemins et fenêtre du parcours ; aucune cible personnelle ouverte. Bilan progressif `journey.json` et journal inclus dans le ZIP ; processus limité à 180 s, échecs/UNKNOWN/SKIPPED conservés. Relancement explicite par `test-clara.cmd`, pas de répétition implicite après échec.
- 2026-10-09 : aide vocale/visuelle locale et catalogue de six capacités connues indisponibles (lancement d'applications déclarées, copie, déplacement/couper-coller, renommage, suppression, undo). Reconnaissance avant Ollama, distinction des fichiers explicitement nommés, rejet intégral des séquences reconnues contenant une opération indisponible. Aide sans résolution Windows, utilisable pendant une séquence ou clarification sans les modifier ; phrase de fin conforme à la configuration. Demandes indisponibles enregistrées avec texte et intention.
- 2026-10-09 : lancement unique supervisé en Python standard et ZIP automatique `diagnostic-clara.zip` : installation/préparation/application journalisées, export périodique toutes les 30 s et final, versions de l'environnement installé, empreintes sources, configuration, fichiers modèles, historique SQLite en lecture seule et dernières traces. Sondes natives isolées et bornées (imports, microphone sans enregistrement, SAPI, Explorateur sans activation). Exceptions d'exécution/audio/STT conservées avec traceback ; aucun envoi automatique.
- 2026-10-09 : ajout autorisé d'un catalogue statique français préchargé (56 gabarits, 184 variantes avant politesse), fichier JSON versionné et paramètres extraits par demande. Reconnaissance avant Ollama, sans apprentissage ni cache de cibles ; résolution et contrôles existants conservés. Le lancement d'applications reste non exécuté ; son indisponibilité est maintenant reconnue par le catalogue de capacités.
- Processus audio Vosk léger, processus STT Faster-Whisper CPU INT8 et processus de voix française SAPI ; coordinateur et travailleur Windows distincts de la boucle PySide6.
- Commandes déterministes et modèle Ollama local candidat `qwen2.5:3b` ; propositions validées contre le schéma et leurs dépendances. Ollama absent produit un mode dégradé explicite avec commandes simples disponibles.
- Instance Ollama dédiée sur boucle locale, cloud désactivé avant lancement ; pas de modification des paramètres du serveur partagé.
- Résolution de fichiers réobservés, choix numéroté si ambiguïté, égalités de dates et ensembles périmés traités explicitement. Retour vocal à l'Explorateur après ouverture.
- Stop/admission ordonnés sous verrou court ; revalidation après commit et avant appel natif ; réponse incompatible suspendue avant question. Résultats tardifs enregistrés, aucune poursuite après stop.
- Journal SQLite WAL/FULL, clés de déduplication, résultats inconnus au redémarrage sans rejeu. Mesures locales de parole, acquisition, STT, début/résultat d'action, stop, RAM et CPU.
- Configurable sans changement de code ; petit panneau sans prise de focus nominale ; fixtures indépendantes des fichiers personnels. Voix SAPI choisie pour le prototype à la place du candidat Piper.
- Les neuf constats de la revue sont intégrés dans la conception technique V1.1 et suivis en section 24.3 ; leur validation native reste distincte des tests simulés.

## Contrôles
- 2026-10-09 : 97 tests locaux réussis sur `feature/voice-comfort`, dont 12 nouveaux tests : variantes/politesse, répétition sans accès Windows/modèle ni rejeu, choix numérotés conservés après aide, nouvelle session, tokens périmés, contexte actualisé/indisponible, maintien de clarification/action et résultat tardif après stop. Compilation et diff vérifiés. Voix et contexte Windows réels non testés ici.
- 2026-10-09 : 85 tests locaux réussis, dont 11 contrôles du parcours : 14 étapes avec Windows simulé, reactivation après document, absence d'ouverture après stop, cibles hors fixtures/fenêtre modifiée refusées, non-réutilisation d'un dossier existant, UNKNOWN natif simulé préservé, étapes suivantes SKIPPED, résultat intégré au ZIP, marqueur de non-rejeu et timeout/rapport corrompu marqués INCOMPLETE. Compilation et diff vérifiés ; aucune exécution interactive Windows ou vocale ici.
- 2026-10-09 : 74 tests locaux réussis, dont 13 tests de l'aide et des capacités indisponibles : aucun appel Ollama/Windows pour l'aide, fichiers Firefox distincts du lancement, négations, séquences refusées, journalisation des besoins, aide en veille/pendant traitement/clarification, réponses périmées et phrase de fin configurée. Syntaxe compilée, diff vérifié. Retours vocaux SAPI réels non testés ici.
- 2026-10-09 : 61 tests locaux réussis, dont export de diagnostic avec dépendances absentes, configuration invalide, journaux bornés, base corrompue, lecture seule sans modification/reprise, timeout de sonde, conservation du ZIP précédent, échec d'installation simulé et erreur Windows originale conservée. Contrôle bootstrap Python `-S` sans paquets tiers sur Linux. Compilation syntaxique réussie ; sondes natives et script CMD non exécutés sur Windows ici.
- 2026-10-09 : suite locale de 49 tests réussie, dont 9 nouveaux tests du catalogue : toutes les variantes préchargées, politesse/infinitifs, paramètres indépendants, résultats contextuels actualisés, négations, séquences non reconnues et repli Ollama simulé. Aucun appel au modèle réel ou essai vocal Windows pour cette extension.
- 2026-10-09 : audit de livraison sur `main` à `78df9515` : les 30 fichiers suivis sont présents sur GitHub ; 29 ont le même SHA de blob que les fichiers locaux, la fonctionnelle diffère uniquement par un saut de ligne final local. Aucun code ni document manquant. Répertoire de travail propre avant cet audit.
- Résultats CI revérifiés via GitHub : jobs Linux et Windows terminés avec succès, installation du noyau et tests inclus. Compilation syntaxique locale de `src` et `scripts` réussie. La relance locale des tests n'a pas abouti dans le runtime courant, où `jsonschema` n'est pas installé ; les résultats confirmés sont ceux de la CI, sans nouvel essai interactif Windows.
- 2026-10-09 : 40 tests automatisés réussis sur Linux. Contrats et relations, négations, chemin inventé, résultats observés, contexte/cible modifiés, séquences, choix périmés, stop pendant préparation/commit/modèle et après admission, remplacement/refus, expiration, veille, déduplication/reprise ; segmentation audio simulée, pauses, tampon maximal et capture pendant synthèse.
- Syntaxe compilée et entrée CLI vérifiée. Schéma embarqué identique au document versionné. Deux PDF de fixtures relus : une page et texte attendu chacun.
- Paquets directs disponibles pour Windows x64/Python 3.11 ; dépendances résolues depuis Linux et verrouillées. Wheel Python pur de srt construit ; marqueurs Windows et installation native encore à vérifier sur Windows.
- Modèle Vosk français réel chargé sur Linux ; mots salut/clara/bonjour/bonne/nuit/stop présents dans le vocabulaire. Aucun score de reconnaissance de la voix de Fréd mesuré.
- Prototype et guide commités dans `3c15d7c`. Git vérifié : 25 fichiers modifiés correspondent aux octets locaux ; fonctionnelle, technique, revue et schéma documentaire inchangés.
- Tests CI réussis sur `ubuntu-latest` et `windows-latest`, Python 3.11 : installation du noyau et suite de 40 tests automatisés. Run : https://github.com/fchautems/Clara-Vibe-OS/actions/runs/37906446644 ; cela ne teste ni microphone ni COM/UIA/SAPI interactifs.
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
- Parcours automatique, diagnostic, catalogue, intentions indisponibles et aide prêts pour les essais Windows ultérieurs. Aucun besoin de manipulation Windows aujourd'hui.
- Mettre le dépôt à jour sur le PC Windows et lancer `start-clara.cmd` : préparation puis dossier d'essai ouvert automatiquement.
- Exécuter le parcours vocal README et les contre-exemples du protocole ; garder les résultats inconnus/échecs et mesures de délai complet.
- Corriger les problèmes observés, puis trancher moteurs, réglages de parole et budgets avant d'ajouter les modifications de fichiers.
