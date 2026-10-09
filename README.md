# Clara Vibe OS — premier prototype

Assistant vocal Python local pour une session Windows interactive. Le premier parcours couvre activation, commandes enchaînées, contexte Explorateur, navigation, recherche dans le dossier courant, filtrage, sélection du plus récent, ouverture, choix vocal et stop. Le noyau est testé avec un adaptateur simulé ; microphone, COM/UIA, voix et performances réelles restent à valider sur le PC Windows.

## Démarrage

Pré-requis : Windows 10/11, Python 3.11 recommandé (3.12/3.13 admis), casque et une voix française Windows SAPI. Ollama installé et accessible dans PATH permet les formulations libres ; s'il manque, les commandes déterministes ci-dessous restent disponibles.

Dans le dossier cloné avec Git/Fork, lancer **`start-clara.cmd`**. Le script crée un environnement isolé, installe les dépendances verrouillées dans `requirements-windows.lock`, prépare les modèles français et ouvre automatiquement le dossier d'essai. Le premier lancement nécessite Internet et de l'espace pour les modèles ; les commandes suivantes utilisent les modèles déjà locaux. L'installation ne configure pas de démarrage automatique de Windows et ne demande pas de droits administrateur.

Le panneau n'accapare pas le focus en mode vocal. Garder la fenêtre Explorateur d'essai active, avec un seul onglet. Les onglets multiples ou une observation indisponible bloquent la résolution ; le prototype ne choisit pas un onglet arbitraire.

## Rapport automatique pour les bugs

Le même lancement `start-clara.cmd` crée **`diagnostic-clara.zip` à la racine du dépôt**, sans étape supplémentaire. Il est actualisé toutes les 30 secondes pendant l'application, puis à la fermeture ou après un échec d'installation/préparation/lancement. En cas de problème, joindre simplement ce ZIP à la conversation ; le lancement et le journal restent aussi consultables dans `%LOCALAPPDATA%\ClaraVibeOS\launcher.log`.

Le rapport regroupe les versions des dépendances dans l'environnement installé, les empreintes du code, la configuration, la présence des fichiers modèles, les sondes de disponibilité, les dernières mesures/transcriptions et l'historique récent avec les erreurs détaillées. Les sondes natives isolées sont limitées à 20 secondes chacune : imports, ouverture brève du microphone sans enregistrement, présence d'une voix française SAPI et observation des fenêtres/onglets Explorateur sans les activer. Un avertissement Explorateur avant l'ouverture du dossier d'essai peut simplement signifier qu'aucune fenêtre n'était encore ouverte.

Le ZIP peut contenir tes transcriptions, noms de fichiers et chemins ; il reste local et n'est jamais envoyé automatiquement. Il n'inclut ni audio, ni contenu des documents, ni variables d'environnement. L'export ne modifie pas l'historique et conserve au plus 100 lignes récentes par table et les derniers 256 Kio de chaque journal. Un diagnostic de disponibilité ne valide pas la qualité vocale, les modèles chargés, ni les performances. Si Python ne peut même pas démarrer ou si le dossier n'est pas accessible en écriture, le rapport ne peut pas être généré.

## Parcours à prononcer

1. « Salut Clara ».
2. « Montre-moi les PDF ».
3. « Ouvre le plus récent ».
4. « Retour à l'Explorateur », puis « Ouvre le dossier documents » (alias configurable) et « Remonte au dossier parent ».
5. Dans les fixtures : « Ouvre rapport » → choix entre deux fichiers → « Un » ou « Deux ».
6. « Montre-moi les PDF, puis ouvre le plus récent » ; essayer « Stop » pendant la préparation.
7. « Bonne nuit Clara » → retour en veille. Sans interaction, la session expire aussi.

Pendant une session, **« aide »**, **« qu'est-ce que tu sais faire ? »** ou **« quelles sont tes commandes ? »** donne une aide affichée et parlée si la voix française est disponible. Cette aide ne nécessite ni Ollama ni fenêtre Explorateur active. Elle garde la séquence ou le choix vocal en cours ; elle ne remplace pas « stop ». La phrase de fin indiquée suit tes réglages.

Les demandes connues mais indisponibles reçoivent une réponse spécifique, sans action : « ouvre Firefox » pour le lancement d'application ; « copie ce fichier », « déplace ce fichier », « renomme », « supprime » et « annule la dernière action ». Une séquence reconnue contenant une opération indisponible après « puis » est refusée en entier. Ces demandes sont conservées dans le diagnostic pour identifier les besoins futurs. Ce catalogue est limité aux formulations et applications déclarées, pas à toutes les demandes possibles.

Pour ouvrir un fichier portant le nom d'une application, préciser **« ouvre le fichier Firefox »** ou **« ouvre Firefox.pdf »** ; « ouvre le dossier Firefox » reste une navigation. Le catalogue et l'aide sont versionnés dans `src/clara/resources/capabilities_fr.json`.

L'ouverture d'un fichier peut mettre son application au premier plan. Pour continuer sans souris, « Retour à l'Explorateur » réactive une fenêtre unique ou demande laquelle si plusieurs sont ouvertes. Le panneau présente les fichiers filtrés ; il ne modifie pas la vue native de l'Explorateur.

