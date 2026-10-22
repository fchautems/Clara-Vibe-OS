# Fiabilisation du prototype — 22 octobre 2026

## Changements

Python conservé. Transcription et voix SAPI non modifiées.

- **Windows** : une navigation absolue (lecteur, chemin explicite ou alias configuré) peut créer un Explorateur. L'appel natif reste après résolution, journalisation et admission par le contrôle Stop. Une destination inexistante n'ouvre aucune fenêtre. Une commande relative sans contexte demande d'activer un Explorateur ou de préciser la destination.
- La fenêtre concernée est restaurée et activée ; son chemin est réobservé avant réussite. Un refus Windows de premier plan, plusieurs fenêtres candidates ou une observation manquante empêchent la réussite. Le dernier Explorateur identifié peut être retrouvé quand le panneau ou un document est au premier plan. Un autre Explorateur actif devient le contexte courant ; les changements pendant une action restent refusés.
- Le panneau possède un champ **Dossier** distinct du journal, actualisé par observation environ chaque seconde entre les commandes et après navigation. Si la fenêtre n'est plus observable, le champ le signale. Pendant une commande bloquante, l'affichage représente la dernière observation ; ce n'est pas une surveillance continue. Le texte d'un plan est préfixé « Demande comprise ».
- **Compréhension** : correspondance directe, puis similarité locale, puis Ollama. Le catalogue JSON utilisateur expose intentions, gabarits, paramètres et commandes associées. Il ne contient pas de code exécutable. Les nouveaux verbes/actions exécutables nécessitent toujours une implémentation Python ; ajouter des formulations d'actions existantes ne nécessite pas de code.
- La similarité compare la partie action ; les noms et lettres de lecteur sont extraits séparément sans correction approximative. Les noms proches de plusieurs fichiers/dossiers restent soumis au choix vocal existant. Les négations sont refusées ; les alternatives « ou » demandent une reformulation complète. Les petits mots dans la partie action et certaines fautes sont tolérés. Les hésitations initiales et la politesse sont nettoyées. La compréhension de toutes les paraphrases et erreurs de noms propres n'est pas garantie.
- **Ollama** : recherche dans PATH, dans l'installation utilisateur habituelle, puis dans la copie privée Clara. S'il manque, acquisition de la distribution officielle Windows x64 sans modification du PATH ni service global. Instance dédiée sur boucle locale et cloud désactivé. Vérification séparée de l'API serveur, du modèle et d'une génération réelle de contrôle. Le modèle par défaut reste `qwen2.5:3b`, choix prudent pour le PC déclaré (16 Go RAM / GTX 1070 Ti 8 Go), sans promesse d'accélération GPU. La génération sur le PC tranche sa capacité à fonctionner.
- Acquisition du modèle avec progression pendant la préparation uniquement. États persistants dans `ollama-status.json` : `absent`, `telechargement`, `verification`, `pret`, `erreur`, plus indicateurs exécutables/serveur/modèle. Ils sont affichés en français dans la console ; l'état final reste dans le panneau. Un échec n'empêche pas les commandes locales. Le marqueur d'installation complète n'est écrit qu'après génération réussie et n'est plus utilisé pour sauter les vérifications suivantes.
- Les réponses du modèle passent dans le schéma fermé et la liste d'intentions autorisées. Ni shell, ni code produit par le modèle. Le diagnostic HTTP de repli journalise `LOCAL_MODEL`, les commandes locales `DETERMINISTIC` ou `LOCAL_SIMILARITY`.

## Réglages sans code

Dans `%LOCALAPPDATA%\ClaraVibeOS\config.json` :

- `catalogue_path` pointe par défaut vers `%LOCALAPPDATA%\ClaraVibeOS\formulations_fr.json`, copié au premier démarrage et jamais écrasé ensuite.
- `similarity_threshold`: `0.86` ; `similarity_margin`: `0.06`. Un score sous le seuil passe au modèle ; deux candidats trop proches demandent une précision.
- `ollama_model`: `qwen2.5:3b` ; `ollama_port`: `11435`.

Redémarrer après édition du JSON. Les anciens réglages 0.1 sont complétés avec ces trois nouveaux champs, en conservant leurs autres valeurs. Une configuration invalide reste refusée.

## Validation automatisée exécutée ici

