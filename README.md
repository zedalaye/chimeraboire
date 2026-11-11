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

### La vidéo

Le serveur de CHIMERA doit tourner, et il faut ffmpeg (`.venv/Scripts/pip install imageio-ffmpeg`).

```sh
bun tools/make_video.ts out/banquet.mp4 --gpu      # 1920×1080, 30 i/s, ~8 min de calcul
```

La page est calculée image par image : l'horloge audio est remplacée par `performance.now()`, que
l'horloge simulée de Playwright fait avancer de 1/30 s entre deux captures. Les têtes, les mots et
le mixage restent synchrones, quelle que soit la vitesse de calcul. Options : `--fps`, `--size`,
`--from`/`--to` (en secondes) pour un extrait, `--probe` pour suivre le temps de la page, et
`--gpu` pour utiliser la carte graphique (sinon, rendu logiciel SwiftShader, plus lent).

## Ce qui est fait

- **`tools/patch_chimera.py`** complète CHIMERA (testé sur le commit `59d1e81`). Depuis le
  ticket #32, CHIMERA lit lui-même les voyelles nasales (`õ`, `ɑ̃`…) et les marques
  d'aspiration (`k˭` non aspiré). Le patch ajoute :
  - la semi-voyelle `ɥ` ;
  - une nasalisation plus légère (0,15 au lieu de 0,3), sinon le chœur sonne nasillard, sauf sur
    les voyelles ouvertes (0,25), sans quoi le « an » s'entend « a » ;
  - `render notes` accepte `"syllables"` (une syllabe IPA par note) ;
  - `render speech` accepte la variable d'environnement `CHIMERA_F0` (hauteur) ;
  - la page Duet affiche le texte `"words"` du fichier mélodie au lieu de passer par le dictionnaire anglais ;
  - la respiration entre deux phrases laisse la place aux consonnes d'attaque de la suivante ;
  - une consonne marquée longue (`lː`) garde sa durée dans le chant.

  Seul `songs_match_typescript` échoue, ce qui est attendu : la respiration modifiée déplace les
  fins de phrase des chansons de référence.
- **`tools/score_to_chimera.py`** lit la partition SATB et produit les fichiers pour CHIMERA :
  - il transcrit les paroles en IPA, avec enchaînements (sauf le « r », qui reste sur son mot),
    « e » muets chantés, « on » fermé (`õ`), « an » postérieur et arrondi (`ɒ̃`), « in »
    central (`ɐ̃`), « è » ouvert (`æ`), p t k non aspirés (`˭`) et consonnes allongées
    en début de phrase (`lː`) ;
  - il déroule les reprises : couplet n, puis refrain deux fois ;
  - il rétablit « Le » (couplet 2) et « Bu » (couplet 4), absents de la partition.
- **`tools/banquet.py`** fait la mise en scène :
  - chanson transposée de 3 demi-tons plus bas (mi mineur) : `TRANSPOSE` ;
  - 11 convives (8 hommes, 3 femmes), dont deux hommes qui chantent la mélodie à l'octave
    inférieure, aux voix humanisées (désaccord, flou rythmique, un ténor éméché) ;
  - égalisation du chœur contre le côté nasillard ;
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
    les notes tenues, brouhaha parlé par CHIMERA ;
  - feu de cheminée, gobelets et salle en pierre, tous synthétisés.
