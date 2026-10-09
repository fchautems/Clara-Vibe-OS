# Clara Vibe OS

Spécification technique V1

Date : 8 octobre 2026. Référence fonctionnelle : Clara V1.1 du 8 octobre 2026. Statut : proposition de conception à relire avant implémentation. Aucune performance décrite dans ce document n’a encore été mesurée sur la machine cible.

Cette spécification décrit comment réaliser un assistant Windows local utilisable par la voix. Elle couvre l’architecture Python, les contrats entre composants, l’Explorateur, la compréhension, les interruptions, l’historique et la reprise. Les exigences fonctionnelles V1.1 restent la référence ; une proposition technique ne les modifie pas implicitement.

## 1 Portée et statut des choix

Le périmètre initial comprend la gestion des sessions vocales, la navigation dans l’Explorateur, la recherche et l’ouverture de fichiers, le changement de fenêtre et les mécanismes communs de clarification, diagnostic et interruption. Les opérations modificatrices sont ajoutées individuellement avec leurs conditions de confirmation et d’annulation. Le catalogue peut annoncer des intentions futures sans les exécuter.

Les règles normatives de ce document traduisent les exigences fonctionnelles. Les technologies et paramètres proposés constituent une base de conception ; ils restent révisables après validation. Le contrôle universel des applications, un agent visuel autonome, les services cloud et les mises à jour automatiques ne font pas partie de la V1.

La machine de référence envisagée est le PC précédemment décrit : Intel i7‑6700K, 16 Go de RAM et GTX 1070 Ti de 8 Go, sous Windows. Ces informations sont une hypothèse à confirmer au début des essais. La version exacte de Windows, le microphone, les périphériques audio et les pilotes ne sont pas encore établis.

| Sujet | Base proposée | Validation restante |
| --- | --- | --- |
| Langage | Python 64 bits dans un environnement isolé | Version commune supportée par les dépendances |
| Interface | PySide6 | Focus, notifications et consommation |
| Écoute légère | Vosk français | Activation configurable, bruit et précision de stop |
| Transcription active | Faster‑Whisper multilingue | Taille du modèle, segmentation et délai |
| Compréhension complexe | Modèle local quantifié via Ollama | Qualité en français, RAM, GPU et délai |
| Automatisation | API Windows, COM et UI Automation | Explorateur et onglets de la version Windows cible |
| Voix | Piper local | Voix française, installation et gestion de l’écho |
| Persistance | SQLite et configuration JSON | Schéma, sauvegarde et migrations |

Les possibilités documentées des moteurs sont référencées en section 25. Elles ne prouvent pas leur qualité dans Clara.

## 2 Architecture globale

Clara repose sur un coordinateur qui possède l’état de session et autorise les actions. Les moteurs de transcription et de langage proposent des données ; ils n’accèdent pas directement au bureau ni au système de fichiers pour agir. Un exécuteur applique uniquement des intentions déclarées dans le catalogue et validées par le coordinateur.

Les responsabilités sont réparties entre les modules suivants : audio, activation, transcription, interprétation, contexte, résolution des cibles, politique d’action, orchestration, adaptateurs Windows, historique, synthèse et interface. Chaque module possède un contrat explicite et peut être remplacé sans réécrire le moteur commun.

Le chemin d’une demande est le suivant : capture audio, transcription finalisée, interprétation, résolution des cibles, validation du risque, puis exécution et observation du résultat. Une pré-analyse pendant la parole peut préparer des candidats, mais aucune action ni confirmation définitive n’est engagée avant la fin de l’énoncé.

Les applications disposent d’adaptateurs dédiés. Le moteur commun sait gérer une séquence, une ambiguïté et une interruption ; l’adaptateur Explorateur sait observer un dossier, naviguer et sélectionner un fichier. Les futurs adaptateurs Firefox, Notepad++ ou Fork réutilisent les mêmes contrats.

## 3 Processus et communication

Le processus principal héberge PySide6 et le coordinateur. La boucle graphique ne réalise ni inférence, ni recherche longue, ni appel Windows susceptible de bloquer. Le coordinateur reçoit des événements et délègue le travail.

Un processus audio maintient la capture, la détection de parole et le canal prioritaire de commandes de contrôle. Un processus STT effectue la transcription active. Ollama est un processus local distinct, appelé par un client dédié avec délai maximal. L’exécution Windows et l’indexation disposent de travailleurs séparés. La synthèse et la lecture audio ne bloquent pas le coordinateur.

Sous Windows, les processus Python démarrent avec le mécanisme spawn et un point d’entrée protégé. Les objets COM et UI Automation sont créés et utilisés dans le travailleur qui les possède ; ils ne circulent pas entre processus. Le mode d’initialisation COM doit correspondre à l’interface utilisée et être fixé par adaptateur.

La V1 utilise des files de messages locales bornées et des événements de contrôle partagés. Les messages contiennent schema_version, message_id, session_id, request_id, sequence_id si nécessaire, generation et timestamp. L’audio circule par tampon borné ou mémoire partagée ; il n’est pas copié intégralement dans chaque événement.

La génération est un compteur invalidé après une interruption ou le remplacement d’une demande. Toute réponse tardive porte sa génération d’origine et est ignorée si elle est périmée. Un identifiant de commande empêche un résultat dupliqué de déclencher deux exécutions.

Le canal stop reste indépendant des files ordinaires. Un événement d’annulation partagé est vérifié avant chaque étape et pendant les opérations contrôlées par Clara. Un travailleur bloqué peut être remplacé, mais tuer un processus ne garantit ni l’annulation d’une opération Windows déjà lancée ni sa restauration.

Les délais maximaux, les limites de file et les politiques de saturation sont configurables. En saturation, Clara abandonne une demande explicitement et le signale ; elle ne supprime jamais silencieusement un événement stop ou une demande de confirmation.

## 4 Démarrage et cycle de vie

Clara démarre à l’ouverture de la session utilisateur, par une tâche planifiée configurée pour s’exécuter dans la session interactive, avec les droits ordinaires. Une seule instance par utilisateur est autorisée. Une application résidente dans cette session est la base proposée ; les services Windows classiques sont isolés du bureau interactif [S1].

