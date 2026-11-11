"""Les réglages propres à notre banquet, par-dessus CHIMERA (testé sur le commit 1d3ea49).

CHIMERA sait déjà, de lui-même : les marques IPA (nasalisation par tilde, ˭ / ʰ, ʲ, ʱ, depuis le
ticket #32), /ɥ/, et chanter des syllabes données en JSON (`"syllables"` dans `render notes` et dans
les fichiers mélodie de la page Duet ; docs/language-front-ends.md). Ce patch ajoute :
 - une voyelle nasale moins ouverte : 0,15 cm² au lieu de 0,3 (le chœur sonnait nasillard), et
   0,25 sur les voyelles ouvertes (le « an » s'entendait « a ») ;
 - le chant :
   - une consonne de durée donnée (« lː ») garde sa durée ;
   - la respiration entre deux phrases laisse la place aux consonnes d'attaque de la suivante
     (le « L' » de « L'eau ») ;
   - dans une note courte, la voyelle garde au moins 55 % du temps (« dis-courir ») ;
 - `render speech` : CHIMERA_F0 (Hz) change la hauteur de la voix parlée.
Usage : python tools/patch_chimera.py <dossier chimera>   (idempotent, sur un CHIMERA propre)
"""
import sys, pathlib

root = pathlib.Path(sys.argv[1])


def patch(rel, pairs):
    p = root / rel
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        if new in s:
            continue  # déjà appliqué
        n = s.count(old)
        if n != 1:
            sys.exit(f"{rel}: motif trouvé {n} fois : {old[:70]!r}")
        s = s.replace(old, new)
    with open(p, "w", encoding="utf-8", newline="\n") as f:  # LF, comme le .gitattributes de CHIMERA
        f.write(s)
    print("ok", rel)


PH = "crates/chimera/src/phonetics/"

patch(PH + "planner.rs", [
    ("""const NASAL_VOWEL_PORT: f64 = 0.3;""",
     """const NASAL_VOWEL_PORT: f64 = 0.15; // chimeraboire : à 0,3 un chœur français sonnait nasillard
/// an open vowel needs a wider port to be heard as nasal (the French « an » sounded oral at 0.15)
const NASAL_OPEN_VOWEL_PORT: f64 = 0.25;"""),
    ("""one(ArticKey::Velum, NASAL_VOWEL_PORT)).label("velum"));""",
     """one(ArticKey::Velum, if s.ipa.starts_with(['a', 'ɑ', 'ɒ', 'æ', 'ɐ']) { NASAL_OPEN_VOWEL_PORT } else { NASAL_VOWEL_PORT })).label("velum"));"""),
])

patch(PH + "sing.rs", [
    # dans une note courte, la voyelle garde au moins 55 % du temps et les consonnes se serrent dans
    # le reste, comme le fait un chanteur : sinon « dis- » (une croche) donnait 70 ms de [i] et
    # 150 ms de [s], « disssscourir »
    ("""    let room = span - MIN_VOWEL;""",
     """    let room = span - js_max(MIN_VOWEL, SUNG_VOWEL_SHARE * span);"""),
    ("""const MIN_VOWEL: f64 = 0.05;""",
     """const MIN_VOWEL: f64 = 0.05;
/// and at least this share of its span (chimeraboire)
const SUNG_VOWEL_SHARE: f64 = 0.55;"""),
    # une consonne de durée donnée (« lː ») garde sa durée : un « L' » en début de phrase chanté à la
    # durée par défaut passait inaperçu
    ("""    segs.iter().map(|c| Segment { ipa: c.ipa.clone(), dur: Some(cdur(&c.ipa, body, k)), aspirated""",
     """    segs.iter().map(|c| Segment { ipa: c.ipa.clone(), dur: Some(c.dur.map_or(cdur(&c.ipa, body, k), |d| js_max(d, cdur(&c.ipa, body, k)))), aspirated"""),
    # la respiration entre deux phrases laisse aussi la place aux consonnes d'attaque de la phrase
    # suivante (chantées avant le temps) : sans quoi le « L' » de « L'eau » tombait dans
    # l'expiration de la phrase d'avant, cordes écartées, et ne sonnait pas
    ("""        let reserve = if j == notes.len() - 1 { 0.05 } else { 0.12 };""",
     """        let reserve = if j == notes.len() - 1 {
            0.05
        } else if melisma(&notes[j + 1].syl) {
            0.12
        } else {
            0.12 + 0.06 + total(&consonants(&notes[j + 1].syl.onset, o.body, 0.8))
        };"""),
])

# la tablée (`?table=<id>`) : nos fichiers stage/ copiés dans src/stage/, et une route à côté de
# celle de la page Duet
import shutil
stage_src = pathlib.Path(__file__).resolve().parent.parent / "stage"
(root / "src" / "stage").mkdir(exist_ok=True)
for f in stage_src.glob("*.ts*"):
    shutil.copy(f, root / "src" / "stage" / f.name)
print("ok src/stage/ (" + ", ".join(f.name for f in stage_src.glob("*.ts*")) + ")")
patch("src/ui/App.tsx", [
    ("""/** the show to play, from `?show=<id>` (a plain folder name under public/shows) */""",
     """// la tablée (`?table=<id>`) : les voix d'un spectacle autour d'une table (chimeraboire)
const TablePage = lazy(() => import("../stage/TablePage.tsx").then((m) => ({ default: m.TablePage })));

/** the show to play, from `?show=<id>` (a plain folder name under public/shows) */"""),
    ("""  const show = showId();
  if (show)""",
     """  const table = new URLSearchParams(window.location.search).get("table");
  if (table && /^[\\w-]+$/.test(table))
    return (
      <Suspense fallback={null}>
        <TablePage id={table} />
      </Suspense>
    );
  const show = showId();
  if (show)"""),
])

patch("crates/chimera-cli/src/render.rs", [
    ("""    let f0 = match body_name {
        "female" => 200.0,
        "child" => 250.0,
        _ => 110.0,
    };""", """    let f0 = match body_name {
        "female" => 200.0,
        "child" => 250.0,
        _ => 110.0,
    };
    let f0: f64 = std::env::var("CHIMERA_F0").ok().and_then(|v| v.parse().ok()).unwrap_or(f0);"""),
])
