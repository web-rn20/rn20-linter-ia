#!/usr/bin/env python3
"""Tests du linter : comptes attendus sur les fixtures, lecture des .docx, ligne
de commande, parite entre le script et la page (moteur.js execute par node),
page generee a jour.

Usage : python3 tests/test_linter.py
Un compte attendu qui change s'explique dans le message de commit.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import linter_ia, build_web

FIX = os.path.join(RACINE, "tests", "fixtures")
MOTIFS = linter_ia.charger_motifs()

ATTENDUS = {
    "bords-accents.md": {
        "tirets_longs": 1, "guillemets_typographiques": 2, "gras_markdown": 1, "puces": 1,
        "titres": 1, "deux_points_explicatifs": 1, "puis_puis": 1, "pas_x_mais_y": 1,
        "ce_n_est_pas": 2, "chute_pour_que": 1, "devient_un_outil": 1, "questions": 1,
        "imperatifs": 1, "selon": 1, "il_faut": 1, "vrai": 2, "signal": 1, "utile": 1,
        "enjeu": 1, "de_x_a_y": 1, "agent": 1, "apostrophes_melangees": 3,
    },
    "cas-corriges.md": {"imperatifs": 1, "utile": 2, "de_x_a_y": 1},
    "exclusions-et-densite.md": {"selon": 2, "il_faut": 2, "connecteurs": 3, "egalement_notamment": 3},
    "exemple-ia.md": {
        "deux_points_explicatifs": 1, "anaphores": 1, "puis_puis": 1, "pas_x_mais_y": 1,
        "ce_n_est_pas": 1, "comme_les_autres": 1, "chute_pour_que": 1, "devient_un_outil": 1,
        "questions": 1, "appel_direct": 1, "il_faut": 1, "promesse": 1, "concret": 1,
        "de_x_a_y": 1, "apostrophes_melangees": 1,
    },
    "paragraphes-et-ancrage.md": {"puces": 1, "titres": 1},
    "texte-sobre.md": {"tricolons": 1, "surtout": 1},
    "tics-generation.md": {
        "residus_conversation": 2, "residus_techniques": 5, "pictogrammes": 5, "filets": 1,
        "questions": 1, "appel_direct": 1, "insistance": 1, "decor_epoque": 1, "cloture_recap": 1,
        "participe_apposition": 1, "inflation_portee": 3, "non_seulement": 1,
        "defis_perspectives": 2, "attribution_vague": 1, "intensifs": 2, "promotionnel": 2,
        "calques_anglais": 2, "plonger": 1,
    },
    "voisins-sans-alerte.md": {},
}

def comptes(texte):
    return {k: len(v) for k, v in linter_ia.occurrences(texte, MOTIFS).items() if v}

def lire(*chemin):
    with open(os.path.join(RACINE, *chemin), encoding="utf-8") as f:
        return f.read()

def textes_fixtures():
    return {nom: linter_ia.lire(os.path.join(FIX, nom)) for nom in sorted(os.listdir(FIX))}

class Comptes(unittest.TestCase):
    def test_chaque_fixture_a_ses_comptes(self):
        self.assertEqual(sorted(ATTENDUS), sorted(os.listdir(FIX)))
        for nom, texte in textes_fixtures().items():
            with self.subTest(nom):
                self.assertEqual(comptes(texte), ATTENDUS[nom])

    def test_motifs_bien_formes(self):
        ids = [m["id"] for m in MOTIFS]
        self.assertEqual(len(ids), len(set(ids)))
        for m in MOTIFS:
            self.assertIn(m["famille"], {"residu", "structure", "mot", "typo"}, m["id"])
            self.assertTrue(m["nom"] and m["conseil"], m["id"])
            self.assertIn(m["niveau"], linter_ia.NIVEAUX, m["id"])

class Lecture(unittest.TestCase):
    def test_front_matter_remplace_par_des_lignes_vides(self):
        self.assertEqual(linter_ia.retirer_front_matter("---\ntitre: x\n---\nCorps"), "\n\n\nCorps")

    def test_filet_en_tete_n_est_pas_un_front_matter(self):
        texte = "---\n\nIntro : il est important de noter.\n\n---\n\nCorps."
        self.assertEqual(linter_ia.retirer_front_matter(texte), texte)

    def test_marque_d_ordre_d_octets_retiree(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "bom.md")
            with open(chemin, "w", encoding="utf-8-sig") as f:
                f.write("Texte.")
            self.assertEqual(linter_ia.lire(chemin), "Texte.")

class Ancrage(unittest.TestCase):
    def test_chiffres_noms_et_chute(self):
        texte = linter_ia.lire(os.path.join(FIX, "paragraphes-et-ancrage.md"))
        a, p = linter_ia.ancrage(texte), linter_ia.paragraphes(texte)
        self.assertEqual((a.chiffres, a.noms_propres), (5, 6))
        self.assertEqual((p.nombre, p.chutes), (3, 1))

    def test_texte_court_sans_mesure(self):
        self.assertIsNone(linter_ia.ancrage("Le chai ouvre à Gaillac le 2 septembre."))
        self.assertIsNone(linter_ia.paragraphes("Un.\n\nDeux."))


class Exclusions(unittest.TestCase):
    def test_off_cible_et_texte_du_commentaire(self):
        texte = "<!-- linter-ia off selon -->Selon elle, il faut voir.<!-- linter-ia on selon --> Selon lui."
        c = comptes(texte)
        self.assertEqual((c.get("selon"), c.get("il_faut")), (1, 1))

    def test_off_sans_on_court_jusqu_a_la_fin(self):
        self.assertEqual(comptes("Il faut voir. <!-- linter-ia off --> Il faut partir, selon elle."),
                         {"il_faut": 1})

    def test_seuil_de_densite_sous_deux_occurrences(self):
        self.assertEqual(comptes("Le site est également refait."), {})


class Configuration(unittest.TestCase):
    def ecrire(self, dossier, nom, contenu):
        chemin = os.path.join(dossier, nom)
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)
        return chemin

    def test_config_cherchee_dans_les_dossiers_parents(self):
        with tempfile.TemporaryDirectory() as d:
            self.ecrire(d, ".linter-ia.json", "{}")
            os.mkdir(os.path.join(d, "sous"))
            texte = self.ecrire(os.path.join(d, "sous"), "t.md", "x")
            self.assertEqual(linter_ia.chercher_config(texte), os.path.join(d, ".linter-ia.json"))

    def test_accepter_et_ignorer(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = self.ecrire(d, "c.json", '{"accepter": ["agents de la DGAL"], "ignorer": ["selon"]}')
            config = linter_ia.charger_config(chemin, MOTIFS)
        texte = "Le rapport des agents de la DGAL à la préfecture, selon elle. Un agent passe."
        resultat = linter_ia.appliquer_config(texte, linter_ia.occurrences(texte, MOTIFS), config)
        c = {k: len(v) for k, v in resultat.items() if v}
        self.assertEqual(c, {"agent": 1})

    def test_erreurs_nomment_le_champ(self):
        with tempfile.TemporaryDirectory() as d:
            cas = {'{"accepte": []}': 'cle inconnue "accepte"',
                   '{"ignorer": ["inconnu"]}': "motif inconnu, 'inconnu'",
                   '{"accepter": "agents"}': '"accepter" doit etre une liste',
                   "[1": "configuration illisible"}
            for contenu, message in cas.items():
                with self.subTest(contenu):
                    chemin = self.ecrire(d, "c.json", contenu)
                    with self.assertRaises(linter_ia.ErreurLecture) as e:
                        linter_ia.charger_config(chemin, MOTIFS)
                    self.assertIn(message, str(e.exception))


class Docx(unittest.TestCase):
    def test_lecture_sans_dependance(self):
        xml = ('<w:document xmlns:w="w"><w:body>'
               '<w:p><w:pPr><w:pStyle w:val="Titre2"/></w:pPr><w:r><w:t>Notre approche</w:t></w:r></w:p>'
               '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr><w:r><w:t>une puce</w:t></w:r></w:p>'
               '<w:p><w:r><w:instrText> TOC \\o </w:instrText></w:r><w:r><w:t xml:space="preserve">Ce n&apos;est pas </w:t></w:r>'
               '<w:del><w:r><w:delText>efface</w:delText></w:r></w:del><w:r><w:t>un outil, c&apos;est un levier.</w:t></w:r></w:p>'
               '</w:body></w:document>')
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "essai.docx")
            with zipfile.ZipFile(chemin, "w") as z:
                z.writestr("word/document.xml", xml)
            texte = linter_ia.lire(chemin)
        self.assertEqual(texte, "## Notre approche\n- une puce\nCe n'est pas un outil, c'est un levier.")
        c = comptes(texte)
        self.assertEqual((c.get("titres"), c.get("puces"), c.get("ce_n_est_pas")), (1, 1, 1))

class LigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = linter_ia.main(list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def test_tableau_et_detail(self):
        code, sortie, _ = self.lancer("--detail", os.path.join(FIX, "texte-sobre.md"))
        self.assertEqual(code, 0)
        self.assertIn("--- TOTAL / fichier ---", sortie)
        self.assertIn("=== texte-sobre.md", sortie)
        self.assertIn("[surtout]", sortie)

    def test_fichier_introuvable(self):
        code, sortie, erreur = self.lancer("absent.md")
        self.assertEqual((code, sortie), (2, ""))
        self.assertIn("absent.md : fichier introuvable", erreur)

    def test_fichier_qui_n_est_pas_du_texte(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "binaire.pdf")
            with open(chemin, "wb") as f:
                f.write(b"%PDF-1.7\n\xff\xfe\x00")
            code, _, erreur = self.lancer(chemin)
        self.assertEqual(code, 2)
        self.assertIn("pas un texte UTF-8", erreur)

    def test_docx_illisible(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "faux.docx")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("pas une archive")
            code, _, erreur = self.lancer(chemin)
        self.assertEqual(code, 2)
        self.assertIn("fichier .docx illisible", erreur)

    def test_json(self):
        code, sortie, _ = self.lancer("--json", "--sans-config", os.path.join(FIX, "texte-sobre.md"))
        self.assertEqual(code, 0)
        donnees = json.loads(sortie)
        self.assertEqual(donnees[0]["reperes"], 2)
        self.assertEqual(donnees[0]["par_niveau"], {"erreur": 0, "avertissement": 0, "info": 2})
        premiere = donnees[0]["occurrences"][0]
        self.assertEqual((premiere["motif"], premiere["ligne"], premiere["texte"]), ("surtout", 1, "surtout"))

    def test_seuil(self):
        sobre = os.path.join(FIX, "texte-sobre.md")
        residus = os.path.join(FIX, "tics-generation.md")
        self.assertEqual(self.lancer("--seuil", "5", "--sans-config", sobre)[0], 0)
        self.assertEqual(self.lancer("--seuil", "1000", "--sans-config", residus)[0], 1)
        self.assertEqual(self.lancer("--sans-config", residus)[0], 0)

    def test_config_invalide(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "c.json")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write('{"ignorer": ["inconnu"]}')
            code, _, erreur = self.lancer("--config", chemin, os.path.join(FIX, "texte-sobre.md"))
        self.assertEqual(code, 2)
        self.assertIn("inconnu", erreur)

    def test_extrait_sur_une_ligne(self):
        texte = "premiere ligne\nseconde ligne"
        self.assertEqual(linter_ia.extrait(texte, 9, 20, marge=5), "...iere [ligne\nsecon]de li...".replace("\n", " "))


@unittest.skipUnless(shutil.which("node"), "node absent : parite script / page non verifiee")
class Parite(unittest.TestCase):
    JS = r"""
