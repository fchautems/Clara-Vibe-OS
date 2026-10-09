# Clara Vibe OS — Revue critique des spécifications
8 octobre 2026 — Fonctionnelle V1.1 et technique V1.

## Avis
Conserver l’architecture proposée, puis compléter les règles d’exécution avant de lancer le noyau applicatif. La spécification technique couvre bien le fonctionnel, mais plusieurs invariants sont décrits en prose sans contrat assez précis pour que deux implémentations se comportent de la même manière.

Des prototypes ciblés peuvent commencer après cette revue : observation de l’Explorateur, pipeline audio, inférence locale. Les opérations modificatrices doivent attendre la formalisation de leur journalisation, de leur admission et de leurs inverses.

Cette revue porte sur les documents actuels et leur cohérence. Aucun prototype Windows, essai vocal ou benchmark Clara n’a été exécuté. Les corrections ci-dessous sont des recommandations ; elles ne modifient pas les specs de référence.

## Ce qui est solide
- Séparation transcription, compréhension et exécution ; aucun script libre produit par le modèle.
- Même validation pour les chemins déterministes, les formulations apprises et le modèle.
- Contexte limité, ensembles de résultats identifiés, cibles dépendantes résolues après l’étape précédente.
- Confirmations liées aux effets concrets ; lancement externe distingué de son résultat.
- Stop distinct d’undo, absence de rollback global et absence de rejeu automatique après crash.
- Statut honnête des moteurs et des performances : candidats à tester, aucune mesure inventée.
- Démarrage dans la session interactive, droits ordinaires, fonctionnement local et diagnostic observable.

## Priorités
P1 : règle à formaliser avant d’implémenter le composant concerné. P2 : comportement à préciser avant son acceptation. Une priorité élevée décrit ici un manque de contrat, pas un bug déjà observé.

| ID | Priorité | Point | Échéance |
| --- | --- | --- | --- |
| R01 | P1 | Admission des actions face à stop | Avant orchestration réelle |
| R02 | P1 | Nouvelle demande pendant une séquence | Avant commandes concurrentes |
| R03 | P1 | Journal validé avant effet et déduplication | Avant toute modification de fichiers |
| R04 | P1 | Contrats typés complets et états | Avant intégration du noyau |
| R05 | P2 | Inactivité et tâches en arrière-plan | Avant validation des sessions |
| R06 | P2 | Portée d’undo et nouvelle tentative corrigée | Avant activation de ces capacités |
| R07 | P2 | Critères mesurables d’acceptation | Avant choisir les moteurs définitifs |
| R08 | P1 | Enforcement du fonctionnement local d’Ollama | Avant activation du modèle |
| R09 | P2 | Chemin d’élévation Windows explicite | Avant annoncer une capacité nécessitant UAC |

### R01 — Le point où une action est engagée reste indéfini
Références : technique §§3, 15, 16 ; fonctionnelle §13.

Le texte vérifie le jeton avant chaque étape et promet de bloquer les étapes restantes. Il ne définit pas l’ordre entre cette vérification, l’admission par le travailleur et l’appel Windows. Scénario : le travailleur vérifie le jeton, stop est accepté, puis le travailleur lance l’appel. Il est alors impossible de dire si cette étape était « déjà engagée ».

Correction : définir un point d’admission côté exécuteur, ordonné avec l’acceptation de stop. Une seule étape de bureau peut être admise à la fois. Une action admise après stop est refusée ; une action déjà admise peut terminer avec un résultat observé. Recontrôler la génération après toute attente, notamment après journalisation. Ne pas considérer une étape simplement placée dans une file comme engagée.

Définir aussi la portée de generation : demande/séquence plutôt qu’un compteur implicitement global. Invalider une séquence ne doit pas faire perdre l’observation d’une copie indépendante ; un résultat tardif peut alimenter l’historique sans autoriser une suite.

Test : insérer une barrière avant admission, accepter stop, libérer le travailleur et vérifier l’absence d’appel. Tester aussi stop après admission, réponse tardive et copie indépendante.

### R02 — Une nouvelle demande incompatible peut laisser avancer l’ancienne
Références : technique §§5, 14, 15, 18 ; fonctionnelle §§7, 10, 14.

La spec prévoit de demander s’il faut interrompre la séquence active. Elle ne dit pas si cette séquence continue pendant la question, ce qui arrive à la nouvelle demande ni comment une réponse « oui » est rattachée à l’attente correcte.

Scénario : Clara navigue dans plusieurs dossiers ; une nouvelle demande concerne un autre dossier ; pendant la question d’interruption, l’ancienne séquence change encore la fenêtre. Le contexte présenté peut devenir périmé.