Linux, Python 3.12. Aucun Windows interactif et aucun vrai Ollama utilisés.

```console
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python scripts/calibrate_similarity.py
python -m compileall -q src scripts tests
```

**110 tests réussis** le 22 octobre 2026 ; compilation et contrôle du diff réussis. La suite inclut les 85 tests antérieurs et les tests ajoutés : ouverture à froid simulée, navigation dossier/sous-dossier/fichier, destination absente, refus de focus, observation échouée sans réussite, paramètres distincts, formulations nouvelles, négations, alternatives, catalogue personnalisé, migration, seuil/marge, réponse de modèle invalide, absence du programme/modèle, panne d'installation, port occupé, téléchargement incomplet et génération manquante.

Un serveur HTTP de test sur boucle locale vérifie le véritable chemin HTTP de repli et l'absence d'appel pour une commande locale. **Ce serveur renvoie une réponse simulée : ce n'est pas une inférence Ollama réelle.**

Calibration reproductible sur `tests/data/similarity_fr.json` : 20 cas (9 paraphrases positives absentes mot pour mot du catalogue, 11 contre-exemples). À marge 0,06 :

| Seuil | Positifs reconnus / 9 | Acceptations erronées / 11 | Positifs manqués |
|---|---:|---:|---:|
| 0,80 | 9 | 0 | 0 |
| 0,84 | 9 | 0 | 0 |
| **0,86** | **9** | **0** | **0** |
| 0,90 | 7 | 0 | 2 |
| 0,94 | 7 | 0 | 2 |
| 0,98 | 0 | 0 | 9 |

0,86 conserve les neuf exemples avec un seuil plus strict que 0,80/0,84. La marge est couverte par un cas synthétique de deux actions concurrentes. Ce petit corpus n'est pas une mesure de précision sur la voix réelle : il faut l'enrichir avec les transcriptions du PC.

## Essais Windows restant à effectuer

1. Mettre à jour le dépôt sur la branche livrée puis lancer `start-clara.cmd`. Vérifier les états du téléchargement et « Ollama prêt » après génération. En cas d'erreur, vérifier que la préparation est indiquée partielle et que les commandes locales restent utilisables.
2. Fermer les fenêtres Explorateur. Dire « Salut Clara », puis « va dans F ». Le lecteur F: doit exister ; sinon un échec explicite est attendu. Vérifier fenêtre visible au premier plan et champ Dossier = `F:\`.
3. Sur des éléments réellement présents, enchaîner « ouvre le dossier projets », « ouvre le dossier [sous-dossier] », « ouvre le fichier [document.txt] ». Vérifier chaque chemin et l'ouverture visible du document. Le titre de la fenêtre du document est une preuve limitée, pas une vérification de son contenu.
4. Tester « affiche donc le disque F », « affiche ce dossier projets », puis « va dans F ou G ». Pour cette dernière, aucune navigation avant une nouvelle commande complète non ambiguë. Tester aussi deux fichiers avec le même début de nom et répondre au choix numéroté.
5. Tester « ne va pas dans F », un lecteur absent et un fichier absent : aucune réussite annoncée. Changer manuellement de dossier ou fermer la fenêtre ; vérifier l'actualisation du panneau. Tester fenêtre minimisée et refus de focus éventuel.
6. Vérifier le journal `history.sqlite`, table `events`, événement `interpretation` : commande locale → `DETERMINISTIC`/`LOCAL_SIMILARITY` ; « emmène-moi un étage plus haut » → `LOCAL_MODEL` si le modèle a répondu avec un plan valide. Sinon conserver l'erreur, ne pas considérer le repli comme validé.
7. Lancer `test-clara.cmd` pour le parcours Windows existant. Son rapport `journey.json` ne remplace pas les essais à froid, vocaux et Ollama ci-dessus. Le mode `start-clara.cmd --text-only` permet d'isoler les actions de la transcription.

Si nécessaire, transmettre `diagnostic-clara.zip`. Le ZIP reste local ; aucune transmission automatique.

Sources techniques consultées le 22 octobre 2026 : [Ollama Windows](https://docs.ollama.com/windows), [API generate](https://docs.ollama.com/api/generate), [API pull](https://docs.ollama.com/api/pull). L'archive officielle est téléchargée depuis les releases du dépôt `ollama/ollama` ; aucune version binaire particulière n'a été exécutée ici.
