#!/usr/bin/env python3
"""Banc d'essai du linter : densite de reperes sur des textes humains et generes.

Cote humain, des articles de Wikipedia en francais dans leur version d'octobre
2022, avant la sortie de ChatGPT. Le depot ne garde que leurs identifiants de
revision (banc/corpus.json) : les textes sont sous licence CC BY-SA et se
retelechargent dans banc/cache/, que git ignore. Cote genere, chaque dossier de
banc/genere/ est un modele, avec un texte .md par sujet.

    python3 outils/banc.py telecharger   # seul appel reseau, vers fr.wikipedia.org
    python3 outils/banc.py mesurer       # tableau markdown pour le README

Le linter lui-meme ne fait aucun appel reseau ; ce script est un outil de
mesure a part, qui ne lit et n'envoie aucun texte de l'utilisateur.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request
from collections import Counter
from typing import Optional

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import linter_ia  # noqa: E402

BANC = os.path.join(RACINE, "banc")
CORPUS = os.path.join(BANC, "corpus.json")
CACHE = os.path.join(BANC, "cache", "wikipedia")
GENERE = os.path.join(BANC, "genere")
API = "https://fr.wikipedia.org/w/api.php"
AGENT = "rn20-linter-ia-banc/1.0 (https://github.com/web-rn20/rn20-linter-ia)"
# Paragraphes plus courts ignores : legendes, notes, lignes de tableau
MOTS_MIN_PARAGRAPHE = 15
MOTIFS_AFFICHES = 8


def charger_corpus() -> dict:
    with open(CORPUS, encoding="utf-8") as f:
        return json.load(f)


def nom_fichier(titre: str) -> str:
    return re.sub(r"\W+", "-", titre.lower()).strip("-") + ".md"


def texte_de_revision(oldid: int) -> str:
    """Prose d'une revision : les paragraphes <p> du rendu, sans appels de note."""
    url = API + "?" + urllib.parse.urlencode(
        {"action": "parse", "oldid": oldid, "prop": "text", "format": "json", "formatversion": 2})
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        rendu = json.load(reponse)["parse"]["text"]
    paragraphes = []
    for p in re.findall(r"<p>(.*?)</p>", rendu, flags=re.S):
        p = re.sub(r"<sup\b.*?</sup>", "", p, flags=re.S)
        p = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
        if len(p.split()) >= MOTS_MIN_PARAGRAPHE:
            paragraphes.append(p)
    return "\n\n".join(paragraphes) + "\n"


def telecharger(corpus: dict) -> None:
    os.makedirs(CACHE, exist_ok=True)
    for entree in corpus["humain"]["textes"]:
        chemin = os.path.join(CACHE, nom_fichier(entree["titre"]))
        if os.path.exists(chemin):
            continue
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(texte_de_revision(entree["oldid"]))
        print(f"lu : {entree['titre']} (revision {entree['oldid']})")


def groupes(corpus: dict) -> list[tuple[str, list[str]]]:
    """(nom du groupe, fichiers) : Wikipedia d'abord, puis un groupe par modele."""
    humains = [os.path.join(CACHE, nom_fichier(e["titre"])) for e in corpus["humain"]["textes"]]
    manquants = [c for c in humains if not os.path.exists(c)]
    if manquants:
        sys.exit(f"{len(manquants)} texte(s) absents de banc/cache : lancer d'abord "
                 "python3 outils/banc.py telecharger")
    sortie = [(corpus["humain"]["nom"], humains)]
    if os.path.isdir(GENERE):
        for modele in sorted(os.listdir(GENERE)):
            dossier = os.path.join(GENERE, modele)
            fichiers = sorted(os.path.join(dossier, f) for f in os.listdir(dossier) if f.endswith(".md"))
            if fichiers:
                sortie.append((modele, fichiers))
    return sortie


def mesurer_groupe(fichiers: list[str], motifs: list[dict], seuil: float) -> dict:
    a_reprendre, mots_total, au_dessus = [], 0, 0
    par_motif: Counter = Counter()
    for chemin in fichiers:
        texte = linter_ia.lire(chemin)
        resultat = linter_ia.occurrences(texte, motifs)
        b = linter_ia.bilan(texte, resultat, motifs)
        mots_total += b["mots"]
        a_reprendre.append(b["a_reprendre_pour_1000_mots"])
        au_dessus += linter_ia.depasse([b], seuil)
        for id_motif, trouves in resultat.items():
            par_motif[id_motif] += len(trouves)
    return {"textes": len(fichiers), "mots": mots_total,
            "mediane": statistics.median(a_reprendre), "maximum": max(a_reprendre),
            "au_dessus": au_dessus, "par_motif": par_motif}


def nombre(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def mesurer(corpus: dict, seuil: Optional[float]) -> None:
    motifs = linter_ia.charger_motifs()
    noms = {m["id"]: m["nom"] for m in motifs}
    niveaux = {m["id"]: m["niveau"] for m in motifs}
    seuil = corpus["seuil"] if seuil is None else seuil
    mesures = [(nom, mesurer_groupe(fichiers, motifs, seuil)) for nom, fichiers in groupes(corpus)]

    print(f"| Source | Textes | Mots | Médiane à reprendre / 1000 mots | Maximum | Au-dessus de {nombre(seuil)} |")
    print("|---|---:|---:|---:|---:|---:|")
    for nom, m in mesures:
        mots = f"{m['mots']:,}".replace(",", " ")
        print(f"| {nom} | {m['textes']} | {mots} | {nombre(m['mediane'])} | "
              f"{nombre(m['maximum'])} | {m['au_dessus']} sur {m['textes']} |")

    # motifs les plus frequents, en occurrences pour 1000 mots, erreurs et avertissements seulement
    total: Counter = Counter()
    for _, m in mesures:
        for id_motif, n in m["par_motif"].items():
            if niveaux[id_motif] != "info":
                total[id_motif] += n * 1000 / m["mots"]
    print()
    print("| Motif | " + " | ".join(nom for nom, _ in mesures) + " |")
    print("|---|" + "---:|" * len(mesures))
    for id_motif, densite in total.most_common(MOTIFS_AFFICHES):
        if densite < 0.05:
            break
        cellules = [nombre(m["par_motif"][id_motif] * 1000 / m["mots"]) for _, m in mesures]
        print(f"| {noms[id_motif]} | " + " | ".join(cellules) + " |")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    sous.add_parser("telecharger", help="retelecharge les textes Wikipedia dans banc/cache/")
    m = sous.add_parser("mesurer", help="affiche les tableaux du README")
    m.add_argument("--seuil", type=float, help="seuil de --seuil compare (defaut : banc/corpus.json)")
    args = parser.parse_args(argv)
    corpus = charger_corpus()
    if args.commande == "telecharger":
        telecharger(corpus)
    else:
        mesurer(corpus, args.seuil)
    return 0


if __name__ == "__main__":
    sys.exit(main())
