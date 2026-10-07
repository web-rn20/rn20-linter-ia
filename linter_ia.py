#!/usr/bin/env python3
"""Linter IA RN20 : repere dans un texte francais les tournures d'ecriture IA.

Le linter compte des tics visibles a l'oeil (tournures, mots-bequilles,
typographie) et indique pour chacun la facon de le reprendre. Il ne dit pas qui
a ecrit le texte : un texte sans repere peut rester plat, et un detecteur d'IA,
qui juge un style d'ensemble, peut le classer autrement.

Les motifs sont dans patterns.json, partage avec la page web/linter-ia.html.
Python 3.9 ou plus recent, bibliotheque standard seulement. Le texte lu n'est
jamais modifie.

Exemples :
    python3 linter_ia.py texte.md
    python3 linter_ia.py --detail memoire.docx
    pbpaste | python3 linter_ia.py --detail -
    python3 linter_ia.py --json --seuil 15 chapitre.md

Exclusions : <!-- linter-ia off --> et <!-- linter-ia on --> dans le texte, pour
tous les motifs ou pour ceux nommes apres off / on ; fichier .linter-ia.json
dans le dossier du texte ou un dossier parent (cles "accepter" et "ignorer").
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import sys
import zipfile
from typing import NamedTuple, Optional

__version__ = "0.3.0"

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER_MOTIFS = os.path.join(ICI, "patterns.json")
FICHIER_CONFIG = ".linter-ia.json"
CLES_CONFIG = {"accepter", "ignorer"}
NIVEAUX = ("erreur", "avertissement", "info")

# Lettres du francais : bornes des apostrophes, comme dans web/moteur.js
LETTRES = "A-Za-zÀ-ÖØ-öø-ÿœŒ"
# "u" sert a JavaScript (emojis hors du plan de base) ; Python lit deja l'Unicode
DRAPEAUX = {"i": re.IGNORECASE, "m": re.MULTILINE, "u": 0}
APOS_COURBE = re.compile(rf"(?<=[{LETTRES}])’(?=[{LETTRES}])")
APOS_DROITE = re.compile(rf"(?<=[{LETTRES}])'(?=[{LETTRES}])")
# Blancs comptes de la meme facon que web/moteur.js : \s differe entre les deux langages
MOT = re.compile(r"[^ \t\n\r\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+")
DIRECTIVE = re.compile(r"<!--[ \t]*linter-ia[ \t]+(off|on)((?:[ \t]+[a-z0-9_]+)*)[ \t]*-->", re.I)
# Un motif a seuil ("densite_max", pour 1000 mots) ne sort qu'a partir de deux occurrences
MIN_OCCURRENCES_DENSITE = 2

# Ancrage : memes classes que web/moteur.js, sans \d ni \w qui different d'un langage a l'autre
# "1 200" compte pour un nombre : espace suivie de trois chiffres exactement
CHIFFRE = re.compile(r"[0-9]+(?:[.,\u00a0\u202f][0-9]+| [0-9]{3}(?![0-9]))*")
NOM_PROPRE = re.compile(
    rf"(?:(?<=[{LETTRES}0-9,;)][ \u00a0])|(?<=[{LETTRES}]'))[A-ZÀ-ÖØ-ÞŒ][{LETTRES}0-9-]*")
MOTS_MIN_ANCRAGE = 100
PARAGRAPHES_MIN = 3
CHUTE_APRES = 40
CHUTE_MOTS = 8

PHRASES_MIN_RYTHME = 5
LARGEUR_COLONNE = 11
LARGEUR_TOTAL = 8
MARGE_EXTRAIT = 35


class ErreurLecture(Exception):
    """Fichier illisible ou motif invalide ; le message nomme le fichier fautif."""


class Rythme(NamedTuple):
    """Longueur des phrases d'un texte, en mots."""

    phrases: int
    moyenne: float
    ecart_type: float


class Ancrage(NamedTuple):
    """Faits situes : chiffres et noms propres, pour 1000 mots."""

    mots: int
    chiffres: int
    noms_propres: int
    chiffres_pour_1000: float
    noms_pour_1000: float


