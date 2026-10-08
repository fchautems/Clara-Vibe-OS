Spécifications fonctionnelles — V1.1

Assistant vocal local pour Windows

| **Statut**   | V1.1 fonctionnelle — périmètre et exigences non fonctionnelles consolidés                               |
|--------------|---------------------------------------------------------------------------------------------------------|
| **Date**     | 8 octobre 2026                                                                                          |
| **Objet**    | Définir ce que Clara doit faire et comment elle doit se comporter, indépendamment des choix techniques. |
| **Principe** | Le fonctionnel décrit le « quoi ». Les choix d’architecture et de technologies sont traités séparément. |

# 1. Vision et objectifs

Clara est un assistant vocal Windows destiné à réduire au maximum les
manipulations manuelles et à permettre un usage naturel de l’ordinateur
par la voix. L’objectif n’est pas de reproduire immédiatement toutes les
possibilités de Windows, mais de disposer d’un noyau fiable, extensible
et confortable à utiliser quotidiennement.

- Interaction naturelle : l’utilisateur parle normalement, sans syntaxe
  rigide.

- Fiabilité avant automatisation : Clara ne doit jamais effectuer une
  action au hasard.

- Rapidité : les commandes courantes doivent sembler immédiates.

- Transparence : en cas de problème, l’utilisateur doit pouvoir voir ce
  que Clara a entendu, compris et tenté.

- Extensibilité : le moteur commun doit permettre l’ajout progressif de
  nouvelles applications et intentions.

- Fonctionnement local par défaut : les fonctions essentielles restent
  disponibles sans Internet.

# 2. Périmètre fonctionnel de la V1.1

La V1.1 vise en priorité l’interaction avec Windows et l’Explorateur de
fichiers. L’architecture fonctionnelle doit néanmoins permettre l’ajout
ultérieur de modules dédiés à d’autres applications, notamment Firefox,
ChatGPT, Notepad++, Fork et d’autres applications fréquemment utilisées.

Une capacité peut être connue de Clara sans être encore implémentée.
Clara doit alors distinguer clairement « je comprends ce que tu veux »
de « je ne sais pas encore le faire ».

# 3. Cycle de vie et activation

## 3.1 Démarrage

- Clara démarre automatiquement avec Windows, sans action manuelle, et
  reste disponible en arrière-plan. Le mécanisme exact (service Windows
  ou équivalent) relève de la spécification technique.

- En veille, Clara attend une ou plusieurs phrases d’activation
  configurables. Les formulations initiales envisagées sont « Bonjour
  Clara » et « Salut Clara » ; elles doivent pouvoir être modifiées sans
  changer le code.

- L’activation peut produire un retour bref configurable : salutation,
  son discret ou absence de retour vocal.

## 3.2 Session active

- Une phrase d’activation reconnue ouvre une session d’interaction
  temporaire.

- Pendant cette session, l’utilisateur peut enchaîner plusieurs demandes
  sans répéter systématiquement la phrase d’activation.

- Après une durée d’inactivité configurable — ordre de grandeur envisagé
  : quelques minutes — Clara revient automatiquement en veille.

- Une nouvelle interaction pendant la session relance naturellement le
  délai d’inactivité.

## 3.3 Fin volontaire

- Une commande de fin telle que « Bonne nuit Clara » met fin à la
  session active. Sa formulation doit pouvoir être paramétrée.

- Une petite page de réglages extensible doit permettre au minimum de
  modifier les phrases d’activation et de fin, la durée d’inactivité,
  les retours sonores/vocaux et le mode d’affichage du panneau de
  diagnostic.

# 4. Détection de la fin d’une demande

- Aucun mot de fin obligatoire tel que « exécute » n’est imposé.

- Clara transcrit pendant que l’utilisateur parle.

- Une durée de silence configurable marque la fin de l’énoncé ; une
  valeur de l’ordre de 2 à 3 secondes constitue le point de départ
  envisagé.

- Clara peut pré-analyser la demande pendant la parole, mais ne doit pas
  exécuter prématurément une action avant que la fin de l’énoncé soit
  considérée comme acquise.

- L’objectif fonctionnel est de réduire au minimum la latence
  perceptible entre la fin de la parole et l’action.

# 5. Contexte, fenêtres et continuité conversationnelle

- Par défaut, une commande agit sur la fenêtre ou l’application active
  lorsque cela a du sens.

- L’utilisateur peut changer de fenêtre ou d’application par la voix.

- Si plusieurs fenêtres ou cibles sont plausibles et que le contexte ne
  suffit pas, Clara demande laquelle.

