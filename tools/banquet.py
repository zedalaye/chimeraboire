"""Scène de banquet : la tablée chante la Chanson à boire (Bataille) avec CHIMERA.

  .venv/Scripts/python tools/banquet.py            # rend tout ce qui manque, puis mixe
  .venv/Scripts/python tools/banquet.py --remix    # remixe sans rien re-rendre
  .venv/Scripts/python tools/banquet.py --fresh    # efface les rendus et recommence

Entrées : out/json/<voix>-couplet<n>.json (tools/score_to_chimera.py)
Sorties : out/render/* (voix isolées), out/banquet.wav et .flac, et le spectacle 3D
          chimera/public/shows/banquet/ (http://127.0.0.1:5317/?show=banquet)

Si on change la tablée ou TRANSPOSE, il faut --fresh (les rendus en cache ne le savent pas).
"""
import json, os, random, re, shutil, subprocess, sys, pathlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve, butter, sosfilt, lfilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXE = ROOT / "chimera" / "target" / "release" / ("chimera.exe" if os.name == "nt" else "chimera")
JSON = ROOT / "out" / "json"
REN = ROOT / "out" / "render"
SR = 48000

# ------------------------------------------------------------------ la tablée
TRANSPOSE = -3  # demi-tons : sol mineur → mi mineur, des voix plus graves
# nom, voix chantée, octave (−12 = la mélodie une octave plus bas), corps, désaccord (cents),
# retard (s), flou rythmique (temps), vibrato, panoramique, gain, meneur, nom affiché
SINGERS = [
    ("alienor",    "soprano",   0, "female",   0, 0.000, 0.012, 22, -0.25, 0.80, True,  "Dame Aliénor"),
    ("robin",      "soprano", -12, "male",     6, 0.020, 0.018, 20,  0.35, 0.95, False, None),
    ("hugues",     "soprano", -12, "male",   -10, 0.040, 0.022, 26, -0.55, 0.85, False, None),
    ("perrine",    "alto",      0, "female",  -6, 0.010, 0.015, 18,  0.30, 0.80, True,  "Perrine"),
    ("guillemette","alto",      0, "female",  12, 0.045, 0.022, 24, -0.65, 0.60, False, None),
    ("jehan",      "tenor",     0, "male",     0, 0.000, 0.012, 22,  0.10, 1.00, True,  "Frère Jehan"),
    ("gauthier",   "tenor",     0, "male",    22, 0.080, 0.045, 40,  0.75, 0.85, False, None),  # l'éméché
    ("colin",      "tenor",     0, "male",    -8, 0.020, 0.020, 18, -0.40, 0.80, False, None),
    ("enguerrand", "basse",     0, "male",     0, 0.005, 0.012, 16, -0.10, 1.15, True,  "Messire Enguerrand"),
    ("thibaut",    "basse",     0, "male",   -14, 0.035, 0.020, 20,  0.50, 0.95, False, None),
    ("mathieu",    "basse",     0, "male",     7, 0.025, 0.018, 14, -0.80, 0.90, False, None),
]
VERSES = [1, 2, 3, 4]
COUPLET, REFRAIN = 32, 24  # en noires
BABBLE_BEATS = 10  # 5 s de brouhaha (à 120) avant que les ménestrels n'attaquent
PRELUDE_BEATS = REFRAIN  # les ménestrels jouent le refrain seuls, puis la tablée entre
INTRO_BEATS, OUTRO = BABBLE_BEATS + PRELUDE_BEATS, 9.0
T0 = 0.3  # le premier temps de la piste (défaut du CLI)

