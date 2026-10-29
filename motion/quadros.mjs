// Quadros de um projeto de motion do kit-editor (sem renderizar o vídeo): abre o index.html no Chrome do sistema,
// posiciona a timeline do GSAP em cada instante e salva PNG com alfa. Roda dentro do wrapper sem rede
// (unshare -rn) pelo kit.py (comando `motion-quadros`). Só lê o projeto local; não baixa nada.
// Uso: node quadros.mjs <index.html> <W> <H> <saida_dir> <t1,t2,...> [--sem-fundo]
// --sem-fundo esconde os fundos de recorte (#fx*-bg) para medir só o conteúdo contra a safe area.
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { mkdirSync } from "node:fs";

const puppeteer = createRequire(process.env.HF_NODE_MODULES + "/")("puppeteer-core");
const [, , html, W, H, outDir, tlist, ...flags] = process.argv;
const semFundo = flags.includes("--sem-fundo");
mkdirSync(outDir, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.HYPERFRAMES_BROWSER_PATH || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--force-device-scale-factor=1"],
});
const page = await browser.newPage();
await page.setViewport({ width: +W, height: +H, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(html).href, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
for (const t of tlist.split(",").map(Number)) {
  await page.evaluate((t, semFundo) => {
    const tl = window.__timelines.main;
    tl.pause();
    tl.seek(t, false);
    for (const c of document.querySelectorAll(".clip")) {
      const s = parseFloat(c.dataset.start), d = parseFloat(c.dataset.duration);
      let vis = t >= s - 1e-6 && t < s + d - 1e-6;
      if (semFundo && /-bg$/.test(c.id)) vis = false;
      c.style.visibility = vis ? "visible" : "hidden";
    }
  }, t, semFundo);
  await page.screenshot({ path: `${outDir}/t_${String(Math.round(t * 1000)).padStart(6, "0")}.png`, omitBackground: true });
}
await browser.close();
