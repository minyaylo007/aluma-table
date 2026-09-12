// Headless renders of the GOREN 3D model.
//
//   node tools/render3d.js                        all views, all tones, both states
//   node tools/render3d.js hero natural           one view, one tone (both states)
//   node tools/render3d.js hero natural closed    one image
//   options: --bg=efeeea   background / floor colour (default: the page ground --plaster)
//            --out=DIR     output folder (default renders-master/)
//            --tex=master|1024|512   texture set (default master, 2048 px, from tools/bake_textures.py)
//            --scale=0.5   quick previews at a fraction of the master size
//
// Output: renders-master/<view>-<tone>-<state>.png at 2400 px wide (not deployed), then
// tools/optimise_renders.py writes WebP + AVIF variants into site/assets/renders/.
//
// Framing is deterministic (Goren.frame fits the model's bounding box), so every tone of a
// view shares the exact same pixels for geometry and the page's tone cross-fade stays clean.
//
// Product set (2026-09-09, site/assets/product/ via tools/product_assets.py):
//   node tools/render3d.js --product                    all 14 masters -> renders-master/product/<id>.png + <id>.json
//   node tools/render3d.js --product goren-compare      only the ids starting with this
//   --bg defaults to f4f1ea here (the page ground since 2026-09-09); --scale for previews;
//   --q="margin=0.15&lift=-0.03" appends query params to iterate a view (bake the result into VIEWS)
//   --ss=2   supersample: render at 2x and LANCZOS-downscale (Pillow) to the nominal size. Clean arrises, and
//            the 1.6 mm seam becomes a steady hairline instead of a dotted one. The 2x frame is kept in
//            renders-master/product/ss2/ (product_assets.py cuts the finish swatches from it).
//   The .json sidecar carries the fitted camera (position, target, az/el, height) and the pipeline string.

const { chromium } = require('playwright');
const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const HTML = 'file:///' + path.join(__dirname, 'render3d.html').replace(/\\/g, '/');

const VIEWS = { hero: [2400, 1500], hero2: [2400, 1500], front: [2400, 1200], end: [1600, 1600], top: [2000, 1400], detail: [1600, 1600] };
const TONES = ['natural', 'smoked', 'white'];
const STATES = ['closed', 'open'];

// The product ids are fixed — the page build depends on these exact names.
// q: harness params that are part of the asset's definition (fit state, light rig for the close-ups).
const EDGE_Q = 'key=-0.5,1.75,2.15&ki=2.2';              // raking key across the top, the end face left to the HDRI
const FRAME_Q = 'fill=1.0&bounce=0.9';                    // fill from the camera side so the beam is not a void
const PRODUCT = [
  { id: 'goren-studio-hero-natural-closed',   view: 'studio',  tone: 'natural', state: 'closed', w: 2400, h: 1091 },
  { id: 'goren-studio-hero-m-natural-closed', view: 'studioM', tone: 'natural', state: 'closed', w: 2000, h: 1333 },
  ...TONES.flatMap(tone => STATES.map(state => ({ id: `goren-compare-${tone}-${state}`, view: 'compare', tone, state, w: 2400, h: 1600, q: 'fit=open' }))),
  ...TONES.map(tone => ({ id: `goren-edge-detail-${tone}`, view: 'edge', tone, state: 'closed', w: 1600, h: 1600, q: EDGE_Q })),
  ...TONES.map(tone => ({ id: `goren-frame-detail-${tone}`, view: 'frame', tone, state: 'closed', w: 1600, h: 1200, q: FRAME_Q }))
];