# ------------------------------------------------------------------ les ménestrels (des voix aussi)
# flûte : un enfant chante la mélodie une octave plus haut, articulée « du-lu » comme une flûte à bec,
#         au prélude et aux refrains (passages ci-dessous : (couplet, passage) ; 0 = le prélude)
FLUTE_REFRAINS = {0, (1, 1), (2, 1), (3, 1), (4, 0), (4, 1)}
# bourdon de vielle : des hommes tiennent « ou » sur la tonique et la quinte, en relais pour respirer
DRONES = [("bourdon-1", 40, 0, -2), ("bourdon-2", 40, 8, 3), ("bourdon-3", 47, 4, -5)]  # nom, midi, décalage (temps), cents
# viole et tambourin : le séquenceur beatbox de CHIMERA (« m:NN » bouche fermée ; B K t !)
MINSTREL_GAIN = {"flute": 1.0, "bourdon": 0.33, "viole": 1.15, "tambourin": 1.0}  # sous la tablée (~ -9 dB)
BEAT_LATENCY = 0.2
BEAT_CHUNK = 128  # pas par rendu beatbox (BeatPlayer::MAX_STEPS) : 8 mesures à 2/2  # le séquenceur joue chaque pas 0,2 s après son instant (BeatPlayer::HORIZON)
TABOR_REFRAIN = "B . . . t . t . K . . . t . ! ."  # une mesure à 2/2, en doubles croches
TABOR_COUPLET = "B . . . . . . . K . . . . . ! ."
# couplets chantés par les seuls meneurs ; les refrains, toujours par tout le monde
SOLO_COUPLETS = {1, 3}

SHOUTS = {  # cris de la tablée (IPA, parole CHIMERA)
    "a_boire": "a ˈbwaʁ", "sante": "sɒ̃ˈte", "encore": "ɒ̃ˈkɔʁ", "chantons": "ʃɒ̃ˈtõ",
    "hola": "ɔˈla", "bravo": "bʁaˈvo", "rire": "ha ˈha ˈha ˈha", "aubergiste": "obæʁˈʒist",
    "du_vin": "dy ˈvɐ̃", "hourra": "uˈʁa", "he": "ˈe",
}
SHOUTERS = [("male", 112), ("male", 92), ("female", 205), ("male", 128)]
FR_SYL = ["la", "le", "di", "mõ", "sa", "tu", "vɐ̃", "pa", "ʒɒ̃", "ki", "ʁə", "bõ", "ty", "nu", "se",
          "va", "ʃa", "ʁi", "kõ", "də", "mi", "lɥi", "bwa", "fæ", "ɒ̃", "ʒə", "tæ", "ve", "ʁo", "pu"]


def unaspirated(ipa):
    """p t k français : sans le souffle de l'anglais (marque IPA ˭, lue par CHIMERA)"""
    return re.sub(r"([ptk])(?!˭)", r"\g<1>˭", ipa)