class Paragraphes(NamedTuple):
    """Longueur des paragraphes, en mots, et chutes d'une phrase courte."""

    nombre: int
    moyenne: float
    ecart_type: float
    chutes: int


class Directive(NamedTuple):
    """Commentaire <!-- linter-ia off|on [motifs] --> : agit apres sa fin."""

    debut: int
    fin: int
    off: bool
    ids: tuple


class Config(NamedTuple):
    """Contenu d'un fichier .linter-ia.json."""

    chemin: str
    accepter: list
    ignorer: list


def charger_motifs(chemin: str = FICHIER_MOTIFS) -> list[dict]:
    """Charge les motifs et compile leur regex (cle "rx")."""
    with open(chemin, encoding="utf-8") as f:
        motifs = json.load(f)
    for motif in motifs:
        if motif.get("niveau") not in NIVEAUX:
            raise ErreurLecture(f"{chemin} : motif '{motif['id']}', champ \"niveau\" "
                                f"absent ou hors de {', '.join(NIVEAUX)}")
        if "regex" not in motif:
            continue
        try:
            drapeaux = 0
            for lettre in motif.get("flags", ""):
                drapeaux |= DRAPEAUX[lettre]
            motif["rx"] = re.compile(motif["regex"], drapeaux)
        except (KeyError, re.error) as e:
            raise ErreurLecture(f"{chemin} : motif '{motif['id']}' invalide ({e})") from e
    return motifs


FRONT_MATTER = re.compile(r"---[ \t]*\n[\w-]+:.*\n(?:.*\n)*?---[ \t]*(?:\n|$)")


def retirer_front_matter(texte: str) -> str:
    """Remplace l'en-tete YAML d'un fichier markdown par des lignes vides.

    L'en-tete ouvre le fichier sur "---" suivi d'une ligne "cle:". Un filet en
    tete de texte reste donc dans le texte. Les lignes vides gardent les numeros
    de ligne du fichier d'origine.
    """
    entete = FRONT_MATTER.match(texte)
    if not entete:
        return texte
    return "\n" * entete.group().count("\n") + texte[entete.end():]


def lire_docx(chemin: str) -> str:
    """Texte du corps d'un .docx, sans dependance.

    Les titres de niveau 2 et 3 et les paragraphes de liste sont rendus en
    markdown pour que les motifs "Intertitres" et "Puces" les comptent. Les
    champs (table des matieres) et le texte barre du suivi des modifications
    sont ignores.
    """
    with zipfile.ZipFile(chemin) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"<w:(instrText|delText)\b[^>]*>.*?</w:\1>", "", xml, flags=re.S)
    lignes = []
    for paragraphe in xml.split("</w:p>"):
        paragraphe = re.sub(r"<w:(tab|br)\b[^>]*/>", " ", paragraphe)
        texte = html.unescape(re.sub(r"<[^>]+>", "", paragraphe)).strip()
        if not texte:
            continue
        if re.search(r'<w:pStyle w:val="(?:Heading|Titre)[23]"', paragraphe):
            texte = "## " + texte
        elif "<w:numPr>" in paragraphe:
            texte = "- " + texte
        lignes.append(texte)
    return "\n".join(lignes)


def lire(chemin: str) -> str:
    """Lit un fichier .md, .txt ou .docx, ou l'entree standard si chemin vaut "-"."""
    if chemin == "-":
        return sys.stdin.read()
    try:
        if chemin.lower().endswith(".docx"):
            return lire_docx(chemin)
        # utf-8-sig : la marque d'ordre d'octets en tete de fichier n'est pas un residu
        with open(chemin, encoding="utf-8-sig") as f:
            return retirer_front_matter(f.read())
    except FileNotFoundError as e:
        raise ErreurLecture(f"{chemin} : fichier introuvable") from e
    except UnicodeDecodeError as e:
        raise ErreurLecture(f"{chemin} : pas un texte UTF-8 (formats lus : .md, .txt, .docx)") from e
    except (zipfile.BadZipFile, KeyError) as e:
        raise ErreurLecture(f"{chemin} : fichier .docx illisible") from e