const api = require(process.argv[1]);
const motifs = api.compiler(require(process.argv[2]));
const textes = JSON.parse(require("fs").readFileSync(0, "utf8"));
// positions JavaScript en unites UTF-16, ramenees en caracteres comme en Python
const car = (t, i) => Array.from(t.slice(0, i)).length;
const out = {};
for (const [nom, t] of Object.entries(textes)) {
  const occ = api.occurrences(t, motifs);
  const r = api.rythme(t), a = api.ancrage(t), p = api.paragraphes(t);
  out[nom] = {
    ancrage: a && [a.chiffres, a.nomsPropres],
    paragraphes: p && [p.nombre, p.moyenne, p.ecartType, p.chutes],
    occ: Object.fromEntries(Object.entries(occ).map(([k, v]) => [k, v.map(o => [car(t, o.debut), car(t, o.fin)])])),
    rythme: r && [r.phrases, r.moyenne, r.ecartType],
  };
}
console.log(JSON.stringify(out));
"""

    def test_script_et_page_trouvent_les_memes_passages(self):
        textes = textes_fixtures()
        sortie = subprocess.run(
            ["node", "-e", self.JS, os.path.join(RACINE, "web", "moteur.js"), os.path.join(RACINE, "patterns.json")],
            input=json.dumps(textes), capture_output=True, text=True, check=True).stdout
        js = json.loads(sortie)
        for nom, texte in textes.items():
            occ = linter_ia.occurrences(texte, MOTIFS)
            for m in MOTIFS:
                with self.subTest(fixture=nom, motif=m["id"]):
                    self.assertEqual([[o.start(), o.end()] for o in occ[m["id"]]], js[nom]["occ"][m["id"]])
            a, p = linter_ia.ancrage(texte), linter_ia.paragraphes(texte)
            with self.subTest(fixture=nom, ancrage=True):
                self.assertEqual(a and [a.chiffres, a.noms_propres], js[nom]["ancrage"])
            with self.subTest(fixture=nom, paragraphes=True):
                if p is None:
                    self.assertIsNone(js[nom]["paragraphes"])
                else:
                    self.assertEqual([p.nombre, p.chutes], [js[nom]["paragraphes"][0], js[nom]["paragraphes"][3]])
                    self.assertAlmostEqual(p.moyenne, js[nom]["paragraphes"][1])
                    self.assertAlmostEqual(p.ecart_type, js[nom]["paragraphes"][2])
            r = linter_ia.rythme(texte)
            with self.subTest(fixture=nom, rythme=True):
                if r is None:
                    self.assertIsNone(js[nom]["rythme"])
                else:
                    self.assertEqual(r.phrases, js[nom]["rythme"][0])
                    self.assertAlmostEqual(r.moyenne, js[nom]["rythme"][1])
                    self.assertAlmostEqual(r.ecart_type, js[nom]["rythme"][2])

class PageGeneree(unittest.TestCase):
    def test_page_a_jour(self):
        page = lire("web", "linter-ia.html")
        self.assertEqual(page, build_web.generer(complet=True),
                         "web/linter-ia.html n'est pas a jour : lancer python3 build_web.py")

    def test_exemple_de_la_page_identique_a_la_fixture(self):
        page = lire("web", "page.html")
        debut = page.index('<script type="text/plain" id="exemple">') + len('<script type="text/plain" id="exemple">')
        exemple = page[debut:page.index("</script>", debut)]
        self.assertEqual(exemple + "\n", lire("tests", "fixtures", "exemple-ia.md"))

if __name__ == "__main__":
    unittest.main(verbosity=1)