Correction : quand l’incompatibilité est identifiée, suspendre l’admission des prochaines étapes avant de poser la question. Conserver la nouvelle demande et son contexte. Donner à chaque clarification/confirmation un dialogue_id et définir une seule attente vocale décisionnelle active. Après la réponse, reprendre, abandonner ou remplacer explicitement la demande, avec nouvelle résolution des cibles. Les demandes compatibles de statut restent disponibles.

Test : arrivée d’une demande incompatible entre deux étapes, réponse positive/négative, expiration, stop pendant la question et réponse tardive à une attente remplacée.

### R03 — « Journaliser avant exécution » doit signifier commit acquitté
Références : technique §§3, 17, 20 ; fonctionnelle §§12, 21.

La règle de journalisation est correcte, mais le protocole entre coordinateur, propriétaire SQLite et exécuteur manque. Envoyer un événement au stockage ne garantit pas que l’écriture est validée avant l’effet Windows. La portée et la persistance de la déduplication ne sont pas définies non plus.

Correction : obtenir un acquittement de commit pour un action_id stable avant admission d’une modification. Enregistrer paramètres résolus, identité attendue, informations préalables nécessaires à l’inverse et état. Une contrainte unique empêche un deuxième envoi du même action_id ; un accusé perdu ne provoque jamais un nouvel effet. Les actions au résultat inconnu restent à réconcilier.

Fixer la politique de durabilité. SQLite distingue WAL avec synchronous=FULL et NORMAL ; NORMAL peut perdre des commits après coupure électrique ou redémarrage brutal. Ce n’est pas une preuve de perte lors d’un simple crash du processus. Pour le journal préalable des modifications, je recommande FULL, à mesurer [S1].

Test : stockage retardé, disque plein, acquittement perdu, message dupliqué, crash avant effet et crash après effet avant résultat. Aucune modification sans commit acquitté, aucun rejeu automatique.

### R04 — Les contrats sont encore des descriptions, pas une interface implémentable
Références : technique §§3, 9, 10, 13, 17, 23.

Le plan d’exemple est utile, mais il ne définit pas les autres variantes CLARIFICATION, UNAVAILABLE et UNKNOWN. Les paramètres des intentions, les événements audio, les identités de cibles et les transitions de tâches ne sont pas entièrement typés. Les noms LANCEE/STARTED et INDETERMINE/UNKNOWN doivent être reliés explicitement à leurs domaines.

Correction : ajouter les schémas minimaux du premier incrément : enveloppe de message, transcription partielle/finale, résultat d’interprétation discriminé, sélecteur de cible, plan, ActionRequest/ActionResult, état d’opération et attente de dialogue. Pour chaque contrat : champs obligatoires, types, valeurs, provenance et transitions autorisées.

Les identifiants d’enveloppe et la génération sont attribués par le coordinateur, puis attachés à la réponse ; le modèle ne doit pas décider leur valeur. Fixer la monotonie des révisions STT, la validation des références et des dépendances, ainsi que les délais et politiques de saturation initiaux. Commencer par le catalogue exact de navigation/ouverture plutôt que spécifier immédiatement toutes les capacités futures.

Test : rejeter champs inconnus, références absentes, cycle de dépendances, résultat d’une autre demande, révision STT ancienne et transition impossible. Vérifier qu’une saturation ne perd ni stop ni résultat nécessaire à l’historique.

### R05 — L’activité d’une tâche et l’activité de la session doivent être séparées
Références : technique §§5, 19 ; fonctionnelle §§3, 14.

Le tableau autorise le retour en veille seulement en cas d’« inactivité sans demande en cours », alors que les tâches longues sont liées à des demandes et que leur continuation après retour en veille est prévue. Une copie de vingt minutes pourrait donc maintenir l’écoute conversationnelle active vingt minutes.

Correction : calculer l’inactivité à partir des interactions utilisateur et des attentes de dialogue protégées. Une tâche détachée ne renouvelle pas ce délai. Après expiration, retourner en veille en conservant le suivi de la tâche. Une séquence qui attend un résultat peut rester suspendue ; elle ne reprend pas ses étapes de bureau après fermeture de session sans règle explicite et nouvelle validation.

Test : copie indépendante durant plus de 180 secondes sans parole, retour en veille, puis réactivation et demande d’état. Tester séparément une clarification et un énoncé en cours, qui ne doivent pas être coupés.

### R06 — Undo et correction ont besoin d’une cible utilisateur stable
Références : technique §§17, 18 ; fonctionnelle §§7, 10, 12.

« Dernière action terminée dans le périmètre courant » ne définit ni le périmètre ni l’effet de la concurrence. Une ancienne copie peut terminer après une navigation récente et devenir la dernière action. Une demande multi-étapes reste une demande utilisateur, mais undo est décrit au niveau d’une action. Enfin, une correction prépare une nouvelle tentative sans préciser son déclenchement ni éviter de répéter une étape déjà réussie.

