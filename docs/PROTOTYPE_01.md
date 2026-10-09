# Prototype 01 — périmètre, contrôles et essai Windows

Date : 9 octobre 2026. Autorisation : premier parcours vocal Explorateur, après technique V1.1. État : implémentation initiale prête pour essai local ; fonctionnement vocal réel et compatibilité Explorateur non encore validés.

## Périmètre

Activation configurable, session de commandes sans réactivation à chaque demande, phrase de fin et délai d'inactivité ; transcription française locale ; catalogue limité à navigation, retour parent, filtre par extension, recherche par nom dans le dossier courant, choix du plus récent, ouverture, liste/activation des fenêtres Explorateur et stop. Petit panneau et retours sonores/vocaux, résultats typés et diagnostic local.

Les résultats filtrés sont montrés dans le panneau Clara et restent identifiés entre commandes. La vue native de l'Explorateur n'est pas filtrée. Une séquence de trois étapes conserve ses dépendances ; le choix du plus récent utilise les dates de modification et demande un choix en cas d'égalité. Les demandes incompatibles suspendent la séquence avant la question de remplacement. Non reprend après revalidation ; oui abandonne l'ancienne ; expiration conserve l'ancienne suspendue sans reprise inattendue.

Hors périmètre : opérations modificatrices, undo, tâches longues, index global, encodeur/cache sémantique appris, autres applications, UAC et lancement automatique à l'ouverture de session Windows.

## Réalisation et choix initiaux

| Composant | Réalisation initiale | Validation restante |
| --- | --- | --- |
| Panneau | PySide6, notifications sans prise de focus en mode vocal | Rendu et focus sur Windows |
| Capture/activation | sounddevice, Vosk français, processus dédié | Microphone, bruit, mots de contrôle, noms contenant stop |
| Fin d'énoncé | Seuil RMS configurable, silence initial 2 s, tampon borné | Remplacer/affiner le VAD selon le bruit et les pauses mesurés |
| Transcription | Faster-Whisper small multilingue, CPU INT8, processus distinct | Noms propres, qualité et latence sur le PC |
| Intention | Commandes déterministes, puis Ollama dédié + proposition JSON validée | Corpus français et modèle candidat qwen2.5:3b |
| Exécution | Travailleur unique, Shell COM STA, probe UIA MTA séparé | APIs, fenêtres et onglets de la version Windows cible |
| Voix | SAPI française installée, processus séparé | Disponibilité de voix, interruption, casque et écho |
| Persistance | SQLite WAL/FULL ; préparation et résultat ; événements | Durabilité effective et gestion d'incident disque sur Windows |
| Mesures | JSONL local : parole/acquisition/STT/action/résultat ; RAM et CPU | Benchmarks réels, GPU manuelle, seuils utiles |

La synthèse SAPI remplace le candidat Piper pour cette tranche afin d'utiliser une voix Windows déjà disponible. Le moteur Windows est un travailleur en thread, pas un processus remplaçable ; un appel COM réellement bloqué n'est pas supervisé par remplacement de processus dans cette version. Le contrôle stop conserve son thread indépendant et bloque les admissions futures ; il ne débloque pas rétroactivement un appel natif engagé. Ces limites ne valident pas les exigences finales de robustesse.

Les enveloppes IPC complètes, un catalogue apprenant et tous les événements typés de la spec ne sont pas intégralement implémentés. Les messages audio internes du prototype utilisent un protocole privé borné ; ModelProposal, ContextSnapshot, ActionRequest et ActionResult suivent le JSON Schema V1.1. La génération est propre à une séquence ; une révision de capture invalide les transcriptions encore en attente après stop/fin de session. Les observations tardives d'actions engagées sont conservées.

Un fichier ouvert est confirmé seulement lorsque sa fenêtre associée au titre correspondant est observée. Le contenu et la fin du chargement ne sont pas prouvés. Si cette observation manque, résultat UNKNOWN et aucune étape dépendante. Les onglets multiples bloquent ce premier adaptateur ; la prise en charge complète des onglets reste à réaliser.

## Contrôles exécutés ici