Au démarrage, le coordinateur charge et valide la configuration, ouvre l’historique, vérifie les modèles locaux puis démarre les composants nécessaires à la veille. Les moteurs lourds peuvent être préchauffés à l’activation. Ce préchauffage est un compromis à mesurer : il réduit l’attente de la première commande mais augmente les ressources réservées.

Un composant manquant produit un état dégradé visible. Sans microphone ou sans moteur d’activation utilisable, Clara ne prétend pas écouter. Sans modèle de langage, les intentions couvertes par le chemin déterministe peuvent rester disponibles ; les autres capacités sont signalées comme indisponibles.

À la fermeture ou au verrouillage de la session Windows, Clara cesse les nouvelles actions et suspend l’écoute selon le réglage proposé. Au déverrouillage, elle revient en veille et exige une nouvelle activation. Le démarrage avant connexion et le contrôle de l’écran de connexion ne sont pas couverts.

## 5 États de session et de demande

L’état de session et l’état des demandes sont distincts. Une session reste active pendant qu’une copie ou une recherche s’exécute en arrière-plan ; son état ne devient donc pas simplement « occupée ».

| État de session | Événement | Transition |
| --- | --- | --- |
| VEILLE | Phrase d’activation reconnue | ACTIVE et ouverture d’un nouveau session_id |
| ACTIVE | Nouvelle parole utilisateur valide | Maintien ACTIVE et renouvellement du délai |
| ACTIVE | Commande de fin | VEILLE après abandon des étapes Clara en attente |
| ACTIVE | Inactivité sans demande en cours | VEILLE et libération du contexte court |
| Tous | Microphone indisponible | SUSPENDUE avec notification |
| SUSPENDUE | Audio rétabli | VEILLE, sans reprise de commandes |
| Tous | Verrouillage Windows | SUSPENDUE jusqu’au déverrouillage |

Une demande suit les états CAPTURE, INTERPRETATION, RESOLUTION, ATTENTE_CLARIFICATION, ATTENTE_CONFIRMATION, EXECUTION et TERMINEE. Ses issues sont SUCCES, PARTIEL, ECHEC, ANNULEE, INDISPONIBLE ou INCOMPRISE. Le diagnostic constitue un échange rattaché à la demande précédente et ne ferme pas la session.

Le délai de session ne coupe pas un énoncé en cours ni une clarification en cours. Une attente de réponse possède son propre délai. À son expiration, la demande est abandonnée sans action. Une tâche externe déjà lancée peut continuer après le retour en veille et demeure visible dans l’historique.

La commande de fin ferme la session et abandonne les étapes Clara non lancées. Elle n’annule pas implicitement les tâches externes. Stop interrompt la séquence orchestrée ; undo constitue une demande différente.

## 6 Capture audio et activation

La capture proposée utilise sounddevice avec une entrée mono normalisée à 16 kHz pour les moteurs qui exigent ce format. Le callback audio se limite à alimenter un tampon ; il ne transcrit pas et n’appelle pas le modèle. Les changements de périphérique, pertes de flux et débordements sont détectés et consignés.

Un détecteur d’activité vocale mesure parole et silence indépendamment de l’interprétation. Il utilise une horloge monotone. Un tampon circulaire conserve un court préambule pour éviter de perdre le début d’une phrase. Les durées de tampon et les seuils sont paramétrables et soumis aux essais audio.

Vosk est le candidat initial pour l’écoute légère, car sa documentation annonce français, fonctionnement local, transcription continue et adaptation du vocabulaire [S2]. Le moteur léger vérifie les phrases d’activation et les commandes de contrôle ; il n’exécute aucune action de fichier.

Les phrases initiales sont « Salut Clara » et « Bonjour Clara » ; la phrase de fin initiale est « Bonne nuit Clara ». Elles sont stockées dans la configuration. Leur modification recharge les paramètres sans modifier le code. Le moteur doit vérifier qu’une nouvelle phrase est exploitable ; un terme absent de son vocabulaire impose une adaptation ou un autre moteur, jamais une acceptation silencieuse du réglage.

La reconnaissance tolère casse et ponctuation, mais une similarité approximative ne suffit pas seule à activer la session. La politique d’activation doit être évaluée avec des phrases proches, la télévision et la voix de Clara. Une phrase suivie immédiatement d’une commande conserve le reste de l’audio pour transcription.

Les phrases de contrôle disposent d’un vocabulaire distinct. Stop n’est actif comme interruption prioritaire que dans le contexte prévu, notamment pendant une séquence Clara. Un mot « stop » inclus dans un nom de fichier ou une phrase plus longue ne doit pas déclencher automatiquement une interruption.

## 7 Transcription et fin des énoncés

Faster‑Whisper est le candidat principal pour les demandes libres. Le moteur prend en charge la quantification INT8 sur CPU ; la documentation présente les intégrations de transcription progressive séparément [S3]. Clara doit donc gérer elle-même les segments, leur recouvrement et leur stabilisation, ou intégrer une couche de streaming évaluée.

Le français est fixé comme langue nominale. Un petit modèle multilingue constitue le premier candidat CPU ; un modèle plus précis est comparé si les noms de fichiers sont mal reconnus. Les modèles sont téléchargés pendant l’installation puis chargés depuis un chemin local. Aucun téléchargement ne survient sur le chemin d’une commande.

La GTX 1070 Ti n’est pas une dépendance obligatoire. L’accélération ne sera activée qu’après vérification de la combinaison pilote, CUDA, CTranslate2 et type de calcul. Les exemples FP16 des moteurs ne constituent pas une preuve de performance sur cette carte. La comparaison doit inclure le partage de mémoire avec le modèle de langage.

La transcription publie des événements partiels révisables et un événement final. Chaque révision possède son numéro ; le diagnostic conserve le texte final exact. Le modèle peut pré-analyser des portions stables, mais le plan n’est utilisable qu’après réception de l’événement final et validation de sa génération.

La fin d’énoncé dépend du silence détecté, avec un silence initial proposé de 2 secondes, configurable dans la plage d’usage envisagée de 2 à 3 secondes. Des pauses internes peuvent produire une coupure prématurée ; les essais doivent inclure des demandes longues avec hésitations. Une durée maximale configurable protège le tampon : si elle est dépassée, Clara demande de reformuler sans exécuter un fragment.

