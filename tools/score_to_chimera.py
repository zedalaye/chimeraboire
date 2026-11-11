"""Partition MusicXML (Chanson à boire, Bataille, SATB) → fichiers « render notes » de CHIMERA.

Pour chaque voix : couplet n (mesures avant le refrain, paroles n), puis le refrain deux fois
(paroles du couplet 1, les seules écrites). Les paroles sont transcrites en IPA syllabe par
syllabe (lexique ci-dessous), avec enchaînement des consonnes finales devant voyelle.

Usage : python tools/score_to_chimera.py score/chanson-a-boire-satb.musicxml out/json [--verses 1,2,3,4]
"""
import json, re, sys, pathlib, xml.etree.ElementTree as ET

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VOICES = {"P1": "soprano", "P2": "alto", "P3": "tenor", "P4": "basse"}

# syllabe écrite (minuscules, sans ponctuation) → IPA chanté
SYL = {
    # couplet 1
    "qui": "ki", "veut": "vø", "chas": "ʃa", "ser": "se", "u": "y", "ne": "nə", "mi": "mi",
    "grai": "ɡʁɛ", "n'a": "na", "qu'à": "ka", "boire": "bwaʁ", "boi": "bwa", "re": "ʁə",
    "tou": "tu", "jours": "ʒuʁ", "du": "dy", "bon": "bɔ̃", "et": "e", "main": "mɛ̃", "te": "tə",
    "nir": "niʁ", "sa": "sa", "ta": "ta", "ble": "blə", "plei": "plɛ", "de": "də", "cer": "sɛʁ",
    "ve": "və", "las": "la", "jam": "ʒɑ̃",
    # refrain
    "l'eau": "lo", "fait": "fɛ", "rien": "ʁjɛ̃", "que": "kə", "pour": "puʁ", "rir": "ʁiʁ",
    "ris": "ʁiʁ", "le": "lə", "pou": "pu", "mon": "mɔ̃", "bou": "bu", "com": "kɔ̃", "pa": "pa",
    "gnon": "ɲɔ̃", "vi": "vi", "des": "də", "nous": "nu", "ce": "sə", "verre": "vɛʁ",
    "rem": "ʁɑ̃", "pli": "pli", "rons": "ʁɔ̃",
    # couplet 2
    "vin": "vɛ̃", "goû": "ɡu", "té": "te", "par": "paʁ", "pè": "pɛ", "s'en": "sɑ̃", "ren": "ʁɑ̃",
    "dit": "di", "si": "si", "gar": "ɡaʁ", "çon": "sɔ̃", "dis": "dis", "cou": "ku", "sans": "sɑ̃",
    "gram": "ɡʁa", "mai": "mɛ", "rend": "ʁɑ̃", "vants": "vɑ̃",
    # couplet 3
    "loth": "lɔt", "bu": "by", "vant": "vɑ̃", "dans": "dɑ̃", "ver": "vɛʁ", "ca": "ka", "ses": "se",
    "filles": "fij", "en": "ɑ̃", "fla": "fla", "sein": "sɛ̃", "trant": "tʁɑ̃", "qu'un": "kœ̃",
    "rop": "ʁo", "pas": "pa", "se": "sə", "lui": "lɥi", "d'un": "dœ̃", "mé": "me", "cin": "sɛ̃",
    # couplet 4
    "vons": "vɔ̃", "donc": "dɔ̃k", "tous": "tus", "à": "a", "la": "la", "bonne": "bɔn",
    "heu": "œ", "é": "e", "mou": "mu", "voir": "vwaʁ", "ro": "ʁɔ", "d'en": "dɑ̃", "tre": "tʁə",
    "meu": "mœ", "dé": "de", "di": "di", "ra": "ʁa", "son": "sɔ̃",
}
# le « on » français est un [o] fermé nasalisé : le /ɔ/ de CHIMERA, très ouvert, donnait « han »
SYL = {k: v.replace("ɔ̃", "õ") for k, v in SYL.items()}
# le « an » français est postérieur et arrondi, un [ɒ̃] : le /ɑ/ de CHIMERA, non arrondi et
# en avant (F2 ≈ 1400 Hz), donnait « ra- » pour « rem- » et « -vin » pour « -vants »
SYL = {k: v.replace("ɑ̃", "ɒ̃") for k, v in SYL.items()}
# le « in » : le /ɛ/ de CHIMERA, lèvres étirées (F2 ≈ 1790 Hz), donnait un « -ien » pincé ;
# [ɐ̃], central et plus ouvert, a été préféré à l'écoute (comparaison A/B/C sur « rien »)
SYL = {k: v.replace("ɛ̃", "ɐ̃") for k, v in SYL.items()}
# le « è » : [æ], plus ouvert que le /ɛ/ de CHIMERA, préféré à l'écoute (« vaire » plutôt que
# « vère », comparaison A/B/C sur « verre ») ; les « ɛ̃ » sont déjà devenus « ɐ̃ » ci-dessus
SYL = {k: v.replace("ɛ", "æ") for k, v in SYL.items()}
# syllabes dont la prononciation dépend du mot
IN_WORD = {("bon-ne", 0): "bɔ", ("fil-les", 0): "fi", ("fil-les", 1): "jə"}

