# Revue de code (rn20-linter-ia)

Avant tout merge sur `main` : `/code-review high`. Niveau `max` si le diff touche
l'affichage du texte collé dans la page web, ou ajoute quoi que ce soit qui sort du
navigateur ou de la machine.

Chaque revue vérifie les règles du dépôt décrites dans CONTRIBUTING.md :

@CONTRIBUTING.md

Publication : la CI déploie `web/linter-ia.html` sur GitHub Pages à chaque push sur
`main`, après les tests. Un merge sur `main` arrive aussi chez chaque personne qui a
installé le skill, à son prochain `git pull`.