def run(args, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run([str(EXE), *args], capture_output=True, text=True, encoding="utf-8", env=e)
    if r.returncode:
        sys.exit(f"échec : {' '.join(args)}\n{r.stdout}{r.stderr}")


# ------------------------------------------------------------------ rendus CHIMERA
def full_melody(part):
    """les 4 couplets d'une voix bout à bout, après l'intro (un silence)"""
    notes, syls, words = [[0, INTRO_BEATS]], [], []
    for v in VERSES:
        d = json.loads((JSON / f"{part}-couplet{v}.json").read_text(encoding="utf-8"))
        notes += d["notes"]; syls += d["syllables"]; words += d["words"]
    return {"bpm": d["bpm"], "notes": notes, "syllables": syls, "words": words}


def singer_json(s):
    name, part, octave, body, cents, late, blur, vib, *_ = s
    d = full_melody(part)
    r = random.Random(name)
    notes = d["notes"]
    # flou rythmique : chaque frontière de note bouge un peu, la durée totale ne change pas
    bounds = np.cumsum([0] + [n[1] for n in notes])
    for i in range(1, len(bounds) - 1):
        lo, hi = bounds[i - 1] + 0.12, bounds[i + 1] - 0.12
        bounds[i] = min(hi, max(lo, bounds[i] + r.gauss(0, blur)))
    drift = -0.12 if name == "gauthier" else 0.0  # l'éméché baisse au fil de la chanson
    out = []
    for i, n in enumerate(notes):
        m = n[0] + TRANSPOSE + octave + (cents + r.gauss(0, 4)) / 100 + drift * i / len(notes) if n[0] > 0 else 0
        out.append([round(m, 4), round(bounds[i + 1] - bounds[i], 4)])
    d["notes"] = out
    d["vibrato"] = vib
    d["t0"] = T0 + late
    p = REN / f"{name}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def part_notes(part, verse):
    """(couplet, refrain) d'une voix : listes [midi, temps] de la partition (sans transposition)"""
    d = json.loads((JSON / f"{part}-couplet{verse}.json").read_text(encoding="utf-8"))
    couplet, refrain, t = [], [], 0.0
    for n in d["notes"]:
        if t < COUPLET - 1e-6:
            couplet.append(list(n))
        elif t < COUPLET + REFRAIN - 1e-6:
            refrain.append(list(n))
        t += n[1]
    return couplet, refrain


def timeline():
    """la chanson en sections, en temps depuis T0 : (début, durée, couplet, passage)
    passage : 'prelude', 'couplet', 0 ou 1 (les deux refrains)"""
    out, t = [(BABBLE_BEATS, PRELUDE_BEATS, 1, "prelude")], INTRO_BEATS
    for v in VERSES:
        out.append((t, COUPLET, v, "couplet")); t += COUPLET
        for k in (0, 1):
            out.append((t, REFRAIN, v, k)); t += REFRAIN
    return out, t


def flute_json():
    """la flûte : la mélodie (soprano) une octave plus haut, au prélude et aux refrains choisis"""
    sections, end = timeline()
    notes, t = [], 0.0
    def rest(b):
        if notes and notes[-1][0] == 0:
            notes[-1][1] += b
        else:
            notes.append([0, b])
    for start, length, v, k in sections:
        rest(start - t) if start > t else None
        key = 0 if k == "prelude" else (v, k)
        if k != "couplet" and key in FLUTE_REFRAINS:
            notes += [[n[0] + TRANSPOSE + 12 if n[0] > 0 else 0, n[1]] for n in part_notes("soprano", 1 if k == "prelude" else v)[1]]
        else:
            rest(length)
        t = start + length
    # articulation de flûte à bec : « du » en attaque (après un silence, sur une note répétée), « lu » lié,
    # et une respiration (virgule) après chaque note longue
    syls, prev = [], 0
    for i, (m, b) in enumerate(notes):
        if m <= 0:
            prev = 0
            continue
        s = "du" if prev == 0 or round(prev) == round(m) else "lu"
        nxt = notes[i + 1][0] if i + 1 < len(notes) else 0
        syls.append(s + ("," if b >= 2 or nxt <= 0 else ""))
        prev = m
    d = {"bpm": 120, "vibrato": 12, "t0": T0, "notes": [[round(m, 3), b] for m, b in notes], "syllables": syls,
         "words": [s.rstrip(",") for s in syls]}
    p = REN / "flute.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def drone_json(name, midi, offset, cents):
    """un bourdon : « ou » tenu par phrases de 4 mesures, décalées d'un chanteur à l'autre"""
    sections, end = timeline()
    # tous démarrent avec le prélude ; seul l'endroit où chacun reprend son souffle est décalé
    notes, t, b = [[0, BABBLE_BEATS]], BABBLE_BEATS, (16 - offset) or 16
    while t < end + 4:  # (midi : déjà dans le ton chanté, mi mineur)
        b = min(b, end + 4 - t)
        notes.append([round(midi + cents / 100, 3), b])
        t += b
        b = 16
    d = {"bpm": 120, "vibrato": 0, "t0": T0, "notes": notes, "syllables": ["ũ,"] * (len(notes) - 1)}
    p = REN / f"{name}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def bass_pattern():
    """la viole : la ligne de basse fredonnée « m:NN », en doubles croches, sur toute la chanson"""
    sections, end = timeline()
    steps = ["."] * int(BABBLE_BEATS * 4)
    for start, length, v, k in sections:
        couplet, refrain = part_notes("basse", 1 if k == "prelude" else v)
        for m, b in (couplet if k == "couplet" else refrain):
            n = int(round(b * 4))
            steps += ([f"m:{int(round(m + TRANSPOSE))}"] if m > 0 else ["."]) + ["."] * (n - 1)
    return " ".join(steps)


def tabor_pattern():
    """le tambourin : léger aux couplets, plus fourni au prélude et aux refrains, un coup final"""
    sections, end = timeline()
    bars = ["." ] * int(BABBLE_BEATS * 4)
    for start, length, v, k in sections:
        bar = TABOR_COUPLET if k == "couplet" else TABOR_REFRAIN
        bars += (bar.split() * int(length // 4))
    return " ".join(bars + ["B>", ".", ".", "."])


def babble_text(r):
    utts = []
    for _ in range(r.randint(3, 5)):
        words = []
        for _ in range(r.randint(2, 5)):
            words.append("".join(r.choice(FR_SYL) for _ in range(r.randint(1, 3))))
        words[-1] = "ˈ" + words[-1]
        utts.append(" ".join(words))
    return " / ".join(utts)


def render_all():
    REN.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s in SINGERS:
        wav = REN / f"{s[0]}.wav"
        if not wav.exists():
            tele = ["--tele", str(REN / f"{s[0]}.tele")] if s[10] else []
            jobs.append((["render", "notes", str(singer_json(s)), str(wav.with_suffix("")), s[3], *tele], None))
    # les ménestrels
    if not (REN / "flute.wav").exists():
        jobs.append((["render", "notes", str(flute_json()), str(REN / "flute"), "child", "--tele", str(REN / "flute.tele")], None))
    for name, midi, offset, cents in DRONES:
        if not (REN / f"{name}.wav").exists():
            jobs.append((["render", "notes", str(drone_json(name, midi, offset, cents)), str(REN / name), "male"], None))
    # le séquenceur garde au plus 128 pas (BeatPlayer::MAX_STEPS, fait pour le temps réel) : les grilles
    # sont rendues par tranches de 8 mesures et recollées au mixage ; une tranche vide est sautée (le CLI
    # jouerait sinon son rythme par défaut)
    for name, pattern in (("beat-viole", bass_pattern), ("beat-tambourin", tabor_pattern)):
        steps = pattern().split()
        for k in range(0, len(steps), BEAT_CHUNK):
            chunk = steps[k:k + BEAT_CHUNK]
            out = REN / name / f"{k // BEAT_CHUNK:03d}"
            if any(x != "." for x in chunk) and not (out / "pattern.wav").exists():
                jobs.append((["render", "beatbox", str(out), " ".join(chunk), "male", "120", "1"], None))
    for key, ipa in SHOUTS.items():
        for k, (body, f0) in enumerate(SHOUTERS):
            wav = REN / f"shout-{key}-{k}.wav"
            if not wav.exists():
                jobs.append((["render", "speech", str(wav.with_suffix("")), unaspirated(ipa), body], {"CHIMERA_F0": str(f0 * (1.15 if key != "rire" else 1.05))}))
    r = random.Random(7)
    for k in range(10):
        wav = REN / f"babble-{k}.wav"
        if not wav.exists():
            body = "female" if k % 4 == 3 else "male"
            f0 = r.uniform(175, 210) if body == "female" else r.uniform(85, 125)
            jobs.append((["render", "speech", str(wav.with_suffix("")), unaspirated(babble_text(r)), body], {"CHIMERA_F0": f"{f0:.0f}"}))
    if jobs:
        print(f"{len(jobs)} rendus CHIMERA…", flush=True)
        done = [0]
        def one(j):
            run(*j)
            done[0] += 1
            if done[0] % 10 == 0:
                print(f"  {done[0]}/{len(jobs)}", flush=True)
        with ThreadPoolExecutor(max(2, (os.cpu_count() or 4) - 2)) as ex:
            list(ex.map(one, jobs))


# ------------------------------------------------------------------ outils audio
def load(p):
    x, sr = sf.read(str(p), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    assert sr == SR, f"{p}: {sr} Hz"
    return x


def pan(x, p, g=1.0):
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a) * g, x * np.sin(a) * g], axis=1)


def place(mix, clip, t):
    i = int(t * SR)
    if i < 0:
        clip, i = clip[-i:], 0
    n = min(len(clip), len(mix) - i)
    if n > 0:
        mix[i:i + n] += clip[:n]


def lp(x, hz, order=2):
    return sosfilt(butter(order, hz, "low", fs=SR, output="sos"), x, axis=0)


def hp(x, hz, order=2):
    return sosfilt(butter(order, hz, "high", fs=SR, output="sos"), x, axis=0)


def biquad(x, kind, f0, gain_db, q=0.9):
    """égaliseur RBJ : 'peak' (en cloche) ou 'lowshelf'"""
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    cw, sw = np.cos(w), np.sin(w)
    if kind == "peak":
        al = sw / (2 * q)
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    else:
        al = sw / 2 * np.sqrt(2)
        sA = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) - (A - 1) * cw + sA), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sA)]
        a = [(A + 1) + (A - 1) * cw + sA, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sA]
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x, axis=0)


