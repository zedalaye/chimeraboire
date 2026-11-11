/**
 * La tablée (`?table=<id>`) : les voix d'un spectacle (public/shows/<id>/, le même que la page Duet)
 * assises autour d'une table, dans une seule scène vue par un convive debout à quelques pas, en
 * légère plongée.
 *
 * Chaque tête reste un Anatomy3D inchangé, dans son propre repère : la caméra commune est exprimée
 * dans le repère de chaque siège, et les têtes sont dessinées l'une après l'autre dans la même image
 * (les traits se mêlent par maximum, comme dans une tête). Ainsi tout ce qu'une tête tire de sa
 * caméra (l'atténuation en profondeur, le regard, les mots à la bouche) reste juste.
 *
 * show.json : `guests` (sinon `voices`) donne pour chaque convive son enregistrement, son siège
 * `{ x, z, y?, look? }` (cm), son costume, sa tunique et s'il montre ses paroles ; `table` la
 * table et la caméra ; `cues` les gestes calés sur la musique (voir tavern.ts).
 */
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Anatomy3D } from "../ui/render/anatomy3d.ts";
import { Glow } from "../ui/render/vector.ts";
import { TeleTrack } from "../show/tele.ts";
import { Transport } from "../show/transport.ts";
import { getModel } from "../ui/useModel.ts";
import { VoiceModel } from "../ui/analysis.ts";
import { mouthWords } from "../ui/mouthWords.ts";
import { V } from "../ui/colors.ts";
import { g2p } from "../ui/speech.ts";
import { lyricsToSyllables } from "../wasm/engine.ts";
import { sungWords, wordAt, type Melody, type SungWords } from "../show/words.ts";
import type { ViewFlags } from "../ui/render/anatomy.ts";
import type { OverlayFn } from "../ui/components/AnatomyView.tsx";
import { Tavern, type Cues, type Sitter } from "./tavern.ts";
import { Costume, type CostumeSpec } from "./costumes.ts";

type V3 = [number, number, number];
interface SeatSpec {
  x: number;
  z: number;
  y?: number;
  look?: V3;
}
interface GuestSpec {
  name: string;
  tele: string;
  melody?: string;
  seat?: SeatSpec;
  costume?: CostumeSpec;
  /** la couleur de la tunique (une couleur de la palette, par nom : blue, red, …) */
  tunic?: string;
  /** les paroles à la bouche (par défaut : oui) */
  words?: boolean;
  /** une chope devant lui (par défaut : oui pour un adulte) */
  mug?: boolean;
}
interface ShowFile {
  title: string;
  audio: string;
  bpm?: number;
  downbeat?: number;
  spell?: Record<string, string>;
  voices: GuestSpec[];
  guests?: GuestSpec[];
  table?: { length?: number; depth?: number; camera?: { pos?: V3; target?: V3; fov?: number } };
  cues?: Cues;
}

/** une tête à table */
interface Guest {
  spec: GuestSpec;
  track: TeleTrack;
  model: VoiceModel;
  r: Anatomy3D;
  costume: Costume | null;
  /** du monde vers le repère du siège, et l'inverse */
  inv: THREE.Matrix4;
  place: THREE.Matrix4;
  yaw: number;
  overlay: OverlayFn | null;
}

/** les traits de la tête seulement : pas de pression ni de particules, plus lisible de loin */
const VIEW: ViewFlags = { pressure: false, particles: false, grid: false, calipers: false };

/** la table et le regard par défaut : un convive debout près du coin avant droit, à quelques pas */
const TABLE = { length: 260, depth: 85 };
const CAMERA: { pos: V3; target: V3; fov: number } = { pos: [115, 45, 165], target: [8, -24, -48], fov: 36 };

const palette = (name: string | undefined, fallback: string): string => (name && name in V ? V[name as keyof typeof V] : name?.startsWith("#") ? name : fallback);

