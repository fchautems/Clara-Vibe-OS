# Tests autonomes sans voix — version 0.3

La saisie simulée entre directement dans le vrai `Planner` puis le vrai `Engine`. Le microphone, Vosk, Whisper et SAPI ne sont pas lancés. Sous Windows, l'adaptateur est le vrai adaptateur COM/UIA : les actions ne sont pas simulées. Les tests Linux utilisent explicitement un adaptateur simulé et le rapport l'indique.

## Lancer sur le PC

Après une première installation par `start-clara.cmd`, fermer Clara puis exécuter :

```bat
test-clara-sans-voix.cmd
```

Le parcours se termine seul, sans ouvrir ensuite l'application vocale. Il refuse de démarrer si Clara ou un autre parcours occupe son port d'instance. Aucun appel Ollama dans ce mode. Jev est désactivé pour les tests, même si activé dans la configuration de l’application. Aucune consommation d’API distante.

Pour exercer aussi le repli réel vers Ollama déjà préparé :

```bat
test-clara-sans-voix.cmd --with-ollama
```

Ce mode vérifie la disponibilité du modèle, puis cherche une formulation effectivement rejetée localement pour remonter d’un dossier dans les fixtures. Si aucun candidat ne nécessite le repli, il annonce NOT_EXERCISED et un bilan incomplet ; les seuils ne sont pas abaissés. Le rapport exige l'origine `LOCAL_MODEL` et l'intention `explorer.parent`. Un modèle indisponible donne un résultat incomplet ; une mauvaise réponse donne un échec. Il n'installe ni ne télécharge de modèle.

Si un autre chemin de sortie est nécessaire :

```bat
test-clara-sans-voix.cmd --output C:\Temp\clara-test\journey.json
```

## Résultats analysables

Dans `resultats-tests/<date-identifiant>/` à la racine du dépôt :

- `journey.json` : rapport complet, commandes, intentions et paramètres attendus/reconnus, origine locale/similarité/modèle, événements, résultats observés, erreurs, dates et historique récent.
- `journey.txt` : résumé lisible.
- `journey-captures\<identifiant>\*.png` : captures après chaque étape et lors d'un échec, si la fenêtre concernée est identifiable et visible.
- **`journey.zip`** : JSON, résumé et captures de cette exécution uniquement ; fichier à analyser ou à transmettre.

Chaque lancement conserve son dossier JSON/TXT/ZIP et captures. Le rapport contient aussi versions/empreintes, traces de routage, scores, candidats de noms, corpus et manifeste des fixtures. Code retour : `0` si les assertions du parcours passent, `1` sinon ; le script CMD renvoie `2` si l'installation Python manque.

Le statut global des actions (`PASSED`, `FAILED`, `INCOMPLETE`) est distinct de celui des captures (`COMPLETE`, `PARTIAL`, `NOT_REQUESTED`). Une capture impossible ne transforme pas une action vérifiée en échec, mais ne constitue jamais une preuve visuelle obtenue. Une image sauvegardée n'est pas analysée automatiquement pour décider de la réussite.

## Ce qui est vérifié

Quatre contrôles de compréhension isolés : lecteur F, formulation similaire, négation et demande ambiguë. Les paramètres du lecteur sont comparés au chemin `F:\` sans ouvrir le vrai lecteur.

Puis vingt-neuf étapes sur des fichiers générés : navigation principale par similarité, sous-dossiers, recherche, ouverture TXT, retour à l'Explorateur, parent, filtre PDF, fichier récent, choix numéroté entre deux fichiers et Stop avant ouverture. Les intentions attendues sont comparées à celles du moteur ; les cibles réobservées sont comparées aux fixtures. Le repli Ollama optionnel remplace une étape de remontée. Les étapes supplémentaires couvrent `_projets` unique ou ambigu face à `projets-2026`, accents, séparateurs/pluriels, fichier absent et continuation après cet échec attendu. Après une erreur inattendue, les étapes dépendantes sont ignorées et les scénarios indépendants repartent après réactivation contrôlée de la fenêtre épinglée. Un changement de fenêtre ou une cible extérieure arrête tout le parcours. Un corpus supplémentaire de 120 phrases teste seulement la compréhension, sans exécuter leurs actions.

La garde refuse les chemins hors des fixtures et les autres fenêtres Explorateur. Les choix et Stop sont injectés en texte. Les PDF/TXT de test et leurs fenêtres restent ouverts après le parcours. Il ne faut pas manipuler les fenêtres pendant l'exécution.

Les captures portent sur l'Explorateur identifié ou la fenêtre au titre correspondant au document attendu. Une fenêtre étrangère est ignorée. Aucun cliché global du bureau n'est demandé. Une fenêtre superposée ou une notification peut toutefois apparaître dans la zone capturée, comme indiqué par la [documentation Qt de grabWindow](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html#PySide6.QtGui.QScreen.grabWindow). Les captures et rapports restent locaux, sans envoi automatique.

## Limites et validation de cette livraison

Le vrai encodeur ONNX CPU et le parcours de 29 étapes avec Windows simulé ont été vérifiés sur Linux. Le bilan automatisé final est dans [COMPREHENSION_03.md](COMPREHENSION_03.md) et `PROJECT_STATE.md`. Aucun Explorateur/panneau/capture Windows réel ni véritable inférence Ollama n’a été testé ici.

Le parcours étendu ouvre sa propre fenêtre par une vraie commande initiale et affiche un panneau utilisant le même composant de chemin que l’application. Pour valider strictement « Explorateur fermé », fermer soi-même ses fenêtres avant le lancement ; aucune fenêtre personnelle n’est fermée automatiquement. Une fenêtre déjà présente laisse cette précondition incomplète, même si les actions passent. Le test utilise son emplacement de fixtures : l’ouverture réelle de F: reste un essai manuel conditionnel si le lecteur existe.

Le corpus applique les critères de la spec : zéro action erronée, cas exacts corrects et au moins 90 % des nouvelles positives reconnues localement. Les phrases manquées restent visibles et `all_cases_passed` distingue 100 % de reconnaissance du succès global. Les corpus ayant déjà révélé des défauts corrigés sont désormais des régressions, pas une évaluation indépendante après corrections.

Lors d’une session donnant accès à l’exécution locale sur le PC, l’assistant pourra lancer les commandes puis lire JSON, résumé et PNG sans parler à Clara. Les essais vocaux de l’utilisateur viennent ensuite.