- Clara conserve un contexte conversationnel court permettant de
  comprendre les références aux demandes précédentes et à l’état courant
  de l’application.

Exemple : « Montre-moi les fichiers PDF de ce dossier », puis « ouvre le
plus récent ». Le second énoncé désigne le plus récent parmi les PDF
précédemment ciblés.

- Règle générale : contexte unique et évident → agir ; plusieurs
  interprétations raisonnables → demander.

# 6. Fichiers, dossiers et recherche

- Clara doit tolérer les formulations approximatives et les noms
  partiels.

- La recherche doit être robuste aux différences de prononciation,
  espaces, tirets, underscores et séparateurs de chemin.

- Si plusieurs éléments correspondent, Clara propose un choix clair.

- Si aucun élément ne correspond, Clara le dit et n’effectue aucune
  action approximative.

- L’objectif est de pouvoir rechercher un fichier ou dossier même
  lorsqu’il n’est pas visible dans l’Explorateur et que son emplacement
  exact n’est pas connu.

Exemple : « Trouve-moi le fichier rapport 2025 » doit pouvoir déclencher
une recherche pertinente au-delà de la seule liste visible.

# 7. Commandes naturelles et séquences multi-étapes

- Clara accepte aussi bien des commandes simples que des demandes
  contenant plusieurs étapes successives.

- Elle doit découper une phrase continue en actions ordonnées et
  comprendre les références contextuelles telles que « là-dedans ».

Exemple : « Va sur C, ouvre Projets, cherche Clara, puis ouvre la
spécification. »

- Les étapes dépendantes sont exécutées dans l’ordre.

- Si une étape échoue, Clara s’arrête à cette étape et demande quoi
  faire au lieu de poursuivre sur une hypothèse.

- Une séquence multi-étapes reste une seule demande utilisateur composée
  d’actions successives.

# 8. Ambiguïté, confirmations et sécurité

- Clara ne réalise jamais une action au hasard pour « essayer ».

- Une action routinière, peu risquée et facilement réversible peut être
  exécutée directement.

- Une action sensible, destructive, externe ou difficilement réversible
  doit être reformulée et confirmée avant exécution.

- Une cible ambiguë doit toujours être clarifiée avant l’action.

- Le niveau de confirmation dépend du risque réel et de la réversibilité
  ; toutes les suppressions ne sont donc pas nécessairement équivalentes
  si, par exemple, un passage par la Corbeille permet une restauration.

# 9. Gestion des erreurs

Clara distingue trois niveaux d’erreur afin que le diagnostic et
l’apprentissage portent sur la bonne couche.

| **Niveau** | **Type**             | **Description**                                                                                                               |
|------------|----------------------|-------------------------------------------------------------------------------------------------------------------------------|
| 1          | Voix → texte         | La transcription ne correspond pas à ce que l’utilisateur a réellement dit.                                                   |
| 2          | Texte → intention    | La transcription est correcte, mais Clara comprend mal l’intention ou la cible.                                               |
| 3          | Commande → exécution | L’intention est correcte, mais l’exécution Windows, le script ou le mécanisme d’action échoue ou produit un mauvais résultat. |

- En cas d’incompréhension, Clara demande de répéter ou de préciser.

- Si la commande est comprise mais impossible à exécuter, Clara explique
  brièvement la cause connue.

- L’apprentissage des corrections concerne principalement le niveau 2 ;
  un échec d’exécution de niveau 3 ne doit pas modifier automatiquement
  la compréhension linguistique.

- Une erreur de transcription, de compréhension ou d’exécution ne doit
  pas faire planter Clara ni fermer la session. Après signalement,
  l’utilisateur doit pouvoir reformuler ou donner immédiatement une
  autre commande.

# 10. Signal d’erreur et mode diagnostic

- L’utilisateur peut signaler naturellement une erreur avec des
  formulations telles que « c’est faux », « non, ce n’est pas ça » ou
  équivalent.

- Ces formulations constituent des intentions reconnues et prioritaires.

- Lorsqu’une erreur est signalée, Clara ouvre un mode de
  clarification/diagnostic.

- Le panneau doit montrer au minimum : la transcription exacte de
  l’énoncé précédent et la commande/intention que Clara avait comprise.

- Le diagnostic peut également présenter l’action envoyée à l’exécution
  et le résultat observé.

- Si la transcription est fausse, Clara peut demander de répéter. Si la
  transcription est correcte mais l’intention erronée, l’utilisateur
  peut reformuler son objectif.