# égalisation des voix (chœur, ménestrels, brouhaha) : (type, Hz, dB, Q)
EQ_PRESETS = {
    # la première : moins nasillard, mais tout le rendu sonnait étouffé (−4 dB de présence, +3 dB de grave)
    "etouffe": [("peak", 1500, -5.0, 1.0), ("peak", 2600, -2.0, 1.4), ("lowshelf", 220, 3.0, None)],
    # un léger creux anti-nasillard, de la présence vers 3,5 kHz, un grave allégé
    "clair": [("peak", 1500, -2.5, 1.0), ("peak", 3500, 3.0, 0.8), ("lowshelf", 220, -1.5, None)],
}
EQ = "clair"  # préférée à l'écoute (comparaison A/B/C)


def denasal(x):
    """l'égalisation des voix (EQ_PRESETS[EQ])"""
    for kind, f0, db, q in EQ_PRESETS[EQ]:
        x = biquad(x, kind, f0, db, q or 0.9)
    return x


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def clink(r):
    """gobelet d'étain / verre : quelques modes inharmoniques qui s'éteignent"""
    n = int(r.uniform(0.6, 1.2) * SR)
    t = np.arange(n) / SR
    f = r.uniform(1400, 3200)
    y = np.zeros(n)
    for ratio, amp in [(1, 1), (2.32, 0.6), (4.25, 0.35), (6.63, 0.2), (1.51, 0.3)]:
        y += amp * np.sin(2 * np.pi * f * ratio * (1 + r.uniform(-0.01, 0.01)) * t) * np.exp(-t * r.uniform(5, 12) * ratio ** 0.5)
    y[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    if r.random() < 0.5:  # deuxième gobelet
        y2 = np.zeros(n); d = int(r.uniform(0.01, 0.04) * SR); y2[d:] = y[: n - d] * 0.7
        y = y + y2
    return y * 0.25


def thump(r):
    """choppe frappée sur la table de chêne"""
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = r.uniform(70, 95)
    body = np.sin(2 * np.pi * f * t * (1 - 0.3 * t)) * np.exp(-t * 18)
    knock = lp(np.random.default_rng(r.randint(0, 9999)).standard_normal(n) * np.exp(-t * 60), 1800)
    return (body * 0.9 + knock * 0.5) * r.uniform(0.7, 1.0)


def fire(seconds, seed=3):
    g = np.random.default_rng(seed)
    n = int(seconds * SR)
    roar = lp(g.standard_normal(n), 400, 2) * 0.25
    roar *= 0.7 + 0.3 * lp(g.standard_normal(n), 0.5, 1) / 0.05
    crackle = np.zeros(n)
    for _ in range(int(seconds * 9)):
        i = g.integers(0, n - 2000); k = g.integers(80, 1500)
        crackle[i:i + k] += g.standard_normal(k) * np.exp(-np.arange(k) / (k / 5)) * g.uniform(0.2, 1.0)
    return roar * 0.6 + hp(crackle, 1500) * 0.35


def hall_ir(rt60=2.1, seconds=2.8):
    """salle en pierre : réflexions précoces + queue diffuse qui s'assombrit"""
    g = np.random.default_rng(11)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / rt60)
    ir = np.zeros((n, 2))
    for c in range(2):
        tail = g.standard_normal(n) * env
        dark = lp(tail, 2500, 1)
        mixw = np.clip(t / 1.2, 0, 1)
        tail = tail * (1 - mixw) + dark * mixw
        tail[: int(0.025 * SR)] *= np.linspace(0, 1, int(0.025 * SR))
        ir[:, c] = tail
        for _ in range(14):  # premières réflexions sur les murs
            d = int(g.uniform(0.008, 0.07) * SR)
            ir[d, c] += g.uniform(-0.6, 0.6)
    return ir / np.sqrt(np.sum(ir ** 2, axis=0))


