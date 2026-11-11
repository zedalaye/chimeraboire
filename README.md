# Chimèraboire

Un banquet médiéval chante la *Chanson à boire* de Gabriel Bataille (« Qui veut chasser une
migraine ») avec [CHIMERA](https://github.com/jamesondh/chimera-vocal-synth), un synthétiseur
vocal par modélisation physique, qu'on fait chanter en français.

## Reconstruire

Il faut Rust et Python 3.

```sh
git clone https://github.com/jamesondh/chimera-vocal-synth.git chimera
python tools/patch_chimera.py chimera          # français : nasales, ɥ, consonnes non aspirées, syllabes IPA
cargo build --release -p chimera-cli --manifest-path chimera/Cargo.toml
python -m venv .venv && .venv/Scripts/pip install numpy scipy soundfile
python tools/score_to_chimera.py score/chanson-a-boire-satb.musicxml out/json
.venv/Scripts/python tools/banquet.py          # → out/banquet.wav / .flac
```

`banquet.py --remix` remixe sans refaire les rendus, `--fresh` repart de zéro.

### Les quatre meneurs en 3D

Il faut [Bun](https://bun.sh) et la cible WebAssembly de Rust.

```sh
rustup target add wasm32-unknown-unknown
cd chimera && bun install && bun run dev       # puis http://127.0.0.1:5317/?show=banquet
```

`banquet.py` écrit le spectacle dans `chimera/public/shows/banquet/` : le mixage, les mouvements
enregistrés (`.tele`) et les paroles des quatre meneurs. `bun tools/check_show.ts <dossier>`
l'ouvre dans Edge sans affichage et prend des captures.

### La tablée

**http://127.0.0.1:5317/?table=banquet** montre toute la tablée dans une seule scène 3D, vue
par un convive debout près d'un coin de la table, en légère plongée :
- les 11 convives et le petit flûtiste, coiffés (hennin, coiffe, tonsure, chaperons, chapeaux,
  capuche, cheveux, bonnet) et habillés d'une tunique de leur couleur ;
- une table à tréteaux, des bancs, des chandelles qui vacillent ;
- des chopes qui frappent la table sur « bou-te » et se lèvent pour trinquer sur « rempli-rons ».

Le code est dans `stage/` : `TablePage.tsx` pour la scène, `tavern.ts` pour le décor et les
gestes, `costumes.ts` pour les coiffes. `patch_chimera.py` le copie dans `chimera/src/stage/`.
Les têtes sont celles de CHIMERA, sans modification : la caméra commune est exprimée dans le
repère de chaque siège, et les têtes sont dessinées l'une après l'autre dans la même image. La
distribution (sièges, costumes, tuniques) et le cadrage se règlent dans `tools/banquet.py`
(`TABLE_GUESTS`, `TABLE_SPEC`).

### La vidéo

Le serveur de CHIMERA doit tourner, et il faut ffmpeg (`.venv/Scripts/pip install imageio-ffmpeg`).

```sh
bun tools/make_video.ts out/banquet.mp4 --gpu      # 1920×1080, 30 i/s, ~8 min de calcul
bun tools/make_video.ts out/tablee.mp4 --gpu --table   # la tablée, ~14 min
```

La page est calculée image par image : l'horloge audio est remplacée par `performance.now()`, que
l'horloge simulée de Playwright fait avancer de 1/30 s entre deux captures. Les têtes, les mots et
le mixage restent synchrones, quelle que soit la vitesse de calcul. Options : `--fps`, `--size`,
`--from`/`--to` (en secondes) pour un extrait, `--probe` pour suivre le temps de la page, et
`--gpu` pour utiliser la carte graphique (sinon, rendu logiciel SwiftShader, plus lent).

## Ce qui est fait

- **`tools/patch_chimera.py`** ajoute nos réglages à CHIMERA (testé sur le commit `1d3ea49`).
  CHIMERA sait déjà, de lui-même, lire les marques IPA (nasales `õ` `ɒ̃`, non-aspiration `k˭`),
  prononcer `ɥ`, et chanter des syllabes données en JSON (`"syllables"`, voir
  `docs/language-front-ends.md`). Le patch ajoute :
  - une nasalisation plus légère (0,15 au lieu de 0,3), sinon le chœur sonne nasillard, sauf sur
    les voyelles ouvertes (0,25), sans quoi le « an » s'entend « a » ;
  - la respiration entre deux phrases laisse la place aux consonnes d'attaque de la suivante ;
  - une consonne de durée donnée (`lː`) garde sa durée dans le chant ;
  - dans une note courte, la voyelle garde au moins 55 % du temps (« dis-courir » et non
    « disss-courir ») ;
  - `render speech` accepte la variable d'environnement `CHIMERA_F0` (hauteur).

  Seul `songs_match_typescript` échoue, ce qui est attendu : la respiration modifiée déplace les
  fins de phrase des chansons de référence.
- **`tools/ipa_syl.py`** convertit nos syllabes IPA (`k˭i`, `mɐʁ`, `lːo`…) au format de syllabes
  de CHIMERA.
- **`tools/score_to_chimera.py`** lit la partition SATB et produit les fichiers pour CHIMERA :
  - il transcrit les paroles en IPA, avec enchaînements (sauf le « r », qui reste sur son mot),
    « e » muets chantés, « on » fermé (`õ`), « an » postérieur et arrondi (`ɒ̃`), « in »
    central (`ɐ̃`), « è » ouvert (`æ`), « eu » ouvert de « meure » et « heure » (`ɐʁ`), p t k non aspirés (`˭`) et consonnes allongées
    en début de phrase (`lː`) ;
  - il déroule les reprises : couplet n, puis refrain deux fois ;
  - il rétablit « Le » (couplet 2) et « Bu » (couplet 4), absents de la partition.
- **`tools/banquet.py`** fait la mise en scène :
  - chanson transposée de 3 demi-tons plus bas (mi mineur) : `TRANSPOSE` ;
  - 11 convives (8 hommes, 3 femmes), dont deux hommes qui chantent la mélodie à l'octave
    inférieure, aux voix humanisées (désaccord, flou rythmique, un ténor éméché) ;
  - égalisation « claire » des voix : léger creux anti-nasillard à 1,5 kHz, présence vers 3,5 kHz,
    grave allégé (la première version, trop creusée, sonnait étouffée) ;
  - des ménestrels, des voix CHIMERA eux aussi :
    - une flûte : un enfant sur « du-lu », la mélodie une octave plus haut ;
    - un bourdon de vielle : trois hommes sur « ou », en relais pour respirer ;
    - une viole : la basse fredonnée bouche fermée (`m:NN` du beatbox) ;
    - un tambourin en beatbox, rendu par tranches de 8 mesures, car le séquenceur temps réel
      garde au plus 128 pas.

    Ils jouent le refrain en prélude, puis accompagnent toute la chanson. Le flûtiste a sa tête
    dans le spectacle 3D ;
  - couplets 1 et 3 chantés par les seuls meneurs, enchaînés sans pause ;
  - le banquet dans les refrains : choppes sur « bou-te », gobelets sur « ce verre », cris sur
    les notes tenues, gobelets sur « rempli-rons » (pas sur « verre », dont ils brouillaient le « è »),
    brouhaha parlé par CHIMERA ;
  - feu de cheminée, gobelets et salle en pierre, tous synthétisés.