- Le panneau expose des éléments observables et utiles au diagnostic ;
  il n’a pas vocation à afficher un raisonnement interne du modèle.

# 11. Panneau d’interaction et de diagnostic

- Mode discret par défaut : le panneau reste caché et apparaît seulement
  lorsque l’attention de l’utilisateur est nécessaire.

- Cas typiques : erreur, ambiguïté, confirmation sensible, interruption,
  résultat partiel ou impossibilité d’exécution.

- Mode permanent/diagnostic : le panneau peut être épinglé, notamment
  pendant le développement.

- En mode permanent, il peut afficher en continu la transcription, le
  texte retenu, l’intention, la commande choisie et l’état/résultat de
  l’exécution.

- Le passage entre mode discret et mode permanent doit être simple.

# 12. Historique et annulation

- Toutes les actions de Clara sont consignées dans un historique
  structuré, y compris les actions non modificatrices : navigation,
  ouverture, recherche, changement de fenêtre, etc.

- Les actions modificatrices conservent les informations nécessaires à
  une annulation lorsqu’elle est techniquement possible.

- Un historique unifié indique notamment si une action est annulable.

- L’utilisateur peut demander « Clara, annule la dernière action ».

- L’annulation est une commande distincte de l’arrêt d’une séquence.

# 13. Arrêt et interruption

- Pendant une séquence que Clara orchestre elle-même, « stop » peut être
  utilisé seul, sans répéter « Clara ».

- « Stop » est une commande prioritaire : Clara arrête les étapes
  restantes de sa séquence dès que possible.

- Les actions déjà terminées ne sont pas annulées automatiquement.

- Si l’action a déjà été déléguée à Windows ou à un autre processus, la
  séquence de Clara peut être terminée alors que l’opération externe
  continue.

Exemple : après le lancement d’une copie Windows, « stop » ne signifie
pas automatiquement arrêter la copie. L’utilisateur peut formuler une
nouvelle demande : « arrête la copie en cours ».

- S’il n’existe qu’une opération correspondant clairement à la demande,
  Clara agit sans question inutile ; s’il y en a plusieurs, elle demande
  laquelle.

- Si une interruption technique n’est pas possible, Clara l’indique sans
  improviser de contournement risqué.

- Une interruption n’efface pas automatiquement les résultats partiels
  déjà produits.

# 14. Opérations longues et tâches en arrière-plan

- Une opération longue confiée à Windows ne doit pas bloquer Clara.

- Après lancement, Clara reste disponible pour de nouvelles commandes.

- Lorsque c’est possible, Clara conserve le lien avec l’opération en
  cours afin de répondre à une demande d’état ou à une demande explicite
  d’arrêt.

- L’historique doit permettre de distinguer l’action de lancement de
  l’état ultérieur de l’opération externe.

# 15. Droits et élévation

- Clara fonctionne normalement avec les droits de l’utilisateur et ne
  reste pas lancée en administrateur.

- Lorsqu’une action nécessite une élévation, le mécanisme standard de
  Windows/UAC assure la demande de confirmation.

- Clara ne contourne jamais l’UAC.

- Un refus d’élévation est traité comme un résultat normal et
  explicable, pas comme une invitation à chercher un contournement.

# 16. Fonctionnement local et services externes

- Les fonctions essentielles doivent rester utilisables sans connexion
  Internet.

- La V1 doit pouvoir fonctionner sans aucun service externe ni API
  activé.

- Des services externes pourront être ajoutés ultérieurement pour
  certaines capacités. Ils ne seront utilisés que lorsqu’ils auront été
  explicitement intégrés et activés dans la configuration.

- Une dépendance réseau ne doit pas dégrader inutilement la réactivité
  du chemin vocal principal.

- Clara doit limiter les déclenchements dus au bruit ambiant et éviter
  de réagir à sa propre synthèse vocale.

# 17. Catalogue d’intentions et fonctions non encore disponibles

- Clara possède un catalogue d’intentions connues.

- Une intention peut être marquée comme implémentée ou connue mais non
  encore implémentée.

- Si l’intention est comprise mais non disponible, Clara répond
  explicitement qu’elle a compris mais que la fonction n’est pas encore
  disponible.

- Une demande réellement incomprise reste distincte de ce cas.

- Les demandes concernant des fonctions non implémentées sont
  enregistrées afin d’identifier les besoins réellement rencontrés et de
  prioriser les évolutions.