FIRST_WORD = {"2": "Le", "4": "Bu"}

VOWELS = set("iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒ")


def pitch(n):
    p = n.find("pitch")
    if p is None:
        return 0
    return 12 * (int(p.findtext("octave")) + 1) + STEP[p.findtext("step")] + round(float(p.findtext("alter") or 0))


def clean(t):
    t = re.sub(r"^\d+\.", "", t or "").strip().lower().replace("’", "'")
    return t


def read_part(part):
    """mesures → liste de notes {midi, beats, lyr{num: (texte, syllabic)}, tie_stop}; repère le refrain"""
    div, measures, refrain_at = 1, [], None
    for i, m in enumerate(part.findall("measure")):
        a = m.find("attributes")
        if a is not None and a.findtext("divisions"):
            div = int(a.findtext("divisions"))
        for b in m.findall("barline"):
            r = b.find("repeat")
            if r is not None and r.get("direction") == "forward":
                refrain_at = i
        notes = []
        for n in m.findall("note"):
            if n.find("chord") is not None or n.find("grace") is not None:
                continue
            if n.findtext("voice") not in (None, "1"):
                continue
            ties = {t.get("type") for t in n.findall("tie")}
            lyr = {l.get("number", "1"): (l.findtext("text"), l.findtext("syllabic") or "single") for l in n.findall("lyric")}
            notes.append({"midi": pitch(n), "beats": int(n.findtext("duration")) / div, "lyr": lyr, "tie_stop": "stop" in ties})
        measures.append(notes)
    return measures, refrain_at


def words_of(notes, num, fallback=None):
    """syllabes de chaque note pour le couplet `num` : ('syl', ipa, ponctuation) | ('-',) | ('rest',)"""
    out, word = [], []
    def flush():
        txt = "-".join(clean(w[1]) for w in word)
        txt_np = re.sub(r"[,.;:!?]", "", txt)
        parts = txt_np.split("-")
        for k, (idx, raw) in enumerate(word):
            s = parts[k]
            ipa = IN_WORD.get((txt_np, k)) or SYL.get(s)
            if ipa is None:
                sys.exit(f"syllabe inconnue : {s!r} (mot {txt_np!r})")
            punct = re.findall(r"[,.;:!?]$", clean(raw))
            shown = re.sub(r"^\d+\.", "", raw).strip().rstrip(",.;:!?") + ("" if k == len(word) - 1 else "-")
            out[idx] = ("syl", ipa, punct[0] if punct else "", shown)
        word.clear()
    for n in notes:
        if n["midi"] == 0:
            out.append(("rest",)); continue
        if n["tie_stop"]:
            out.append(("tie",)); continue
        l = n["lyr"].get(num) or (n["lyr"].get(fallback) if fallback else None)
        if l is None:
            out.append(("-",)); continue
        out.append(None)
        text = l[0]
        if not clean(text) and num in FIRST_WORD:  # la partition a perdu « Le » (c. 2) et « Bu » (c. 4)
            text = FIRST_WORD[num]
        word.append((len(out) - 1, text))
        if l[1] in ("single", "end"):
            flush()
    if word:
        flush()
    return out