def apostrophes_minoritaires(texte: str) -> list[re.Match]:
    """Apostrophes droites et courbes melangees : renvoie le type minoritaire.

    Le melange trahit un texte colle (souvent droites, depuis un chat) dans un
    texte tape sous Word (courbes). A egalite, les courbes sont signalees.
    """
    courbes = list(APOS_COURBE.finditer(texte))
    droites = list(APOS_DROITE.finditer(texte))
    if not (courbes and droites):
        return []
    return courbes if len(courbes) <= len(droites) else droites


def compter_mots(texte: str) -> int:
    return len(MOT.findall(texte))


def directives(texte: str) -> list[Directive]:
    return [Directive(m.start(), m.end(), m.group(1).lower() == "off", tuple(m.group(2).lower().split()))
            for m in DIRECTIVE.finditer(texte)]


def actif(dirs: list[Directive], id_motif: str, position: int) -> bool:
    """Le motif est-il actif a cette position, d'apres les commentaires qui precedent ?

    "off" seul coupe tout, "on" seul retablit tout ; avec des identifiants, seuls
    ces motifs sont coupes ou retablis. Le texte du commentaire lui-meme n'est
    jamais lu.
    """
    tout, coupes = True, set()
    for d in dirs:
        if d.debut <= position < d.fin:
            return False
        if d.fin > position:
            break
        if not d.ids:
            tout = not d.off
            if not d.off:
                coupes.clear()
        elif d.off:
            coupes.update(d.ids)
        else:
            coupes.difference_update(d.ids)
    return tout and id_motif not in coupes


def occurrences(texte: str, motifs: list[dict]) -> dict[str, list[re.Match]]:
    """Occurrences de chaque motif dans le texte, par identifiant de motif.

    Les motifs lisent le texte aux apostrophes courbes normalisees, sauf ceux
    marques "brut". La normalisation remplace un caractere par un autre : les
    positions restent valables dans le texte d'origine. Les passages coupes par
    un commentaire linter-ia sont retires, et un motif a seuil ne garde ses
    occurrences qu'au-dessus de sa densite maximale.
    """
    normalise = texte.replace("’", "'")
    dirs = directives(texte)
    mots = compter_mots(texte)
    resultat = {}
    for motif in motifs:
        if motif.get("special") == "apostrophes":
            trouves = apostrophes_minoritaires(texte)
        else:
            source = texte if motif.get("brut") else normalise
            trouves = list(motif["rx"].finditer(source))
        trouves = [o for o in trouves if actif(dirs, motif["id"], o.start())]
        if "densite_max" in motif and not (
                len(trouves) >= MIN_OCCURRENCES_DENSITE
                and len(trouves) * 1000 / mots > motif["densite_max"]):
            trouves = []
        resultat[motif["id"]] = trouves
    return resultat


def chercher_config(chemin_texte: str) -> Optional[str]:
    """.linter-ia.json le plus proche, du dossier du texte jusqu'a la racine."""
    dossier = os.path.abspath(os.path.dirname(chemin_texte) if chemin_texte != "-" else os.getcwd())
    while True:
        candidat = os.path.join(dossier, FICHIER_CONFIG)
        if os.path.isfile(candidat):
            return candidat
        parent = os.path.dirname(dossier)
        if parent == dossier:
            return None
        dossier = parent


def charger_config(chemin: str, motifs: list[dict]) -> Config:
    """Lit et valide un .linter-ia.json ; l'erreur nomme le champ fautif."""
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            brut = json.load(f)
    except (OSError, ValueError) as e:
        raise ErreurLecture(f"{chemin} : configuration illisible ({e})") from e
    if not isinstance(brut, dict):
        raise ErreurLecture(f"{chemin} : un objet JSON est attendu")
    inconnues = sorted(set(brut) - CLES_CONFIG)
    if inconnues:
        raise ErreurLecture(f"{chemin} : cle inconnue \"{inconnues[0]}\" "
                            f"(cles lues : {', '.join(sorted(CLES_CONFIG))})")
    for cle in CLES_CONFIG:
        valeur = brut.get(cle, [])
        if not (isinstance(valeur, list) and all(isinstance(v, str) and v.strip() for v in valeur)):
            raise ErreurLecture(f"{chemin} : \"{cle}\" doit etre une liste de textes non vides")
    ids = {m["id"] for m in motifs}
    for id_motif in brut.get("ignorer", []):
        if id_motif not in ids:
            raise ErreurLecture(f"{chemin} : \"ignorer\" nomme un motif inconnu, '{id_motif}'")
    return Config(chemin, list(brut.get("accepter", [])), list(brut.get("ignorer", [])))