def env_gain(n, points):
    """courbe de gain par morceaux [(t, g), ...]"""
    ts = np.arange(n) / SR
    tt, gg = zip(*sorted(points))
    return np.interp(ts, tt, gg)


# ------------------------------------------------------------------ mise en scène
def mix(dest=None, show=True):
    """le mixage, dans out/banquet.wav et .flac (ou dest, un .wav), et le spectacle 3D si show"""
    bpm = json.loads((JSON / "soprano-couplet1.json").read_text(encoding="utf-8"))["bpm"]
    beat = 60 / bpm
    verse_beats = COUPLET + 2 * REFRAIN
    starts = [T0 + (INTRO_BEATS + k * verse_beats) * beat for k in range(len(VERSES))]  # 1er temps de chaque couplet
    refrains = [(v, k, T + (COUPLET + k * REFRAIN) * beat) for v, T in zip(VERSES, starts) for k in (0, 1)]  # (couplet, passage, début)
    end = starts[-1] + verse_beats * beat
    total = end + OUTRO
    N = int(total * SR)
    choir = np.zeros((N, 2))  # les chanteurs
    dry = np.zeros((N, 2))    # cris et objets
    amb = np.zeros((N, 2))    # brouhaha, feu
    r = random.Random(42)
    at = lambda t0, beats: t0 + beats * beat

    # --- le chœur
    for s in SINGERS:
        name, part, octave, body, cents, late, blur, vib, p, g, lead, _ = s
        x = norm(load(REN / f"{name}.wav"), 0.5) * g
        if not lead:
            # les autres attendent le refrain pour se joindre aux couplets des meneurs
            pts = [(0, 1.0), (9999, 1.0)]
            for v, T in zip(VERSES, starts):
                if v in SOLO_COUPLETS:
                    c_end = at(T, COUPLET)
                    pts += [(T - 1.0, 1.0), (T - 0.6, 0.0), (c_end - 0.35, 0.0), (c_end - 0.05, 1.0)]
            x = x * env_gain(len(x), pts)
        place(choir, pan(x, p), 0)
    choir = denasal(choir)

    # --- les ménestrels (le pas 0 des grilles beatbox est le temps 0 de la chanson, à T0)
    prelude = at(T0, BABBLE_BEATS)
    minstrels = np.zeros((N, 2))
    place(minstrels, pan(norm(load(REN / "flute.wav"), 0.5), 0.45, MINSTREL_GAIN["flute"]), 0)
    for name, midi, *_ in DRONES:
        x = lp(norm(load(REN / f"{name}.wav"), 0.5), 1800)
        place(minstrels, pan(x, -0.15 if midi == 40 else 0.2, MINSTREL_GAIN["bourdon"] * (1.0 if midi == 40 else 0.6)), 0)
    for name, p, g in (("beat-viole", -0.35, MINSTREL_GAIN["viole"]), ("beat-tambourin", -0.55, MINSTREL_GAIN["tambourin"])):
        track = np.zeros(N)
        for chunk in sorted((REN / name).glob("*/pattern.wav")):
            place(track[:, None], load(chunk)[:, None], T0 - BEAT_LATENCY + int(chunk.parent.name) * BEAT_CHUNK * beat / 4)
        place(minstrels, pan(norm(track, 0.5), p, g), 0)
    minstrels = denasal(minstrels)

    def shout(key, t, p=None, g=0.5, k=None):
        k = r.randrange(len(SHOUTERS)) if k is None else k
        x = norm(load(REN / f"shout-{key}-{k}.wav"), g)
        place(dry, pan(x, r.uniform(-0.85, 0.85) if p is None else p), t)

    def clinks(t, n, g=0.35):
        for _ in range(n):
            place(dry, pan(clink(r), r.uniform(-0.9, 0.9), g), t + r.uniform(-0.05, 0.25))

    def thumps(t, n, g):
        for _ in range(n):
            place(dry, pan(thump(r), r.uniform(-0.8, 0.8), g), t + r.uniform(-0.03, 0.04))

    # --- avant le chant
    for _ in range(5):
        clinks(r.uniform(0.5, prelude - 1.5), 1)
    shout("hola", 1.0, -0.5)
    shout("chantons", prelude - 2.6, 0.2, 0.65, k=0)  # … et les ménestrels attaquent le refrain
    shout("hourra", starts[0] - 1.6, 0.6, 0.4); shout("hourra", starts[0] - 1.45, -0.6, 0.4)  # la tablée entre

    # --- le banquet dans les refrains (temps en noires depuis le début du refrain) :
    #   0 « L'eau ne fait rien que » · 4 « pour-rir le pou- » · 6 « mon, » (tenu)
    #   8 « bou-te bou-te bou- » · 11 « te » · 12 « bou-te com-pa- » · 14 « gnon, » (tenu)
    #   16 « Vi-des nous ce » · 18 « verre » · 19 « et » · 20 « nous le rem-pli- » · 22 « rons. » (tenu)
    for v, k, R in refrains:
        loud = k == 1 or v >= 3  # la tablée s'échauffe
        first = v == 1 and k == 0
        if not first:  # au tout premier refrain, on écoute encore
            for b in (8, 9, 10, 12, 13):
                thumps(at(R, b), r.randint(3, 6) if loud else r.randint(1, 3), 0.42 if loud else 0.28)
        if k == 1:
            for b in (6, 14):
                thumps(at(R, b), r.randint(2, 4), 0.38)
        clinks(at(R, 22.2), r.randint(3, 6) if not first else 2)  # sur « rem-pli-rons. » (sur « verre », le tintement brouillait le « è »)
        if k == 0 and v >= 2:
            shout(r.choice(["he", "hola"]), at(R, 6.4), g=0.42)
        if k == 1 and v in (2, 4):
            shout("rire", at(R, 14.3), g=0.32)
        if v == 3 and k == 1:
            shout("aubergiste", at(R, 14.4), 0.7, 0.5)
        if k == 1 and v < VERSES[-1]:
            # sur « rem-pli-rons. », juste avant le couplet suivant
            shout(r.choice(["a_boire", "du_vin", "sante"]), at(R, 22.3), g=0.5)
            if v == 2:
                shout("encore", at(R, 22.9), g=0.42)

    # --- la fin
    for i, key in enumerate(["hourra", "hourra", "bravo", "rire", "a_boire", "encore", "rire", "sante"]):
        shout(key, end + 0.1 + i * 0.55 + r.uniform(0, 0.3), g=0.5)
    for _ in range(4):
        clinks(end + r.uniform(0.5, OUTRO - 2.5), r.randint(1, 3))
    thumps(end + 0.05, 6, 0.45)

    # --- brouhaha : fort avant et après, discret aux couplets, un peu plus aux refrains
    bab = np.zeros((N, 2))
    for k in range(10):
        x = norm(load(REN / f"babble-{k}.wav"), 0.3)
        p = r.uniform(-0.9, 0.9)
        t = r.uniform(0, 2.5)
        while t < total:
            place(bab, pan(x, p), t)
            t += len(x) / SR + r.uniform(0.5, 3)
    bab = denasal(lp(bab, 3200))
    pts = [(0, 0.0), (0.8, 1.0), (prelude - 0.8, 1.0), (prelude + 1.5, 0.3), (starts[0] - 0.8, 0.3)]
    for v, T in zip(VERSES, starts):
        c_end = at(T, COUPLET)
        pts += [(T + 0.5, 0.05), (c_end - 0.5, 0.05), (c_end + 1.0, 0.16), (at(c_end, 2 * REFRAIN) - 0.6, 0.16)]
    pts += [(end + 0.6, 1.0), (total - 2.5, 0.7), (total, 0.0)]
    amb += bab * env_gain(N, pts)[:, None]

    # --- la cheminée, à gauche
    amb += pan(fire(total), -0.7, 0.18)

    # --- la salle
    ir = hall_ir()
    src = choir + minstrels + dry + amb * 0.9
    wet = np.stack([fftconvolve(src[:, c], ir[:, c])[:N] for c in range(2)], axis=1)
    out = (choir + minstrels + dry) * 0.75 + amb * 0.35 + wet * 0.45
    out = hp(out, 40)
    out *= env_gain(N, [(0, 0), (1.0, 1), (total - 2.5, 1), (total, 0)])[:, None]
    out = norm(out, 0.89)
    if dest:
        sf.write(str(dest), out.astype(np.float32), SR, subtype="PCM_16")
        return out
    for ext in ("wav", "flac"):  # (pas d'OGG : libsndfile plante sur les longs fichiers Vorbis)
        sf.write(str(ROOT / "out" / f"banquet.{ext}"), out.astype(np.float32), SR, subtype="PCM_16")
    if show:
        export_show(out, starts, beat)
    print(f"out/banquet.wav ({total:.0f} s) ; couplets à " + ", ".join(f"{t:.0f} s" for t in starts))


