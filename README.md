# Linter IA RN20

[![CI](https://github.com/web-rn20/rn20-linter-ia/actions/workflows/ci.yml/badge.svg)](https://github.com/web-rn20/rn20-linter-ia/actions/workflows/ci.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
![Statut : en cours de développement](https://img.shields.io/badge/statut-en%20cours%20de%20d%C3%A9veloppement-orange)

Un linter pour les textes en français. Il surligne les tournures que les lecteurs associent désormais aux IA génératives, comme « pas X, mais Y » ou les tirets longs, et propose pour chacune une façon de la reprendre.

[Essayer dans le navigateur](https://web-rn20.github.io/rn20-linter-ia/). Le texte collé reste dans la page, rien n'est envoyé ni enregistré.

> Projet en cours de développement. Les motifs et le format de sortie évoluent encore entre deux versions. Les retours sont bienvenus dans les [issues](https://github.com/web-rn20/rn20-linter-ia/issues).

## Utilisation

### Dans le navigateur

La page [web-rn20.github.io/rn20-linter-ia](https://web-rn20.github.io/rn20-linter-ia/) fonctionne sans compte ni installation. On colle un texte n'importe où sur la page avec Cmd+V ou Ctrl+V. Un clic sur un motif de la colonne de droite fait défiler ses occurrences et affiche le conseil. La même page existe en un seul fichier, [`web/linter-ia.html`](web/linter-ia.html), qui s'ouvre aussi hors connexion.

### En ligne de commande

Python 3.9 ou plus récent suffit, sans dépendance.

```sh
git clone https://github.com/web-rn20/rn20-linter-ia.git
cd rn20-linter-ia
python3 linter_ia.py --detail texte.md
```

Le script lit les fichiers `.md`, `.txt` et `.docx`, ou l'entrée standard avec `-`. Sans `--detail`, il affiche un tableau des comptes avec un fichier par colonne, ce qui permet de comparer deux versions d'un même texte.

```sh
python3 linter_ia.py avant.md apres.md
pbpaste | python3 linter_ia.py --detail -
```

Sous le tableau, une ligne par fichier donne la densité de repères pour 1000 mots et leur répartition par niveau. Les résidus de génération sont des erreurs, les tournures franchement typées des avertissements, les mots fréquents et la mise en forme des infos. L'option `--json` sort le même bilan et chaque occurrence avec sa ligne, sa colonne et son conseil.

### Exclusions et seuil

Un passage cité ou voulu se met hors de portée dans le texte même, par un commentaire HTML que le rendu markdown n'affiche pas. Les noms de motifs sont ceux de [`patterns.json`](patterns.json).

```markdown
<!-- linter-ia off -->
Passage relu et assumé, aucun motif n'y est compté.
<!-- linter-ia on -->

<!-- linter-ia off selon agent -->
Ici seuls « selon » et « agent » sont coupés.
<!-- linter-ia on selon agent -->
```

Pour tout un projet, un fichier `.linter-ia.json` posé dans le dossier du texte ou dans un dossier parent liste les expressions acceptées et les motifs à ignorer. Une occurrence qui touche une expression acceptée disparaît du compte. Le script indique quelle configuration il a lue ; `--config` en désigne une autre et `--sans-config` les ignore toutes.

```json
{
  "accepter": ["agents de la DGAL", "chef de projet"],
  "ignorer": ["appel_direct"]
}
```

Avec `--seuil N`, le script rend le code 1 si un texte contient une erreur, ou plus de N erreurs et avertissements pour 1000 mots. De quoi bloquer un commit ou une intégration continue :

```sh
python3 linter_ia.py --seuil 15 chapitres/*.md
```

### Comme skill Claude Code

Le dépôt est aussi un skill pour [Claude Code](https://claude.com/claude-code). Claude lance le script, puis propose des retouches passage par passage.

```sh
git clone https://github.com/web-rn20/rn20-linter-ia.git ~/.claude/skills/linter-ia
```

Dans une session, `/linter-ia texte.docx` ou une demande en langage naturel suffit. Sur un `.docx`, les retouches sont données à reporter dans Word, pour garder le suivi des modifications.

## Ce que le linter mesure

Quarante-huit motifs répartis en quatre familles, décrits dans [`patterns.json`](patterns.json) avec leur conseil de reprise. Les résidus de génération sont les traces qu'un chatbot laisse dans un texte copié : « J'espère que cela vous aide », renvois `oaicite`, caractères invisibles. Les tournures visent par exemple les définitions par la négation ou les chutes en « pour que ». Les mots-béquilles sont ceux qu'on retrouve très souvent sous la plume des modèles de langage. Côté typographie, le linter relève entre autres les tirets longs et les apostrophes droites mêlées aux courbes.

Les motifs viennent de relectures de textes réels et de catalogues publics, recoupés entre eux : la page [Aide:Identifier l'usage d'une IA générative](https://fr.wikipedia.org/wiki/Aide:Identifier_l%27usage_d%27une_IA_g%C3%A9n%C3%A9rative) de Wikipédia, le skill [humaniseur-fr](https://github.com/samber/cc-skills/tree/main/skills/humaniseur-fr) de Samuel Berthe (MIT) et des relevés publiés par des rédacteurs francophones. Un motif cité par une seule source, ou que l'une d'elles range parmi les marques d'une plume humaine, n'entre pas.

Deux motifs, les connecteurs en tête de phrase (« En outre », « Par ailleurs ») et « également » ou « notamment », ne sortent qu'au-delà d'une densité : un seul n'a rien de suspect, leur accumulation l'est. Les seuils actuels sont provisoires et seront calés sur un corpus.

Un indicateur de rythme complète le décompte. Il mesure la longueur des phrases et son écart-type, car une suite de phrases de même longueur se remarque même quand aucun motif ne sort. Il reste hors du total.

## Ce qu'il ne dit pas

Le linter compte des tics visibles à l'œil. Il ne dit pas qui a écrit un texte. Un texte sans aucun repère peut rester plat, et un détecteur d'IA, qui juge un style d'ensemble, peut le classer autrement. Le score aide à relire ; il ne certifie rien.

## Contribuer

Les propositions de motifs et les faux positifs repérés sont les bienvenus. Le mode d'emploi et les règles du dépôt sont dans [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[MIT](LICENSE). Développé à Toulouse par [RN20](https://rn20.digital), agence-laboratoire IA des filières agricoles et viticoles.