- 40 tests automatisés sur Linux : contrats fermés et relations de dépendance, négations, chemin inventé, résultats observés, filtrage, égalité de date, contexte périmé, cible modifiée, séquences, choix vocal simulé, stop pendant préparation/commit/modèle et après admission, reprise après refus de remplacement, expiration, veille, verrouillage simulé, déduplication et reprise sans rejeu ; segmentation audio simulée, pauses, taille maximale, réveil avec commande et rejet de capture pendant la voix.
- Syntaxe Python compilée ; paquets directs fixés disponibles en wheels pour Windows x64 et Python 3.11. Cette vérification n'est pas une installation Windows complète.
- Résolution des dépendances Windows préparée et versions verrouillées ; `srt` est distribué en source et son wheel Python pur a été construit avec succès. Les marqueurs propres à Windows restent à vérifier lors de l'installation réelle.
- Modèle Vosk français réel chargé sur Linux : salut, clara, bonjour, bonne, nuit et stop sont présents dans son vocabulaire. Cela ne mesure pas la reconnaissance de la voix de l'utilisateur.
- Les deux PDF de fixtures ont été relus par un lecteur PDF Python : une page et texte attendus pour chacun. Schéma embarqué identique à celui des specs.
- Après commit `3c15d7c`, CI réussie sur Linux et Windows avec Python 3.11 : installation du noyau et suite automatisée, https://github.com/fchautems/Clara-Vibe-OS/actions/runs/37906446644. Le runner Windows n'exécute pas le microphone ni les adaptateurs interactifs COM/UIA/SAPI.
- Aucun microphone, voix SAPI, modèle d'intention réel ou Explorateur Windows exécuté dans cet environnement Linux. Aucun score vocal ni chiffre de performance mesuré.

## Essai sur le PC Windows

1. Mettre le dépôt à jour dans Fork/Git, puis lancer `start-clara.cmd`. Une seule préparation des dépendances/modèles est nécessaire. Un dossier d'essai indépendant est ouvert automatiquement ; utiliser un casque.
2. Vérifier les indicateurs microphone et voix. Si un composant manque, son état est explicite ; ne pas considérer le parcours vocal accepté en mode dégradé.
3. Exécuter le parcours README : activation, liste PDF, ouverture du plus récent, retour vocal à l'Explorateur, navigation/parent, ouverture ambiguë et choix numéroté, séquence PDF puis ouverture, stop et fin de session.
4. Ajouter les contre-exemples : « n'ouvre pas notes », « ouvre stop », aucun fichier correspondant, égalité de dates, changement de dossier pendant un choix, réponse après expiration, stop pendant interprétation.
5. Rejouer les scénarios sensibles au moins trois fois ; comparer démarrage froid/session active, PC au repos/en charge. Mesurer depuis le dernier mot et ne pas confondre le ding avec un début d'action.
6. Rejouer avec réseau coupé, puis observer les connexions sortantes lorsque le réseau est disponible. Le simple essai hors ligne ne prouve pas l'absence d'envoi nominal.

`scripts/windows_smoke.py` automatise séparément observation, navigation et ouverture des fixtures, sans microphone. Une erreur ou un résultat inconnu doit être conservé comme tel, pas transformé en réussite. Les rapports sont locaux ; aucune télémétrie distante n'est intégrée.

Le premier essai détermine les corrections nécessaires et les choix de moteurs. L'objectif 1–2 s depuis le dernier mot demeure en conflit avec le silence initial de 2 s ; il reste à arbitrer après mesure, sans changer implicitement la fonctionnelle.

## Sources de mise en œuvre

- Vosk, modèle français et licence : https://alphacephei.com/vosk/models
- Faster-Whisper, CPU INT8 et fichiers locaux : https://github.com/SYSTRAN/faster-whisper
- sounddevice RawInputStream : https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html
- Ollama, génération structurée et paramètres : https://docs.ollama.com/api/generate
- Ollama, configuration locale/cloud : https://docs.ollama.com/faq
- Microsoft ShellWindows : https://learn.microsoft.com/en-us/windows/win32/shell/ishelldispatch-windows
- Microsoft UI Automation threading : https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading

Sources consultées le 9 octobre 2026 ; elles décrivent les interfaces, pas la réussite du prototype sur le PC cible.