Les phrases de réveil/fin, le délai de silence, le microphone, les alias de dossiers et les extensions ouvrables sont dans `%LOCALAPPDATA%\ClaraVibeOS\config.json`. Changer ces réglages puis relancer, sans modifier le code. La configuration invalide n'est pas écrasée ; une phrase dont un mot manque au modèle léger est refusée explicitement.

## Catalogue statique de formulations

Un catalogue préchargé reconnaît 56 gabarits (184 variantes avec les extensions), en plus des règles initiales. Il accepte les accents, « Clara », les demandes comme « peux-tu », « j'aimerais » et « s'il te plaît ». Exemples utilisables sans Ollama :

| Formulation | Commande comprise |
|---|---|
| « Peux-tu afficher les documents PDF ? » | Filtrer les PDF du dossier courant |
| « Remonte d'un niveau » | Aller au dossier parent |
| « Affiche le fichier rapport 2025 » | Ouvrir le fichier correspondant, ou demander lequel |
| « Entre dans le dossier documents » | Naviguer vers ce dossier ou cet alias |
| « Ouvre le dernier fichier » | Ouvrir le plus récemment modifié parmi les résultats précédents |
| « Liste les PDF et ouvre le dernier » | Filtrer puis ouvrir le plus récemment modifié |

La liste est versionnée dans `src/clara/resources/formulations_fr.json` et chargée une fois par processus. Elle contient des formulations et paramètres, jamais les chemins observés, résultats ou fenêtres d'une ancienne commande. Les cibles sont toujours résolues et vérifiées à nouveau ; les ambiguïtés et négations gardent les contrôles existants. Les demandes non reconnues suivent le chemin Ollama habituel s'il est disponible. Ce catalogue n'apprend pas automatiquement et ne reconnaît pas toutes les paraphrases ; il n'ajoute pas le lancement d'applications comme Firefox. Redémarrer Clara après modification du catalogue.

## Limites de ce prototype

- Les fichiers personnels ne sont pas nécessaires pour les essais : fixtures indépendantes et deux PDF valides sont créés automatiquement. Aucune copie, suppression, modification, opération longue ni undo n'est disponible.
- Recherche non récursive, dans le dossier courant ; 128 résultats au maximum, au-delà demander un filtre plus précis. Plus de cinq cibles ambiguës imposent une reformulation. Aucun index global ou classement phonétique appris.
- Une négation est refusée plutôt que simplifiée ; le modèle local ne peut émettre ni commande shell ni code exécutable. Seules les extensions document/image configurées sont ouvrables ; les exécutables et raccourcis ne le sont pas par défaut.
- Après stop, une étape déjà admise peut terminer. Une réponse du modèle ou une transcription périmée ne déclenche pas d'action. Au redémarrage, les actions sans résultat sont marquées inconnues et ne sont jamais rejouées.
- Les fenêtres avec onglets multiples ne sont pas pilotées dans cette tranche. UI Automation sert à détecter l'ambiguïté ; le Shell STA possède ses objets et le probe UIA tourne en MTA.
- La voix initiale utilise **SAPI française locale**, au lieu du candidat Piper, pour utiliser une voix déjà installée. Sans voix française, le mode est signalé comme dégradé et les choix restent visibles. Utiliser un casque : la suppression d'écho sur haut-parleurs n'est pas implémentée. Le microphone continue d'écouter les contrôles pendant les retours vocaux.
- Une fenêtre de document dont le titre correspond au fichier constitue une observation limitée. Le chargement intégral et le contenu du document ne sont pas vérifiés ; sinon l'ouverture est marquée UNKNOWN et la séquence s'arrête.
- La compatibilité de la GTX 1070 Ti n'est pas présumée. Faster-Whisper utilise CPU INT8 dans ce premier essai. Le modèle Ollama initial `qwen2.5:3b` est un candidat, pas un choix validé par benchmark.

## Isolation et mesures

Ollama démarre dans une instance dédiée sur `127.0.0.1:11435`, avec `OLLAMA_NO_CLOUD=1` avant lancement et un modèle local présent. Si ce port est occupé, l'instance existante n'est pas réutilisée : seul le chemin déterministe reste actif. Les paramètres du serveur Ollama partagé de l'utilisateur ne sont pas modifiés.

Le dossier utilisateur contient `history.sqlite`, `measurements.jsonl`, configuration et modèles. Transcriptions, plans, cibles et résultats restent locaux. L'audio brut est transitoire, sans fichier d'enregistrement. Les mesures distinguent dernier échantillon de parole, acquisition, fin STT, début d'action et résultat. Stop distingue reconnaissance et acceptation. RAM du processus et de ses enfants, CPU système et état de session sont échantillonnés toutes les cinq secondes. La GPU n'est pas mesurée automatiquement. Les journaux du prototype n'ont pas encore de purge automatique ; ils se suppriment manuellement une fois les essais archivés.

## Vérification

Tests du noyau, sans voix et sans interaction Windows :

```console
python -m pip install -e .
python -m unittest discover -s tests -v
```

Essai réel explicite COM/UIA sur Windows, dans les fixtures uniquement :

```console
.venv\Scripts\python.exe scripts\windows_smoke.py
```

Diagnostic avec saisie (facultatif, pas le mode vocal nominal) :

```console
start-clara.cmd --text-only
```

Le protocole vocal et les résultats connus sont dans [docs/PROTOTYPE_01.md](docs/PROTOTYPE_01.md). Le corpus complet de 140 cas de la spec reste un protocole d'acceptation ultérieur, pas un essai annoncé comme exécuté.
