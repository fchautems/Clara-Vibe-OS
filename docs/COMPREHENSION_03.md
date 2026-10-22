# Compréhension et validation — version 0.3

## Lancer

Récupérer la branche `codex/fiabilisation-prototype`, puis lancer `start-clara.cmd`. La préparation acquiert aussi l’encodeur multilingue MiniLM ONNX quantifié pour CPU AVX2, à une révision figée. Aucun besoin de GPU. Le premier téléchargement nécessite Internet ; les commandes locales suivantes utilisent les fichiers installés.

Fermer Clara puis lancer :

```bat
test-clara-sans-voix.cmd
test-clara-sans-voix.cmd --with-ollama
```

Le second lancement exige Ollama et son modèle déjà préparés. Chaque lancement écrit son propre dossier sous `resultats-tests`, avec `journey.json`, `journey.txt`, captures et `journey.zip`. Garder ce ZIP pour l’analyse. Ne pas manipuler les fenêtres pendant le parcours.

Ensuite, lancer Clara et prononcer : « va dans F », « ouvre le dossier projet », « ouvre le dossier sous dossier », « ouvre le fichier notes ». Le lecteur et les noms doivent naturellement exister. Pour un essai indépendant des fichiers personnels, utiliser les noms générés indiqués dans le rapport.

## Compréhension

Ordre : règles/catalogue → encodeur sémantique local → similarité lexicale complémentaire → Jev facultatif → Ollama → clarification/refus. Une commande locale reconnue ne sollicite aucun service de repli. Les négations, alternatives et opérations interdites sont contrôlées avant les modèles. « Où est » reste distinct de « ou ».

Le catalogue contient **239 gabarits**, sans compter les expansions de paramètres/politesse. Le fichier utilisateur `%LOCALAPPDATA%\ClaraVibeOS\formulations_fr.json` reste modifiable. La migration ajoute les formulations livrées sans enlever les ajouts personnels, avec sauvegarde `formulations_fr.json.before-v3.bak`. Les changements sont relus sans redémarrer et invalident l’index sémantique.

L’intention et les paramètres sont séparés. Les noms viennent de la demande ; le résolveur ne construit pas de chemin imaginaire. Il compare les vraies entrées : casse, accents, séparateurs, pluriels prudents et petites fautes. « Projet » peut ouvrir `_projets` s’il est seul plausible ; `_projets` et `projets-2026` entraînent un choix. Les chiffres demandés et extensions restent discriminants. Les chemins absolus gardent leur casse et leurs accents.

Les contraintes de type et les indices de sens explicites limitent les intentions comparables : un fichier n’est pas transformé en dossier par son seul score. Les scores ne sont pas des probabilités de réussite. Tous les plans, y compris ceux d’Ollama, passent le même validateur ; code arbitraire, intention interdite et nom de cible inventé sont refusés.

## Réglages

Dans `%LOCALAPPDATA%\ClaraVibeOS\config.json` :

| Réglage | Valeur livrée | Rôle |
|---|---|---|
| `semantic_enabled` | `true` | Activer le moteur sémantique |
| `semantic_threshold` | `0.78` | Score minimal de similarité |
| `semantic_margin` | `0.04` | Écart minimal entre intentions compatibles distinctes |
| `name_threshold` | `0.84` | Score minimal des noms observés |
| `name_margin` | `0.08` | Conserver les noms concurrents pour clarification |
| `jev_enabled` | `false` | Autoriser l’option externe payante |

Jev utilise l’API officielle TypeSafe et `TYPESAFE_API_KEY` dans l’environnement, jamais dans le JSON ou les traces. Il ne reçoit pas le contexte Windows ; les paramètres libres extraits sont remplacés dans le texte envoyé. Les tests sans voix et corpus désactivent systématiquement Jev. L’option reste inactive sans activation utilisateur et clé. Aucun véritable appel Jev n’a été effectué pour cette livraison.

Si l’encodeur manque ou échoue, les commandes directes et la similarité lexicale restent disponibles, avec état dégradé visible. Programme Ollama, serveur, modèle et génération de contrôle restent vérifiés séparément. La préparation ne se dit complète que si les composants activés sont prêts. La télémétrie ONNX/Hugging Face est désactivée avant leur initialisation.

## Corpus reproductibles

