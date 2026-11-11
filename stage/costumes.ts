/**
 * Les coiffes des convives, en traits lumineux comme les têtes (dans l'esprit des cheveux et du
 * casque du « Chimeraroll »). Elles sont tracées dans le repère de la tête (cm : x vers l'avant,
 * y vers le haut, z vers la droite, 0 à la glotte) et suivent ses hochements : leur groupe copie,
 * à chaque image, la pose du groupe de la tête.
 *
 * La forme du crâne vient de la tête elle-même : à chaque hauteur, l'avant (F), l'arrière (Bk) et
 * la demi-largeur (W) de sa section (Anatomy3D, forme de repos de la tête pour ce corps).
 */
import * as THREE from "three";
import { Beams } from "../ui/render/beams3d.ts";
import type { Anatomy3D } from "../ui/render/anatomy3d.ts";
import type { VoiceModel } from "../ui/analysis.ts";

export type CostumeKind = "hennin" | "coiffe" | "tonsure" | "chaperon" | "chapeau" | "capuche" | "cheveux" | "bonnet" | "aucun";
export interface CostumeSpec {
  kind: CostumeKind;
  color: string;
  /** chapeau de travers (radians) */
  tilt?: number;
  /** une flûte à bec à la bouche */
  flute?: boolean;
}

interface Section {
  F: number;
  Bk: number;
  W: number;
}
interface HeadShape {
  y0: number;
  y1: number;
  at(y: number): Section | null;
}

type Pt = [number, number, number];

export class Costume {
  private readonly beams = new Beams();
  private head: HeadShape | null = null;
  private k = 1;

  constructor(
    readonly spec: CostumeSpec,
    private readonly r: Anatomy3D,
  ) {
    r.scene.add(this.beams.group);
  }

  setResolution(w: number, h: number): void {
    this.beams.setResolution(w, h);
  }

  dispose(): void {
    this.beams.dispose();
  }

  /** après r.update : suivre la pose de la tête et retracer la coiffe */
  update(model: VoiceModel, t: number): void {
    // la tête trace tout dans le premier groupe de sa scène, qu'elle fait hocher
    const headGroup = this.r.scene.children[0] as THREE.Object3D;
    const g = this.beams.group;
    g.position.copy(headGroup.position);
    g.quaternion.copy(headGroup.quaternion);
    if (!this.head) {
      // (la forme de repos de la tête : interne à Anatomy3D, lue telle quelle)
      this.head = (this.r as unknown as { restFor(m: VoiceModel): { head: HeadShape } }).restFor(model).head;
      this.k = model.tract.scale;
    }
    const B = this.beams;
    B.begin();
    const line = (pts: Pt[], color: string, w: number, alpha: number, close = false) => {
      const a = new Float32Array(pts.length * 3);
      pts.forEach((p, i) => a.set(p, 3 * i));
      B.line(a, pts.length, color, w, { alpha, close });
    };
    const s = this.spec;
    switch (s.kind) {
      case "hennin": this.hennin(line, s.color, t); break;
      case "coiffe": this.coiffe(line, s.color); break;
      case "tonsure": this.tonsure(line, s.color); break;
      case "chaperon": this.chaperon(line, s.color, t); break;
      case "chapeau": this.chapeau(line, s.color, s.tilt ?? 0); break;
      case "capuche": this.capuche(line, s.color); break;
      case "cheveux": this.cheveux(line, s.color, t); break;
      case "bonnet": this.bonnet(line, s.color); break;
    }
    if (s.flute) this.flute(line);
    B.end();
  }

  // ------------------------------------------------------------------ le crâne
  /** un point du crâne à la hauteur y, à l'angle u (0 : l'avant, π/2 : la droite), décollé de `off` cm */
  private skull(y: number, u: number, off = 0.5): Pt {
    const H = this.head!, k = this.k;
    const s = H.at(Math.min(y, H.y1 - 0.15 * k)) ?? H.at(H.y1 - 0.5 * k)!;
    const c = (s.F + s.Bk) / 2, a = (s.F - s.Bk) / 2 + off * k, b = s.W + off * k;
    return [c + a * Math.cos(u), y, b * Math.sin(u)];
  }

