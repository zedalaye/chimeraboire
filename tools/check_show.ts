// Ouvre le spectacle Duet dans Edge sans affichage, lance la lecture et prend des captures.
//   bun tools/check_show.ts <dossier des captures> [secondes...]
import { chromium } from "../chimera/node_modules/playwright-core/index.mjs";

const out = process.argv[2] ?? ".";
const at = (process.argv.slice(3).length ? process.argv.slice(3) : ["10.5", "30"]).map(Number);
const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  args: ["--autoplay-policy=no-user-gesture-required", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
page.on("console", (m) => (m.type() === "error" || m.type() === "warning") && console.log(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => console.log(`[pageerror] ${e.message}`));
await page.goto("http://127.0.0.1:5317/?show=banquet");
const play = page.getByRole("button", { name: "Play" });
await play.waitFor({ timeout: 120000 });
await page.waitForFunction(() => !(document.querySelector("button.primary") as HTMLButtonElement)?.disabled, null, { timeout: 120000 });
console.log("chargé");
await play.click();
for (const t of at) {
  await page.getByRole("slider", { name: "Position in the song" }).evaluate((el, t) => {
    const s = el as HTMLInputElement;
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    set.call(s, String(t));
    s.dispatchEvent(new Event("input", { bubbles: true }));
  }, t);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/show-${t}.png` });
  console.log("capture", t, await page.locator(".duet-time").textContent());
}
await browser.close();