Les ressources embarquées contiennent 65 cas de calibration, 130 cas du premier corpus et 120 cas de confirmation, avec empreintes. Pour relancer sans Windows ni voix, depuis l’environnement installé :

```bat
.venv\Scripts\python.exe -m clara.comprehension_test --split confirmation --output resultats-tests\comprehension.json
.venv\Scripts\python.exe scripts\calibrate_semantic.py --output resultats-tests\calibration.json
```

La calibration utilise uniquement ses propres cas et ne modifie pas automatiquement les réglages. Le rapport garde chaque phrase, résultat attendu, résultat obtenu, route, scores/marge et durées. Le statut global du corpus applique les critères de la spec : zéro action erronée, formulations exactes correctes et au moins 90 % des positives nouvelles reconnues localement. `all_cases_passed` et les statuts individuels restent distincts : un succès global ne signifie pas 100 % de reconnaissance.

Les premières évaluations ont révélé des défauts corrigés. Les deux corpus finaux sont donc maintenant des **corpus de régression**. Ils ne constituent plus une évaluation indépendante après ces corrections. Un nouveau corpus indépendant, puis les formulations réelles de l’utilisateur, restent nécessaires pour mesurer la généralisation sans ce biais.

## Bilan accessible

Les résultats détaillés sont dans [validation/semantic-2026-10-22.json](validation/semantic-2026-10-22.json).

| Vérification | Résultat effectivement obtenu |
|---|---|
| Suite automatisée Linux/Python 3.12 | 144 tests réussis |
| Encodeur ONNX réel sur CPU Linux | Téléchargement, empreintes et encodage vérifiés |
| Calibration finale | 45/45 positives, zéro action erronée sur 65 cas |
| Premier corpus après corrections | 86/90 positives ; 63/66 nouvelles hors correspondance directe ; zéro action erronée sur 130 cas |
| Confirmation après corrections | 78/80 positives ; 52/54 formulations étiquetées nouvelles ; zéro action erronée sur 120 cas |
| Parcours avec vrai encodeur et Windows simulé | 29 étapes réussies |
| Explorateur/panneau/captures Windows réels | Non effectués |
| Inférence Ollama réelle et Jev réel | Non effectuées ; routage, erreurs et contrats testés avec simulations |

Les quelques demandes positives non reconnues sont conservées dans le bilan, sans seuil abaissé après lecture des évaluations. En particulier, certaines restrictions « ne … que » restent refusées prudemment. Aucune réussite d’action n’est annoncée pour ces cas.

## Validations Windows restantes

1. Préparation sur le PC : états du moteur sémantique et d’Ollama, modèle téléchargé, inférences de contrôle, mode dégradé en cas d’absence.
2. Explorateur fermé : lancer le parcours, vérifier `cold_start.no_initial_explorer`, fenêtre visible et chemin du panneau conforme. Si un Explorateur est déjà ouvert, cette précondition stricte n’est pas validée ; aucune fenêtre personnelle n’est fermée automatiquement.
3. Parcours de 29 étapes : navigation, TXT/PDF, noms approximatifs, choix numérotés, stop, échec prévu et reprise de scénarios indépendants. Examiner JSON et captures.
4. Relancer avec `--with-ollama` : vérifier le vrai repli naturel, son intention et son effet observé. Si toutes les phrases candidates sont comprises localement, `NOT_EXERCISED` et résultat incomplet, sans abaisser les seuils. Le repli forcé automatisé ne remplace pas cette preuve.
5. Si F: existe, tester « va dans F » manuellement : le parcours isolé utilise son propre emplacement et ne prétend pas valider ce lecteur. Terminer par les essais vocaux de l’utilisateur.

Les durées Linux ne prédisent pas les performances du PC cible. Le panneau de test réutilise le composant d’affichage du chemin de l’application ; l’application vocale et ses événements réels doivent également être observés sur Windows. L’observation d’un titre de document ne prouve pas son chargement intégral.

## Sources techniques

- [Modèle MiniLM officiel](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), révision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.
- [TypeSafe Choice](https://docs.typesafe.ai/primitives/choice) et [démarrage officiel](https://docs.typesafe.ai/quick-start).
- [Désactivation officielle de la télémétrie ONNX](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md).

Sources consultées le 22 octobre 2026. Les performances commerciales ne sont pas utilisées comme preuve de fonctionnement de Clara.