Correction proposée : distinguer la demande, l’étape et la tâche. Afficher et reformuler la cible exacte d’undo. Définir si « dernière action » vise la dernière étape explicitement engagée par l’utilisateur ou une demande composée ; ne pas laisser l’ordre des fins de tâches décider implicitement. En cas d’ambiguïté, demander.

Une correction ouvre le diagnostic et prépare un nouveau plan ; elle ne rejoue pas automatiquement les effets déjà terminés. Une demande explicite de réessai déclenche la nouvelle résolution et les confirmations nécessaires.

Test : séquence à trois étapes, tâche ancienne terminant tard, dernière action non annulable, collision lors d’un inverse et correction après réussite partielle. Le choix du périmètre d’undo est un arbitrage produit à faire valider.

### R07 — La matrice de couverture ne donne pas encore un verdict de réussite
Références : technique §§21, 24 ; fonctionnelle §§18, 22, 24.

La spec prévoit les bons types d’essais, mais aucun corpus versionné, nombre de répétitions, seuil de qualité ni budget de ressources initial ne permet de choisir un moteur ou de déclarer le prototype acceptable.

Correction : définir un protocole court avant les benchmarks. Proposition de départ à valider : 60 commandes simples, 10 séquences, 30 situations d’ambiguïté/erreur/contrôle et 40 contre-exemples incluant négations et noms proches. Séparer corpus de réglage et corpus d’évaluation, puis rejouer les cas sensibles plusieurs fois.

Mesurer compréhension correcte, clarification utile, action indésirable, délai dernier mot→action/retour, délai de reconnaissance de stop et délai reconnaissance→blocage. Pour le corpus sensible, toute action indésirable bloque l’acceptation ; zéro incident dans ce corpus ne constitue pas une garantie universelle. Fixer ensuite le seuil de réussite utile et les budgets CPU/RAM/GPU en tenant compte du confort réel sur le PC.

Test : rapport reproductible indiquant versions, matériel, état froid/chaud, médiane, p95, dépassements de 5 secondes et cas échoués. La cible de latence doit d’abord être arbitrée.

### R08 — L’adresse locale d’Ollama ne suffit pas comme mécanisme de contrôle
Références : technique §§9, 19, 20 ; fonctionnelle §§16, 23.

La spec impose des modèles locaux et aucune donnée externe ; c’est la bonne exigence. Elle ne décrit pas comment l’installateur et le client garantissent cette configuration. Ollama possède aujourd’hui des fonctions cloud et documente un mode local seul [S2]. Utiliser une adresse de boucle locale ne remplace donc pas cette vérification.

Correction : installer/sélectionner uniquement des modèles locaux autorisés, désactiver explicitement les fonctions cloud avec le mécanisme de la version retenue et vérifier cette configuration au démarrage. Si Clara utilise une instance Ollama déjà présente, établir son mode d’intégration sans modifier silencieusement les réglages des autres usages de l’utilisateur.

Test : modèle local disponible hors ligne, tentative de sélectionner un modèle cloud refusée par Clara, contrôle des connexions sortantes en fonctionnement nominal. Un essai Internet coupé prouve la disponibilité hors ligne ; il ne prouve pas à lui seul l’absence d’envoi lorsque le réseau est disponible.

### R09 — UAC nécessite un chemin d’exécution défini par capacité
Références : technique §§13, 14 ; fonctionnelle §15.

La spec réserve correctement la validation à Windows, mais ne désigne pas le mécanisme d’élévation. Un appel refusé pour droits insuffisants ne doit pas être considéré comme un appel qui fera automatiquement apparaître UAC.

Correction : pour chaque capacité nécessitant une élévation, déclarer soit un mécanisme Windows qui la prend réellement en charge, soit un auxiliaire d’exécution limité à des opérations définies. Décrire son lancement, ses paramètres validés, son résultat, le refus et les interactions avec stop. Le verbe Windows runas est un mécanisme documenté de lancement avec demande UAC ; il ne suffit pas à définir le protocole complet [S3]. Le processus principal demeure sous droits ordinaires.

Test : refus d’accès ordinaire, consentement/refus UAC, perte du processus auxiliaire et résultat indéterminé. Tant que ce chemin n’est pas validé, annoncer la capacité indisponible plutôt qu’une élévation garantie.

## Arbitrage fonctionnel déjà identifié : silence et réactivité
Références : fonctionnelle §§4, 18, 24 ; technique §21.

Deux secondes de silence consomment déjà la totalité d’une cible de deux secondes calculée depuis le dernier mot, avant le traitement final et le retour. La technique signale correctement cette contradiction ; ce n’est pas une omission découverte par cette revue.

