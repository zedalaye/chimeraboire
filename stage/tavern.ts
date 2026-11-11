/**
 * Le décor de la tablée, en traits lumineux comme les têtes : une table à tréteaux, des bancs, un
 * sol dallé, des chandelles qui vacillent, et les convives (bustes, bras, chopes d'étain).
 *
 * Centimètres, comme les têtes : y vers le haut, 0 à hauteur de la glotte d'un adulte assis
 * (≈ 115 cm du sol) ; la table court le long de x ; le spectateur est du côté des z positifs.
 *
 * Les chopes suivent la musique (`Cues`, instants en secondes) : levées puis frappées sur la table
 * à chaque `bump`, levées ensemble pour trinquer au-dessus de la table pendant chaque `toast`.
 */
import * as THREE from "three";
import { Beams } from "../ui/render/beams3d.ts";
import { V } from "../ui/colors.ts";

export interface TableSpec {
  /** longueur et profondeur du plateau (cm) */
  length: number;
  depth: number;
}

/** un convive : où, tourné vers où (radians autour de y, comme les têtes), sa taille, sa tunique */
export interface Sitter {
  x: number;
  y: number;
  z: number;
  yaw: number;
  scale: number;
  color: string;
  /** une chope devant lui (les adultes attablés) */
  mug: boolean;
}

export interface Cues {
  /** les coups de chope sur la table (s) */
  bump?: number[];
  /** les toasts : [début, fin] (s) */
  toast?: [number, number][];
}

const FLOOR = -115; // le sol
const TOP = -40; // le dessus du plateau (table de 75 cm)
const WOOD = V.amber;
const PEWTER = V.white;
const STONE = V.blueDim;

type Pt = number[];
type PolyFn = (pts: Pt[], color: string, w: number, alpha: number, close?: boolean) => void;

const smooth = (a: number, b: number, x: number) => {
  const u = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return u * u * (3 - 2 * u);
};

export class Tavern {
  readonly scene = new THREE.Scene();
  private readonly beams = new Beams();
  private clock = 0;

  constructor(
    readonly table: TableSpec,
    readonly sitters: Sitter[],
    readonly cues: Cues = {},
  ) {
    this.scene.add(this.beams.group);
  }

  setResolution(w: number, h: number): void {
    this.beams.setResolution(w, h);
  }

  dispose(): void {
    this.beams.dispose();
  }

  /** retrace le décor à l'instant `t` de la chanson (les chandelles vacillent en temps réel) */
  update(dt: number, t: number): void {
    this.clock += dt;
    const B = this.beams;
    const { length: L, depth: D } = this.table;
    const hx = L / 2, hz = D / 2;
    B.begin();
    const poly: PolyFn = (pts, color, w, alpha, close = false) => {
      const a = new Float32Array(pts.length * 3);
      pts.forEach((p, i) => a.set(p, 3 * i));
      B.line(a, pts.length, color, w, { alpha, close });
    };

    // ---- le sol : des dalles, qui donnent la profondeur
    for (let x = -hx - 150; x <= hx + 150; x += 60) poly([[x, FLOOR, -hz - 160], [x, FLOOR, hz + 180]], STONE, 0.6, 0.22);
    for (let z = -hz - 160; z <= hz + 180; z += 60) poly([[-hx - 150, FLOOR, z], [hx + 150, FLOOR, z]], STONE, 0.6, 0.22);

    // ---- le plateau : les bords, l'épaisseur, les planches
    const T = TOP, Tb = TOP - 5;
    poly([[-hx, T, -hz], [hx, T, -hz], [hx, T, hz], [-hx, T, hz]], WOOD, 1.3, 0.85, true);
    poly([[-hx, Tb, hz], [hx, Tb, hz], [hx, Tb, -hz]], WOOD, 1.0, 0.5);
    for (const [x, z] of [[-hx, hz], [hx, hz], [hx, -hz]]) poly([[x, T, z], [x, Tb, z]], WOOD, 1.0, 0.6);
    for (let z = -hz + D / 5; z < hz - 1; z += D / 5) poly([[-hx, T, z], [hx, T, z]], WOOD, 0.85, 0.32);

    // ---- les tréteaux : deux chevalets en A sous le plateau, reliés par une traverse
    for (const x of [-hx + 35, hx - 35]) {
      for (const zz of [-hz + 12, hz - 12]) {
        const zf = zz + Math.sign(zz) * 6;
        for (const s of [-1, 1]) poly([[x + s * 4, Tb, zz], [x + s * 22, FLOOR, zf]], WOOD, 1.05, 0.55);
        poly([[x - 13, FLOOR + 45, zz + Math.sign(zz) * 3], [x + 13, FLOOR + 45, zz + Math.sign(zz) * 3]], WOOD, 0.85, 0.4);
      }
      poly([[x, Tb, -hz + 12], [x, Tb, hz - 12]], WOOD, 1.0, 0.5);
    }
    poly([[-hx + 35, FLOOR + 30, 0], [hx - 35, FLOOR + 30, 0]], WOOD, 0.85, 0.35);

    // ---- les bancs, des deux côtés
    for (const s of [-1, 1]) {
      const by = FLOOR + 45, z0 = s * (hz + 18), z1 = s * (hz + 38);
      poly([[-hx + 10, by, z0], [hx - 10, by, z0], [hx - 10, by, z1], [-hx + 10, by, z1]], WOOD, 1.0, 0.45, true);
      for (const x of [-hx + 25, 0, hx - 25]) for (const z of [z0 + s * 3, z1 - s * 3]) poly([[x, by, z], [x, FLOOR, z]], WOOD, 0.85, 0.35);
    }

    // ---- les convives et leurs chopes
    for (let i = 0; i < this.sitters.length; i++) this.guest(poly, this.sitters[i], i, t);

    // ---- les chandelles, et leur flamme qui vacille
    for (const [x, z, k] of [[-hx * 0.45, 3, 0], [hx * 0.1, -4, 1.7], [hx * 0.62, 5, 3.1]]) this.candle(poly, x, z, k);
    B.end();
  }