  private ring(y: number, off: number, n = 40, u0 = 0, u1 = Math.PI * 2): Pt[] {
    const pts: Pt[] = [];
    for (let i = 0; i <= n; i++) pts.push(this.skull(y, u0 + ((u1 - u0) * i) / n, off));
    return pts;
  }

  /** le sommet du crâne et un peu de dôme : `top` cm sous le sommet, au centre de la section */
  private crownPt(below: number): Pt {
    const H = this.head!, k = this.k;
    const s = H.at(H.y1 - 1.0 * k)!;
    return [(s.F + s.Bk) / 2, H.y1 - below * k, 0];
  }

  // ------------------------------------------------------------------ les coiffes
  private hennin(line: LineFn, color: string, t: number): void {
    const H = this.head!, k = this.k;
    const yb = H.y1 - 5.5 * k;
    // le bandeau sur le front, et le cône pointé vers l'arrière
    const band = this.ring(yb, 0.6, 48);
    line(band, color, 1.3, 0.9, true);
    line(this.ring(yb + 1.2 * k, 0.6, 48), color, 1.0, 0.6, true);
    const c = this.crownPt(0);
    const apex: Pt = [c[0] - 30 * k, H.y1 + 25 * k, 0]; // pointé vers l'arrière, comme les vrais
    for (let i = 0; i < 16; i++) {
      const p = band[i * 3];
      line([p, apex], color, 0.85, 0.55);
    }
    for (const u of [0.35, 0.62, 0.82]) {
      const ring: Pt[] = band.map((p) => [p[0] + (apex[0] - p[0]) * u, p[1] + (apex[1] - p[1]) * u, p[2] * (1 - u)]);
      line(ring, color, 0.85, 0.45, true);
    }
    // le voile qui tombe de la pointe, et ondule
    for (let i = 0; i < 9; i++) {
      const z = (i / 8 - 0.5) * 14 * k;
      const pts: Pt[] = [];
      for (let j = 0; j <= 16; j++) {
        const u = j / 16;
        const sway = 1.2 * k * Math.sin(t * 1.7 + i * 0.9 + u * 4) * u;
        pts.push([apex[0] - 2 * k * u + 3 * k * u * u + sway, apex[1] - 48 * k * u, z * u * 1.8 + sway * 0.5]);
      }
      line(pts, "#eef6f8", 0.85, 0.5 + 0.2 * (i % 2));
    }
  }

  private coiffe(line: LineFn, color: string): void {
    const H = this.head!, k = this.k;
    // un bonnet de lin qui couvre le crâne jusqu'au front et aux oreilles…
    for (const d of [1.5, 3.5, 6, 8.5]) line(this.ring(H.y1 - d * k, 0.9, 40), color, d === 8.5 ? 1.2 : 0.85, d === 8.5 ? 0.85 : 0.45, true);
    const top = this.crownPt(-0.6);
    for (let i = 0; i < 12; i++) {
      const u = (i / 12) * Math.PI * 2;
      const pts: Pt[] = [top];
      for (const d of [1.5, 3.5, 6, 8.5]) pts.push(this.skull(H.y1 - d * k, u, 0.9));
      line(pts, color, 0.85, 0.4);
    }
    // … et ses deux pans qui descendent devant les oreilles jusqu'à la mâchoire
    for (const sd of [1, -1]) {
      const pts: Pt[] = [];
      for (let j = 0; j <= 10; j++) pts.push(this.skull(H.y1 - (8.5 + 1.3 * j) * k, sd * (1.25 - 0.02 * j), 1.0 + 0.1 * j));
      line(pts, color, 1.0, 0.7);
      const back: Pt[] = [];
      for (let j = 0; j <= 10; j++) back.push(this.skull(H.y1 - (8.5 + 1.3 * j) * k, sd * (1.85 + 0.03 * j), 1.0 + 0.1 * j));
      line(back, color, 0.85, 0.5);
      line([pts[10], back[10]], color, 0.85, 0.6);
    }
  }

  private tonsure(line: LineFn, color: string): void {
    const H = this.head!, k = this.k;
    // une couronne de cheveux courts, le sommet rasé
    line(this.ring(H.y1 - 4 * k, 0.6, 48), color, 1.05, 0.75, true);
    line(this.ring(H.y1 - 10 * k, 0.8, 48), color, 0.85, 0.45, true);
    for (let i = 0; i < 64; i++) {
      const u = (i / 64) * Math.PI * 2;
      const wob = 0.6 * Math.sin(i * 2.3);
      line([this.skull(H.y1 - (4 + 0.3 * wob) * k, u, 0.6), this.skull(H.y1 - (8 + wob) * k, u + 0.05, 1.0), this.skull(H.y1 - (10.5 + wob) * k, u + 0.02, 0.8)], color, 0.6, 0.55);
    }
  }