def appliquer_config(texte: str, resultat: dict, config: Optional[Config]) -> dict:
    """Retire les motifs ignores et les occurrences qui touchent une expression acceptee."""
    if config is None:
        return resultat
    normalise = texte.replace("’", "'")
    acceptes = [(m.start(), m.end()) for expr in config.accepter
                for m in re.finditer(re.escape(expr.replace("’", "'")), normalise, re.I)]
    return {
        id_motif: [] if id_motif in config.ignorer else
        [o for o in trouves if not any(o.start() < fin and debut < o.end() for debut, fin in acceptes)]
        for id_motif, trouves in resultat.items()
    }


def rythme(texte: str) -> Optional[Rythme]:
    """Longueur des phrases, ou None sous cinq phrases.

    Un rythme tres regulier se remarque meme quand aucun motif ne sort.
    L'indicateur reste hors du total des reperes.
    """
    phrases = [
        p for p in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", texte))
        if len(p.split()) > 2
    ]
    if len(phrases) < PHRASES_MIN_RYTHME:
        return None
    longueurs = [len(p.split()) for p in phrases]
    return Rythme(len(longueurs), float(statistics.mean(longueurs)), statistics.pstdev(longueurs))


def ancrage(texte: str) -> Optional[Ancrage]:
    """Chiffres et noms propres pour 1000 mots, ou None sous cent mots.

    Un texte qui ne donne ni date, ni nombre, ni nom reste en surplomb, et c'est
    ce qui le fait lire comme genere. Un nom propre est un mot a majuscule qui
    n'ouvre pas une phrase. L'indicateur reste hors du total des reperes.
    """
    mots = compter_mots(texte)
    if mots < MOTS_MIN_ANCRAGE:
        return None
    chiffres = len(CHIFFRE.findall(texte))
    noms = len(NOM_PROPRE.findall(texte.replace("’", "'")))
    return Ancrage(mots, chiffres, noms, chiffres * 1000 / mots, noms * 1000 / mots)


def paragraphes(texte: str) -> Optional[Paragraphes]:
    """Longueur des paragraphes et chutes, ou None sous trois paragraphes.

    Une chute est un paragraphe d'une phrase de moins de huit mots qui suit un
    paragraphe d'au moins quarante mots : l'effet de clausule des textes
    generes. Les intertitres et les listes ne comptent pas comme paragraphes.
    """
    blocs = [b for b in re.split(r"\n[ \t]*\n", texte)
             if compter_mots(b) and not re.match(r"[ \t\n\r]*(?:#|[-*•][ \t])", b)]
    if len(blocs) < PARAGRAPHES_MIN:
        return None
    longueurs = [compter_mots(b) for b in blocs]
    chutes = sum(
        1 for avant, n, bloc in zip(longueurs, longueurs[1:], blocs[1:])
        if avant >= CHUTE_APRES and n < CHUTE_MOTS
        and len([p for p in re.split(r"(?<=[.!?])\s+", bloc.strip()) if p]) == 1
    )
    return Paragraphes(len(longueurs), float(statistics.mean(longueurs)),
                       statistics.pstdev(longueurs), chutes)


def extrait(texte: str, debut: int, fin: int, marge: int = MARGE_EXTRAIT) -> str:
    """Passage sur une ligne, l'occurrence entre crochets dans son contexte."""
    def aplatir(s: str) -> str:
        return s.replace("\n", " ")

    avant = aplatir(texte[max(0, debut - marge):debut])
    apres = aplatir(texte[fin:fin + marge])
    return f"...{avant}[{aplatir(texte[debut:fin])}]{apres}..."