- Les formulations validées peuvent enrichir progressivement la
  connaissance de Clara. Une correction explicite de l’utilisateur doit
  empêcher qu’une interprétation erronée soit réutilisée comme
  référence.

Exemple : « Mets cette fenêtre sur mon deuxième écran » peut être une
intention connue mais non implémentée. Clara doit alors signaler
l’indisponibilité, et non prétendre ne pas comprendre.

# 18. Réactivité, retour utilisateur et confort d’usage

- Le fonctionnement normal doit rester discret lorsque tout se passe
  bien, sauf configuration contraire.

- Clara parle surtout lorsqu’une clarification, une confirmation, une
  erreur ou une information utile l’exige. Une commande réussie n’a pas
  besoin d’une réponse vocale complète.

- Pour une commande simple, la cible de réactivité est de l’ordre de 1 à
  2 secondes après la fin de l’énoncé ; 5 secondes constituent la limite
  haute acceptable en usage normal.

- Lorsque Clara considère qu’un énoncé est terminé et pris en compte
  pour traitement, elle peut émettre un unique son bref (« ding »),
  configurable. Ce son signifie : « demande prise en compte, laisse-moi
  traiter/exécuter ».

- Le son ne doit pas interrompre la dictée : il intervient après la
  détection de fin d’énoncé, y compris lorsque la demande contient
  plusieurs étapes.

- Si une commande est comprise mais ne peut pas être exécutée, Clara
  fournit une information vocale courte et une notification visuelle
  indiquant le problème.

- L’usage quotidien doit minimiser les clics, les manipulations
  répétitives et les interactions manuelles.

# 19. Critères fonctionnels transversaux

1.  Ne jamais agir au hasard.

2.  Demander uniquement lorsque l’ambiguïté est réelle.

3.  Exploiter le contexte lorsque celui-ci permet une interprétation
    unique.

4.  Rester disponible pendant les opérations longues déléguées.

5.  Permettre l’interruption des séquences pilotées par Clara.

6.  Conserver un historique exploitable et permettre l’annulation
    lorsque possible.

7.  Distinguer transcription, compréhension et exécution dans le
    diagnostic.

8.  Distinguer fonction inconnue et fonction comprise mais non encore
    implémentée.

9.  Rester localement fonctionnelle sans Internet.

10. Préserver une interaction naturelle, rapide et peu intrusive.

# 20. Hors périmètre / à préciser lors des versions suivantes

- Contrôle universel et exhaustif de toutes les applications Windows dès
  la V1.

- Définition exhaustive de toutes les intentions futures.

- Choix définitif des moteurs de transcription, synthèse vocale, modèles
  de langage ou technologies d’automatisation.

- Automatisation de contournements de sécurité ou d’UAC.

- Garantie d’annulation pour toute action : l’Undo dépend de la nature
  de l’opération et des informations disponibles.

- Détection parfaite du fait que l’utilisateur parle à une autre
  personne : la conception repose plutôt sur les états veille/session
  active et les règles d’activation.

# 21. Robustesse, reprise et état

- Une erreur ponctuelle ne doit jamais obliger à relancer Clara ni à
  redémarrer la session.

- Après un redémarrage de Windows ou un crash, Clara redémarre
  proprement et retrouve ses réglages, son catalogue/cache validé et son
  historique persistant.

- Les commandes ou étapes qui n’ont pas été exécutées avant
  l’interruption ne sont jamais rejouées automatiquement au redémarrage.

- Ces commandes non exécutées peuvent rester visibles dans l’historique
  avec un statut du type « interrompu » ou « abandonné après redémarrage
  », mais la nouvelle session repart sans file d’actions en attente.

# 22. Consommation de ressources

- Clara doit pouvoir rester lancée toute la journée sans gêner l’usage
  normal du PC.

- En veille, la consommation CPU, GPU et mémoire doit rester faible ;
  les traitements lourds ne doivent être déclenchés que lorsqu’ils sont
  réellement nécessaires.

- Le choix des modèles et moteurs devra privilégier le meilleur
  compromis entre précision, réactivité et consommation sur la machine
  cible.

# 23. Confidentialité et réseau

- Le fonctionnement nominal de la V1 est local : aucune donnée
  utilisateur ne doit être envoyée à un service externe par défaut.

- Si une capacité externe est ajoutée dans une version ultérieure, son
  usage devra être explicitement configuré. Les modalités d’autorisation
  seront définies au moment où un besoin réel existera.

- Une indisponibilité d’Internet ne doit pas empêcher la navigation et
  les fonctions locales prévues dans le périmètre V1.

# 24. Critères d’acceptation de la V1

