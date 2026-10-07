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

__version__ = "0.2.0"

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER_MOTIFS = os.path.join(ICI, "patterns.json")

# Lettres du francais : bornes des apostrophes, comme dans web/moteur.js
LETTRES = "A-Za-zÀ-ÖØ-öø-ÿœŒ"
# "u" sert a JavaScript (emojis hors du plan de base) ; Python lit deja l'Unicode
DRAPEAUX = {"i": re.IGNORECASE, "m": re.MULTILINE, "u": 0}
APOS_COURBE = re.compile(rf"(?<=[{LETTRES}])’(?=[{LETTRES}])")
APOS_DROITE = re.compile(rf"(?<=[{LETTRES}])'(?=[{LETTRES}])")

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


def charger_motifs(chemin: str = FICHIER_MOTIFS) -> list[dict]:
    """Charge les motifs et compile leur regex (cle "rx")."""
    with open(chemin, encoding="utf-8") as f:
        motifs = json.load(f)
    for motif in motifs:
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


def occurrences(texte: str, motifs: list[dict]) -> dict[str, list[re.Match]]:
    """Occurrences de chaque motif dans le texte, par identifiant de motif.

    Les motifs lisent le texte aux apostrophes courbes normalisees, sauf ceux
    marques "brut". La normalisation remplace un caractere par un autre : les
    positions restent valables dans le texte d'origine.
    """
    normalise = texte.replace("’", "'")
    resultat = {}
    for motif in motifs:
        if motif.get("special") == "apostrophes":
            resultat[motif["id"]] = apostrophes_minoritaires(texte)
        else:
            source = texte if motif.get("brut") else normalise
            resultat[motif["id"]] = list(motif["rx"].finditer(source))
    return resultat


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


def afficher_rythmes(noms: list[str], textes: list[str]) -> None:
    for nom, texte in zip(noms, textes):
        r = rythme(texte)
        if r:
            print(f"rythme {nom} : {r.phrases} phrases, {r.moyenne:.0f} mots en moyenne, "
                  f"ecart-type {r.ecart_type:.0f} (plus il est faible, plus le texte est regulier)")


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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = analyser_arguments(argv)
    try:
        motifs = charger_motifs()
        textes = [lire(f) for f in args.fichiers]
    except ErreurLecture as e:
        print(f"linter_ia : {e}", file=sys.stderr)
        return 2
    noms = ["stdin" if f == "-" else os.path.basename(f) for f in args.fichiers]
    resultats = [occurrences(t, motifs) for t in textes]
    afficher_tableau(noms, resultats, motifs)
    afficher_rythmes(noms, textes)
    if args.detail:
        afficher_detail(noms, textes, resultats, motifs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