def afficher_tableau(noms: list[str], resultats: list[dict], motifs: list[dict]) -> None:
    """Un motif par ligne, un fichier par colonne, et les totaux."""
    largeur = max(len(m["nom"]) for m in motifs)
    entete = "".join(f"{nom[:LARGEUR_COLONNE - 1]:>{LARGEUR_COLONNE}}" for nom in noms)
    print(f"{'motif':<{largeur}}{entete}{'TOTAL':>{LARGEUR_TOTAL}}")
    for motif in motifs:
        comptes = [len(r[motif["id"]]) for r in resultats]
        colonnes = "".join(f"{c:>{LARGEUR_COLONNE}}" for c in comptes)
        print(f"{motif['nom']:<{largeur}}{colonnes}{sum(comptes):>{LARGEUR_TOTAL}}")
    totaux = [sum(len(v) for v in r.values()) for r in resultats]
    colonnes = "".join(f"{t:>{LARGEUR_COLONNE}}" for t in totaux)
    print(f"{'--- TOTAL / fichier ---':<{largeur}}{colonnes}{sum(totaux):>{LARGEUR_TOTAL}}")


def bilan(texte: str, resultat: dict, motifs: list[dict]) -> dict:
    """Comptes par niveau et densites pour 1000 mots.

    La densite "a reprendre" ne compte que les erreurs et les avertissements :
    c'est elle que --seuil compare.
    """
    mots = compter_mots(texte)
    par_niveau = {n: 0 for n in NIVEAUX}
    for motif in motifs:
        par_niveau[motif["niveau"]] += len(resultat[motif["id"]])
    total = sum(par_niveau.values())
    a_reprendre = par_niveau["erreur"] + par_niveau["avertissement"]
    return {
        "mots": mots,
        "reperes": total,
        "par_niveau": par_niveau,
        "pour_1000_mots": round(total * 1000 / mots, 1) if mots else 0.0,
        "a_reprendre_pour_1000_mots": round(a_reprendre * 1000 / mots, 1) if mots else 0.0,
    }


def afficher_bilans(noms: list[str], textes: list[str], bilans: list[dict], configs: list) -> None:
    for nom, texte, b, config in zip(noms, textes, bilans, configs):
        n = b["par_niveau"]
        print(f"densite {nom} : {b['pour_1000_mots']:g} reperes pour 1000 mots sur {b['mots']} mots ; "
              f"{n['erreur']} erreur(s), {n['avertissement']} avertissement(s), {n['info']} info(s)")
        r = rythme(texte)
        if r:
            print(f"rythme {nom} : {r.phrases} phrases, {r.moyenne:.0f} mots en moyenne, "
                  f"ecart-type {r.ecart_type:.0f} (plus il est faible, plus le texte est regulier)")
        a = ancrage(texte)
        if a:
            print(f"ancrage {nom} : {a.chiffres_pour_1000:.0f} chiffres et {a.noms_pour_1000:.0f} noms propres "
                  f"pour 1000 mots (plus ils sont rares, plus le texte reste en surplomb)")
        p = paragraphes(texte)
        if p:
            print(f"paragraphes {nom} : {p.nombre}, {p.moyenne:.0f} mots en moyenne, ecart-type "
                  f"{p.ecart_type:.0f}, {p.chutes} chute(s) d'une phrase courte apres un long paragraphe")
        if config:
            print(f"config {nom} : {config.chemin}")


