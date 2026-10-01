// Moteur du linter pour la page web : meme logique que linter_ia.py, memes
// motifs (patterns.json). Aucun acces au DOM ni au reseau. Charge tel quel par
// node dans tests/test_linter.py, qui verifie que le script et la page trouvent
// les memes passages aux memes positions.
(function (exporter) {
  "use strict";
  var L = "A-Za-zÀ-ÿœŒ";
  var MOT = "[" + L + "0-9_]";
  // \b et \w sont ASCII en JavaScript, Unicode en Python : on les remplace
  var LIMITE = "(?:(?<=" + MOT + ")(?!" + MOT + ")|(?<!" + MOT + ")(?=" + MOT + "))";
  var APOS_COURBE = new RegExp("(?<=[" + L + "])’(?=[" + L + "])", "g");
  var APOS_DROITE = new RegExp("(?<=[" + L + "])'(?=[" + L + "])", "g");
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

  function occurrences(texte, motifs) {
    var n = texte.replace(/’/g, "'");
    var occ = {};
    motifs.forEach(function (m) {
      if (m.special === "apostrophes") {
        // on signale le type minoritaire, comme le script
        var c = positions(APOS_COURBE, texte), d = positions(APOS_DROITE, texte);
        occ[m.id] = c.length && d.length ? (c.length <= d.length ? c : d) : [];
      } else {
        occ[m.id] = positions(m.rx, m.brut ? texte : n);
      }
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

  exporter({ compiler: compiler, occurrences: occurrences, rythme: rythme });
})(typeof module !== "undefined"
  ? function (api) { module.exports = api; }
  : function (api) { window.LinterIA = api; });
