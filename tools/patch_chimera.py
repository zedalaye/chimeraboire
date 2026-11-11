"""Ce qui manque encore à CHIMERA pour chanter notre banquet en français.

CHIMERA lit lui-même les marques IPA depuis le ticket #32 (étape 1, commit 59d1e81) :
nasalisation par tilde (ã õ ɛ̃ ɑ̃…), aspiration ʰ / non-aspiration ˭, ʲ, ʱ. Ce patch ajoute :
 - /ɥ/ (« lui », « celui ») à l'inventaire ;
 - une voyelle nasale moins ouverte (0,15 cm² au lieu de 0,3 : le chœur sonnait nasillard) ;
 - `render notes` accepte "syllables" (une syllabe IPA par note) à la place de "lyrics" ;
 - le chant : une consonne marquée longue (« lː ») garde sa durée, et la respiration entre deux
   phrases laisse la place aux consonnes d'attaque de la suivante (le « L' » de « L'eau ») ;
 - `render speech` : CHIMERA_F0 (Hz) change la hauteur de la voix parlée ;
 - la page Duet affiche le texte "words" d'un fichier mélodie au lieu du dictionnaire anglais.
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

patch(PH + "inventory.rs", [
    ("""        c("j", "palatal approximant",""",
     """        c("ɥ", "labial-palatal approximant", M::Approximant, Voiced, "labial-palatal", t(&[(TbX, 3.8), (TbY, 7.9), (Jaw, 0.25), (LipAp, 0.35), (LipProt, 1.0), (LipWidth, 0.1)]), &[TbX, TbY, LipAp, LipProt, LipWidth], 0.055),
        c("j", "palatal approximant","""),
])

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
    # une consonne marquée longue en IPA (« lː ») garde sa durée : un « L' » en début de phrase
    # chanté à la durée par défaut passait inaperçu
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

patch("src/ui/components/DuetPage.tsx", [
    ("""          return sungWords(m, lyricsToSyllables(m.lyrics), show.spell);""",
     """          const shown = (m as Melody & { words?: string[] }).words;
          const syls = shown ? (shown.map((w) => ({ text: w.replace(/-$/, ""), melisma: w === "~", wordEnd: !w.endsWith("-") })) as unknown as ReturnType<typeof lyricsToSyllables>) : lyricsToSyllables(m.lyrics);
          return sungWords(m, syls, show.spell);"""),
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
    ("""    let g = g2p()?;
    let syl = lyrics_to_syllables(j["lyrics"].as_str().ok_or("lyrics missing")?, &g);
    let sounding""",
     """    // "syllables": one IPA syllable per sounding note ("k˭i", "ʃa", "bõ,"), "-" for a melisma,
    // a trailing , . ; ! ? for a breath; otherwise "lyrics" through the English dictionary
    let syl = if let Some(list) = j["syllables"].as_array() {
        ipa_syllables(list)?
    } else {
        let g = g2p()?;
        lyrics_to_syllables(j["lyrics"].as_str().ok_or("lyrics missing")?, &g)
    };
    let sounding"""),
    ("""pub fn notes(ctx: &Ctx, a: &[String]) -> Result<(), String> {""",
     """/// IPA syllables (one per sung note) → syllables: consonants before the vowel are the onset,
/// after it the coda.
fn ipa_syllables(list: &[serde_json::Value]) -> Result<Vec<chimera::phonetics::Syllable>, String> {
    use chimera::anatomy::human::BodyMix;
    use chimera::phonetics::{Syllable, ipa::tokenize_ipa, planner::is_vowel};
    let mut out: Vec<Syllable> = Vec::new();
    for (n, v) in list.iter().enumerate() {
        let raw = v.as_str().ok_or_else(|| format!("syllables[{n}] is not a string"))?.trim();
        let phrase_end = raw.ends_with([',', '.', ';', '!', '?']);
        let s = raw.trim_end_matches([',', '.', ';', '!', '?']).trim();
        if s == "-" || s == "~" {
            let prev = out.last().ok_or("a melisma cannot come first")?.clone();
            out.push(Syllable { text: "~".into(), onset: vec![], nucleus: prev.nucleus, coda: vec![], melisma: Some(true), word_end: prev.word_end, phrase_end });
            continue;
        }
        let segs = tokenize_ipa(s);
        let vi: Vec<usize> = segs.iter().enumerate().filter(|(_, x)| is_vowel(&x.ipa, BodyMix::MALE)).map(|(i, _)| i).collect();
        if vi.len() != 1 {
            return Err(format!("syllables[{n}] \\"{s}\\": {} vowels (need exactly 1)", vi.len()));
        }
        let k = vi[0];
        let mut nucleus = segs[k].clone();
        nucleus.word_end = None;
        out.push(Syllable { text: s.to_string(), onset: segs[..k].to_vec(), nucleus, coda: segs[k + 1..].to_vec(), melisma: None, word_end: true, phrase_end });
    }
    Ok(out)
}

pub fn notes(ctx: &Ctx, a: &[String]) -> Result<(), String> {"""),
])
