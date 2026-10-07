// Moteur du linter pour la page web : meme logique que linter_ia.py, memes
// motifs (patterns.json). Aucun acces au DOM ni au reseau. Charge tel quel par
// node dans tests/test_linter.py, qui verifie que le script et la page trouvent
// les memes passages aux memes positions.
(function (exporter) {
  "use strict";
  var L = "A-Za-zÀ-ÖØ-öø-ÿœŒ";
  var MOT = "[" + L + "0-9_]";
  // \b et \w sont ASCII en JavaScript, Unicode en Python : on les remplace
  var LIMITE = "(?:(?<=" + MOT + ")(?!" + MOT + ")|(?<!" + MOT + ")(?=" + MOT + "))";
  var APOS_COURBE = new RegExp("(?<=[" + L + "])’(?=[" + L + "])", "g");
  var APOS_DROITE = new RegExp("(?<=[" + L + "])'(?=[" + L + "])", "g");
  // Blancs comptes de la meme facon que linter_ia.py : \s differe entre les deux langages
  var MOT_DU_TEXTE = /[^ \t\n\r\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g;
  var DIRECTIVE = /<!--[ \t]*linter-ia[ \t]+(off|on)((?:[ \t]+[a-z0-9_]+)*)[ \t]*-->/gi;
  // Un motif a seuil ("densite_max", pour 1000 mots) ne sort qu'a partir de deux occurrences
  var MIN_OCCURRENCES_DENSITE = 2;
  var PHRASES_MIN_RYTHME = 5;

  function compiler(motifs) {
    return motifs.map(function (m) {
      if (!m.regex) return m;
      var src = m.regex.replace(/\\b/g, LIMITE).replace(/\\w/g, MOT);
      return Object.assign({}, m, { rx: new RegExp(src, "g" + (m.flags || "")) });
    });
  }

  function positions(rx, texte) {
    var out = [];
    for (var m of texte.matchAll(rx)) out.push({ debut: m.index, fin: m.index + m[0].length });
    return out;
  }

  function compterMots(texte) {
    return (texte.match(MOT_DU_TEXTE) || []).length;
  }

  function directives(texte) {
    var out = [];
    for (var m of texte.matchAll(DIRECTIVE)) {
      var ids = m[2].trim();
      out.push({ debut: m.index, fin: m.index + m[0].length, off: m[1].toLowerCase() === "off",
                 ids: ids ? ids.toLowerCase().split(/[ \t]+/) : [] });
    }
    return out;
  }

  // "off" seul coupe tout, "on" seul retablit tout ; avec des identifiants,
  // seuls ces motifs sont coupes ou retablis. Le texte du commentaire lui-meme
  // n'est jamais lu. Meme regle que le script.
  function actif(dirs, id, position) {
    var tout = true, coupes = {};
    for (var i = 0; i < dirs.length; i++) {
      var d = dirs[i];
      if (d.debut <= position && position < d.fin) return false;
      if (d.fin > position) break;
      if (!d.ids.length) {
        tout = !d.off;
        if (!d.off) coupes = {};
      } else {
        d.ids.forEach(function (x) { if (d.off) coupes[x] = true; else delete coupes[x]; });
      }
    }
    return tout && !coupes[id];
  }

  function occurrences(texte, motifs) {
    var n = texte.replace(/’/g, "'");
    var dirs = directives(texte), mots = compterMots(texte);
    var occ = {};
    motifs.forEach(function (m) {
      var trouves;
      if (m.special === "apostrophes") {
        // on signale le type minoritaire, comme le script
        var c = positions(APOS_COURBE, texte), d = positions(APOS_DROITE, texte);
        trouves = c.length && d.length ? (c.length <= d.length ? c : d) : [];
      } else {
        trouves = positions(m.rx, m.brut ? texte : n);
      }
      trouves = trouves.filter(function (o) { return actif(dirs, m.id, o.debut); });
      if ("densite_max" in m && !(trouves.length >= MIN_OCCURRENCES_DENSITE &&
          trouves.length * 1000 / mots > m.densite_max)) trouves = [];
      occ[m.id] = trouves;
    });
    return occ;
  }

  function rythme(texte) {
    var phrases = texte.replace(/\s+/g, " ").split(/(?<=[.!?])\s+/).filter(function (p) {
      return p.trim().split(/\s+/).filter(Boolean).length > 2;
    });
    if (phrases.length < PHRASES_MIN_RYTHME) return null;
    var lg = phrases.map(function (p) { return p.trim().split(/\s+/).length; });
    var moy = lg.reduce(function (a, b) { return a + b; }, 0) / lg.length;
    var variance = lg.reduce(function (a, b) { return a + (b - moy) * (b - moy); }, 0) / lg.length;
    return { phrases: lg.length, longueurs: lg, moyenne: moy, ecartType: Math.sqrt(variance) };
  }

  exporter({ compiler: compiler, occurrences: occurrences, rythme: rythme, compterMots: compterMots });
})(typeof module !== "undefined"
  ? function (api) { module.exports = api; }
  : function (api) { window.LinterIA = api; });