const args = process.argv.slice(2);
const opt = Object.fromEntries(args.filter(a => a.startsWith('--')).map(a => { const i = a.indexOf('='); return i < 0 ? [a.slice(2), '1'] : [a.slice(2, i), a.slice(i + 1)]; }));   // split on the first '=' only: --q carries its own k=v pairs
const positional = args.filter(a => !a.startsWith('--'));
const [onlyView, onlyTone, onlyState] = positional;
const PRODUCT_MODE = opt.product !== undefined;
const BG = (opt.bg || (PRODUCT_MODE ? 'f4f1ea' : 'efeeea')).replace(/^#/, '');
const OUT = path.resolve(ROOT, opt.out || (PRODUCT_MODE ? 'renders-master/product' : 'renders-master'));
const TEX = opt.tex || 'master';
const SCALE = +opt.scale || 1;
const SS = Math.max(1, Math.round(+opt.ss || 1));
const EXTRA_Q = opt.q && opt.q !== '1' ? opt.q : '';
const DOWNSCALE = "import sys; from PIL import Image; s, d, w, h = sys.argv[1:]; Image.open(s).convert('RGB').resize((int(w), int(h)), Image.LANCZOS).save(d)";

function gitSha() { try { return execSync('git rev-parse --short HEAD', { cwd: ROOT, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch (e) { return 'unknown'; } }

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (TEX === 'master' && !fs.existsSync(path.join(ROOT, 'renders-master', 'textures', 'oak-normal-2048.jpg'))) {
    console.error('missing renders-master/textures — run: python tools/bake_textures.py'); process.exit(1);
  }
  const b = await chromium.launch({ args: [
    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--allow-file-access-from-files'   // textures + HDRI are read from file:// by the page
  ] });
  const jobs = [];
  if (PRODUCT_MODE) {
    for (const p of PRODUCT) {
      if (positional.length && !positional.some(pre => p.id.startsWith(pre))) continue;
      jobs.push({ ...p, name: p.id, w: Math.round(p.w * SCALE), h: Math.round(p.h * SCALE), q: [p.q, EXTRA_Q].filter(Boolean).join('&') });
    }
  } else {
    for (const [view, [w, h]] of Object.entries(VIEWS)) {
      if (onlyView && view !== onlyView) continue;
      for (const tone of TONES) {
        if (onlyTone && tone !== onlyTone) continue;
        for (const state of STATES) {
          if (onlyState && state !== onlyState) continue;
          if ((view === 'detail' || view === 'end') && state === 'open') continue;
          jobs.push({ view, tone, state, name: `${view}-${tone}-${state}`, w: Math.round(w * SCALE), h: Math.round(h * SCALE), q: EXTRA_Q });
        }
      }
    }
  }
  const sha = gitSha(), t0 = Date.now();
  if (SS > 1) fs.mkdirSync(path.join(OUT, `ss${SS}`), { recursive: true });
  for (const j of jobs) {
    const rw = j.w * SS, rh = j.h * SS;                       // rendered size (supersampled)
    const p = await b.newPage({ viewport: { width: rw, height: rh }, deviceScaleFactor: 1 });
    p.on('pageerror', e => console.error('  page error:', e.message));
    const query = `view=${j.view}&tone=${j.tone}&state=${j.state}&w=${rw}&h=${rh}&bg=${BG}&tex=${TEX}` + (j.q ? `&${j.q}` : '');
    await p.goto(`${HTML}?${query}`, { waitUntil: 'load' });
    await p.waitForFunction(() => window.__done === true || window.__error, null, { timeout: 300000 });
    const err = await p.evaluate(() => window.__error);
    if (err) { console.error('render failed', j, err); await p.close(); continue; }
    await p.waitForTimeout(200);
    const file = path.join(OUT, `${j.name}.png`);
    const ssFile = SS > 1 ? path.join(OUT, `ss${SS}`, `${j.name}.png`) : null;
    await p.screenshot({ path: ssFile || file, clip: { x: 0, y: 0, width: rw, height: rh } });
    const frame = await p.evaluate(() => window.__frame);
    await p.close();
    if (ssFile) {
      const r = spawnSync('python', ['-c', DOWNSCALE, ssFile, file, String(j.w), String(j.h)], { stdio: 'inherit' });
      if (r.status !== 0) { console.error('downscale failed', j.name); continue; }
    }
    if (PRODUCT_MODE) {
      const side = {
        id: j.id, view: j.view, tone: j.tone, state: j.state, width: j.w, height: j.h, scale: SCALE, supersample: SS,
        ss_source: ssFile ? path.relative(ROOT, ssFile).replace(/\\/g, '/') : null, bg: '#' + BG, tex: TEX, hdr: 1,
        query, harness_params: j.q || '',
        pipeline: `tools/render3d.js --product ${j.id}${SS > 1 ? ` --ss=${SS}` : ''} (view=${j.view} tone=${j.tone} state=${j.state} bg=${BG} tex=${TEX} hdr=1${j.q ? ' ' + j.q.replace(/&/g, ' ') : ''})`,
        goren3d_sha: sha, generated: new Date().toISOString(), frame
      };
      fs.writeFileSync(path.join(OUT, `${j.name}.json`), JSON.stringify(side, null, 2));
    }
    console.log('rendered', path.basename(file), `${j.w}x${j.h}`, `cam d=${frame.distance.toFixed(2)} fov=${frame.fov} az=${frame.az.toFixed(1)} el=${frame.el.toFixed(1)} h=${frame.height.toFixed(2)}m`, `${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await b.close();
})();
