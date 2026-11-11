// La vidéo du banquet : la page Duet (?show=banquet) calculée image par image, avec le mixage.
//
//   bun tools/make_video.ts [sortie.mp4] [--fps 30] [--size 1920x1080] [--from 0] [--to fin] [--gpu] [--table]
//
// --table : la tablée (?table=banquet) au lieu de la page Duet (?show=banquet).
//
// Il faut le serveur de CHIMERA (`bun run dev` dans chimera/) et ffmpeg (paquet Python
// imageio-ffmpeg du .venv). Le temps de la page est piloté : l'horloge audio est remplacée par
// performance.now(), que l'horloge simulée de Playwright avance de 1/fps entre deux captures. Les
// têtes, les mots et le son restent donc synchrones quelle que soit la vitesse de calcul.
import { chromium } from "../chimera/node_modules/playwright-core/index.mjs";
import { spawn, execFileSync } from "node:child_process";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..");
const args = process.argv.slice(2);
const opt = (name: string, dflt: string) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
};
const out = resolve(args[0] && !args[0].startsWith("--") ? args[0] : `${ROOT}/out/banquet.mp4`);
const fps = Number(opt("--fps", "30"));
const [W, H] = opt("--size", "1920x1080").split("x").map(Number);
const from = Number(opt("--from", "0"));
const toArg = opt("--to", "");
const gpu = args.includes("--gpu");
const ffmpeg = execFileSync(`${ROOT}/.venv/Scripts/python`, ["-c", "import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())"]).toString().trim();
const audio = `${ROOT}/chimera/public/shows/banquet/banquet.wav`;

const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  args: gpu ? ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"] : ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: W, height: H } });
page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}`));
page.on("console", (m) => m.type() === "error" && console.log(`[console] ${m.text()}`));

// l'horloge audio suit performance.now() (que l'horloge simulée pilote), sans latence ni son
await page.addInitScript(() => {
  Object.defineProperty(BaseAudioContext.prototype, "currentTime", { get: () => performance.now() / 1000 });
  Object.defineProperty(AudioContext.prototype, "getOutputTimestamp", { value: undefined });
  Object.defineProperty(AudioContext.prototype, "outputLatency", { get: () => 0 });
  Object.defineProperty(AudioContext.prototype, "baseLatency", { get: () => 0 });
  // le son part dans un gain muet : la vidéo prend le mixage, pas la sortie du navigateur
  const realDestination = Object.getOwnPropertyDescriptor(BaseAudioContext.prototype, "destination")!.get!;
  const mutes = new WeakMap<BaseAudioContext, GainNode>();
  Object.defineProperty(BaseAudioContext.prototype, "destination", {
    get() {
      let g = mutes.get(this);
      if (!g) {
        g = this.createGain();
        g.gain.value = 0;
        g.connect(realDestination.call(this));
        mutes.set(this, g);
      }
      return g;
    },
  });
});
await page.clock.install({ time: 0 });
await page.goto(`http://127.0.0.1:5317/?${args.includes("--table") ? "table" : "show"}=banquet`);
// le chargement : on fait avancer l'horloge jusqu'à ce que Play soit actif
for (let i = 0; ; i++) {
  await page.clock.runFor(200);
  if (await page.evaluate(() => { const b = document.querySelector("button.primary") as HTMLButtonElement | null; return !!b && !b.disabled; })) break;
  if (i > 1500) throw new Error("le spectacle ne se charge pas");
  await new Promise((r) => setTimeout(r, 20));
}
const renderer = await page.evaluate(() => {
  const gl = document.createElement("canvas").getContext("webgl");
  const ext = gl?.getExtension("WEBGL_debug_renderer_info");
  return ext ? gl!.getParameter(ext.UNMASKED_RENDERER_WEBGL) : "?";
});
console.log("rendu 3D :", renderer);
const duration = await page.evaluate(() => {
  const s = document.querySelector(".duet-time")?.textContent ?? "";
  const m = s.split("/")[1]?.trim().match(/(\d+):(\d+)/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : 0;
});
const to = toArg ? Number(toArg) : duration + 0.9;
// l'horloge simulée court en temps réel tant qu'on ne la met pas en pause : figée, elle n'avance plus
// que des pas de 1/fps (sinon le temps de chaque capture s'ajoutait et la page filait trop vite)
await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000); // (une marge : une page lourde avance pendant l appel)
// (clics en JavaScript : avec l'horloge simulée, Playwright attendrait des images qui ne viennent pas)
await page.evaluate((t) => {
  (document.querySelector("button.primary") as HTMLButtonElement).click();
  if (t > 0) {
    const s = document.querySelector('input[type="range"]') as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(s, String(t));
    s.dispatchEvent(new Event("input", { bubbles: true }));
  }
}, from);
await page.clock.runFor(50);
// la barre de lecture n'a rien à faire dans la vidéo
await page.addStyleTag({ content: ".duet-bar { visibility: hidden; }" });

const frames = Math.round((to - from) * fps);
const enc = spawn(ffmpeg, [
  "-y", "-loglevel", "error",
  "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
  "-ss", String(from), "-t", String(to - from), "-i", audio,
  "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p",
  "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out,
], { stdio: ["pipe", "inherit", "inherit"] });
const t0 = Date.now();
for (let f = 0; f < frames; f++) {
  await page.clock.runFor(1000 / fps);
  const jpg = await page.screenshot({ type: "jpeg", quality: 92 });
  if (!enc.stdin.write(jpg)) await new Promise((r) => enc.stdin.once("drain", r));
  if (f % (fps * (args.includes("--probe") ? 0.5 : 5)) === 0) {
    const el = (Date.now() - t0) / 1000;
    const rate = (f + 1) / el;
    const shown = await page.evaluate(() => document.querySelector(".duet-time")?.textContent);
    console.log(`${(from + (f + 1) / fps).toFixed(2).padStart(7)} s (page : ${shown})  |  ${rate.toFixed(1)} images/s  |  reste ~${((frames - f) / rate / 60).toFixed(1)} min`);
  }
}
enc.stdin.end();
await new Promise((r) => enc.on("close", r));
await browser.close();
console.log(`${out} : ${frames} images, ${((Date.now() - t0) / 60000).toFixed(1)} min de calcul`);