Le ding est émis une seule fois lorsque l’énoncé complet est acquis. Il ne signifie ni intention validée ni action réussie. Une reprise de parole avant l’acquisition prolonge le même énoncé ; après acquisition, elle devient une nouvelle demande ou une commande de contrôle.

## 8 Synthèse et gestion de l’écho

Piper est le candidat de synthèse locale [S4]. La voix française et ses paramètres sont configurables. La synthèse intervient surtout pour les clarifications, confirmations, erreurs et informations demandées. Les réussites simples peuvent rester silencieuses. Une indisponibilité de la voix conserve les informations dans le panneau et signale le mode dégradé.

La capture doit rester disponible pendant la réponse vocale pour permettre une interruption. Couper tout le microphone pendant la synthèse empêcherait ce comportement. Le pipeline doit distinguer la parole utilisateur du signal joué par Clara, avec une référence de sortie audio et une réduction d’écho adaptée au matériel.

Pendant la synthèse, l’admission des commandes ordinaires peut être suspendue jusqu’à détection d’une intervention utilisateur, puis la voix est arrêtée et l’énoncé est traité. Le canal stop reste prioritaire. Le simple fait de filtrer les mots connus du texte prononcé ne suffit pas à garantir l’absence de faux déclenchement.

Le choix précis du mécanisme de réduction d’écho reste ouvert. Les essais avec casque et haut-parleurs sont obligatoires avant de déclarer l’interruption vocale fiable. Une limitation constatée est documentée ; elle ne devient pas une suppression implicite de l’exigence fonctionnelle.

## 9 Compréhension et représentation des intentions

Le moteur reconnaît d’abord les contrôles prioritaires, puis les intentions déterministes et formulations validées. Une recherche sémantique peut proposer des candidats ; les demandes non résolues passent au modèle local. Tous les chemins produisent le même contrat d’intention et traversent les mêmes vérifications.

Ollama permet de contraindre une sortie par un schéma JSON et de la valider avec Pydantic [S5]. Clara utilise ce mécanisme pour demander des étapes appartenant au catalogue. Une sortie structurée peut néanmoins être sémantiquement fausse : le schéma ne prouve ni l’exactitude d’un fichier désigné ni la légitimité d’une action.

Le modèle reçoit la transcription finale, le catalogue pertinent et un contexte court structuré. Il retourne une intention, des sélecteurs de cibles et des dépendances. Il ne produit ni script Python, ni commande PowerShell, ni commande shell destinée à être exécutée librement. Les paramètres non déclarés et les étapes hors catalogue sont rejetés.

Un modèle local multilingue quantifié de quelques milliards de paramètres est la classe initiale proposée. Son identité et sa quantification restent à sélectionner sur un corpus français représentatif. L’acceptation exige une comparaison de qualité et de latence, notamment pour les négations, les références contextuelles et les demandes en plusieurs étapes.

Les contenus observés dans les fichiers, titres de fenêtres ou résultats sont des données. Ils ne peuvent modifier le catalogue, la politique de confirmation ou les règles d’exécution. Le moteur limite le nombre d’étapes et la taille du contexte. Un dépassement demande une clarification plutôt qu’une troncature suivie d’une action.

Chaque étape contient step_id, intent_id, arguments et depends_on. Les références figurent dans arguments et indiquent « résultat de l’étape s2 » ou « dernier ensemble de PDF ». Le niveau de risque, les droits et l’annulabilité sont calculés par le catalogue et l’adaptateur, jamais accordés par le modèle.

| Résultat de compréhension | Traitement |
| --- | --- |
| Intention disponible et cible unique | Validation puis exécution |
| Intention disponible et cible ambiguë | Clarification rattachée à la demande |
| Intention connue non implémentée | Réponse d’indisponibilité et comptage du besoin |
| Formulation incomprise | Reformulation demandée sans action |
| Plan invalide ou réponse hors délai | Erreur d’interprétation sans exécution |

Une probabilité annoncée par le modèle ne constitue pas un seuil de sécurité. La certitude d’une cible repose sur sa résolution et sur les règles de l’intention. Les formulations approximatives restent utilisables sans autoriser un choix arbitraire.

## 10 Catalogue et cache de compréhension

Le catalogue versionné décrit chaque intent_id, son application, le schéma des paramètres, des exemples français, ses préconditions, sa disponibilité et son niveau de confirmation. Il déclare également les possibilités d’annulation et d’interruption ; l’adaptateur précise si elles sont réalisables dans le cas courant.

Un premier noyau couvre session.start, session.end, control.stop, diagnostic.report_error, history.undo, window.list, window.activate, explorer.navigate, explorer.parent, files.search, files.filter, files.open et files.select_recent. Les opérations copy, move, rename, create_folder et recycle sont enregistrées séparément et deviennent disponibles uniquement après leurs contrôles spécifiques.

Le cache possède deux niveaux : des formulations et exemples préchargés avec le catalogue, puis des associations apprises validées. Il associe des variantes à une intention et à une règle d’extraction des paramètres, éventuellement à un plan paramétré. Il ne mémorise pas une commande concrète avec le chemin ancien d’un fichier à réexécuter.

La similarité sémantique est un mécanisme de recherche de candidats. Un encodeur local multilingue peut être ajouté derrière une interface dédiée. Son modèle, les seuils et l’écart minimal entre candidats restent à calibrer. Une forte similarité entre « déplace » et « ne déplace pas » ne doit jamais effacer une négation ; nombres, extensions, destinations et portée sont vérifiés séparément.

Chaque association possède association_id, texte ou gabarit, intention, paramètres variables, versions du catalogue et de l’encodeur, statut et origine. Ses statuts sont CANDIDATE, VALIDEE, INVALIDE et ARCHIVEE. Une exécution réussie crée au plus un candidat ; elle ne valide pas automatiquement l’association.

Une validation explicite de l’utilisateur, ou plusieurs exemples relus et confirmés, permet la promotion. « C’est faux » invalide immédiatement l’association utilisée en attendant le diagnostic. Si l’erreur provient ensuite de la transcription ou de l’exécution, le diagnostic permet de rétablir l’association sans apprendre une mauvaise reformulation. Une mise à jour du catalogue réévalue les entrées concernées.

