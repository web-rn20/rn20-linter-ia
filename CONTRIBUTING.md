# Contribuer

Merci de votre intérêt. Le projet est en cours de développement : une issue avant une grosse modification évite de travailler pour rien.

## Organisation du dépôt

| Fichier | Rôle |
|---|---|
| `patterns.json` | Source unique des motifs, lue par le script et par la page |
| `linter_ia.py` | Script en ligne de commande, Python 3.9+, bibliothèque standard |
| `web/moteur.js` | Même logique en JavaScript, sans accès au DOM ni au réseau |
| `web/page.html` | Interface de la page web |
| `web/linter-ia.html` | Page autonome générée par `build_web.py`, publiée sur GitHub Pages |
| `SKILL.md` | Instructions du skill Claude Code |
| `tests/` | Tests et textes d'essai |

## Ajouter ou modifier un motif

1. Modifier `patterns.json`. Chaque motif a un `id` unique, un `nom`, une `famille` (`structure`, `mot` ou `typo`), une `regex`, des `flags` facultatifs (`i`, `m`) et un `conseil`. La même regex est lue par Python et par JavaScript : pas de drapeau en ligne comme `(?i)`, passer par `flags`. Un motif qui doit voir les apostrophes courbes telles quelles porte `"brut": true`.
2. Ajouter dans `tests/fixtures/` une phrase qui déclenche le motif, et une qui ne doit pas le déclencher si le risque de faux positif est réel. Mettre à jour les comptes attendus dans `tests/test_linter.py`.
3. Régénérer la page : `python3 build_web.py`. Le fichier `web/linter-ia.html` ne se modifie jamais à la main.
4. Lancer les tests : `python3 tests/test_linter.py`. Le test de parité entre le script et la page demande `node` ; sans lui, il est sauté en local, mais il tourne toujours dans la CI.

## Règles du dépôt

Elles sont vérifiées à chaque revue.

- **Le texte analysé ne sort jamais.** On colle dans ce linter des textes non publiés. La page ne fait aucun appel réseau, ne charge aucune ressource externe (ni CDN, ni police, ni statistiques) et ne stocke pas le texte collé. Le script ne lit que les fichiers qu'on lui donne.
- **Tout texte inséré dans la page est échappé.** Jamais de `innerHTML` sur une chaîne qui contient du texte utilisateur non échappé.
- **Une seule source de motifs.** Un diff qui touche `patterns.json`, `web/page.html` ou `web/moteur.js` sans régénérer `web/linter-ia.html` est incomplet ; un test le vérifie.
- **Deux moteurs, mêmes résultats.** `\b` et `\w` sont ASCII en JavaScript et Unicode en Python : `web/moteur.js` les réécrit. Tout motif passe le test de parité, qui compare les positions trouvées par les deux moteurs sur les mêmes textes.
- **Aucune dépendance.** Python 3.9, bibliothèque standard seulement : le script doit se lancer tel quel sur le Python livré avec macOS. Pas de `match`, pas d'annotation `X | Y`.
- **Textes d'essai inventés.** Les fixtures sont écrites pour l'occasion. Jamais un extrait de document réel, même court.
- **Lecture seule.** Le script et la page ne modifient jamais le texte analysé. Le skill propose des retouches et n'écrit dans un fichier qu'à la demande.
- **Comptes expliqués.** Un compte attendu qui change dans les tests s'explique dans le message de commit.

## Proposer une modification

Forker le dépôt, travailler sur une branche, ouvrir une pull request. La CI lance les tests sous Python 3.9 et sous la dernière version de Python, avec `node`. Une pull request qui ajoute un motif décrit en une phrase le tic visé et donne un exemple réel de tournure (inventé ou public).