async function fetchOk(url: string): Promise<Response> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status} ${r.statusText}`);
  return r;
}

const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

/** les sièges par défaut : tout le monde du côté opposé au spectateur, face à lui (une Cène) */
function defaultSeats(n: number, length: number, depth: number): SeatSpec[] {
  return Array.from({ length: n }, (_, i) => ({ x: -length / 2 + ((i + 0.5) * length) / n, z: -depth / 2 - 22 }));
}

export function TablePage(props: { id: string }) {
  const base = `${import.meta.env.BASE_URL}shows/${props.id}/`;
  const [transport, setTransport] = useState<Transport | null>(null);
  const [show, setShow] = useState<ShowFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const guestsRef = useRef<Guest[] | null>(null);

  useEffect(() => {
    const t = new Transport();
    setTransport(t);
    return () => t.dispose();
  }, []);

  // ---- le chargement : le spectacle, le mixage, les enregistrements, les paroles
  useEffect(() => {
    if (!transport) return;
    let live = true;
    (async () => {
      const s = (await (await fetchOk(base + "show.json")).json()) as ShowFile;
      const specs = s.guests ?? s.voices;
      const [audio, ...teles] = await Promise.all([fetchOk(base + s.audio).then((r) => r.arrayBuffer()), ...specs.map((v) => fetchOk(base + v.tele).then((r) => r.arrayBuffer()))]);
      const melodies = await Promise.all(specs.map((v) => (v.melody && v.words !== false ? fetchOk(base + v.melody).then((r) => r.json() as Promise<Melody>) : null)));
      if (melodies.some((m) => m && !m.syllables)) await g2p.load().catch(() => {});
      const L = s.table?.length ?? TABLE.length, D = s.table?.depth ?? TABLE.depth;
      const seats = defaultSeats(specs.length, L, D);
      const camPos = new THREE.Vector3(...(s.table?.camera?.pos ?? CAMERA.pos));
      const guests: Guest[] = specs.map((v, i) => {
        const track = new TeleTrack(teles[i]);
        const model = getModel(track.body, track.sampleRate);
        const seat = { ...seats[i], ...(v.seat ?? {}) };
        const pos = new THREE.Vector3(seat.x, seat.y ?? 0, seat.z);
        // le visage (l'axe x de la tête) se tourne vers ce qu'il regarde, à l'horizontale
        const look = seat.look ? new THREE.Vector3(...seat.look) : camPos.clone().multiplyScalar(0.6);
        const yaw = Math.atan2(-(look.z - pos.z), look.x - pos.x);
        const place = new THREE.Matrix4().compose(pos, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), yaw), new THREE.Vector3(1, 1, 1));
        const r = new Anatomy3D();
        r.centred = true;
        let overlay: OverlayFn | null = null;
        const m = melodies[i];
        if (m) {
          try {
            const words: SungWords = sungWords(m, m.syllables ?? lyricsToSyllables(m.lyrics), s.spell);
            overlay = mouthWords(() => wordAt(words, transport.time()), V.green, seat.x < 0 ? -1 : 1);
          } catch (e) {
            console.warn("tablée : pas de paroles pour", v.name, e);
          }
        }
        const costume = v.costume && v.costume.kind !== "aucun" ? new Costume({ ...v.costume, color: palette(v.costume.color, V.white) }, r) : null;
        return { spec: v, track, model, r, costume, inv: place.clone().invert(), place, yaw, overlay };
      });
      await transport.load(audio);
      if (!live) return;
      guestsRef.current = guests;
      setShow(s);
    })().catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [base, transport]);

  // ---- le rendu : une scène, une caméra, toutes les têtes
  useEffect(() => {
    if (!show || !transport || !guestsRef.current) return;
    const guests = guestsRef.current;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const wrap = wrapRef.current!;
    const glCanvas = document.createElement("canvas");
    const gl = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, alpha: false, powerPreference: "high-performance" });
    gl.outputColorSpace = THREE.LinearSRGBColorSpace;
    gl.setClearColor(0x000000, 1);
    gl.autoClear = false;
    const L = show.table?.length ?? TABLE.length, D = show.table?.depth ?? TABLE.depth;
    // un buste sous chaque tête, tourné comme elle ; une chope devant chaque adulte attablé
    const sitters: Sitter[] = guests.map((g, i) => {
      const e = new THREE.Vector3().setFromMatrixPosition(g.place);
      const child = g.track.body.child ?? 0, female = g.track.body.female ?? 0;
      return { x: e.x, y: e.y, z: e.z, yaw: g.yaw, scale: 1 - 0.3 * child - 0.08 * female, color: palette(g.spec.tunic, i % 2 ? V.blueMid : V.blue), mug: g.spec.mug ?? child < 0.5 };
    });
    const tavern = new Tavern({ length: L, depth: D }, sitters, show.cues ?? {});
    const cam = new THREE.PerspectiveCamera(show.table?.camera?.fov ?? CAMERA.fov, 1, 5, 4000);
    cam.position.set(...(show.table?.camera?.pos ?? CAMERA.pos));
    cam.lookAt(new THREE.Vector3(...(show.table?.camera?.target ?? CAMERA.target)));
    cam.updateMatrixWorld(true);
    const glow = new Glow();
    const m4 = new THREE.Matrix4();

    let w = 0, h = 0, dpr = 1;
    const fit = () => {
      const b = wrap.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = b.width;
      h = b.height;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      gl.setPixelRatio(dpr);
      gl.setSize(Math.max(1, w), Math.max(1, h), false);
      cam.aspect = w / Math.max(1, h);
      cam.updateProjectionMatrix();
      tavern.setResolution(Math.max(1, w), Math.max(1, h));
      for (const g of guests) {
        g.r.resize(Math.max(1, w), Math.max(1, h));
        g.costume?.setResolution(Math.max(1, w), Math.max(1, h));
      }
    };
    const ro = new ResizeObserver(fit);
    ro.observe(wrap);

    const beatStep = (t: number) => {
      if (!show.bpm) return -1;
      const s = Math.floor(((t - (show.downbeat ?? 0)) * show.bpm * 4) / 60);
      return s < 0 ? -1 : s % 16;
    };
    let raf = 0, last = performance.now(), epoch = -1;
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      const elapsed = Math.min(0.5, (now - last) / 1000);
      last = now;
      if (w > 0 && h > 0) {
        const t = transport.time();
        if (transport.epoch !== epoch) {
          epoch = transport.epoch;
          for (const g of guests) g.r.resetMotion();
        }
        gl.clear();
        tavern.update(dt, t);
        gl.render(tavern.scene, cam);
        const faces: (() => void)[] = [];
        for (const g of guests) {
          const msg = g.track.message(g.track.indexAt(t), beatStep(t));
          const tele = transport.isPlaying ? msg : null;
          const a = VoiceModel.articFromArray(msg.t.artic);
          // la caméra commune, vue depuis le siège de cette tête
          m4.multiplyMatrices(g.inv, cam.matrixWorld);
          m4.decompose(g.r.camera.position, g.r.camera.quaternion, g.r.camera.scale);
          g.r.camera.fov = cam.fov;
          g.r.camera.aspect = cam.aspect;
          g.r.camera.near = cam.near;
          g.r.camera.far = cam.far;
          g.r.camera.clearViewOffset();
          g.r.camera.updateProjectionMatrix();
          g.r.camera.updateMatrixWorld(true);
          g.r.face.update(tele, elapsed);
          const f = g.model.frame(a);
          g.r.update(g.model, f, a, tele, VIEW, dt);
          g.costume?.update(g.model, t);
          gl.render(g.r.scene, g.r.camera);
          if (g.overlay) faces.push(() => g.overlay!(ctx, g.r.faceView(g.model, f, a), g.model, f, a, { w, h, dt }));
        }
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(glCanvas, 0, 0, canvas.width, canvas.height);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        for (const draw of faces) draw();
        glow.apply(canvas, ctx, dpr);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      tavern.dispose();
      for (const g of guests) {
        g.costume?.dispose();
        g.r.dispose();
      }
      gl.dispose();
      gl.forceContextLoss();
    };
  }, [show, transport]);

  // la barre de lecture suit le transport
  useEffect(() => {
    if (!transport) return;
    const off = transport.subscribe(() => setTick((n) => n + 1));
    const id = setInterval(() => transport.isPlaying && setTick((n) => n + 1), 250);
    return () => {
      off();
      clearInterval(id);
    };
  }, [transport]);

  if (error)
    return (
      <div className="duet">
        <p className="duet-msg error">La tablée n'a pas pu se charger : {error}</p>
      </div>
    );
  const st = transport?.state ?? { playing: false, time: 0, duration: 0, epoch: 0 };
  return (
    <div className="duet">
      <header className="duet-top">
        <span className="wordmark">Chimera</span>
        <span className="duet-title">{show?.title ?? "La tablée s'installe…"}</span>
      </header>
      <main ref={wrapRef} style={{ position: "relative", minHeight: 0 }}>
        <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} aria-label="La tablée qui chante, en 3D" role="img" />
        {!show && <p className="duet-msg">La tablée s'installe…</p>}
      </main>
      <footer className="duet-bar">
        <button className="primary large" disabled={!show} onClick={() => (st.playing ? transport?.pause() : transport?.play())}>
          {st.playing ? "Pause" : st.duration > 0 && st.time >= st.duration - 0.05 ? "Again" : "Play"}
        </button>
        <span className="duet-time">
          {clock(st.time)} / {clock(st.duration)}
        </span>
        <input
          type="range"
          aria-label="Position in the song"
          min={0}
          max={st.duration || 1}
          step={0.1}
          value={st.time}
          disabled={!show}
          onChange={(e) => transport?.seek(Number(e.target.value))}
          style={{ "--pos": `${st.duration ? (100 * st.time) / st.duration : 0}%` } as React.CSSProperties}
        />
      </footer>
    </div>
  );
}
