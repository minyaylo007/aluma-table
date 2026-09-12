// Measures the on-page 3D viewer: time from Goren.mount() to the first rendered frame, long
// tasks on the main thread, and a tone switch — under a 4x CPU throttle in headless Chromium
// (SwiftShader WebGL, so GPU time is pessimistic).
//
//   node tools/viewer_perf.js            # 4x throttle, 390 px phone box and 760 px desktop box
//   node tools/viewer_perf.js --cpu=1    # no throttle
//
// Serves site/ over a local http server (textures + HDR are fetched like in production) and
// mounts the viewer into a hero-sized box that starts display:none, like #viewer on the page.

const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'site');
const opt = Object.fromEntries(process.argv.slice(2).filter(a => a.startsWith('--')).map(a => { const [k, v] = a.slice(2).split('='); return [k, v === undefined ? '1' : v]; }));
const CPU = +opt.cpu || 4;
const MIME = { '.js': 'text/javascript', '.jpg': 'image/jpeg', '.hdr': 'application/octet-stream', '.html': 'text/html', '.css': 'text/css', '.webp': 'image/webp' };

const PAGE = `<!doctype html><meta charset="utf-8"><title>viewer perf</title>
<style>body{margin:0;background:#e9e6de}.hero{position:relative;width:WIDTHpx;aspect-ratio:16/10}
.hero img{display:block;width:100%;height:100%;background:#ddd}.viewer{position:absolute;inset:0;display:none}.viewer.is-on{display:block}
.viewer canvas{width:100%!important;height:100%!important}</style>
<div class="hero" id="hero-media"><img alt=""><div class="viewer" id="viewer" aria-label="rotate"></div></div>
<script>
window.__long = []; window.__t0 = 0;
new PerformanceObserver(l => { for (const e of l.getEntries()) window.__long.push({ start: Math.round(e.startTime), dur: Math.round(e.duration) }); }).observe({ entryTypes: ['longtask'] });
</script>
<script src="/assets/goren3d.js"></script>`;

function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const u = decodeURIComponent(req.url.split('?')[0]);
      if (u.startsWith('/perf')) { const w = +(new URL(req.url, 'http://x').searchParams.get('w') || 760); res.setHeader('content-type', 'text/html'); return res.end(PAGE.replace('WIDTH', w)); }
      const f = path.join(SITE, u);
      if (!f.startsWith(SITE) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.statusCode = 404; return res.end('nope'); }
      res.setHeader('content-type', MIME[path.extname(f)] || 'application/octet-stream');
      fs.createReadStream(f).pipe(res);
    }).listen(0, '127.0.0.1', () => resolve(srv));
  });
}

(async () => {
  const srv = await serve();
  const port = srv.address().port;
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const [label, w, dpr] of [['phone 390', 390, 3], ['desktop 760', 760, 1.5]]) {
    const ctx = await b.newContext({ viewport: { width: Math.max(w, 400), height: 800 }, deviceScaleFactor: dpr });
    const p = await ctx.newPage();
    const cdp = await ctx.newCDPSession(p);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU });
    p.on('pageerror', e => console.error('  page error:', e.message));
    await p.goto(`http://127.0.0.1:${port}/perf?w=${w}`, { waitUntil: 'load' });
    await p.waitForFunction(() => !!window.Goren);
    const r = await p.evaluate(async () => {
      const el = document.getElementById('viewer');
      const prog = [];
      const t0 = performance.now(); window.__t0 = t0;
      const api = await window.Goren.mount(el, { tone: 'natural', state: 'closed', onProgress: f => prog.push([Math.round(performance.now() - t0), +f.toFixed(2)]) });
      const tMount = performance.now() - t0;
      el.classList.add('is-on'); document.getElementById('hero-media').classList.add('is-3d');
      const c = el.querySelector('canvas');
      const canvas = { css: [c.clientWidth, c.clientHeight], buffer: [c.width, c.height] };
      await new Promise(r => setTimeout(r, 300));
      const tSwitch0 = performance.now(); await api.setTone('smoked'); const tSwitch = performance.now() - tSwitch0;
      await new Promise(r => setTimeout(r, 4500));       // let the idle turntable finish
      const longAfterReady = window.__long.filter(l => l.start > t0 + tMount);
      const longDuringMount = window.__long.filter(l => l.start >= t0 && l.start <= t0 + tMount);
      const tState0 = performance.now(); api.setState('open'); const tState = performance.now() - tState0;
      return { tMount: Math.round(tMount), tSwitch: Math.round(tSwitch), tState: Math.round(tState), canvas, prog,
        longDuringMount, longAfterReady, worstAfterReady: Math.max(0, ...longAfterReady.map(l => l.dur)) };
    });
    await p.screenshot({ path: path.join(ROOT, 'renders-master', `viewer-perf-${w}.png`), clip: { x: 0, y: 0, width: w, height: Math.round(w / 1.6) } });
    console.log(`\n[${label}] cpu x${CPU}  mount->first frame ${r.tMount} ms  tone switch ${r.tSwitch} ms  state switch ${r.tState} ms`);
    console.log(`  canvas css ${r.canvas.css.join('x')} buffer ${r.canvas.buffer.join('x')}`);
    console.log(`  progress: ${r.prog.map(([t, f]) => `${f}@${t}`).join(' ')}`);
    console.log(`  long tasks during mount: ${r.longDuringMount.map(l => l.dur + 'ms').join(', ') || 'none'}`);
    console.log(`  long tasks after ready:  ${r.longAfterReady.map(l => l.dur + 'ms').join(', ') || 'none'}  (worst ${r.worstAfterReady} ms)`);
    results.push({ label, ...r });
    await ctx.close();
  }
  await b.close(); srv.close();
  const bad = results.filter(r => r.tMount > 1500 || r.worstAfterReady > 200);
  console.log(bad.length ? `\nFAIL: ${bad.map(r => r.label).join(', ')} over budget (first frame <= 1500 ms, long task <= 200 ms)` : '\nPASS: first frame <= 1500 ms and no long task > 200 ms after ready');
  process.exit(bad.length ? 1 : 0);
})();
