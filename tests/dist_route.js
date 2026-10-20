// dist/ (python3 build.py) у браузері без порту й без мережі: page.route на вигаданому origin.
// API підмінено, будь-який сторонній запит обривається. Спільне для a11y.spec.js і responsive.spec.js.
const fs = require('fs');
const path = require('path');

const DIST = path.resolve(__dirname, '..', 'dist');
const ORIGIN = 'https://aluma.test';
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.webp': 'image/webp', '.avif': 'image/avif', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2',
  '.json': 'application/json', '.glb': 'model/gltf-binary', '.webmanifest': 'application/manifest+json',
  '.xml': 'application/xml', '.txt': 'text/plain', '.ico': 'image/x-icon',
};

// Кожна .html у dist/ — сторінка: index.html → /, en/index.html → /en/, privacy.html → /privacy.
// (Файли без розширення поруч — копії .html для чистих адрес; віддаються як text/html.)
function pages() {
  if (!fs.existsSync(DIST)) return [];
  const out = [];
  (function walk(dir) {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name);
      if (fs.statSync(full).isDirectory()) { if (name !== 'assets') walk(full); continue; }
      if (!name.endsWith('.html')) continue;
      const rel = path.relative(DIST, full).split(path.sep).join('/');
      out.push(rel.endsWith('index.html') ? '/' + rel.slice(0, -'index.html'.length) : '/' + rel.slice(0, -5));
    }
  })(DIST);
  return out;
}

function fileFor(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]);
  const candidates = clean.endsWith('/') ? [clean + 'index.html'] : [clean, clean + '.html', clean + '/index.html'];
  for (const c of candidates) {
    const full = path.join(DIST, c);
    if (full.startsWith(DIST) && fs.existsSync(full) && fs.statSync(full).isFile()) return full;
  }
  return null;
}

async function serveDist(page) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname === '/api/fx/config') {
      // з пікселем — щоб банер згоди (tracking.js або вітрини) теж показувався
      return route.fulfill({ json: { pixel_id: '123456789012345', clarity_id: null, prelaunch: true, contact: {} } });
    }
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: { ok: true } });
    const file = fileFor(url.pathname);
    if (!file) return route.fulfill({ status: 404, contentType: 'text/html', body: fs.readFileSync(path.join(DIST, '404.html')) });
    return route.fulfill({ status: 200, contentType: TYPES[path.extname(file) || '.html'] || 'application/octet-stream', body: fs.readFileSync(file) });
  });
}

const built = () => fs.existsSync(path.join(DIST, 'index.html'));

module.exports = { DIST, ORIGIN, pages, serveDist, built };