## 11 Contexte et résolution des cibles

Le contexte contient la fenêtre ciblée et son identifiant Windows, l’application, l’onglet Explorateur quand il est identifiable, le dossier, la sélection et les derniers ensembles de résultats. Un ensemble possède result_set_id, identifiants ou chemins, filtres, ordre, date d’observation et portée de recherche. L’historique conversationnel est limité par durée et nombre de demandes.

La fenêtre active est capturée au début de l’énoncé utilisateur, puis recontrôlée avant l’action. Le panneau Clara ne doit pas remplacer artificiellement la cible par défaut en prenant le focus. Une fenêtre disparue ou une cible devenue incompatible impose une nouvelle résolution. Le contexte évolue après chaque étape réussie.

« Montre-moi les PDF de ce dossier » crée un ensemble filtré. « Ouvre le plus récent » utilise cet ensemble, avec la date de modification comme convention proposée affichable dans le diagnostic. Une égalité de dates significative crée une ambiguïté. Le modèle ne peut pas remplacer discrètement cet ensemble par tous les fichiers du disque.

« Là-dedans » dans une séquence référence le dossier obtenu par l’étape précédente. Ce dossier n’est résolu qu’après réussite de cette étape. Un plan ne fige pas au départ les cibles qui dépendent d’un résultat encore inconnu.

Avant une modification, l’exécuteur revérifie existence, type, droits et identité attendue. Lorsque possible, il utilise un identifiant de fichier et les métadonnées nécessaires pour détecter un remplacement ou une modification concurrente. Une résolution textuelle n’accorde pas automatiquement l’autorisation d’écraser une destination existante.

Une clarification conserve des candidats numérotés et leurs identifiants stables : « le deuxième » désigne cette liste, pas une liste reconstruite dans un autre ordre. L’utilisateur peut donner un nom plus précis. Une liste périmée est rafraîchie et présentée à nouveau avant l’action.

## 12 Recherche de fichiers

La recherche combine l’observation du dossier courant et un index local de métadonnées. L’index initial proposé est SQLite, alimenté par un scanner en arrière-plan sur les lecteurs et racines autorisés. Les champs minimaux sont chemin, nom, extension, type, taille, date de modification, racine et date d’indexation. Le contenu intégral des documents n’est pas indexé dans cette V1.

La normalisation conserve le nom original mais produit une forme de recherche avec casse, accents et séparateurs harmonisés. Une recherche approximative, par exemple avec RapidFuzz, classe les noms partiels. Des alias utilisateur et variantes issues de corrections vocales peuvent compléter ce classement ; la tolérance phonétique doit être évaluée sur des noms français réels.

Les filtres et la portée précèdent le classement. La sélection d’un candidat ne repose pas uniquement sur son rang : une absence de correspondance suffisamment plausible produit « aucun résultat », et plusieurs candidats plausibles produisent une clarification. Les règles de correspondance exactes et approximatives sont calibrées séparément.

Une recherche hors index utilise un parcours en arrière-plan limité à la portée annoncée. Clara reste disponible et distingue résultats partiels, recherche terminée et racine inaccessible. Un scan incomplet ne permet pas d’annoncer une absence certaine sur tout le PC. Les jonctions, liens symboliques, volumes amovibles et boucles de parcours sont traités explicitement.

Le scanner effectue un premier parcours puis des mises à jour incrémentales et des réconciliations périodiques. Les événements du système de fichiers ne suffisent pas seuls à garantir un index à jour. L’exécuteur vérifie toujours le fichier au moment de l’ouverture ou de la modification.

Windows Search ou Everything peuvent être intégrés plus tard derrière le même contrat. La V1 ne doit pas dépendre d’un logiciel de recherche supplémentaire pour rester fonctionnelle.

## 13 Adaptateur Windows et Explorateur

L’adaptateur utilise les interfaces natives pour les opérations dont la cible est connue et COM ou UI Automation pour observer et piloter l’Explorateur. pywinauto propose notamment un backend UI Automation [S6]. Sa compatibilité avec les contrôles et les onglets réellement utilisés doit être vérifiée sur le Windows cible.

L’adaptateur privilégie des identifiants de fenêtre et des contrôles accessibles. Les clics par coordonnées ne sont pas le mécanisme nominal. Si un raccourci clavier est requis, la fenêtre, l’onglet et le focus sont vérifiés avant son émission, puis le résultat est observé. Un manque d’observabilité donne un résultat incertain et stoppe les étapes dépendantes.

Le contrat d’observation renvoie application, window_id, tab_id éventuel, chemin courant, sélection, capacités et horodatage. Le contrat d’exécution renvoie action_id, statut, résultat observé, erreur typée et operation_id pour une tâche longue. Un simple appel envoyé à Windows n’est pas nécessairement une réussite achevée.

La navigation aboutit au dossier demandé et le vérifie. L’ouverture d’un fichier utilise son association Windows ; le lancement est distingué de la confirmation que l’application a fini de charger. Le changement de fenêtre vérifie la fenêtre effectivement active après demande.

Les opérations modificatrices utilisent un mécanisme natif ou une implémentation contrôlée qui expose résultat et gestion des collisions. Le choix exact entre API Shell et implémentation Python est fixé par opération après essais. La suppression nominale passe par la Corbeille lorsqu’elle est disponible ; une suppression définitive est une capacité différente avec confirmation explicite.

La prise en charge des onglets Explorateur est obligatoire lorsque la version cible les utilise. À défaut d’une identification fiable, Clara explique la limitation ou demande la fenêtre et l’onglet ; elle ne choisit pas le premier résultat COM disponible.

## 14 Validation et confirmations

Chaque action traverse la même validation : intention disponible, paramètres conformes, contexte valide, cible résolue, préconditions satisfaites, niveau de risque et permissions. Les intentions routinières uniques peuvent agir directement. Les actes sensibles, externes ou difficiles à restaurer demandent une reformulation et une confirmation vocales.