  private chaperon(line: LineFn, color: string, t: number): void {
    const H = this.head!, k = this.k;
    // le bourrelet : un gros boudin roulé autour de la tête
    const y = H.y1 - 3.5 * k;
    for (const [dy, off] of [[-1.6, 2.4], [0, 3.6], [1.6, 2.6], [2.6, 0.8]]) line(this.ring(y + dy * k, off, 48), color, 1.05, 0.7, true);
    for (let i = 0; i < 24; i++) {
      const u = (i / 24) * Math.PI * 2;
      line([this.skull(y - 1.6 * k, u, 2.4), this.skull(y, u + 0.12, 3.6), this.skull(y + 1.6 * k, u + 0.24, 2.6)], color, 0.85, 0.5);
    }
    // la calotte, et la cornette qui pend sur le côté
    const top = this.crownPt(-1.5);
    for (let i = 0; i < 8; i++) line([this.skull(y + 2.6 * k, (i / 8) * Math.PI * 2, 0.8), top], color, 0.85, 0.4);
    const p0 = this.skull(y, -2.3, 3.4);
    const tail: Pt[] = [];
    for (let j = 0; j <= 14; j++) {
      const u = j / 14;
      tail.push([p0[0] - 6 * k * u, p0[1] - 30 * k * u, p0[2] - 3 * k * u + 1.2 * k * Math.sin(t * 1.3 + u * 3)]);
    }
    line(tail, color, 1.3, 0.7);
    line(tail.map(([x, yy, z]) => [x - 2.5 * k, yy, z + 1.5 * k] as Pt), color, 0.85, 0.45);
  }

  private chapeau(line: LineFn, color: string, tilt: number): void {
    const H = this.head!, k = this.k;
    const y = H.y1 - 4.5 * k;
    // de travers : on incline autour de l'axe avant-arrière, au-dessus de la tête
    const c = this.crownPt(4.5);
    const rot = (p: Pt): Pt => {
      const dy = p[1] - c[1], dz = p[2];
      return [p[0], c[1] + dy * Math.cos(tilt) - dz * Math.sin(tilt), dy * Math.sin(tilt) + dz * Math.cos(tilt)];
    };
    const L = (pts: Pt[], w: number, a: number, close = false) => line(pts.map(rot), color, w, a, close);
    L(this.ring(y, 7.5, 56), 1.2, 0.8, true); // le bord
    L(this.ring(y, 4.5, 56), 0.85, 0.45, true);
    L(this.ring(y + 0.3 * k, 1.0, 48), 1.0, 0.7, true); // le pied de la calotte
    const top = this.ring(y + 9 * k, 0.3, 48).map(([x, yy, z]) => [c[0] + (x - c[0]) * 0.85, yy, z * 0.85] as Pt);
    L(top, 1.0, 0.7, true);
    for (let i = 0; i < 12; i++) L([this.skull(y + 0.3 * k, (i / 12) * Math.PI * 2, 1.0), top[i * 4]], 0.85, 0.45);
    // une plume sur le côté
    const f0 = top[36];
    const plume: Pt[] = [];
    for (let j = 0; j <= 10; j++) plume.push([f0[0] - 14 * k * (j / 10), f0[1] + 8 * k * Math.sin((j / 10) * 2.2), f0[2] - 2 * k]);
    L(plume, 1.05, 0.75);
    for (let j = 2; j < 10; j++) L([plume[j], [plume[j][0] - 1.5 * k, plume[j][1] + 2.2 * k, plume[j][2]]], 0.6, 0.45);
  }