def en_json(noms: list[str], textes: list[str], resultats: list[dict], bilans: list[dict],
            configs: list, motifs: list[dict]) -> str:
    """Un objet par fichier, occurrences avec ligne, colonne et extrait."""
    sortie = []
    for nom, texte, resultat, b, config in zip(noms, textes, resultats, bilans, configs):
        normalise = texte.replace("’", "'")
        occ = []
        for motif in motifs:
            source = texte if motif.get("brut") or motif.get("special") else normalise
            for o in resultat[motif["id"]]:
                debut_ligne = texte.rfind("\n", 0, o.start()) + 1
                occ.append({
                    "motif": motif["id"], "nom": motif["nom"], "famille": motif["famille"],
                    "niveau": motif["niveau"], "ligne": texte.count("\n", 0, o.start()) + 1,
                    "colonne": o.start() - debut_ligne + 1, "debut": o.start(), "fin": o.end(),
                    "texte": source[o.start():o.end()], "conseil": motif["conseil"],
                })
        occ.sort(key=lambda x: (x["debut"], x["fin"]))
        r, a, p = rythme(texte), ancrage(texte), paragraphes(texte)
        sortie.append(dict(
            fichier=nom, **b,
            rythme=r._asdict() if r else None,
            ancrage=a._asdict() if a else None,
            paragraphes=p._asdict() if p else None,
            config=config.chemin if config else None,
            occurrences=occ,
        ))
    return json.dumps(sortie, ensure_ascii=False, indent=2)


def depasse(bilans: list[dict], seuil: float) -> bool:
    """Vrai si un texte a une erreur ou plus de `seuil` reperes a reprendre pour 1000 mots."""
    return any(b["par_niveau"]["erreur"] or b["a_reprendre_pour_1000_mots"] > seuil for b in bilans)


def afficher_detail(noms: list[str], textes: list[str], resultats: list[dict], motifs: list[dict]) -> None:
    """Chaque occurrence avec son numero de ligne et son contexte."""
    largeur = max(len(m["nom"]) for m in motifs)
    for nom, texte, resultat in zip(noms, textes, resultats):
        print(f"\n=== {nom}")
        normalise = texte.replace("’", "'")
        for motif in motifs:
            source = texte if motif.get("brut") or motif.get("special") else normalise
            for o in resultat[motif["id"]]:
                ligne = texte.count("\n", 0, o.start()) + 1
                print(f"  l.{ligne:<4} {motif['nom']:<{largeur}}  {extrait(source, o.start(), o.end())}")


def analyser_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="linter_ia.py",
        description="Repere dans un texte francais les tournures d'ecriture IA.",
        epilog="Formats lus : .md, .txt, .docx. Le texte n'est jamais modifie.",
    )
    parser.add_argument("fichiers", nargs="+", metavar="fichier",
                        help='texte a relire, ou "-" pour l\'entree standard')
    parser.add_argument("--detail", action="store_true",
                        help="liste chaque passage avec son numero de ligne")
    parser.add_argument("--json", action="store_true",
                        help="sortie JSON : bilan et occurrences de chaque fichier")
    parser.add_argument("--seuil", type=float, metavar="N",
                        help="code de retour 1 si un texte a une erreur, ou plus de N erreurs "
                             "et avertissements pour 1000 mots")
    parser.add_argument("--config", metavar="FICHIER",
                        help=f"configuration a utiliser au lieu du {FICHIER_CONFIG} le plus proche")
    parser.add_argument("--sans-config", action="store_true",
                        help=f"ignorer tout fichier {FICHIER_CONFIG}")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = analyser_arguments(argv)
    try:
        motifs = charger_motifs()
        textes = [lire(f) for f in args.fichiers]
        if args.sans_config:
            chemins = [None] * len(args.fichiers)
        elif args.config:
            chemins = [args.config] * len(args.fichiers)
        else:
            chemins = [chercher_config(f) for f in args.fichiers]
        configs = [charger_config(c, motifs) if c else None for c in chemins]
    except ErreurLecture as e:
        print(f"linter_ia : {e}", file=sys.stderr)
        return 2
    noms = ["stdin" if f == "-" else os.path.basename(f) for f in args.fichiers]
    resultats = [appliquer_config(t, occurrences(t, motifs), c) for t, c in zip(textes, configs)]
    bilans = [bilan(t, r, motifs) for t, r in zip(textes, resultats)]
    if args.json:
        print(en_json(noms, textes, resultats, bilans, configs, motifs))
    else:
        afficher_tableau(noms, resultats, motifs)
        afficher_bilans(noms, textes, bilans, configs)
        if args.detail:
            afficher_detail(noms, textes, resultats, motifs)
    return 1 if args.seuil is not None and depasse(bilans, args.seuil) else 0


if __name__ == "__main__":
    sys.exit(main())