  /** où est la chope d'un convive à l'instant t, dans son repère (x vers l'avant, z vers sa droite) */
  private mugAt(i: number, t: number): { x: number; y: number; z: number; toward: number } {
    const jitter = ((i * 37) % 11) / 11 - 0.5; // chacun frappe un peu à son heure
    let lift = 0;
    for (const tb of this.cues.bump ?? []) {
      const d = tb + 0.02 * jitter - t;
      if (d > -0.15 && d < 0.32) lift = Math.max(lift, d >= 0 ? 9 * Math.sin((Math.PI * d) / 0.32) : 1.5 * Math.sin((Math.PI * -d) / 0.15));
    }
    let toward = 0;
    for (const [a, b] of this.cues.toast ?? []) toward = Math.max(toward, smooth(a - 0.5, a + 0.3, t) * (1 - smooth(b - 0.4, b + 0.4, t)));
    return { x: 30 + 22 * toward, y: TOP + lift + 38 * toward, z: 13 - 6 * toward, toward };
  }

  /** un convive : son buste assis, son bras droit qui tient sa chope */
  private guest(poly: PolyFn, b: Sitter, i: number, t: number): void {
    const k = b.scale, cy = Math.cos(b.yaw), sy = Math.sin(b.yaw);
    // du repère du convive vers le monde (rotation autour de y, comme les têtes)
    const P = (x: number, y: number, z: number): Pt => [b.x + cy * x + sy * z, b.y + y, b.z - sy * x + cy * z];
    // des sections elliptiques du cou à la taille : (hauteur, demi-largeur, demi-profondeur, recul)
    const rings: [number, number, number, number][] = [
      [-5, 5, 4.5, -1.5], [-11, 15, 8, -2.5], [-15, 16, 8.5, -2.5], [-24, 13.5, 8.5, -2], [-34, 12, 8, -1.5], [-42, 12.5, 8.5, -1.5],
    ];
    const at = (y: number, hw: number, hd: number, dx: number, u: number) => P(k * (dx + hd * Math.cos(u)), k * y, k * hw * Math.sin(u));
    rings.forEach(([y, hw, hd, dx], j) => {
      const pts: Pt[] = [];
      for (let n = 0; n < 28; n++) pts.push(at(y, hw, hd, dx, (n / 28) * Math.PI * 2));
      poly(pts, b.color, 0.85, j === 1 ? 0.55 : 0.32, true);
    });
    for (const u of [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2]) poly(rings.slice(1).map(([y, hw, hd, dx]) => at(y, hw, hd, dx, u)), b.color, 0.85, 0.4);
    // les épaules
    for (const s of [-1, 1]) {
      const arc: Pt[] = [];
      for (let n = 0; n <= 10; n++) {
        const u = n / 10;
        arc.push(P(k * -2, k * (-5 - 6 * u * u - 1.5 * Math.sin(Math.PI * u)), k * s * (5 + 11 * u)));
      }
      poly(arc, b.color, 1.05, 0.75);
    }
    // le bras gauche, posé sur la table
    poly([P(k * -2, k * -12, k * -16), P(k * 2, k * -34, k * -15), P(k * 24, k * -38, k * -9)], b.color, 0.85, 0.42);
    if (!b.mug) {
      poly([P(k * -2, k * -12, k * 16), P(k * 2, k * -34, k * 15), P(k * 22, k * -38, k * 11)], b.color, 0.85, 0.42);
      return;
    }
    // le bras droit qui tient la chope (l'anse est du côté de la main)
    const m = this.mugAt(i, t);
    const hand = [m.x - 6, m.y + 6.5, m.z];
    const elbow = [6 + 8 * m.toward, -32 + 14 * m.toward, 17];
    poly([P(k * -2, k * -12, k * 16), P(k * elbow[0], k * elbow[1], k * elbow[2]), P(hand[0], hand[1], hand[2])], b.color, 1.0, 0.6);
    this.tankard(poly, P, m.x, m.y, m.z);
  }