def starts_with_vowel(ipa):
    return ipa[0] in VOWELS


def enchain(sy):
    """« tous à » → tu sa : la consonne finale passe à la syllabe suivante si elle commence par une
    voyelle. Sauf le « r » : « verre et » chanté « vè-ré » a été jugé moins bien que « vair-é »."""
    for i in range(len(sy) - 1):
        a, b = sy[i], sy[i + 1]
        if a[0] == "syl" and b[0] == "syl" and not a[2] and starts_with_vowel(b[1]):
            ipa = a[1]
            if ipa[-1] not in VOWELS and ipa[-1] not in "̃ɥʁ":
                sy[i] = ("syl", ipa[:-1], a[2], a[3])
                sy[i + 1] = ("syl", ipa[-1] + b[1], b[2], b[3])
    return sy


def unaspirated(ipa):
    """p t k français : sans le souffle de l'anglais (marque IPA ˭, lue par CHIMERA)"""
    return re.sub(r"([ptk])(?!˭)", r"\g<1>˭", ipa)


def lengthen_phrase_onsets(syls):
    """une consonne sonore en début de phrase (« L'eau », « Le vin », « Nous ») est allongée,
    sinon elle se fond dans l'attaque du souffle"""
    out, start = [], True
    for s in syls:
        if s != "-" and start and s[0] in "lmnʁ":
            s = s[0] + "ː" + s[1:]
        out.append(s)
        if s != "-":
            start = s[-1] in ",.;:!?"
    return out


def build(measures, refrain_at, verse):
    couplet = [n for m in measures[:refrain_at] for n in m]
    refrain = [n for m in measures[refrain_at:] for n in m]
    v = str(verse)
    seq = [(couplet, words_of(couplet, v)), (refrain, words_of(refrain, v, fallback="1")), (refrain, words_of(refrain, v, fallback="1"))]
    notes, syls, shown = [], [], []
    for ns, sy in seq:
        sy = enchain(sy)
        for n, s in zip(ns, sy):
            if s[0] == "tie":
                notes[-1][1] += n["beats"]
                continue
            if s[0] == "rest":
                notes.append([0, n["beats"]]); continue
            notes.append([n["midi"], n["beats"]])
            syls.append("-" if s[0] == "-" else s[1] + s[2])
            shown.append("~" if s[0] == "-" else s[3])
    return notes, [unaspirated(x) for x in lengthen_phrase_onsets(syls)], shown


def main():
    src, outdir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    verses = [1, 2, 3, 4]
    if "--verses" in sys.argv:
        verses = [int(x) for x in sys.argv[sys.argv.index("--verses") + 1].split(",")]
    outdir.mkdir(parents=True, exist_ok=True)
    root = ET.parse(src).getroot()
    bpm = float(next((s.get("tempo") for s in root.iter("sound") if s.get("tempo")), 120))
    for part in root.iter("part"):
        name = VOICES[part.get("id")]
        measures, refrain_at = read_part(part)
        for v in verses:
            notes, syls, shown = build(measures, refrain_at, v)
            f = outdir / f"{name}-couplet{v}.json"
            f.write_text(json.dumps({"bpm": bpm, "vibrato": 25, "notes": notes, "syllables": syls, "words": shown}, ensure_ascii=False), encoding="utf-8")
            print(f"{f.name}: {len(notes)} notes, {sum(n[0] * 0 + n[1] for n in notes):g} temps | " + " ".join(syls[:14]) + " …")


if __name__ == "__main__":
    main()
