#!/usr/bin/env python3
"""Assemble la page web autonome a partir de web/page.html, web/moteur.js et patterns.json.

Usage :
    python3 build_web.py             ecrit web/linter-ia.html, document complet,
                                     a ouvrir dans un navigateur (publie sur GitHub Pages)
    python3 build_web.py --artifact  ecrit dist/artifact.html, corps seul, pour un
                                     hebergeur qui fournit son propre squelette HTML

A relancer apres toute modification de patterns.json, web/page.html ou web/moteur.js.
La page generee ne charge aucune ressource externe.
"""
from __future__ import annotations

import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
DESCRIPTION = ("Repère dans un texte en français les tournures que les lecteurs associent "
               "aux IA, avec pour chacune une façon de la reprendre. Le texte ne quitte pas "
               "le navigateur.")
FIN_TETE = "</style>"


def lire(*chemin: str) -> str:
    with open(os.path.join(ICI, *chemin), encoding="utf-8") as f:
        return f.read()


def generer(complet: bool = True) -> str:
    """Page avec les motifs et le moteur incorpores.

    complet=True : document HTML entier, titre et styles dans <head>.
    complet=False : contenu de web/page.html seul, tel quel.
    """
    motifs = json.loads(lire("patterns.json"))
    # "<" echappe : aucune sequence ne peut fermer la balise <script> qui porte les motifs
    motifs_json = json.dumps(motifs, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    page = (lire("web", "page.html")
            .replace("/*MOTIFS*/", motifs_json)
            .replace("/*MOTEUR*/", lire("web", "moteur.js")))
    if not complet:
        return page
    coupure = page.index(FIN_TETE) + len(FIN_TETE)
    tete, corps = page[:coupure], page[coupure:].lstrip("\n")
    return (
        "<!doctype html>\n<html lang=\"fr\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        f"<meta name=\"description\" content=\"{DESCRIPTION}\">\n"
        f"{tete}\n</head>\n<body>\n{corps}</body>\n</html>\n"
    )


def main(argv: list[str]) -> int:
    if "--artifact" in argv:
        os.makedirs(os.path.join(ICI, "dist"), exist_ok=True)
        cible, contenu = os.path.join(ICI, "dist", "artifact.html"), generer(complet=False)
    else:
        cible, contenu = os.path.join(ICI, "web", "linter-ia.html"), generer(complet=True)
    with open(cible, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"ecrit : {os.path.relpath(cible, ICI)} ({len(contenu) // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