Le risque est déterminé par le cas réel. Un déplacement vers une destination vide et un écrasement de fichier ne partagent pas la même politique. Un passage par la Corbeille peut être réversible, mais sa disponibilité et son caractère restaurable doivent être connus. La politique ne présente pas une opération comme annulable sur la seule base de son nom.

Une confirmation est liée à request_id, au plan concret, aux cibles et à une expiration. « Oui » ne vaut que pour l’attente courante. Si la cible, la destination ou les effets changent, la confirmation est périmée. Un refus ou une expiration termine la demande sans action.

Une séquence peut recevoir une confirmation globale si ses effets sont déjà déterminés. Lorsqu’une étape ultérieure révèle une nouvelle collision ou un effet sensible non annoncé, Clara demande une nouvelle confirmation au moment pertinent. Le modèle ne peut pas sauter cette étape.

Clara reste sous le compte utilisateur. Une action nécessitant une élévation passe par le mécanisme Windows/UAC normal. Le refus est une issue normale. L’écran sécurisé UAC n’est pas automatisé ; il constitue l’exception manuelle admise par la spécification fonctionnelle.

## 15 Séquences et disponibilité pendant les opérations

L’orchestrateur parcourt les étapes dans l’ordre de leurs dépendances. Avant chaque étape, il vérifie l’annulation, la disponibilité du composant, les préconditions et la validité du contexte. Après l’étape, il enregistre le résultat observé et actualise le contexte avant de résoudre l’étape suivante.

Une séquence s’arrête au premier échec, à la première ambiguïté non résolue ou à un refus. Les étapes terminées restent acquises. Elle n’est pas une transaction globale ; aucune restauration automatique des étapes précédentes n’est promise. La reprise nécessite une demande explicite et une nouvelle vérification des cibles.

Une seule séquence de manipulation du bureau est active à la fois. Les recherches et opérations de fichiers indépendantes peuvent tourner en arrière-plan avec une limite de concurrence configurable. Une nouvelle demande incompatible n’est pas mise en attente silencieusement : Clara demande si elle doit interrompre la séquence active ou traite la demande lorsqu’elle est compatible.

Une tâche longue reçoit operation_id, type, cibles, propriétaire, état, progression éventuelle et possibilités d’arrêt. Les commandes d’état ou d’arrêt résolvent cet identifiant. La limite initiale proposée est une opération modificatrice par cible, avec verrou logique local pour éviter deux opérations Clara contradictoires. Ce verrou ne bloque pas les autres logiciels ; les modifications concurrentes sont donc toujours recontrôlées.

Un appel initial peut retourner LANCEE pendant que l’opération se poursuit. Si la prochaine étape dépend du résultat, la séquence attend un événement de fin, sans monopoliser l’écoute. Le lancement seul ne permet pas d’ouvrir un fichier copié dont la copie n’est pas encore terminée.

## 16 Stop et arrêt explicite des tâches

Le canal prioritaire reconnaît stop sans attendre la fin habituelle d’une demande de 2 à 3 secondes. Il invalide la génération de la séquence, déclenche le jeton d’annulation et empêche le départ des étapes restantes. La cible de délai proposée est inférieure à 500 ms entre reconnaissance du contrôle et blocage de la prochaine étape ; ce délai exclut la durée nécessaire pour reconnaître la parole et doit être mesuré.

Une courte action déjà engagée peut finir. L’événement stop conserve l’état obtenu et les résultats partiels. Si un travailleur continue à répondre, sa réponse peut être enregistrée comme observation mais ne relance pas une séquence invalidée.

« Arrête la copie en cours » est une nouvelle intention qui vise une opération, distincte du stop de séquence. Si une seule tâche correspond, Clara l’arrête par le mécanisme qu’elle expose. Si plusieurs copies correspondent, elle demande laquelle. Un arrêt demandé possède les statuts DEMANDE, CONFIRME, IMPOSSIBLE ou INCONNU ; la demande d’arrêt n’est pas assimilée à sa réussite.

Pour une copie contrôlée par Clara, le moteur vérifie le jeton entre blocs et enregistre les fichiers achevés ainsi que les fichiers partiels. Pour une copie déléguée à Windows, l’adaptateur expose seulement les possibilités réellement disponibles. Une copie externe sans identifiant ni contrôle exploitable ne peut pas être déclarée stoppée.

Les fichiers partiels ne sont ni supprimés ni réutilisés automatiquement si leur propriété ou leur état est incertain. Ils sont indiqués dans le résultat. Une demande de nettoyage constitue une action séparée, soumise à résolution et politique de confirmation.

## 17 Historique et annulation

SQLite conserve toutes les demandes et actions, y compris recherche, navigation et ouverture. Les événements sont appendus ; une correction ou un changement d’état crée un nouvel événement plutôt que de masquer l’observation précédente. Un index facilite les demandes de dernière action et les diagnostics.

Pour chaque action modificatrice, le moteur journalise l’intention d’action avant exécution, puis l’issue observée. Une coupure entre les deux produit une action d’état INDETERMINE à réconcilier, pas une action réputée réussie ou non exécutée. Les opérations de fichiers et la transaction SQLite ne constituent pas une transaction atomique commune.

| Entité | Champs principaux |
| --- | --- |
| requests | Identifiants, transcription finale, contexte, origine de compréhension, issue |
| steps | Intention, paramètres résolus, dépendances, statut, horodatages |
| events | Type, couche STT ou intention ou exécution, données observées, génération |
| operations | Tâche longue, propriétaire, progression, capacités et état |
| undo_records | Action source, inverse autorisé, préconditions, état et expiration |
| associations | Cache, gabarits, validation, correction et versions |
| unmet_needs | Intention indisponible ou demande incomprise, fréquence et date |

L’annulation repose sur un inverse déclaré et des préconditions. Un renommage conserve les deux noms et l’identité du fichier ; l’inverse échoue proprement si le nom initial est repris. Une copie peut autoriser la suppression des fichiers créés uniquement si leur identité et leur état n’ont pas changé. Un écrasement n’est restaurable que si une sauvegarde exploitable a réellement été conservée.

Une restauration depuis la Corbeille exige un mécanisme et une référence de restauration disponibles. Une navigation peut conserver le dossier précédent. Une ouverture d’application ne justifie pas automatiquement de fermer sa fenêtre, notamment si elle contient ensuite du travail utilisateur.

