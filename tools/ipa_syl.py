"""Nos syllabes IPA (« k˭i », « mɐʁ », « lːo », « ʁjɐ̃ », « - » pour un mélisme) → le format de
syllabes de CHIMERA (docs/language-front-ends.md), que `render notes` et la page Duet chantent tel
quel avec "syllables".

Les marques sont lues comme le fait le lecteur IPA de CHIMERA (phonetics/ipa.rs) :
˭ / ʰ → "aspirated" sur la consonne, tilde → "nasalized" sur la voyelle, ː → durée allongée
(×1,7 sur 90 ms pour une consonne, 150 ms pour une voyelle), ɡ → g. Une virgule ou un point final
marque la fin d'une phrase (une respiration).
"""
import unicodedata

VOWELS = set("iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒɝɚ")
MULTI = ["tʃ", "dʒ", "ts", "dz", "pf", "tɕ", "dʑ", "tʂ", "dʐ"]
PUNCT = ",.;:!?"


def segments(ipa):
    """« k˭i » → [{"ipa": "k", "aspirated": false}, {"ipa": "i"}] (l'ordre de la syllabe)"""
    s = unicodedata.normalize("NFD", ipa).replace("ɡ", "g")
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch in "˭ʰ" and out:
            out[-1]["aspirated"] = ch == "ʰ"
        elif ch == "̃" and out and out[-1]["ipa"] in VOWELS:
            out[-1]["nasalized"] = True
        elif ch in "ː:" and out:
            out[-1]["dur"] = round((0.15 if out[-1]["ipa"] in VOWELS else 0.09) * 1.7, 4)
        elif unicodedata.combining(ch) or ch in " .ˈˌ'":
            pass  # (autres diacritiques : ignorés, comme dans CHIMERA)
        else:
            tok = next((m for m in MULTI if s.startswith(m, i)), ch)
            out.append({"ipa": tok})
            i += len(tok)
            continue
        i += 1
    return out


def syllable(ipa, text, word_end=True, phrase_end=False):
    segs = segments(ipa)
    vi = [k for k, x in enumerate(segs) if x["ipa"] in VOWELS]
    if len(vi) != 1:
        raise ValueError(f"syllabe {ipa!r} : {len(vi)} voyelles (il en faut une)")
    k = vi[0]
    return {"text": text, "onset": segs[:k], "nucleus": segs[k], "coda": segs[k + 1:],
            "wordEnd": word_end, "phraseEnd": phrase_end}


def syllables(ipas, texts=None):
    """une liste de syllabes IPA (« - » : mélisme ; ponctuation finale : fin de phrase) et le texte
    affiché pour chacune (« chas- » : le mot continue ; « ~ » ou None : mélisme)"""
    out = []
    for n, ipa in enumerate(ipas):
        text = texts[n] if texts else None
        phrase_end = ipa.endswith(tuple(PUNCT))
        core = ipa.rstrip(PUNCT).strip()
        if core in ("-", "~"):
            prev = out[-1]
            out.append({"text": "~", "onset": [], "nucleus": prev["nucleus"], "coda": [], "melisma": True,
                        "wordEnd": prev["wordEnd"], "phraseEnd": phrase_end})
            continue
        shown = text if text not in (None, "~") else core
        out.append(syllable(core, shown.rstrip("-"), word_end=not shown.endswith("-"), phrase_end=phrase_end))
    return out
