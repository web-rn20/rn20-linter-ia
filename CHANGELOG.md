# Journal des versions

Le projet suit le [versionnage sémantique](https://semver.org/lang/fr/). Tant qu'il reste en 0.x, les motifs, leurs comptes et le format de sortie peuvent changer d'une version à l'autre.

## 0.3.0 (2026-10-07)

Chaque motif porte un niveau : erreur pour les résidus de génération, avertissement pour les tournures franchement typées, info pour les mots fréquents et la mise en forme. Le script donne pour chaque fichier la densité de repères pour 1000 mots et leur répartition par niveau ; la page affiche aussi sa densité pour 1000 mots.

Exclusions : commentaires `<!-- linter-ia off -->` et `<!-- linter-ia on -->` dans le texte, pour tous les motifs ou pour ceux qu'on nomme, lus par le script et par la page ; fichier `.linter-ia.json` par projet, avec des expressions acceptées et des motifs ignorés, lu par le script.

Nouvelles options : `--json`, `--seuil N` (code de retour 1 au-delà de N erreurs et avertissements pour 1000 mots, ou dès une erreur), `--config` et `--sans-config`.

Deux motifs à seuil, qui ne sortent qu'au-delà de trois occurrences pour 1000 mots et à partir de deux : les connecteurs en tête de phrase et « également, notamment ». Les seuils sont provisoires.

Indicateur d'ancrage, hors du total comme le rythme : chiffres et noms propres pour 1000 mots, nombre et longueur des paragraphes, chutes d'une phrase courte après un long paragraphe. Affiché par le script, dans `--json` et dans la page.

Correction : « de X à Y » ne prend plus le verbe « a » pour la préposition « à » (« le chef de projet a validé » sortait).

## 0.2.0 (2026-10-07)

Seize motifs de plus, quarante-six en tout. Une quatrième famille, les résidus de génération, regroupe les phrases du chatbot restées dans le texte (« Bien sûr ! », « J'espère que cela vous aide ») et les traces techniques (renvois `oaicite`, paramètres `utm_source=chatgpt.com`, caractères invisibles). Les nouvelles tournures couvrent les formules d'insistance (« il est important de noter que »), le décor d'époque (« dans un monde en constante évolution »), les conclusions récapitulatives, le participe présent en apposition, l'inflation de portée (« joue un rôle clé », « pierre angulaire »), « non seulement X, mais aussi Y », le diptyque « défis » puis « avenir prometteur » et les attributions vagues. Côté mots : adjectifs d'insistance et de brochure, calques de l'anglais, « plongeons dans ». Côté typographie : émojis et pictogrammes, filets horizontaux.

Corrections : « utilité » accentué est compté et « utiliser » ne l'est plus ; « de X à Y » ignore les fourchettes chiffrées, ne part de « des » que vers « aux » (#1) et reconnaît « de l'… à la… » ; l'impératif « Créez » accentué est compté. Un fichier qui s'ouvre sur un filet `---` n'est plus pris pour un en-tête YAML, et l'en-tête retiré laisse des lignes vides pour garder les numéros de ligne. Les caractères × et ÷ ne comptent plus comme des lettres, ni pour le script ni pour la page.

## 0.1.0 (2026-10-01)

Première version publique : trente motifs, script en ligne de commande pour les fichiers `.md`, `.txt` et `.docx`, page web autonome publiée sur GitHub Pages, skill Claude Code.