  /** une chope d'étain posée (ou levée) en (x, y, z) du repère d'un convive, l'anse vers lui */
  private tankard(poly: PolyFn, P: (x: number, y: number, z: number) => Pt, x: number, y0: number, z: number): void {
    const r = 4.5, h = 13, y1 = y0 + h;
    const ring = (y: number, rr: number) => {
      const pts: Pt[] = [];
      for (let n = 0; n < 24; n++) {
        const a = (n / 24) * Math.PI * 2;
        pts.push(P(x + rr * Math.cos(a), y, z + rr * Math.sin(a)));
      }
      poly(pts, PEWTER, 1.0, 0.6, true);
    };
    ring(y0, r);
    ring(y1, r * 0.92);
    for (let n = 0; n < 6; n++) {
      const a = (n / 6) * Math.PI * 2;
      poly([P(x + r * Math.cos(a), y0, z + r * Math.sin(a)), P(x + r * 0.92 * Math.cos(a), y1, z + r * 0.92 * Math.sin(a))], PEWTER, 0.6, 0.3);
    }
    const anse: Pt[] = [];
    for (let n = 0; n <= 10; n++) {
      const a = -Math.PI / 2 + Math.PI * (n / 10);
      anse.push(P(x - r - 3.2 * Math.cos(a), y0 + h / 2 + 4.5 * Math.sin(a), z));
    }
    poly(anse, PEWTER, 1.0, 0.55);
  }

  private candle(poly: PolyFn, x: number, z: number, phase: number): void {
    const t = this.clock;
    const ring = (y: number, rr: number, c: string, a: number) => {
      const pts: Pt[] = [];
      for (let n = 0; n < 20; n++) {
        const u = (n / 20) * Math.PI * 2;
        pts.push([x + rr * Math.cos(u), y, z + rr * Math.sin(u)]);
      }
      poly(pts, c, 0.85, a, true);
    };
    ring(TOP + 0.5, 6, PEWTER, 0.45);
    ring(TOP + 2.5, 2.2, V.white, 0.6);
    ring(TOP + 20, 2.2, V.white, 0.6);
    for (const s of [-1, 1]) poly([[x + s * 2.2, TOP + 2.5, z], [x + s * 2.2, TOP + 20, z]], V.white, 0.85, 0.5);
    // la flamme : une goutte qui oscille et palpite
    const sway = 0.8 * Math.sin(t * 7.1 + phase) + 0.5 * Math.sin(t * 13.3 + 2 * phase);
    const tall = 5.5 + 0.9 * Math.sin(t * 11.7 + phase) + 0.5 * Math.sin(t * 23.0 + phase);
    const flame: Pt[] = [];
    for (let n = 0; n <= 18; n++) {
      const a = (n / 18) * Math.PI * 2;
      const up = (1 - Math.cos(a)) / 2;
      const wide = 1.3 * Math.sin(a) * (1 - up * 0.85);
      flame.push([x + wide + sway * up * up, TOP + 21 + tall * up, z]);
    }
    poly(flame, V.amber, 1.6, 0.95, true);
    poly(flame.map(([fx, fy, fz]) => [x + (fx - x) * 0.45, TOP + 21 + (fy - TOP - 21) * 0.6, fz]), V.white, 1.05, 0.9, true);
  }
}