« Annule la dernière action » vise la dernière action terminée dans le périmètre courant. Si elle n’est pas annulable, Clara le dit et peut proposer la précédente annulable ; elle ne saute pas silencieusement vers une ancienne modification. L’inverse passe par les validations et confirmations habituelles et possède son propre enregistrement.

La proposition V1 inclut undo et pas de redo obligatoire. L’expiration des informations d’annulation est configurable ; elle ne permet pas de supprimer des sauvegardes encore nécessaires sans les règles de conservation définies.

## 18 Diagnostic et corrections

Le panneau expose transcription finale, intention ou plan, origine de compréhension, cibles résolues, action envoyée et résultat observé. Il distingue les couches VOIX_TEXTE, TEXTE_INTENTION et COMMANDE_EXECUTION. Il n’affiche pas de raisonnement interne du modèle.

« C’est faux » vise la dernière demande pertinente de la session, suspend sa poursuite si nécessaire et ouvre un échange de diagnostic. S’il existe plusieurs demandes plausibles, Clara demande laquelle. Le panneau peut afficher « tu as dit », « Clara avait compris » et « résultat » avec les identifiants utiles pour le support.

Une correction de transcription remplace le texte retenu pour une nouvelle tentative, tout en conservant l’original. Une correction d’intention invalide l’association utilisée et propose une reformulation candidate. Une erreur d’exécution garde l’intention intacte et décrit la cause Windows connue. Les inconnues restent marquées comme telles.

Les codes de base comprennent AUDIO_UNAVAILABLE, STT_FAILED, PLAN_INVALID, TARGET_NOT_FOUND, TARGET_AMBIGUOUS, CAPABILITY_UNAVAILABLE, ACCESS_DENIED, WINDOW_CHANGED, TIMEOUT et RESULT_UNKNOWN. Les messages utilisateurs restent courts et en français ; le détail technique reste dans le diagnostic.

Après une erreur, les attentes périmées et résultats tardifs sont invalidés. Le coordinateur reste en session active et accepte immédiatement une reformulation. Une erreur ponctuelle d’un travailleur ne ferme pas Clara.

## 19 Configuration et interface

La configuration JSON possède un schema_version et une validation stricte. Les réglages utilisateur sont séparés du catalogue livré et du cache appris. Une écriture utilise un fichier temporaire puis un remplacement atomique ; le dernier réglage valide est conservé. Une configuration invalide produit un message précis sans effacer les préférences existantes.

| Paramètre | Valeur initiale proposée | Règle |
| --- | --- | --- |
| wake_phrases | Salut Clara et Bonjour Clara | Liste modifiable, vérifiée par le moteur |
| sleep_phrases | Bonne nuit Clara | Liste modifiable |
| session_idle_seconds | 180 | Ne coupe pas une demande en cours |
| end_silence_ms | 2000 | Valeur à régler selon parole et latence |
| max_utterance_seconds | 60 | Dépassement signalé sans exécution partielle |
| clarification_timeout_seconds | 60 | Expiration sans action |
| confirmation_timeout_seconds | 30 | Autorisation limitée au plan présenté |
| feedback_ding | Activé | Un seul son après acquisition |
| activation_feedback | Son discret | Voix, son ou aucun |
| panel_mode | Discret | Discret ou permanent |
| stt_backend et stt_model | Faster‑Whisper et petit modèle français compatible | Modèle multilingue local à sélectionner |
| intent_model | Modèle local à sélectionner | Aucun modèle cloud nominal |
| search_roots | Lecteurs et racines validés à l’installation | Racines inaccessibles signalées |
| external_services_enabled | Faux | Aucune donnée sortante nominale |
| history_retention_days | 30 | Conservation undo coordonnée séparément |

Ces valeurs sont des propositions de départ, pas des performances établies ni des exigences nouvelles. La page de réglages expose au minimum phrases, délai de session, silence, retours et panneau. Les mêmes réglages usuels disposent d’intentions vocales avec validation de leurs valeurs et retour explicite.

Le panneau possède un mode discret et un mode permanent. Il affiche l’état réel du microphone et de la session. Une notification sans prise de focus est privilégiée ; si une interaction prend le focus, la cible précédente reste mémorisée et sera recontrôlée. Les choix ambigus sont numérotés et accessibles à la voix.

Les données utilisateur sont proposées sous LOCALAPPDATA dans un dossier ClaraVibeOS : config.json, history.sqlite, catalogue utilisateur, logs et sauvegardes de migration. Le dossier des modèles est configurable pour éviter de saturer le disque système. Les préférences et l’historique ne sont pas stockés dans le dépôt Git.

## 20 Reprise et confidentialité

Un superviseur local détecte la perte d’un travailleur et tente une relance bornée. La proposition initiale limite les relances à trois en cinq minutes, puis place le composant en état dégradé pour éviter une boucle. Une instance principale relancée repart en veille ; elle ne rejoue aucune demande.

Au redémarrage, les demandes encore actives sont marquées interrompues. Les étapes non lancées deviennent abandonnées. Les actions marquées en exécution sans résultat deviennent indéterminées. Les tâches externes sont réconciliées seulement si leur identité et leur état sont observables ; sinon elles restent de résultat inconnu. Aucun signalement d’échec ne justifie un nouvel envoi automatique d’une action modificatrice.

SQLite utilise des transactions courtes, un propriétaire d’écriture et le mode WAL lorsque l’environnement le permet. La base peut contenir des sauvegardes cohérentes via son API de sauvegarde. Copier uniquement le fichier principal alors qu’un journal WAL est actif n’est pas la procédure de sauvegarde nominale [S7].

Une erreur de base empêche de nouvelles modifications si leur journalisation ne peut pas être assurée. Le moteur conserve les observations disponibles et explique le mode dégradé. Il ne recrée pas silencieusement une base vide ni ne détruit l’historique corrompu.

L’audio brut reste en mémoire et est éliminé après traitement selon les limites du tampon. L’enregistrement audio de diagnostic exige un réglage explicite désactivé par défaut. Les transcriptions, chemins et paramètres d’action restent locaux avec une durée de conservation configurable. L’export de diagnostic peut masquer les noms personnels et chemins.