def export_show(out, starts, beat):
    """la page Duet de CHIMERA : le flûtiste et les quatre meneurs en 3D sur le mixage"""
    d = ROOT / "chimera" / "public" / "shows" / "banquet"
    d.mkdir(parents=True, exist_ok=True)
    sf.write(str(d / "banquet.wav"), out.astype(np.float32), SR, subtype="PCM_16")
    shutil.copy(REN / "flute.tele", d / "flute.tele")
    shutil.copy(REN / "flute.json", d / "flute.json")
    voices = [{"name": "Le petit flûtiste", "tele": "flute.tele", "melody": "flute.json"}]
    for s in SINGERS:
        if s[10]:
            shutil.copy(REN / f"{s[0]}.tele", d / f"{s[0]}.tele")
            shutil.copy(REN / f"{s[0]}.json", d / f"{s[0]}.json")
            voices.append({"name": s[11], "tele": f"{s[0]}.tele", "melody": f"{s[0]}.json"})
    show = {"title": "Chanson à boire — G. Bataille", "audio": "banquet.wav", "bpm": 60 / beat, "downbeat": starts[0], "voices": voices}
    (d / "show.json").write_text(json.dumps(show, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if "--fresh" in sys.argv and REN.exists():
        shutil.rmtree(REN)
    if "--remix" not in sys.argv:
        render_all()
    mix()