- Critère principal : après démarrage de Windows, l’utilisateur doit
  pouvoir ouvrir une session avec Clara puis effectuer une séquence
  représentative dans l’Explorateur sans toucher à la souris ni au
  clavier.

- Le scénario doit inclure au minimum : activation vocale, navigation
  entre lecteurs et dossiers, ouverture d’un fichier, commande
  contextuelle, demande multi-étapes, ambiguïté nécessitant une
  clarification, signalement d’une erreur et commande « stop ».

- Une erreur de commande ne doit pas casser la session : Clara signale
  le problème et reste immédiatement disponible.

- Une commande simple correctement reconnue doit normalement produire un
  début d’action ou un retour de prise en compte dans la cible de 1 à 2
  secondes, et rester sous 5 secondes dans les conditions normales de la
  machine cible.

- Le scénario d’acceptation doit rester réalisable sans Internet et sans
  intervention manuelle, à l’exception d’une validation imposée par
  Windows, par exemple l’UAC.

# 25. Distribution et mises à jour de la V1

- Le code source de Clara est prévu pour être versionné dans Git/GitHub.

- Pour la V1, les mises à jour sont manuelles : récupération de la
  nouvelle version via Git/Fork, puis relance selon la procédure du
  projet.

- Aucun mécanisme d’auto-update n’est requis dans la V1.

# Annexe A — Pistes techniques évoquées, non validées comme exigences

Cette annexe conserve les idées techniques apparues pendant l’analyse
afin de ne pas les perdre. Elles ne constituent pas encore des décisions
d’architecture.

- Transcription locale possible avec un moteur de type Faster-Whisper.

- Synthèse vocale locale possible avec un moteur de type Piper.

- Interprétation locale possible via un modèle exécuté localement, par
  exemple au travers d’un environnement tel qu’Ollama.

- Pré-analyse progressive pendant la parole afin de réduire le travail
  restant après détection de fin d’énoncé.

- Historique structuré potentiellement stocké dans une base locale, par
  exemple SQLite.

- Architecture modulaire : moteur commun + modules spécifiques aux
  applications.

- Cache sémantique à deux niveaux : catalogue préchargé et cache appris
  à partir des formulations réellement utilisées.

- Le cache doit associer des variantes de formulation à une intention et
  à ses paramètres plutôt qu’à une simple chaîne de caractères exacte.

- Une association ne doit pas être renforcée automatiquement après une
  seule exécution ; une correction utilisateur doit pouvoir l’invalider.

- Le catalogue peut précharger des intentions futures connues mais non
  implémentées.

- L’idée d’un service externe très rapide et peu coûteux pour certaines
  tâches de classification a été évoquée ; le produit exact et son
  intérêt restent à vérifier avant toute décision technique.

# Annexe B — Scénarios de référence

**Navigation simple —** « Ouvre le disque C » → Clara ouvre C: sans
confirmation si la cible est unique.

**Séquence —** « Va sur C, ouvre Projets, là-dedans cherche Clara, puis
ouvre le fichier de spécification » → exécution ordonnée ; arrêt au
premier échec.

**Contexte —** « Montre-moi les PDF de ce dossier » puis « ouvre le plus
récent » → la seconde demande s’applique au sous-ensemble précédemment
identifié.

**Ambiguïté —** Deux fichiers correspondent à un nom approximatif →
Clara demande lequel avant d’agir.

**Fonction connue non disponible —** « Mets cette fenêtre sur mon
deuxième écran » → Clara indique qu’elle comprend mais que la fonction
n’est pas encore disponible.

**Erreur d’interprétation —** L’utilisateur dit « c’est faux » →
ouverture du diagnostic montrant transcription et intention retenue.

**Interruption —** Pendant une séquence multi-étapes, « stop » → les
étapes restantes sont abandonnées sans annuler celles déjà terminées.

**Opération Windows —** Après lancement d’une copie, Clara reste
disponible. « Arrête la copie en cours » constitue une nouvelle commande
visant l’opération externe.

**Undo —** « Annule la dernière action » → Clara tente l’inverse
uniquement si l’historique indique que l’action est annulable.

# Annexe C — Statut de la spécification

La présente V1.1 constitue la base fonctionnelle de référence pour
démarrer la conception technique. Elle consolide également les exigences
non fonctionnelles et les critères d’acceptation discutés. Les détails
découverts pendant l’implémentation ou l’usage réel pourront être
ajoutés dans des versions ultérieures sans remettre en cause les
principes structurants ci-dessus.