Ollama est joint uniquement sur une adresse de boucle locale ; ses modèles sont présents sur disque. Les autres IPC restent locaux, sans serveur réseau ouvert. La V1 ne contacte aucun service externe pendant les commandes. L’installation peut nécessiter Internet pour les dépendances et modèles, puis le scénario d’acceptation est rejoué hors ligne.

La purge d’historique ne supprime pas un inverse ou une sauvegarde encore référencés sans en expirer explicitement l’annulabilité. Le catalogue et les associations validées ont une conservation indépendante. Les identifiants de fenêtres, ensembles de résultats et autorisations de confirmation ne sont pas restaurés comme contexte actif après un redémarrage.

## 21 Réactivité et ressources

La réactivité est mesurée avec quatre instants : dernier échantillon de parole, acquisition de fin d’énoncé, intention validée, puis début d’action ou retour utilisateur. Le délai ressenti inclut le silence. Le délai de calcul après acquisition constitue une autre mesure et ne remplace pas la cible fonctionnelle.

La V1.1 prévoit 2 à 3 secondes de silence et une réponse en 1 à 2 secondes après la fin de l’énoncé. Si cette fin signifie le dernier mot réellement prononcé, ces deux valeurs sont incompatibles. Le document conserve cette question ouverte : réduire le silence après essais, ou préciser la définition de la cible dans la prochaine révision fonctionnelle. Aucun test ne doit compter seulement le délai après acquisition pour masquer cette différence.

| Mesure | Objectif ou traitement |
| --- | --- |
| Commande simple depuis le dernier mot | Cible fonctionnelle 1 à 2 s et limite 5 s ; définition à arbitrer |
| Commande simple après acquisition | Budget technique proposé inférieur à 1 s sur le chemin rapide |
| Commande complexe | Mesure séparée et notification si attente prolongée |
| Stop après reconnaissance | Blocage de la prochaine étape visé sous 500 ms |
| Activation et première commande | Mesurer moteur froid et moteur préchauffé |
| Veille | Pas d’inférence LLM ni de transcription lourde en continu |
| CPU RAM GPU | Mesures au repos, en session et sous charge normale du PC |

Les budgets CPU, RAM et GPU définitifs restent à fixer après mesures sur la machine confirmée. La veille conserve seulement les composants audio légers indispensables ; l’indexation est limitée ou suspendue pendant l’usage intensif. Les modèles lourds peuvent être déchargés à la fin de session selon une politique configurable.

La faible consommation en veille et la faible latence de première commande peuvent entrer en tension. Le prototype compare les stratégies de chargement sans imposer un gros modèle résident toute la journée. Les rapports distinguent médiane, percentile 95, cas au-delà de 5 secondes et taux de compréhension correcte.

## 22 Distribution et structure du projet

La V1 se développe et se met à jour depuis Git avec un environnement Python isolé et un fichier de dépendances verrouillées. Les versions exactes sont fixées une fois la compatibilité Windows et les moteurs vérifiés. Le téléchargement des modèles est une étape d’installation distincte, avec version, taille attendue et empreinte lorsque disponible.

La structure proposée comprend src/clara/audio, speech, intents, context, orchestration, adapters, storage et ui. Le catalogue livré réside dans resources/catalog ; les schémas dans schemas ; les tests dans tests ; les scripts d’installation et de lancement dans scripts ; les documents dans docs. PROJECT_STATE.md résume l’état vérifié et la prochaine action.

Un script d’installation effectue les vérifications préalables, installe l’environnement, prépare les modèles et enregistre le démarrage interactif. Un script de diagnostic regroupe les versions, l’état audio, les capacités disponibles et les erreurs récentes. Le fonctionnement quotidien ne demande pas une suite de manipulations manuelles.

Les mises à jour restent manuelles via Git ou Fork. Avant migration de base, Clara réalise une sauvegarde cohérente. La version de schéma et les migrations sont enregistrées. Un retour à une ancienne version du code ne doit pas ouvrir une base qu’elle ne sait pas lire ; il nécessite une procédure de restauration compatible et documentée.

Le projet documente les licences des bibliothèques, moteurs et voix retenus avant distribution. Cette vérification n’empêche pas la conception ; elle fait partie du choix final des composants. Aucun système d’auto-update n’est requis.

## 23 Contrats et scénario représentatif

Les contrats sont décrits par des modèles Pydantic versionnés. Leurs champs obligatoires et valeurs autorisées sont testés indépendamment des moteurs. Une réponse finale d’interprétation contient kind, request_id, generation, catalog_version et steps. kind distingue PLAN, CLARIFICATION, UNAVAILABLE et UNKNOWN.

Exemple de plan schématique pour « montre-moi les PDF de ce dossier, puis ouvre le plus récent » :

```json
{
  "kind": "PLAN",
  "request_id": "r42",
  "generation": 7,
  "catalog_version": "1",
  "steps": [
    {
      "step_id": "s1",
      "intent_id": "files.filter",
      "arguments": {"scope": "current_folder", "extension": "pdf"},
      "depends_on": []
    },
    {
      "step_id": "s2",
      "intent_id": "files.select_recent",
      "arguments": {"source_step": "s1", "date_field": "modified"},
      "depends_on": ["s1"]
    },
    {
      "step_id": "s3",
      "intent_id": "files.open",
      "arguments": {"source_step": "s2"},
      "depends_on": ["s2"]
    }
  ]
}
```

Ce plan ne contient aucun chemin inventé. L’étape s1 observe le dossier et crée un ensemble de fichiers existants. L’étape s2 vérifie les dates et résout les éventuelles égalités. L’étape s3 recontrôle le fichier choisi avant de l’ouvrir. Une interruption entre s1 et s2 laisse la recherche dans l’historique et empêche l’ouverture.

Le contrat d’action retourne status parmi SUCCEEDED, STARTED, PARTIAL, FAILED, CANCELLED et UNKNOWN, avec observed_result, error éventuelle, operation_id éventuel et undo_record éventuel. Le catalogue distingue encore l’intention disponible de sa réussite dans cette situation. Une réponse HTTP réussie du modèle ne constitue pas un résultat d’action.

