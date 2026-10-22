# Clara — compréhension sémantique et parcours de validation

**Version 0.3 — validée par le « go » utilisateur du 22 octobre 2026.** Implémentation et limites : [COMPREHENSION_03.md](COMPREHENSION_03.md).

## 1. Objectif et point de départ

Comprendre davantage de formulations françaises, retrouver les destinations réellement présentes sur le PC et vérifier les actions Windows par des parcours reproductibles sans microphone.

La branche actuelle dispose de 66 gabarits de commandes, d’une similarité lexicale, d’un repli Ollama et d’un parcours texte avec rapports et captures. Elle ne dispose pas encore du moteur sémantique décrit ici. La recherche actuelle peut déjà retrouver « projet » dans `_projets` par sous-chaîne ; cette proposition rend la résolution plus explicite, mesurable et prudente face aux concurrents.

Python est conservé. La latence de transcription et la qualité de la voix restent hors périmètre. Aucune nouvelle capacité de suppression, déplacement, renommage ou exécution de code n’est ajoutée.

## 2. Chaîne de compréhension

| Ordre | Traitement | Condition de poursuite |
|---|---|---|
| 0 | Contrôles prioritaires : stop, aide, négation, opération interdite, alternative explicite | Une demande autorisée et interprétable reste à traiter |
| 1 | Correspondance directe dans les règles et le catalogue local | Aucune correspondance suffisamment précise |
| 2 | Recherche sémantique locale parmi les intentions autorisées | Score ou écart entre intentions concurrents insuffisant |
| 3 | Jev, uniquement si activé explicitement | Désactivé, indisponible ou décision insuffisante |
| 4 | Modèle local servi par Ollama | Réponse inexploitable ou informations toujours insuffisantes |
| 5 | Clarification ou refus expliqué | Aucune action exécutée au hasard |

Une reconnaissance locale suffisante ne sollicite ni Jev ni Ollama. Une négation ou une ambiguïté réelle sur la destination ne doit pas être contournée par un modèle. Par exemple, « ouvre projets ou archives » appelle une question. Une phrase inhabituelle mais cohérente peut, elle, bénéficier du repli.

Tous les chemins produisent le même contrat : intention autorisée, paramètres typés, provenance et éventuelles étapes dépendantes. Le validateur existant reste obligatoire. Aucun modèle ne fournit de code à exécuter. Un plan valide syntaxiquement ne constitue pas une preuve que la demande a été comprise ou exécutée.

## 3. Catalogue et moteur sémantique local

### Catalogue enrichi

Le JSON utilisateur reste persistant et modifiable sans changer le code. Chaque entrée décrit une intention connue, ses paramètres et des formulations. Ajouter une formulation ne permet pas d’ajouter une action arbitraire.

**Cible proposée : au moins 200 formulations distinctes**, avec au moins 15 par intention existante et davantage pour la navigation et l’ouverture. Les déclinaisons automatiques de politesse ou de lettre de lecteur ne sont pas comptées comme autant d’exemples nouveaux.

Couverture : navigation vers lecteur/dossier, parent, recherche, filtre, sélection du plus récent, ouverture et gestion des fenêtres déjà autorisée. Inclure tournures courantes, hésitations, demandes indirectes et petites erreurs plausibles de transcription. Les négations, alternatives et commandes interdites appartiennent aussi au corpus de contrôle, sans devenir des exemples positifs.

La mise à jour doit enrichir les installations existantes : migration versionnée, sauvegarde préalable, conservation des ajouts utilisateur et dédoublonnage. Le modèle et le catalogue utilisés sont identifiables par version et empreinte ; une modification du catalogue invalide son index sémantique.

### Moteur

