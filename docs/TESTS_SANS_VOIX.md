# Tests autonomes sans voix

La saisie simulée entre directement dans le vrai `Planner` puis le vrai `Engine`. Le microphone, Vosk, Whisper et SAPI ne sont pas lancés. Sous Windows, l'adaptateur est le vrai adaptateur COM/UIA : les actions ne sont pas simulées. Les tests Linux utilisent explicitement un adaptateur simulé et le rapport l'indique.

## Lancer sur le PC

Après une première installation par `start-clara.cmd`, fermer Clara puis exécuter :

```bat
test-clara-sans-voix.cmd
```

Le parcours se termine seul, sans ouvrir ensuite l'application vocale. Il refuse de démarrer si Clara ou un autre parcours occupe son port d'instance. Aucun appel Ollama dans ce mode. Aucune consommation d'API distante.

Pour exercer aussi le repli réel vers Ollama déjà préparé :

```bat
test-clara-sans-voix.cmd --with-ollama
```

Ce mode vérifie la disponibilité du modèle, puis utilise une formulation non reconnue localement pour remonter d'un dossier dans les fixtures. Le rapport exige l'origine `LOCAL_MODEL` et l'intention `explorer.parent`. Un modèle indisponible donne un résultat incomplet ; une mauvaise réponse donne un échec. Il n'installe ni ne télécharge de modèle.

Si un autre chemin de sortie est nécessaire :

```bat
test-clara-sans-voix.cmd --output C:\Temp\clara-test\journey.json
```

## Résultats analysables

Dans `resultats-tests` à la racine du dépôt :

- `journey.json` : rapport complet, commandes, intentions et paramètres attendus/reconnus, origine locale/similarité/modèle, événements, résultats observés, erreurs, dates et historique récent.
- `journey.txt` : résumé lisible.
- `journey-captures\<identifiant>\*.png` : captures après chaque étape et lors d'un échec, si la fenêtre concernée est identifiable et visible.
- **`journey.zip`** : JSON, résumé et captures de cette exécution uniquement ; fichier à analyser ou à transmettre.

JSON/TXT/ZIP sont remplacés au prochain lancement. Les dossiers de captures ont un identifiant unique ; les anciens restent disponibles. Code retour : `0` si les assertions du parcours passent, `1` sinon ; le script CMD renvoie `2` si l'installation Python manque.

Le statut global des actions (`PASSED`, `FAILED`, `INCOMPLETE`) est distinct de celui des captures (`COMPLETE`, `PARTIAL`, `NOT_REQUESTED`). Une capture impossible ne transforme pas une action vérifiée en échec, mais ne constitue jamais une preuve visuelle obtenue. Une image sauvegardée n'est pas analysée automatiquement pour décider de la réussite.

## Ce qui est vérifié

Quatre contrôles de compréhension isolés : lecteur F, formulation similaire, négation et demande ambiguë. Les paramètres du lecteur sont comparés au chemin `F:\` sans ouvrir le vrai lecteur.

Puis quatorze étapes sur des fichiers générés : navigation principale par similarité, sous-dossiers, recherche, ouverture TXT, retour à l'Explorateur, parent, filtre PDF, fichier récent, choix numéroté entre deux fichiers et Stop avant ouverture. Les intentions attendues sont comparées à celles du moteur ; les cibles réobservées sont comparées aux fixtures. Le repli Ollama optionnel remplace une étape de remontée.

La garde refuse les chemins hors des fixtures et les autres fenêtres Explorateur. Les choix et Stop sont injectés en texte. Les PDF/TXT de test et leurs fenêtres restent ouverts après le parcours. Il ne faut pas manipuler les fenêtres pendant l'exécution.

Les captures portent sur l'Explorateur identifié ou la fenêtre au titre correspondant au document attendu. Une fenêtre étrangère est ignorée. Aucun cliché global du bureau n'est demandé. Une fenêtre superposée ou une notification peut toutefois apparaître dans la zone capturée, comme indiqué par la [documentation Qt de grabWindow](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html#PySide6.QtGui.QScreen.grabWindow). Les captures et rapports restent locaux, sans envoi automatique.

## Limites et validation de cette livraison

118 tests automatisés réussis sous Linux/Python 3.12. Les nouveaux contrôles utilisent des captures et un modèle simulés : cela valide leur intégration et la conservation des échecs, pas la capture Windows ni une inférence réelle.

Le parcours démarre avec une fenêtre de fixtures : il ne valide pas l'ouverture à froid d'un lecteur réel, ni l'affichage du panneau Clara. Ces essais restent décrits dans `FIABILISATION_02.md`. Il ne valide pas le contenu intégral d'un document, la qualité de la voix ni la transcription.

Lors d'une session donnant accès à l'exécution locale sur le PC, l'assistant peut lancer cette commande puis lire directement le JSON, le résumé et les PNG. Aucun besoin de prononcer les commandes. Si tout passe, les essais vocaux manuels restent la dernière vérification.