## 24 Validation et couverture fonctionnelle

La validation comporte des essais unitaires ciblés pour les contrats, le contexte, les transitions, les confirmations périmées et les inverses ; des essais d’intégration Windows pour l’Explorateur ; puis des scénarios vocaux représentatifs sur le PC. Un simulacre d’adaptateur permet de provoquer erreurs et blocages sans modifier de vrais fichiers.

Le corpus vocal comprend commandes simples, séquences avec pauses, noms proches, extensions, lettres de lecteurs, corrections, négations, bruit et demandes inconnues. Les scores de transcription et d’intention sont distingués. Les tests Windows utilisent un dossier de fixtures isolé et vérifient les résultats réels ; ils n’autorisent pas une action sur des fichiers personnels pour démontrer une capacité.

| Exigences V1.1 | Réalisation décrite | Contrôle attendu |
| --- | --- | --- |
| 1 et 2 vision et portée | Noyau modulaire et adaptateurs | Scénario Explorateur couvert sans prétention universelle |
| 3 activation et session | États, phrases et configuration | Activation, enchaînement, fin et délai sans saisie |
| 4 fin de demande | VAD et transcription révisable | Pauses internes sans action prématurée |
| 5 contexte | Fenêtre, dossier et ensembles identifiés | PDF puis plus récent dans le même ensemble |
| 6 recherche | Index et parcours hors affichage | Fichier absent de la vue trouvé ou portée incomplète signalée |
| 7 séquences | Dépendances et arrêt au premier échec | Étape suivante jamais lancée après échec |
| 8 confirmations | Politique et autorisation liée au plan | Ambiguïté et écrasement correctement arrêtés |
| 9 et 10 erreurs | Couches et corrections | Chaque couche diagnostiquée sans fermer la session |
| 11 panneau | Modes discret et permanent | Informations visibles et choix accessibles à la voix |
| 12 historique et undo | Journal et inverses conditionnels | Renommage annulé puis collision détectée |
| 13 interruption | Canal prioritaire et jetons | Stop pendant interprétation et pendant séquence |
| 14 opérations longues | Tâches identifiées en arrière-plan | Nouvelle commande possible pendant copie |
| 15 droits | Session utilisateur et UAC | Refus d’élévation traité sans contournement |
| 16 et 23 local et réseau | Modèles locaux et boucle locale | Scénario sans Internet et sans envoi externe |
| 17 intentions futures | Catalogue et besoins non satisfaits | Fonction connue distinguée d’une demande incomprise |
| 18 réactivité et confort | Mesures et retours courts | Ding unique, erreurs brèves et délais complets |
| 19 principes transversaux | Contrôles communs | Aucune sélection arbitraire ni action non validée |
| 20 limites | Portée et capabilities | Limitation explicitement signalée |
| 21 reprise | Journal préalable et invalidation | Crash sans aucun rejeu de modification |
| 22 ressources | Veille légère et travailleurs bornés | Mesures au repos et sous charge |
| 24 acceptation | Parcours vocal hors ligne | Activation, navigation, contexte, ambiguïté, erreur et stop |
| 25 mises à jour | Git, scripts et migrations | Mise à jour manuelle et retour compatible |
| Annexe A cache | Catalogue et associations validées | Correction invalidante et cibles résolues à nouveau |

Les essais d’interruption injectent un stop pendant le STT, le modèle, une attente de confirmation et l’exécution entre deux étapes. Les essais de reprise provoquent une coupure après journalisation et après effet Windows mais avant résultat. Les scénarios vérifient également qu’une réponse tardive ne lance rien et qu’un « oui » ancien n’autorise pas une nouvelle cible.

La preuve d’acceptation finale est un parcours mains libres après ouverture de session Windows, incluant toutes les situations prévues en V1.1, avec Internet coupé. Le rapport indique configuration matérielle, versions, corpus, taux de réussite et délais. Aucun de ces essais n’a encore été exécuté.

### 24 1 Points à trancher avant de figer les composants

Les choix ouverts sont : définition du point de départ de la latence ; taille et moteur STT ; modèle d’intention et encodeur sémantique ; compatibilité GPU ; gestion de l’écho et interruption pendant la voix ; API d’observation des onglets Explorateur ; moteur précis des opérations modificatrices et inverses ; seuils de correspondance ; budgets de ressources.

Ces choix sont validés par essais ciblés après relecture de la spécification technique. Une première tranche doit couvrir une session complète, la navigation et l’ouverture, le contexte et stop. Les opérations modificatrices et leurs inverses sont activés au fur et à mesure de leur validation. Cette progression ne réduit pas les critères d’acceptation finaux.

## 25 Références techniques

Les références primaires ci-dessous ont été consultées le 8 octobre 2026. Elles étayent les capacités annoncées des composants, pas les performances de Clara. Les sources évoluent ; les versions réellement utilisées seront consignées lors de l’implémentation.

[S0] Spécification fonctionnelle Clara V1.1 et état de projet du dépôt : https://github.com/fchautems/Clara-Vibe-OS/blob/main/docs/Clara_Specifications_fonctionnelles_V1.1.md et https://github.com/fchautems/Clara-Vibe-OS/blob/main/PROJECT_STATE.md

[S1] Microsoft Interactive Services. Isolation des services et application dans la session interactive : https://learn.microsoft.com/en-us/windows/win32/services/interactive-services

[S2] Vosk. Fonctionnement hors ligne, français, streaming et vocabulaire : https://alphacephei.com/vosk/ et modèles disponibles : https://alphacephei.com/vosk/models

[S3] Faster‑Whisper. CPU INT8, GPU et couches de streaming : https://github.com/SYSTRAN/faster-whisper

[S4] Piper. Moteur local et API Python : https://github.com/OHF-Voice/piper1-gpl

[S5] Ollama Structured Outputs. Schéma JSON et validation Pydantic : https://docs.ollama.com/capabilities/structured-outputs

[S6] pywinauto Getting Started. Backend UI Automation et observation des contrôles : https://pywinauto.readthedocs.io/en/latest/getting_started.html

[S7] SQLite. Mode WAL et sauvegarde cohérente : https://sqlite.org/wal.html et https://sqlite.org/backup.html