Candidat initial à évaluer : `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, encodeur multilingue destiné notamment à la recherche sémantique. Le choix définitif dépend des résultats sur le corpus français et le PC cible ; aucune supériorité sur Ollama n’est présumée.

Le moteur fonctionne sur CPU, sans dépendre d’un GPU. Le téléchargement appartient à la préparation, jamais à une commande. Une fois installé, il fonctionne hors ligne ; les représentations du catalogue sont mises en cache et le modèle reste chargé pendant la session.

Les seuils d’acceptation et l’écart minimal entre **intentions distinctes** sont configurables. Deux exemples de la même intention ne doivent pas créer une fausse ambiguïté. Un score de similarité n’est pas une probabilité de réussite. Les seuils lexicaux actuels ne sont pas recopiés arbitrairement pour ce nouveau moteur.

Les paramètres viennent de la demande et du contexte observé, jamais du lecteur ou du nom de fichier d’un exemple voisin. La similarité lexicale peut rester un signal complémentaire, avec une trace explicite de son rôle.

## 4. Retrouver les vrais noms de dossiers et fichiers

La reconnaissance de l’intention est séparée de la résolution de la destination. Clara inspecte les entrées du dossier concerné et compare leurs noms, sans inventer de chemin ni élargir silencieusement la recherche à tout le PC.

Comparaisons graduées : nom explicite, casse et accents, séparateurs usuels, variantes singulier/pluriel prudentes, puis petites fautes. Les noms originaux sont conservés pour l’exécution et l’affichage. Ne pas supprimer systématiquement tous les `s` ou `x` finaux. Les nombres, extensions et différences significatives restent discriminants.

| Demande et contenu observé | Résultat attendu |
|---|---|
| « ouvre projet » ; seul `_projets` correspond | Ouvrir `_projets` après résolution suffisamment nette |
| « ouvre projet » ; `_projets` et `projets-2026` sont plausibles | Présenter les candidats et demander lequel |
| « ouvre projets 2026 » | Préserver `2026` dans la résolution |
| « ouvre le rapport PDF » ; TXT et PDF disponibles | Respecter l’extension demandée |
| Destination absente | Expliquer l’absence, sans annoncer une ouverture |

Une correspondance littérale accidentelle ne doit pas masquer plusieurs variantes plausibles d’un nom prononcé. Une précision explicite, un nom épelé ou un choix numéroté peut lever le doute. La réponse au choix reste liée aux candidats présentés ; si le contexte change, ils sont réobservés.

« Va dans F dans le dossier projet » devient une séquence dépendante : résoudre le lecteur F:, ouvrir et vérifier son emplacement, puis rechercher le dossier à cet endroit. Si le lecteur manque ou si une étape échoue, aucune étape suivante n’est engagée.

## 5. Jev et Ollama

**Jev est une option désactivée par défaut.** Son rôle éventuel est de départager des choix structurés autorisés. Les noms libres de dossiers et fichiers restent extraits et vérifiés localement. Son intégration ne doit pas devenir nécessaire au fonctionnement de Clara. Aucun appel payant ni envoi externe sans activation explicite ; clé exclue des journaux et données transmises limitées au nécessaire. Les tests ordinaires n’appellent pas ce service.

**Ollama reste le dernier recours**, avec un modèle local configuré. Sa réponse est limitée aux intentions autorisées et aux paramètres validables. Les chemins sont vérifiés contre la demande et le contexte ; les cibles restent résolues par le même composant que pour une commande locale.

La préparation vérifie séparément programme, serveur, modèle disponible et inférence de contrôle. Affichage explicite : absent, préparation/téléchargement en cours, prêt ou erreur, avec le composant concerné. Un modèle manquant interdit l’état « prêt ».

En cas de panne, délai dépassé ou réponse invalide : pas de fausse réussite, pas d’action improvisée, limitation expliquée et commandes locales conservées. L’absence du moteur sémantique conserve également les règles directes et la similarité lexicale existantes, en mode dégradé signalé.

## 6. Parcours sans voix sur des fichiers connus

Le test injecte le texte **à l’entrée commune après transcription**, en conservant le vrai Planner, le moteur d’exécution, les validations et l’adaptateur Windows. Seule la partie microphone/transcription est contournée pour le parcours natif. Les tests unitaires simulés sont identifiés séparément.

Chaque exécution crée un dossier unique sous l’emplacement de fixtures de Clara, avec un manifeste des chemins, contenus et dates attendus. Il contient notamment :

- des dossiers imbriqués pour tester lecteur → dossier → sous-dossier → fichier ;
- un cas où `_projets` est la seule destination plausible et un autre où plusieurs noms concurrents existent ;
- des noms avec accents, espaces, tirets et majuscules, sans créer de doublons impossibles sur Windows ;
- des TXT et PDF valides, dont deux rapports avec dates distinctes et des noms proches ;
- une cible volontairement absente, sans toucher aux documents personnels.

Le lecteur de test est celui qui héberge réellement les fixtures. La compréhension de « F » est testée indépendamment ; l’ouverture réelle de F: est un essai conditionnel si ce lecteur existe. Aucun lecteur fictif n’est annoncé comme validé.

Le parcours vérifie ouverture à froid sans fenêtre Explorateur nécessaire, premier plan, chemin persistant du panneau, navigation enchaînée, recherche, filtre, plus récent, ouverture TXT/PDF, retour à l’Explorateur, remontée, clarification et réponse numérotée, stop et échecs prévus. Il ne ferme pas les fenêtres personnelles pour préparer le test. Le scénario strict « aucun Explorateur ouvert » exige cette précondition et la consigne dans le rapport.

Les actions restent limitées aux fixtures et fenêtres autorisées. Les étapes dépendantes s’arrêtent après échec ; les scénarios indépendants repartent d’un contexte contrôlé pour poursuivre le bilan. Aucun nettoyage destructif hors du dossier créé n’est autorisé.

## 7. Corpus et tests du repli

Trois ensembles distincts : catalogue, calibration des seuils, évaluation finale non utilisée pour enrichir le catalogue ou régler les seuils. Versionner les corpus et leurs empreintes.

Cible initiale : au moins 40 cas de calibration et 120 cas d’évaluation, mêlant formulations exactes, nouvelles formulations proches, paraphrases sémantiques, paramètres différents, négations, ambiguïtés et opérations hors périmètre. Pour chaque cas, définir l’intention/les paramètres attendus ou la clarification/le refus attendu.

Les tests Ollama comprennent obligatoirement :

1. **Absence d’appel** : une commande reconnue localement n’appelle aucun repli.
2. **Repli forcé** : simuler une compréhension locale insuffisante pour vérifier le routage et la validation. Ce test ne prouve pas qu’une phrase réelle atteint naturellement Ollama.
3. **Repli naturel réel** : utiliser des demandes cohérentes réellement rejetées par les étages locaux, appeler le modèle installé et vérifier l’action sur fixtures. Ne pas abaisser artificiellement les seuils pour obtenir ce résultat. Si aucun cas ne déclenche le repli, le signaler : ce critère n’est pas validé par le test forcé.
4. **Échecs et limites** : modèle absent, timeout, réponse mal formée, intention interdite, paramètre inventé, phrase incompréhensible ou ambiguë. Attendre une réponse sûre, pas nécessairement une action.

Les réponses simulées rendent les contrôles automatiques reproductibles ; les appels réels évaluent le modèle installé et peuvent varier. Le rapport distingue systématiquement les deux. Les essais Jev réels restent optionnels, séparés et explicitement activés.

## 8. Rapports et preuves

Un dossier par exécution conserve JSON, résumé TXT et ZIP, sans écraser le bilan précédent. Il enregistre : phrase, attentes, intention/paramètres obtenus, route suivie, candidats et scores, motif de chaque repli, résultat natif observé, chemin réel, erreurs et durées. Les scores d’intention et de nom de fichier sont séparés.

Ajouter versions et empreintes du code, du catalogue, des corpus, modèles et configuration utile, sans secret ; disponibilité de chaque moteur ; mode simulé ou Windows réel ; préconditions manquantes. Mesurer séparément démarrage à froid et temps de compréhension à chaud, sans inclure la transcription.

Les captures des fenêtres du test accompagnent les étapes significatives et les échecs. Leur statut est distinct de celui de l’action. Une capture manquante ne devient pas une capture réussie ; une image ou un simple titre de fenêtre ne prouve pas à lui seul le contenu d’un document ouvert. Les observations insuffisantes restent « inconnues » ou « à vérifier ».

Le panneau est contrôlé contre le chemin réellement observé. Les résultats possibles distinguent réussite, échec, résultat inconnu et test non effectué, avec raison. Le ZIP reste local et n’est pas envoyé automatiquement.

## 9. Critères d’acceptation et livraison

| Critère | Preuve demandée |
|---|---|
| Catalogue enrichi et personnalisations préservées | Comptage et test de migration |
| Reconnaissance exacte | Tous les cas exacts attendus passent |
| Généralisation locale | Objectif initial : au moins 90 % des demandes positives simples inédites du corpus, sans repli |
| Prudence | Aucune action erronée dans les cas négatifs/ambigus du corpus ; clarification ou refus attendu |
| Noms approximatifs | Cas unique résolu, cas concurrents clarifiés, nombres/extensions préservés |
| Priorité locale | Zéro appel Jev/Ollama pour les cas localement reconnus |
| Ollama | Routage simulé et inférence naturelle réelle documentés séparément |
| Windows | Ouverture visible, parcours complet, chemin panneau conforme et erreurs fidèles |
| Mode dégradé | Commandes locales opérationnelles malgré moteur ou modèle indisponible |
| Traçabilité | Rapports exploitables, captures honnêtes, aucun test non effectué marqué réussi |

Ces objectifs portent sur le corpus versionné ; ils ne promettent pas une compréhension universelle. Un objectif manqué impose un bilan explicite, pas un assouplissement silencieux des seuils ou des attentes.

Après validation de cette spec : implémenter les trois composants de compréhension/résolution/repli, enrichir et migrer le catalogue, étendre les parcours et rapports, puis mettre à jour les guides et `PROJECT_STATE.md`. Livrer les contrôles automatisés accessibles et la liste précise des essais Windows restants. Les essais vocaux de l’utilisateur viennent après le parcours texte.

**Suivi : implémentation livrée dans cette branche ; les critères et essais réellement exécutés sont distingués des validations Windows restantes dans le bilan lié ci-dessus. Les corpus ayant révélé des défauts corrigés sont désormais des régressions ; une nouvelle évaluation indépendante reste à effectuer.**

## Références

- État et limites actuels : `PROJECT_STATE.md`, `docs/FIABILISATION_02.md`, `docs/TESTS_SANS_VOIX.md` et spécification technique V1.1 du dépôt.
- Candidat encodeur : [fiche officielle MiniLM multilingue](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), consultée le 22 octobre 2026.
- Option Jev : [présentation officielle TypeSafe](https://typesafe.ai/blog/introducing-system-one-models-and-jev), consultée le 22 octobre 2026. Contrat API et conditions à revérifier avant intégration ; les promesses commerciales ne sont pas des résultats Clara.