Je recommande de conserver le délai depuis le dernier mot comme mesure de confort. Comparer un silence fixe de 2 secondes à une fin de parole plus courte ou adaptative, avec des phrases contenant des pauses. La valeur finale et les objectifs doivent être repris dans la spec fonctionnelle après essais. Ne pas déplacer artificiellement le chronomètre après acquisition, ni promettre 1–2 secondes avant mesure.

Le ding indique seulement l’acquisition ; il ne doit pas suffire à déclarer respecté un objectif de début d’action.

## Risques à lever par prototypes
Ces points sont déjà ouverts dans la technique. Leur présence n’invalide pas l’architecture, mais ils doivent avoir un essai de décision.

| Prototype | Question à résoudre | Preuve attendue |
| --- | --- | --- |
| Explorateur | Peut-on identifier fenêtre, onglet, dossier et sélection sur le Windows cible ? | Navigation réelle, onglet actif, changement de focus et fenêtre disparue ; arrêt propre si observation incertaine |
| Audio | Stop est-il assez rapide tout en restant distinct d’un mot dans un nom de fichier ? Clara réagit-elle à sa voix ? | Casque et haut-parleurs, bruit, phrases de contrôle, mots intégrés à une phrase et interruption pendant TTS |
| Activation | Les phrases peuvent-elles être changées sans travail de développement ? | Modification réelle, validation atomique conservant l’ancien réglage en cas d’échec ; essai d’une phrase hors vocabulaire |
| STT et modèle | La machine peut-elle traiter le français et les noms de fichiers avec un délai confortable ? | Comparaison CPU d’abord, GPU ensuite si compatible ; chaîne complète froide/chaude sous charge normale |
| Recherche | La recherche hors dossier visible reste-t-elle utile avant fin d’indexation ? | Recherche avec index incomplet, racine inaccessible, fichier déplacé et parcours annulé, avec portée annoncée |

Vosk distingue adaptation de vocabulaire et adaptation plus profonde des modèles ; une simple liste de phrases ne prouve pas que tout nouveau terme sera reconnu [S4]. Faster-Whisper présente les couches de transcription en temps réel comme des intégrations distinctes : retenir une stratégie de segmentation évaluée plutôt qu’implémenter plusieurs couches à la fois [S5].

Pour UI Automation, fixer un travailleur sans fenêtre et le modèle COM adapté ; Microsoft recommande le modèle MTA pour les appels UIA de ce type [S6]. Les appels Shell peuvent avoir d’autres contraintes COM [S3] : éviter de supposer qu’un seul thread convient à toutes les interfaces.

## Suite recommandée
1. Rédiger une technique V1.1 centrée sur les contrats R01–R04, l’inactivité et les invariants de reprise. Intégrer R08 dans l’installation du moteur. Conserver une liste explicite des arbitrages produit.
2. Versionner cette révision et le rapport dans le dépôt une fois les choix produit arrêtés.
3. Valider l’observation Explorateur, l’audio et l’inférence par petits prototypes Windows. Choisir les versions et modèles à partir du protocole R07.
4. Réaliser un premier parcours vertical : activation → navigation → ensemble de PDF → ouverture contextuelle → stop → diagnostic, hors ligne et avec historique.
5. Activer ensuite chaque modification de fichiers avec journalisation et inverse vérifiés.

Je différerais l’encodeur sémantique supplémentaire et l’index global complet tant que ce parcours n’est pas fiable. Conserver dès le départ les contrats du catalogue et les corrections validées ; reporter une optimisation ne supprime pas les exigences d’apprentissage ou de recherche finale.

## Références
Documents relus dans leurs versions actuelles : Clara_Specifications_fonctionnelles_V1.1.docx et Clara_Vibe_OS_Specification_technique_V1.docx. État de projet vérifié sur main, blob f459da127d73b2b25ccbd543cf41099f11d923fd. Aucun changement des deux specs dans cette revue.

Sources primaires consultées le 8 octobre 2026 :
- [S1 — SQLite, WAL et durabilité](https://sqlite.org/wal.html)
- [S2 — Ollama, mode local, chargement et concurrence](https://docs.ollama.com/faq)
- [S3 — Microsoft, ShellExecute et runas](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shellexecutea)
- [S4 — Vosk, adaptation des modèles](https://alphacephei.com/vosk/adaptation)
- [S5 — Faster-Whisper, documentation et intégrations](https://github.com/SYSTRAN/faster-whisper)
- [S6 — Microsoft, threading UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)

Les corrections et priorités proposées relèvent de l’analyse de conception. Les sources établissent les propriétés des composants, pas la performance de Clara.