  private capuche(line: LineFn, color: string): void {
    const H = this.head!, k = this.k;
    // le capuchon relevé : il enveloppe le crâne et la nuque, et s'ouvre autour du visage
    const open = 0.95; // demi-ouverture du visage (radians, autour de l'avant)
    for (const d of [0, 3, 7, 11, 15, 19]) line(this.ring(H.y1 - d * k, 2.6 + 0.12 * d, 36, open, Math.PI * 2 - open), color, 0.85, 0.5);
    const peak: Pt = [this.crownPt(0)[0] - 9 * k, H.y1 + 4 * k, 0];
    for (let i = 0; i <= 10; i++) {
      const u = open + ((Math.PI * 2 - 2 * open) * i) / 10;
      const pts: Pt[] = [peak];
      for (const d of [0, 3, 7, 11, 15, 19, 24]) pts.push(this.skull(H.y1 - d * k, u, 2.6 + 0.12 * d + (d > 19 ? 3 : 0)));
      line(pts, color, i === 0 || i === 10 ? 1.2 : 0.85, i === 0 || i === 10 ? 0.85 : 0.45);
    }
  }

  private cheveux(line: LineFn, color: string, t: number): void {
    const H = this.head!, k = this.k;
    const top = this.crownPt(-0.4);
    // des mèches du sommet vers la nuque et les tempes, la frange sur le front
    for (let i = 0; i < 30; i++) {
      const u = (i / 30) * Math.PI * 2;
      const front = Math.cos(u) > 0.55;
      const len = front ? 6.5 : 12 + 2 * Math.sin(i * 1.7);
      const pts: Pt[] = [top];
      for (let j = 1; j <= 8; j++) {
        const d = (len * j) / 8;
        const p = this.skull(H.y1 - d * k, u + 0.04 * Math.sin(i + j), 0.9 + 0.15 * j);
        p[0] += 0.25 * k * Math.sin(t * 0.8 + i);
        pts.push(p);
      }
      line(pts, color, 0.85, 0.55);
    }
  }

  private bonnet(line: LineFn, color: string): void {
    const H = this.head!, k = this.k;
    // un bonnet rond à revers
    line(this.ring(H.y1 - 6 * k, 1.6, 44), color, 1.2, 0.85, true);
    line(this.ring(H.y1 - 4.5 * k, 1.7, 44), color, 1.0, 0.65, true);
    line(this.ring(H.y1 - 2.5 * k, 1.2, 44), color, 0.85, 0.5, true);
    const top = this.crownPt(-1.8);
    for (let i = 0; i < 10; i++) {
      const u = (i / 10) * Math.PI * 2;
      line([this.skull(H.y1 - 4.5 * k, u, 1.7), this.skull(H.y1 - 2.5 * k, u, 1.2), top], color, 0.85, 0.45);
    }
    // le pompon
    const pts: Pt[] = [];
    for (let i = 0; i <= 16; i++) {
      const u = (i / 16) * Math.PI * 2;
      pts.push([top[0] + 1.6 * k * Math.cos(u), top[1] + 1.6 * k + 1.6 * k * Math.sin(u), 0]);
    }
    line(pts, color, 1.05, 0.75, true);
  }

  /** une flûte à bec, de la bouche vers l'avant et le bas */
  private flute(line: LineFn): void {
    const H = this.head!, k = this.k;
    const y = H.y1 - 16.3 * k;
    const s = H.at(y);
    if (!s) return;
    const x0 = s.F + 0.6 * k;
    const dir: Pt = [Math.cos(-0.75), Math.sin(-0.75), 0];
    const L = 30;
    const end: Pt = [x0 + dir[0] * L, y + dir[1] * L, 0];
    for (const dz of [-0.9, 0.9]) line([[x0, y, dz], [end[0], end[1], dz * 1.3]], "#ffb340", 1.05, 0.85);
    // les trous, et le pavillon
    for (let i = 2; i <= 8; i++) {
      const u = (i / 10) * L;
      line([[x0 + dir[0] * u - 0.6, y + dir[1] * u - 0.6, 1.0], [x0 + dir[0] * u + 0.6, y + dir[1] * u + 0.6, 1.0]], "#eef6f8", 0.85, 0.7);
    }
    const bell: Pt[] = [];
    for (let i = 0; i <= 16; i++) {
      const u = (i / 16) * Math.PI * 2;
      bell.push([end[0] + 0.8 * Math.cos(u) * -dir[1], end[1] + 0.8 * Math.cos(u) * dir[0], 1.9 * Math.sin(u)]);
    }
    line(bell, "#ffb340", 1.05, 0.8, true);
  }
}

type LineFn = (pts: Pt[], color: string, w: number, alpha: number, close?: boolean) => void;
