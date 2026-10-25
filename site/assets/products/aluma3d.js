/* ALUMA — параметричні 3D-моделі товарів каталогу (catalog/products.json).
   Одне джерело для рендерів (tools/render_products.html) і для перегляду на сторінці.

   window.Aluma3D.build(THREE, opts)  -> Promise<model { group, bounds(), setFinish(id), dispose() }>
     opts: { product: 'tavor'|'sahar'|'ofek'|'saf'|'tal', size: {length_cm, width_cm, height_cm, extended_cm?},
             finish: 'natural'|'light'|'honey'|'smoked'|'black', base: 'oak'|'steel', state: 'closed'|'open',
             texDir, texRes — тека й розмір файлів тону для рендерів (типово /assets/textures/ і '1024', як на сайті),
             textures: { albedo, normal, rough } — один набір без тонування (старі сцени),
             decor: true — ваза/книжки для інтер'єрного кадру }
   window.Aluma3D.studio(THREE, scene, renderer, o)    -> світло й підлога світлого фону; середовище з градієнтів
   window.Aluma3D.interior(THREE, scene, renderer, o)  -> стіна, підлога-плитка, сонце з вікна з тінню рами
   window.Aluma3D.frame(THREE, camera, box, view)      -> детермінований кадр: усі кути коробки в кадрі
   window.Aluma3D.swatch(THREE, opts)                  -> дощечка шпону для свотча тонування
   window.Aluma3D.mount(el, opts)                      -> Promise<{ setFinish, setState, setSize, setBase, dispose }>
                                                          (three.js 0.160.0 — свій файл /assets/vendor/three.min.js)
     opts: { product, size, finish, base, state, label, description, keysText, roleText } — малюється лише на дію,
     жодної анімації; полотно aria-hidden, контейнер — role=img у фокусі, опис — прихований абзац.

   Розміри — з сітки каталогу; усе в метрах, x — довжина, z — глибина (перед до камери), y — вгору.
   Матеріал: справжні CC0-скани шпону Poly Haven, свій на тон (FINISHES, tools/oak_tones.py): альбедо тону,
   нормалі й шорсткість його скану — ті самі файли, що в зразках на сайті й у Blender-рендерах.
*/
(function (root) {
  'use strict';

  var TILE = 1.2;        // метрів дерева на повтор текстури — масивні деталі
  var TILE_FACE = 2.4;   // шпон стільниці: один повтор на 2,4 м, довше за відкритий стіл — стовпчик шпону не повторюється
  var GAP = 0.0016;      // шов між половинами й вставкою: 1,6 мм
  var SINK = 0.0005;     // деталі в одній площині заходять одна в одну на 0,5 мм — без z-fighting

  // Тони: кожен — справжній скан шпону з олійним тоном (tools/oak_tones.py, docs/ASSETS.md «Тони дуба»).
  //   albedo, nmap, rmap — альбедо тону, нормалі й шорсткість його скану; шляхи абсолютні й повні — build.py знаходить їх
  //   тут, публікує й хешує; scale — щільність повтору (скани 1 м проти 1,83 м),
  //   rough — множник шорсткості (олія з пігментом матовіша), normal — сила рельєфу. Ті самі файли бере Blender.
  var FINISHES = {
    natural: { rough: 1.00, normal: 0.7,  scale: 1,    albedo: '/assets/textures/tone-natural-albedo-1024.jpg',
               nmap: '/assets/textures/oak-normal-1024.jpg',        rmap: '/assets/textures/oak-rough-1024.jpg' },
    light:   { rough: 1.08, normal: 0.7,  scale: 1.83, albedo: '/assets/textures/tone-light-albedo-1024.jpg',
               nmap: '/assets/textures/washed-oak-normal-1024.jpg', rmap: '/assets/textures/washed-oak-rough-1024.jpg' },
    honey:   { rough: 0.95, normal: 0.7,  scale: 1,    albedo: '/assets/textures/tone-honey-albedo-1024.jpg',
               nmap: '/assets/textures/oak-normal-1024.jpg',        rmap: '/assets/textures/oak-rough-1024.jpg' },
    smoked:  { rough: 1.00, normal: 0.7,  scale: 1.83, albedo: '/assets/textures/tone-smoked-albedo-1024.jpg',
               nmap: '/assets/textures/black-oak-normal-1024.jpg',  rmap: '/assets/textures/black-oak-rough-1024.jpg' },
    black:   { rough: 1.12, normal: 0.55, scale: 1.83, albedo: '/assets/textures/tone-black-albedo-1024.jpg',
               nmap: '/assets/textures/black-oak-normal-1024.jpg',  rmap: '/assets/textures/black-oak-rough-1024.jpg' }
  };


  function loadImage(url) {
    return new Promise(function (resolve, reject) {
      var im = new Image(); im.crossOrigin = 'anonymous';
      im.onload = function () { resolve(im); };
      im.onerror = function () { reject(new Error('image ' + url)); };
      im.src = url;
    });
  }

  // ---- геометрія: трикутники з підказкою нормалі, UV у світових метрах ---------------------------------
  function Builder() { this.p = []; this.n = []; this.uv = []; }
  Builder.prototype.push = function (p, n, t) { this.p.push(p[0], p[1], p[2]); this.n.push(n[0], n[1], n[2]); this.uv.push(t[0], t[1]); };
  Builder.prototype.tri = function (a, b, c, uvf, hint) {
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    var n = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx], len = Math.hypot(n[0], n[1], n[2]) || 1;
    n = [n[0] / len, n[1] / len, n[2] / len];
    if (hint && n[0] * hint[0] + n[1] * hint[1] + n[2] * hint[2] < 0) { var t = b; b = c; c = t; n = [-n[0], -n[1], -n[2]]; }
    this.push(a, n, uvf(a)); this.push(b, n, uvf(b)); this.push(c, n, uvf(c));
  };
  Builder.prototype.quad = function (a, b, c, d, uvf, hint) { this.tri(a, b, c, uvf, hint); this.tri(a, c, d, uvf, hint); };
  // чотирикутник з нормаллю в кожній вершині (гладкі вигини); порядок a-b-c-d — проти годинникової, якщо дивитися ззовні
  Builder.prototype.quadN = function (a, b, c, d, na, nb, nc, nd, ta, tb, tc, td) {
    this.push(a, na, ta); this.push(b, nb, tb); this.push(c, nc, tc);
    this.push(a, na, ta); this.push(c, nc, tc); this.push(d, nd, td);
  };
  Builder.prototype.geometry = function (THREE) {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    return g;
  };

  // Брусок, вирівняний по осях. grain: 'x'|'y'|'z' — куди йде волокно; UV = (поперек, уздовж) / tile.
  function box(bd, cx, cy, cz, w, h, d, grain, off, tile) {
    var x0 = cx - w / 2, x1 = cx + w / 2, y0 = cy - h / 2, y1 = cy + h / 2, z0 = cz - d / 2, z1 = cz + d / 2;
    off = off || [0, 0]; tile = tile || TILE;
    var ax = { x: 0, y: 1, z: 2 }[grain || 'x'];
    function uvFor(normalAxis) {
      var across = [0, 1, 2].filter(function (i) { return i !== normalAxis && i !== ax; })[0];
      var along = ax === normalAxis ? [0, 1, 2].filter(function (i) { return i !== normalAxis && i !== across; })[0] : ax;
      return function (p) { return [p[across] / tile + off[0], p[along] / tile + off[1]]; };
    }
    var P = function (x, y, z) { return [x, y, z]; };
    bd.quad(P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1), uvFor(1), [0, 1, 0]);
    bd.quad(P(x0, y0, z0), P(x1, y0, z0), P(x1, y0, z1), P(x0, y0, z1), uvFor(1), [0, -1, 0]);
    bd.quad(P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1), uvFor(2), [0, 0, 1]);
    bd.quad(P(x0, y0, z0), P(x1, y0, z0), P(x1, y1, z0), P(x0, y1, z0), uvFor(2), [0, 0, -1]);
    bd.quad(P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1), uvFor(0), [1, 0, 0]);
    bd.quad(P(x0, y0, z0), P(x0, y1, z0), P(x0, y1, z1), P(x0, y0, z1), uvFor(0), [-1, 0, 0]);
  }

  // Контури в площині xz (масив [x, z], проти годинникової, якщо дивитися згори).
  function roundedRect(cx, cz, L, W, r, seg) {
    r = Math.max(0, Math.min(r, L / 2, W / 2)); seg = seg || 10;
    var pts = [], hx = L / 2 - r, hz = W / 2 - r;
    var corners = [[hx, hz, 0], [-hx, hz, 0.5], [-hx, -hz, 1], [hx, -hz, 1.5]];
    corners.forEach(function (c) {
      for (var i = 0; i <= seg; i++) {
        var a = (c[2] + i / seg * 0.5) * Math.PI;
        pts.push([cx + c[0] + r * Math.cos(a), cz + c[1] + r * Math.sin(a)]);
        if (r === 0) break;
      }
    });
    return pts;
  }
  // Половина круга (D): дуга радіуса R з центром (cx, 0), відкрита в бік dir (+1 праворуч, -1 ліворуч), плюс лінія розрізу.
  function halfDisc(cx, R, dir, seg) {
    var pts = [];
    for (var i = 0; i <= seg; i++) {
      var a = -Math.PI / 2 + i / seg * Math.PI;
      pts.push([cx + dir * R * Math.cos(a), dir * R * Math.sin(a)]);
    }
    return pts;
  }
  function circle(cx, cz, R, seg) {
    var pts = [];
    for (var i = 0; i < seg; i++) { var a = i / seg * Math.PI * 2; pts.push([cx + R * Math.cos(a), cz + R * Math.sin(a)]); }
    return pts;
  }

  // Лофт по кільцях: rings = [{pts, y}], усі з однаковою кількістю точок. Верхня кришка — з першого кільця,
  // нижня — з останнього. sideGrain 'ring' — волокно вздовж контуру (кромка), 'y' — вертикально (ніжка).
  // capGrain — вісь волокна на кришці ('x' | 'z'), capTile — щільність шпону на кришці.
  function loft(THREE, bdSide, bdCap, rings, o) {
    o = o || {};
    var n = rings[0].pts.length, smooth = o.smooth === undefined ? 0.82 : o.smooth;
    var tile = o.tile || TILE, capTile = o.capTile || TILE, capOff = o.capOff || [0, 0];
    // довжина дуги по першому кільцю — координата UV вздовж контуру
    var s = [0];
    for (var k = 1; k <= n; k++) {
      var a = rings[0].pts[k - 1], b = rings[0].pts[k % n];
      s.push(s[k - 1] + Math.hypot(b[0] - a[0], b[1] - a[1]));
    }
    for (var r = 0; r < rings.length - 1; r++) {
      var A = rings[r], B = rings[r + 1], fn = [];
      for (var e = 0; e < n; e++) {          // нормаль кожної грані смуги
        var p0 = [A.pts[e][0], A.y, A.pts[e][1]], p1 = [A.pts[(e + 1) % n][0], A.y, A.pts[(e + 1) % n][1]];
        var q0 = [B.pts[e][0], B.y, B.pts[e][1]];
        var u = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]], v = [q0[0] - p0[0], q0[1] - p0[1], q0[2] - p0[2]];
        var nn = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
        var mid = [(p0[0] + p1[0]) / 2, (p0[2] + p1[2]) / 2], c = o.center || [0, 0];
        if (nn[0] * (mid[0] - c[0]) + nn[2] * (mid[1] - c[1]) < 0 && !o.inward) nn = [-nn[0], -nn[1], -nn[2]];
        var l = Math.hypot(nn[0], nn[1], nn[2]) || 1; fn.push([nn[0] / l, nn[1] / l, nn[2] / l]);
      }
      var vn = function (e, k) {             // нормаль вершини k для грані e: гладко, якщо кут між гранями малий
        var other = fn[k === e ? (e - 1 + n) % n : (e + 1) % n], me = fn[e];
        if (me[0] * other[0] + me[1] * other[1] + me[2] * other[2] < smooth) return me;
        var m = [me[0] + other[0], me[1] + other[1], me[2] + other[2]], l = Math.hypot(m[0], m[1], m[2]) || 1;
        return [m[0] / l, m[1] / l, m[2] / l];
      };
      for (var e2 = 0; e2 < n; e2++) {
        if (o.open && e2 === n - 1) continue;
        var k0 = e2, k1 = (e2 + 1) % n;
        var a0 = [A.pts[k0][0], A.y, A.pts[k0][1]], a1 = [A.pts[k1][0], A.y, A.pts[k1][1]];
        var b0 = [B.pts[k0][0], B.y, B.pts[k0][1]], b1 = [B.pts[k1][0], B.y, B.pts[k1][1]];
        var s0 = s[e2] / tile, s1 = s[e2 + 1] / tile;
        var uvA0, uvA1, uvB0, uvB1;
        if (o.sideGrain === 'y') { uvA0 = [s0, A.y / tile]; uvA1 = [s1, A.y / tile]; uvB0 = [s0, B.y / tile]; uvB1 = [s1, B.y / tile]; }
        else { uvA0 = [A.y / tile, s0]; uvA1 = [A.y / tile, s1]; uvB0 = [B.y / tile, s0]; uvB1 = [B.y / tile, s1]; }
        var na0 = vn(e2, k0), na1 = vn(e2, k1);
        // орієнтація: нормаль грані має дивитися назовні
        var ux = a1[0] - a0[0], uy = a1[1] - a0[1], uz = a1[2] - a0[2], vx = b0[0] - a0[0], vy = b0[1] - a0[1], vz = b0[2] - a0[2];
        var cx = uy * vz - uz * vy, cy = uz * vx - ux * vz, cz = ux * vy - uy * vx;
        // (a1-a0)×(b0-a0) уздовж зовнішньої нормалі -> обхід a0-a1-b1-b0 проти годинникової ззовні
        if (cx * fn[e2][0] + cy * fn[e2][1] + cz * fn[e2][2] > 0) bdSide.quadN(a0, a1, b1, b0, na0, na1, na1, na0, uvA0, uvA1, uvB1, uvB0);
        else bdSide.quadN(a0, b0, b1, a1, na0, na0, na1, na1, uvA0, uvB0, uvB1, uvA1);
      }
    }
    if (o.caps === false) return;
    [[rings[0], [0, 1, 0]], [rings[rings.length - 1], [0, -1, 0]]].forEach(function (cap) {
      var R = cap[0], contour = R.pts.map(function (p) { return new THREE.Vector2(p[0], p[1]); });
      var faces = THREE.ShapeUtils.triangulateShape(contour, []);
      var uvf = o.capGrain === 'z' ? function (p) { return [p[0] / capTile + capOff[0], p[2] / capTile + capOff[1]]; }
                                   : function (p) { return [p[2] / capTile + capOff[0], p[0] / capTile + capOff[1]]; };
      faces.forEach(function (f) {
        var P = f.map(function (i) { return [R.pts[i][0], R.y, R.pts[i][1]]; });
        (cap[1][1] > 0 ? bdCap : (o.bdUnder || bdCap)).tri(P[0], P[1], P[2], uvf, cap[1]);
      });
    });
  }

  // Прямокутна плита зі скосом знизу (TAVOR): x0..x1, z0..z1, низ на y0, товщина t;
  // скіс cv угору, ch усередину — лише по сторонах, де bev[side] (лінія розрізу — без скосу).
  function chamferSlab(bdTop, bdEdge, bdUnder, x0, x1, z0, z1, y0, t, cv, ch, bev, capOff) {
    var il = bev.l ? ch : 0, ir = bev.r ? ch : 0, ib = bev.b ? ch : 0, iff = bev.f ? ch : 0;
    var yt = y0 + t, ym = y0 + cv;
    var P = function (x, y, z) { return [x, y, z]; };
    var off = capOff || [0, 0];
    var top = function (p) { return [p[2] / TILE_FACE + off[0], p[0] / TILE_FACE + off[1]]; };
    var under = function (p) { return [p[2] / TILE_FACE * 2.2 + off[0], p[0] / TILE_FACE + off[1]]; };
    var alongX = function (p) { return [p[1] / TILE * 2.5, p[0] / TILE]; };
    var alongZ = function (p) { return [p[1] / TILE * 2.5, p[2] / TILE]; };
    bdTop.quad(P(x0, yt, z0), P(x1, yt, z0), P(x1, yt, z1), P(x0, yt, z1), top, [0, 1, 0]);
    bdEdge.quad(P(x0, ym, z1), P(x1, ym, z1), P(x1, yt, z1), P(x0, yt, z1), alongX, [0, 0, 1]);
    bdEdge.quad(P(x0, ym, z0), P(x1, ym, z0), P(x1, yt, z0), P(x0, yt, z0), alongX, [0, 0, -1]);
    bdEdge.quad(P(x1, ym, z0), P(x1, yt, z0), P(x1, yt, z1), P(x1, ym, z1), alongZ, [1, 0, 0]);
    bdEdge.quad(P(x0, ym, z0), P(x0, yt, z0), P(x0, yt, z1), P(x0, ym, z1), alongZ, [-1, 0, 0]);
    var b0 = [x0 + il, y0, z0 + ib], b1 = [x1 - ir, y0, z0 + ib], b2 = [x1 - ir, y0, z1 - iff], b3 = [x0 + il, y0, z1 - iff];
    var m0 = [x0, ym, z0], m1 = [x1, ym, z0], m2 = [x1, ym, z1], m3 = [x0, ym, z1];
    bdEdge.quad(m3, m2, b2, b3, alongX, [0, -iff, 1 + 0.0001]);
    bdEdge.quad(m0, m1, b1, b0, alongX, [0, -ib, -1 - 0.0001]);
    bdEdge.quad(m1, m2, b2, b1, alongZ, [1 + 0.0001, -ir, 0]);
    bdEdge.quad(m0, m3, b3, b0, alongZ, [-1 - 0.0001, -il, 0]);
    bdUnder.quad(b0, b1, b2, b3, under, [0, -1, 0]);
  }

  // Ніжка, що звужується донизу: квадрат topA на висоті y1 -> botA на y0; центр низу зсунутий на (dx, dz).
  function taperLeg(THREE, bd, x, z, y0, y1, topA, botA, dx, dz) {
    var sq = function (cx, cz, a) { return roundedRect(cx, cz, a, a, 0.004, 2); };
    loft(THREE, bd, bd, [{ pts: sq(x, z, topA), y: y1 }, { pts: sq(x + (dx || 0), z + (dz || 0), botA), y: y0 }],
      { sideGrain: 'y', center: [x, z], capGrain: 'z', capTile: 0.3 });
  }
  function roundLeg(THREE, bd, x, z, y0, y1, rTop, rBot, seg) {
    loft(THREE, bd, bd, [{ pts: circle(x, z, rTop, seg || 32), y: y1 }, { pts: circle(x, z, rBot, seg || 32), y: y0 }],
      { sideGrain: 'y', center: [x, z], capGrain: 'z', capTile: 0.3 });
  }

  // ---- товари ---------------------------------------------------------------------------------------
  // Кожен будівник повертає { parts: {oak, face, under, steel, dark}, footprint: [[x,z,w,d]...] } —
  // footprint для контактної тіні під опорами.
  var PRODUCTS = {};

  // TAVOR — розсувний прямокутний: стільниця 40 мм зі скосом знизу 20×26 мм, царги, ніжки звужуються донизу.
  PRODUCTS.tavor = function (THREE, P, sz, base, state) {
    var L = sz.length_cm / 100, W = sz.width_cm / 100, H = sz.height_cm / 100, leaf = (sz.extended_cm - sz.length_cm) / 100;
    // state 'half' — кадр механізму: половини розведені на пів вставки, видно напрямні й складену вставку під ними
    var open = state === 'open', T = 0.04, y0 = H - T, foot = [];
    var ext = open ? leaf : state === 'half' ? leaf / 2 : 0, ends = [-(L + ext) / 2, (L + ext) / 2];
    var halves = [[ends[0], -ext / 2 - GAP / 2], [ext / 2 + GAP / 2, ends[1]]];
    halves.forEach(function (h, i) {
      chamferSlab(P.face, P.oak, P.under, h[0], h[1], -W / 2, W / 2, y0, T, 0.020, 0.026,
        { l: i === 0, r: i === 1, f: true, b: true }, [0, 0]);
    });
    if (open) chamferSlab(P.face, P.oak, P.under, -leaf / 2 + GAP / 2, leaf / 2 - GAP / 2, -W / 2, W / 2, y0, T, 0.020, 0.026,
      { l: false, r: false, f: true, b: true }, [0.31, 0.5]);
    if (base === 'steel') {
      // дві П-рами з профілю 60×20 біля торців: стійки, верхня й нижня поперечка
      ends.forEach(function (e) {
        var x = e - Math.sign(e) * 0.16, zw = W - 0.14;
        box(P.steel, x, y0 - 0.012, 0, 0.06, 0.024, zw, 'z');
        box(P.steel, x, 0.012, 0, 0.06, 0.024, zw + 0.04, 'z');
        [-1, 1].forEach(function (s) { box(P.steel, x, y0 / 2, s * (zw / 2 - 0.01), 0.06, y0 - SINK, 0.02, 'y'); });
        foot.push([x, 0, 0.14, zw + 0.1]);
      });
      // поздовжня балка під стільницею: на ній їздять напрямні
      box(P.steel, 0, y0 - 0.02, 0, (L + ext) - 0.32, 0.04, 0.04, 'x');
    } else {
      var inset = 0.07, legT = 0.065, legB = 0.045, aprH = 0.085, aprT = 0.022;
      ends.forEach(function (e) {
        var sx = Math.sign(e), lx = e - sx * (inset + legT / 2);
        [-1, 1].forEach(function (s) {
          var lz = s * (W / 2 - inset - legT / 2);
          taperLeg(THREE, P.oak, lx, lz, 0, y0 + SINK, legT, legB, 0, 0);
          foot.push([lx, lz, 0.2, 0.2]);
        });
        // торцева царга між ніжками
        box(P.oak, lx, y0 - aprH / 2, 0, aprT, aprH, W - 2 * (inset + legT) + SINK * 2, 'z');
      });
      // поздовжні царги: у відкритому стані розходяться разом із половинами — показуємо їх від ніжки до центру
      [-1, 1].forEach(function (s) {
        var z = s * (W / 2 - inset - aprT / 2 - 0.012);
        halves.forEach(function (h, i) {
          var a = i === 0 ? ends[0] + inset + legT : (open ? 0.03 + leaf / 2 : ext / 2 + GAP / 2);
          var b = i === 0 ? (open ? -0.03 - leaf / 2 : -ext / 2 - GAP / 2) : ends[1] - inset - legT;
          box(P.oak, (a + b) / 2, y0 - aprH / 2, z, b - a, aprH, aprT, 'x');
        });
      });
      // напрямні: дві сталеві шини 30×25 мм під стільницею, між царгами; довжина — закритий стіл без ніжок
      var railZ = W / 2 - inset - aprT - 0.05, railL = L - 2 * (inset + legT) - 0.04;
      [-1, 1].forEach(function (s) { box(P.steel, 0, y0 - 0.0125 - SINK, s * railZ, railL + ext, 0.025, 0.03, 'x'); });
      // вставка зберігається складеною вдвоє (80×W -> 80×W/2, два шари) між шинами; у розкладеному стані вона на місці
      if (!open) {
        var lw = Math.min(W / 2, 2 * railZ - 0.05) / 2, yl = y0 - aprH;
        chamferSlab(P.under, P.oak, P.under, -leaf / 2, leaf / 2, -lw, lw, yl, T, 0.020, 0.026, { l: false, r: false, f: false, b: false }, [0.2, 0.1]);
        chamferSlab(P.face, P.oak, P.under, -leaf / 2, leaf / 2, -lw, lw, yl + T + 0.001, T, 0.020, 0.026,
          { l: false, r: false, f: false, b: false }, [0.31, 0.5]);
      }
    }
    return { foot: foot };
  };

  // SAHAR — круглий Ø115 -> овал 155: дві половини-D і вставка 40 см; дуб — чотири ніжки, сталь — колона на хресті.
  PRODUCTS.sahar = function (THREE, P, sz, base, state) {
    var D = sz.length_cm / 100, R = D / 2, H = sz.height_cm / 100, leaf = (sz.extended_cm - sz.length_cm) / 100;
    var open = state === 'open', T = 0.035, y0 = H - T, foot = [], ch = 0.018, cv = 0.016, seg = 72;
    var c = open ? leaf / 2 + GAP / 2 : GAP / 2;
    [-1, 1].forEach(function (dir) {
      var cx = dir * c;
      var outer = halfDisc(cx, R, dir, seg), inner = halfDisc(cx, R - ch, dir, seg);
      // точки лінії розрізу внутрішнього кільця лишаються на розрізі: скосу на шві немає
      inner[0] = [cx, inner[0][1]]; inner[seg] = [cx, inner[seg][1]];
      loft(THREE, P.oak, P.face, [{ pts: outer, y: H }, { pts: outer, y: y0 + cv }, { pts: inner, y: y0 }],
        { center: [cx, 0], bdUnder: P.under, capTile: TILE_FACE, tile: TILE / 2.5 });
    });
    if (open) chamferSlab(P.face, P.oak, P.under, -leaf / 2 + GAP / 2, leaf / 2 - GAP / 2, -R, R, y0, T, cv, ch,
      { l: false, r: false, f: true, b: true }, [0.31, 0.5]);
    if (base === 'steel') {
      // колона Ø100 мм, хрестова опора 70 см з плоского профілю, верхня хрестовина під стільницею
      roundLeg(THREE, P.steel, 0, 0, 0.03, y0 - 0.03, 0.05, 0.05, 40);
      [0, Math.PI / 2].forEach(function (a) {
        var g = new Builder();
        box(g, 0, 0.015, 0, 0.72, 0.03, 0.06, 'x');
        box(g, 0, y0 - 0.015, 0, 0.62, 0.03, 0.05, 'x');
        var geo = g.geometry(THREE); geo.rotateY(a);
        P.extra.push({ geo: geo, mat: 'steel' });
      });
      foot.push([0, 0, 0.9, 0.9]);
    } else {
      // ніжки на колі радіуса 0,36 м під 45°, звужуються донизу; кільцева царга — чотири прямі ланки
      var rl = 0.34;
      [45, 135, 225, 315].forEach(function (deg) {
        var a = deg * Math.PI / 180, sx = Math.cos(a) > 0 ? 1 : -1;
        var lx = rl * Math.cos(a) + (open ? sx * leaf / 2 : 0), lz = rl * Math.sin(a);
        taperLeg(THREE, P.oak, lx, lz, 0, y0 + SINK, 0.06, 0.042, 0, 0);
        foot.push([lx, lz, 0.2, 0.2]);
      });
      // царги по квадрату між ніжками; поздовжні — по половині на кожну частину, у відкритому стані розходяться
      var a = rl * Math.SQRT1_2, sxo = open ? leaf / 2 : 0, len = a - 0.03 - GAP / 2;
      [-1, 1].forEach(function (s) {
        box(P.oak, s * (a + sxo), y0 - 0.04, 0, 0.022, 0.08, 2 * a - 0.06, 'z');
        [-1, 1].forEach(function (t) {
          box(P.oak, s * (sxo + GAP / 2 + len / 2), y0 - 0.04, t * a, len, 0.08, 0.022, 'x');
        });
      });
    }
    return { foot: foot };
  };

  // OFEK — підвісна тумба: корпус шпон 19 мм, фасади масив із вертикальними канелюрами, ніша-тінь під корпусом.
  PRODUCTS.ofek = function (THREE, P, sz) {
    var L = sz.length_cm / 100, D = sz.width_cm / 100, H = sz.height_cm / 100, t = 0.019, y0 = 0.32;
    var zb = -D / 2, zf = D / 2;
    box(P.face, 0, y0 + H - t / 2, 0, L, t, D, 'x', [0, 0], TILE_FACE);            // кришка
    box(P.oak, 0, y0 + t / 2, 0, L, t, D, 'x');                                      // дно
    [-1, 1].forEach(function (s) { box(P.oak, s * (L / 2 - t / 2), y0 + H / 2, 0, t, H - 2 * t + 2 * SINK, D, 'y'); });
    box(P.oak, 0, y0 + H / 2, zb + 0.004, L - 2 * t, H - 2 * t, 0.008, 'x');          // задня стінка
    // фасади: 2 двері для 160, 3 для 180/200, між боковинами, зазор 4 мм, канелюри крок 24 мм, глибина 4 мм;
    // по краях двері гладка смуга 8 мм — шов між дверима читається (конструктивне допущення, docs/ASSETS.md)
    var n = L <= 1.65 ? 2 : 3, gap = 0.004, land = 0.008, inner = L - 2 * t, dw = (inner - (n + 1) * gap) / n;
    var fh = H - 2 * t - 2 * gap, fy0 = y0 + t + gap, ft = 0.02, pitch = 0.024, depth = 0.004;
    for (var i = 0; i < n; i++) {
      var d0 = -inner / 2 + gap + i * (dw + gap), d1 = d0 + dw, zf0 = zf - 0.002;
      var x0 = d0 + land, x1 = d1 - land;
      [[d0, x0], [x1, d1]].forEach(function (e) {   // гладкі смуги по краях
        P.oak.quad([e[0], fy0, zf0], [e[1], fy0, zf0], [e[1], fy0 + fh, zf0], [e[0], fy0 + fh, zf0],
                   function (q) { return [q[0] / TILE * 2.5, q[1] / TILE]; }, [0, 0, 1]);
      });
      var flutes = Math.max(4, Math.round((x1 - x0) / pitch)), step = (x1 - x0) / flutes, sub = 8;
      // лице фасаду: профіль z(x) = zf0 - depth * sin²(π·u), гладкі нормалі
      for (var f = 0; f < flutes; f++) {
        for (var k = 0; k < sub; k++) {
          var u0 = k / sub, u1 = (k + 1) / sub;
          var xa = x0 + (f + u0) * step, xb = x0 + (f + u1) * step;
          var za = zf0 - depth * Math.pow(Math.sin(Math.PI * u0), 2), zb2 = zf0 - depth * Math.pow(Math.sin(Math.PI * u1), 2);
          var slope = function (u) { var d = -depth * Math.PI * Math.sin(2 * Math.PI * u) / step; var l = Math.hypot(d, 1); return [d / l * -1, 0, 1 / l]; };
          var na = slope(u0), nb = slope(u1);
          var tA = [xa / TILE * 2.5, fy0 / TILE], tB = [xb / TILE * 2.5, fy0 / TILE], tC = [xb / TILE * 2.5, (fy0 + fh) / TILE], tD = [xa / TILE * 2.5, (fy0 + fh) / TILE];
          P.oak.quadN([xa, fy0, za], [xb, fy0, zb2], [xb, fy0 + fh, zb2], [xa, fy0 + fh, za], na, nb, nb, na, tA, tB, tC, tD);
        }
      }
      // торці фасаду і тіло дверей
      box(P.oak, (d0 + d1) / 2, fy0 + fh / 2, zf0 - depth - (ft - depth) / 2 - 0.0005, dw, fh, ft - depth, 'y');
      box(P.oak, (d0 + d1) / 2, fy0 + fh - 0.0005, zf0 - ft / 2, dw, 0.001, ft, 'x');
      box(P.oak, (d0 + d1) / 2, fy0 + 0.0005, zf0 - ft / 2, dw, 0.001, ft, 'x');
    }
    // темна порожнина за зазорами
    box(P.dark, 0, y0 + H / 2, zf - ft - 0.01, inner, H - 2 * t, 0.004, 'x');
    return { foot: [], floating: true, wallZ: zb };
  };

  // SAF — консоль: кришка 30 мм, дві тонкі шухляди з пазом знизу, нижня полиця; дуб — ніжки 40 мм, сталь — рама 20 мм.
  PRODUCTS.saf = function (THREE, P, sz, base) {
    var L = sz.length_cm / 100, D = sz.width_cm / 100, H = sz.height_cm / 100, T = 0.03, foot = [];
    var y0 = H - T, band = 0.11, zf = D / 2, zb = -D / 2;
    var top = roundedRect(0, 0, L, D, 0.004, 2);
    var topIn = roundedRect(0, 0, L - 0.02, D - 0.02, 0.004, 2);
    loft(THREE, P.oak, P.face, [{ pts: top, y: H }, { pts: top, y: y0 + 0.012 }, { pts: topIn, y: y0 }],
      { bdUnder: P.under, capTile: TILE_FACE, tile: TILE / 2.5, smooth: 0.99 });
    var legA = base === 'steel' ? 0.02 : 0.04, inset = base === 'steel' ? 0.012 : 0.02;
    var lx = L / 2 - inset - legA / 2, lz = D / 2 - inset - legA / 2, shelfY = 0.16;
    var mat = base === 'steel' ? P.steel : P.oak;
    [-1, 1].forEach(function (s) {
      [-1, 1].forEach(function (t) {
        box(mat, s * lx, y0 / 2, t * lz, legA, y0 + SINK, legA, 'y');
        foot.push([s * lx, t * lz, 0.12, 0.12]);
      });
    });
    // шухлядний пояс: боковини й зад, фасад шухляди посередині, пояс по краях
    var bay = L - 2 * (inset + legA), dwW = Math.min(0.56, (bay - 0.03) / 2), bandZ = zf - inset - legA / 2;
    if (base === 'steel') {
      [-1, 1].forEach(function (s) { box(P.steel, s * lx, y0 - 0.01, 0, legA, 0.02, D - 2 * inset, 'z'); });
      [-1, 1].forEach(function (t) { box(P.steel, 0, y0 - 0.01, t * lz, L - 2 * inset, 0.02, legA, 'x'); });
      [-1, 1].forEach(function (t) { box(P.steel, 0, shelfY - 0.03, t * lz, L - 2 * inset, 0.02, legA, 'x'); });
    }
    var fz = base === 'steel' ? zf - 0.03 : bandZ;
    box(P.oak, 0, y0 - band / 2, fz - 0.009, L - 2 * (inset + legA), band, 0.018, 'x');           // передня царга
    box(P.oak, 0, y0 - band / 2, -fz + 0.009, L - 2 * (inset + legA), band, 0.018, 'x');          // задня царга
    // два фасади шухляд: врізані в царгу, зазор 2 мм, паз-захват 12 мм уздовж нижньої кромки
    [-1, 1].forEach(function (s) {
      var cx = s * (dwW / 2 + 0.008);
      box(P.dark, cx, y0 - band / 2, fz + 0.0006, dwW + 0.004, band - 0.018, 0.0006, 'x');
      box(P.oak, cx, y0 - band / 2 + 0.006, fz + 0.002, dwW, band - 0.022 - 0.012, 0.004, 'x');
      box(P.dark, cx, y0 - band + 0.009 + 0.006, fz + 0.0012, dwW, 0.012, 0.0012, 'x');
    });
    // нижня полиця
    var shelf = roundedRect(0, 0, L - 2 * inset - 2 * legA + 0.002, D - 2 * inset - (base === 'steel' ? 0 : 2 * legA) + 0.002, 0.003, 2);
    loft(THREE, P.oak, P.face, [{ pts: shelf, y: shelfY }, { pts: shelf, y: shelfY - 0.02 }], { bdUnder: P.under, capTile: TILE_FACE, tile: TILE / 2.5 });
    return { foot: foot, wallZ: zb - 0.004 };
  };

  // TAL — журнальний: стільниця 40 мм з радіусом кутів 12 см (або коло Ø80), товсті круглі ніжки Ø90 мм або сталеві трубки.
  PRODUCTS.tal = function (THREE, P, sz, base) {
    var L = sz.length_cm / 100, W = sz.width_cm / 100, H = sz.height_cm / 100, T = 0.04, foot = [];
    var round = /Ø/.test(sz.label || '') || L === W;
    var outer = round ? circle(0, 0, L / 2, 96) : roundedRect(0, 0, L, W, 0.12, 16);
    var inner = round ? circle(0, 0, L / 2 - 0.02, 96) : roundedRect(0, 0, L - 0.04, W - 0.04, 0.10, 16);
    var y0 = H - T;
    loft(THREE, P.oak, P.face, [{ pts: outer, y: H }, { pts: outer, y: y0 + 0.018 }, { pts: inner, y: y0 }],
      { bdUnder: P.under, capTile: TILE_FACE, tile: TILE / 2.5 });
    var legs = round ? [45, 165, 285].map(function (d) { var a = d * Math.PI / 180, r = L / 2 - 0.12; return [r * Math.cos(a), r * Math.sin(a)]; })
                     : [[-1, -1], [-1, 1], [1, -1], [1, 1]].map(function (s) { return [s[0] * (L / 2 - 0.13), s[1] * (W / 2 - 0.12)]; });
    legs.forEach(function (p) {
      if (base === 'steel') roundLeg(THREE, P.steel, p[0], p[1], 0, y0 + SINK, 0.013, 0.013, 24);
      else roundLeg(THREE, P.oak, p[0], p[1], 0, y0 + SINK, 0.046, 0.043, 48);
      foot.push([p[0], p[1], 0.16, 0.16]);
    });
    return { foot: foot };
  };

  // ---- декор інтер'єрного кадру: керамічна ваза й низька миска (матова глина), без брендів ----------------
  function lathe(THREE, profile, seg) {
    return new THREE.LatheGeometry(profile.map(function (p) { return new THREE.Vector2(p[0], p[1]); }), seg || 64);
  }
  function decor(THREE, product, sz, group) {
    var clay = new THREE.MeshStandardMaterial({ color: 0xd9cfc2, roughness: 0.92, side: THREE.DoubleSide });
    var terra = new THREE.MeshStandardMaterial({ color: 0xb77b5a, roughness: 0.9, side: THREE.DoubleSide });
    var H = sz.height_cm / 100, add = function (geo, mat, x, y, z) { var m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; group.add(m); return m; };
    var vase = lathe(THREE, [[0.001, 0], [0.06, 0], [0.085, 0.06], [0.09, 0.13], [0.07, 0.21], [0.035, 0.26], [0.032, 0.30], [0.04, 0.31], [0.036, 0.312]]);
    var bowl = lathe(THREE, [[0.001, 0], [0.05, 0], [0.11, 0.035], [0.15, 0.075], [0.146, 0.078], [0.104, 0.04], [0.045, 0.008], [0.001, 0.008]]);
    if (product === 'tavor' || product === 'sahar') add(bowl, clay, 0.05, H, -0.04);
    if (product === 'ofek') { add(vase, terra, sz.length_cm / 200 - 0.28, 0.32 + sz.height_cm / 100, -0.02); }
    if (product === 'saf') { add(vase, clay, -sz.length_cm / 200 + 0.24, H, 0); add(bowl, terra, 0.22, H, 0.01).scale.set(0.6, 0.6, 0.6); }
    if (product === 'tal') add(bowl, clay, 0.1, H, 0.02);
  }

  // ---- матеріали й складання --------------------------------------------------------------------------
  var texCache = {};
  function loadTex(THREE, url, srgb, scale) {
    var key = url + '|' + (scale || 1);
    if (!texCache[key]) {
      texCache[key] = loadImage(url).then(function (img) {
        var t = new THREE.Texture(img);
        t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; t.repeat.set(scale || 1, scale || 1);
        t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace; t.needsUpdate = true;
        return t;
      }, function (e) { delete texCache[key]; throw e; });   // мережа впала — наступне відкриття спробує знову
    }
    return texCache[key];
  }
  // файли тону: на сайті — шляхи з FINISHES; рендери підміняють теку (opts.texDir) і розмір (opts.texRes, '2048');
  // opts.textures {albedo, normal, rough} — один набір на всі тони (старі сцени), без тонування
  function toneTextures(opts, f) {
    if (opts.textures) return { albedo: opts.textures.albedo, normal: opts.textures.normal, rough: opts.textures.rough, scale: 1 };
    var t = FINISHES[f];
    function at(u) {
      if (opts.texDir) u = opts.texDir + u.split('/').pop();
      return opts.texRes ? u.replace(/-1024\.jpg$/, '-' + opts.texRes + '.jpg') : u;
    }
    return { albedo: at(t.albedo), normal: at(t.nmap), rough: at(t.rmap), scale: t.scale };
  }

  function build(THREE, opts) {
    var product = opts.product, finish = FINISHES[opts.finish] ? opts.finish : 'natural';
    var bd = { oak: new Builder(), face: new Builder(), under: new Builder(), steel: new Builder(), dark: new Builder(), extra: [] };
    var info = PRODUCTS[product](THREE, bd, opts.size, opts.base || 'oak', opts.state || 'closed');
    var group = new THREE.Group(); group.name = product;
    var oak = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1, metalness: 0 });
    var under = new THREE.MeshStandardMaterial({ color: 0xe8e2da, roughness: 1, metalness: 0 });
    var steel = new THREE.MeshStandardMaterial({ color: 0x1c1b1a, roughness: 0.48, metalness: 0.35 });
    var dark = new THREE.MeshStandardMaterial({ color: 0x0e0b09, roughness: 1 });
    var mats = { oak: oak, face: oak, under: under, steel: steel, dark: dark };
    ['oak', 'face', 'under', 'steel', 'dark'].forEach(function (k) {
      if (!bd[k].p.length) return;
      var m = new THREE.Mesh(bd[k].geometry(THREE), mats[k]); m.castShadow = true; m.receiveShadow = true; m.name = k; group.add(m);
    });
    bd.extra.forEach(function (e) { var m = new THREE.Mesh(e.geo, mats[e.mat]); m.castShadow = m.receiveShadow = true; group.add(m); });
    var bounds = new THREE.Box3().setFromObject(group);
    if (opts.decor) decor(THREE, product, opts.size, group);
    function setFinish(f) {
      f = FINISHES[f] ? f : 'natural';
      var tex = toneTextures(opts, f);
      return Promise.all([loadTex(THREE, tex.albedo, true, tex.scale), loadTex(THREE, tex.normal, false, tex.scale),
                          loadTex(THREE, tex.rough, false, tex.scale)]).then(function (r) {
        var alb = r[0], nor = r[1], rgh = r[2];
        [oak, under].forEach(function (m) {
          m.map = alb; m.normalMap = nor; m.roughnessMap = rgh; m.aoMap = rgh; m.aoMapIntensity = 0.6;
          m.normalScale.set(FINISHES[f].normal, FINISHES[f].normal); m.roughness = FINISHES[f].rough; m.needsUpdate = true;
        });
        under.color.set(f === 'black' ? 0x8a8580 : 0xe8e2da);
        model.finish = f; return model;
      });
    }
    var model = {
      group: group, info: info, finish: finish,
      bounds: function () { return bounds.clone(); },
      setFinish: setFinish,
      dispose: function () { group.traverse(function (o) { if (o.geometry) o.geometry.dispose(); }); [oak, under, steel, dark].forEach(function (m) { m.dispose(); }); }
    };
    return setFinish(finish);
  }

  // ---- середовище з градієнтів: «студія» без HDRI-файлу -------------------------------------------
  function gradientRoom(THREE, o) {
    o = o || {};
    var s = new THREE.Scene();
    var c = document.createElement('canvas'); c.width = 4; c.height = 256;
    var g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 256);
    gr.addColorStop(0, o.sky || '#fbf7f0'); gr.addColorStop(0.48, o.horizon || '#e9e1d4'); gr.addColorStop(0.52, o.ground || '#b8ad9e'); gr.addColorStop(1, o.floor || '#8f8578');
    g.fillStyle = gr; g.fillRect(0, 0, 4, 256);
    var t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    s.add(new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.MeshBasicMaterial({ map: t, side: THREE.BackSide })));
    function panel(w, h, x, y, z, col, i) {
      var m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(col).multiplyScalar(i), side: THREE.DoubleSide }));
      m.position.set(x, y, z); m.lookAt(0, 0.6, 0); s.add(m);
    }
    (o.panels || [[4, 3, -5, 6, 5, 0xfff2e0, 4.0], [6, 2.5, 6, 3, -2, 0xeef2ff, 1.4], [8, 2, 0, 9, -4, 0xffffff, 2.2]])
      .forEach(function (p) { panel.apply(null, p); });
    return s;
  }
  function envFrom(THREE, renderer, o) {
    var pmrem = new THREE.PMREMGenerator(renderer);
    var env = pmrem.fromScene(gradientRoom(THREE, o), 0.035).texture; pmrem.dispose(); return env;
  }

  // м'яка контактна тінь: радіальний градієнт під кожною опорою (один 64×64 canvas)
  var blobTex = null;
  function blob(THREE) {
    if (blobTex) return blobTex;
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, 'rgba(28,22,15,1)'); gr.addColorStop(0.45, 'rgba(28,22,15,0.45)'); gr.addColorStop(1, 'rgba(28,22,15,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    blobTex = new THREE.CanvasTexture(c); return blobTex;
  }
  function contacts(THREE, scene, model, opacity) {
    var grp = new THREE.Group(); grp.name = 'contacts';
    (model.info.foot || []).forEach(function (f) {
      var m = new THREE.Mesh(new THREE.PlaneGeometry(f[2], f[3]), new THREE.MeshBasicMaterial({ map: blob(THREE), transparent: true, opacity: opacity, depthWrite: false }));
      m.rotation.x = -Math.PI / 2; m.position.set(f[0], 0.0008, f[1]); m.renderOrder = 1; grp.add(m);
    });
    scene.add(grp); return grp;
  }

  function softKey(THREE, pos, target, o) {
    var key = new THREE.DirectionalLight(o.color || 0xfff1e2, o.intensity || 2.4);
    key.position.copy(pos); key.target.position.copy(target);
    key.castShadow = true;
    var sm = o.shadowMap || 2048, ext = o.extent || 2.6;
    key.shadow.mapSize.set(sm, sm); key.shadow.bias = -0.0003; key.shadow.normalBias = 0.02;
    key.shadow.radius = o.radius || 18; key.shadow.blurSamples = 24;
    key.shadow.camera.left = -ext; key.shadow.camera.right = ext; key.shadow.camera.top = ext; key.shadow.camera.bottom = -ext;
    key.shadow.camera.near = 0.5; key.shadow.camera.far = o.far || 16;
    return key;
  }

  // Світлий фон: безшовна підлога кольору фону (ShadowMaterial), м'який ключ згори-зліва, заповнення з середовища.
  function studio(THREE, scene, renderer, model, o) {
    o = o || {};
    scene.environment = envFrom(THREE, renderer, {});
    scene.environmentIntensity = o.env || 0.9;
    var b = model.bounds(), c = b.getCenter(new THREE.Vector3());
    var key = softKey(THREE, new THREE.Vector3(c.x - 2.2, 5.0, c.z + 2.4), new THREE.Vector3(c.x, 0.3, c.z), { intensity: o.key || 2.2, radius: 22, extent: 2.4 });
    scene.add(key, key.target);
    var floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.ShadowMaterial({ color: 0x2a2218, opacity: o.shadow || 0.16 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    scene.add(new THREE.HemisphereLight(0xffffff, 0xf0ebe3, 0.35));
    if (model.info.wallZ !== undefined) {   // підвісне й пристінне — на стіні кольору фону, щоб тінь лягла на неї
      var wall = new THREE.Mesh(new THREE.PlaneGeometry(30, 10), new THREE.ShadowMaterial({ color: 0x2a2218, opacity: (o.shadow || 0.16) * 0.8 }));
      wall.position.set(0, 5, model.info.wallZ); wall.receiveShadow = true; scene.add(wall);
    }
    contacts(THREE, scene, model, 0.55);
    return { key: key, floor: floor };
  }

  // Плитка 60×120 світлого керамограніту з ледь помітним швом і шумом — тайл на canvas.
  function tileTexture(THREE, o) {
    var S = 1024, c = document.createElement('canvas'); c.width = c.height = S;
    var g = c.getContext('2d'); g.fillStyle = o.floor || '#cfc5b5'; g.fillRect(0, 0, S, S);
    var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var i = 0; i < 26000; i++) { var a = rnd() * 0.05; g.fillStyle = (rnd() > 0.5 ? 'rgba(255,255,255,' : 'rgba(90,80,66,') + a + ')'; g.fillRect(rnd() * S, rnd() * S, 1 + rnd() * 3, 1 + rnd() * 3); }
    g.fillStyle = 'rgba(120,108,92,0.55)'; g.fillRect(0, 0, S, 2); g.fillRect(0, S / 2, S, 2); g.fillRect(0, 0, 2, S);
    var t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
    return t;   // один тайл = 1,2 × 1,2 м (дві плитки 60×120)
  }
  function plasterTexture(THREE, col) {
    var S = 512, c = document.createElement('canvas'); c.width = c.height = S;
    var g = c.getContext('2d'); g.fillStyle = col; g.fillRect(0, 0, S, S);
    var seed = 3; function rnd() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
    for (var i = 0; i < 6000; i++) { var a = rnd() * 0.014; g.fillStyle = (rnd() > 0.5 ? 'rgba(255,255,255,' : 'rgba(80,70,60,') + a + ')'; var r = 2 + rnd() * 10; g.beginPath(); g.arc(rnd() * S, rnd() * S, r, 0, 7); g.fill(); }
    var t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }

  // Інтер'єр-натяк: тепла штукатурна стіна, підлога-плитка, плінтус, сонце з вікна праворуч-спереду,
  // рама вікна поза кадром кидає тінь на стіну й підлогу. Без людей, без брендів.
  function interior(THREE, scene, renderer, model, o) {
    o = o || {};
    scene.environment = envFrom(THREE, renderer, { sky: '#fff6ea', horizon: '#efe4d3', ground: '#c9bba7', floor: '#a4957f',
      panels: [[5, 4, 6, 4, 5, 0xffe8cc, 3.2], [6, 3, -6, 3, 2, 0xe9eefc, 0.9]] });
    scene.environmentIntensity = o.env || 0.32;
    var b = model.bounds(), size = b.getSize(new THREE.Vector3());
    var wallZ = model.info.wallZ !== undefined ? model.info.wallZ : b.min.z - (o.wallGap || 0.9);
    var wall = new THREE.Mesh(new THREE.PlaneGeometry(14, 6), new THREE.MeshStandardMaterial({ map: plasterTexture(THREE, o.wall || '#e7e0d5'), roughness: 0.96 }));
    wall.material.map.repeat.set(5, 2.2);
    wall.position.set(0, 3, wallZ); wall.receiveShadow = true; scene.add(wall);
    var ft = tileTexture(THREE, o); ft.repeat.set(14 / 1.2, 10 / 1.2);
    var floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 10), new THREE.MeshStandardMaterial({ map: ft, roughness: 0.55, metalness: 0 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set(0, 0, wallZ + 5); floor.receiveShadow = true; scene.add(floor);
    var skirt = new THREE.Mesh(new THREE.BoxGeometry(14, 0.07, 0.012), new THREE.MeshStandardMaterial({ color: 0xe9e3d9, roughness: 0.8 }));
    skirt.position.set(0, 0.035, wallZ + 0.006); skirt.receiveShadow = true; scene.add(skirt);
    // сонце: праворуч-спереду-згори; вікно — отвір 2,4 × 2,6 м у непрозорій площині, хрестова рама
    var target = new THREE.Vector3(o.sunX || 0.3, 0.5, wallZ + 0.6);
    var dir = new THREE.Vector3(o.sunDir ? o.sunDir[0] : -0.85, o.sunDir ? o.sunDir[1] : 0.95, o.sunDir ? o.sunDir[2] : 0.7).normalize();
    var sun = softKey(THREE, target.clone().addScaledVector(dir, 9), target, { color: 0xffe6c4, intensity: o.sun || 4.4, radius: 7, extent: 4.2, shadowMap: 4096, far: 20 });
    scene.add(sun, sun.target);
    var gobo = new THREE.Group(), gm = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide, colorWrite: false, depthWrite: false });
    var ww = o.winW || 2.6, wh = o.winH || 2.8, bar = 0.06;
    function gb(w, h, x, y) { var m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), gm); m.position.set(x, y, 0); m.castShadow = true; gobo.add(m); }
    gb(20, 10, 0, wh / 2 + 5); gb(20, 10, 0, -wh / 2 - 5); gb(10, wh, -ww / 2 - 5, 0); gb(10, wh, ww / 2 + 5, 0);
    gb(bar, wh, 0, 0); gb(ww, bar, 0, wh * 0.18);
    gobo.position.copy(target.clone().addScaledVector(dir, o.goboDist || 3.2)); gobo.lookAt(target);
    scene.add(gobo);
    scene.add(new THREE.HemisphereLight(0xfff4e6, 0xcfc4b4, o.hemi || 0.12));
    contacts(THREE, scene, model, 0.5);
    return { sun: sun, wall: wall, floor: floor, wallZ: wallZ, size: size };
  }

  // ---- детермінований кадр ------------------------------------------------------------------------
  // view: { az, el (градуси), fov, margin (частка кадру з кожного боку), lift (зсув цілі вгору, м),
  //         shiftY (частка кадру: >0 — виріб нижче в кадрі), aspect }
  function frame(THREE, camera, box, v) {
    var c = box.getCenter(new THREE.Vector3()); c.y += v.lift || 0;
    var az = (v.az || 0) * Math.PI / 180, el = (v.el || 0) * Math.PI / 180;
    var dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
    camera.fov = v.fov || 30; camera.aspect = v.aspect; camera.near = 0.05; camera.far = 60; camera.updateProjectionMatrix();
    var corners = [];
    for (var i = 0; i < 8; i++) corners.push(new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z));
    var m = v.margin === undefined ? 0.1 : v.margin, lim = 1 - 2 * m;
    function fits(d) {
      camera.position.copy(c).addScaledVector(dir, d); camera.lookAt(c); camera.updateMatrixWorld(true);
      return corners.every(function (p) { var q = p.clone().project(camera); return Math.abs(q.x) <= lim && Math.abs(q.y + (v.shiftY || 0)) <= lim && q.z < 1; });
    }
    var lo = 0.3, hi = 60;
    for (var k = 0; k < 60; k++) { var mid = (lo + hi) / 2; if (fits(mid)) hi = mid; else lo = mid; }
    fits(hi);
    if (v.shiftY) {   // виріб нижче в кадрі: камера дивиться трохи вище за центр
      var up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
      var h = 2 * hi * Math.tan(camera.fov * Math.PI / 360);
      camera.lookAt(c.clone().addScaledVector(up, v.shiftY * h / 2)); camera.updateMatrixWorld(true);
    }
    return { distance: hi, az: v.az || 0, el: v.el || 0, fov: camera.fov, position: camera.position.toArray(), target: c.toArray() };
  }

  // ---- свотч: дощечка шпону з кромкою, згори під скісним світлом -------------------------------------
  function swatch(THREE, opts) {
    return build(THREE, { product: 'tal', size: { length_cm: 60, width_cm: 60, height_cm: 4, label: 'swatch' }, finish: opts.finish, textures: opts.textures, texDir: opts.texDir, texRes: opts.texRes, base: 'none' });
  }

  // ---- перегляд на сторінці: three.js — свій файл (без CDN і cookie), обертання пальцем і мишею --------
  // Шлях абсолютний і повний: build.py знаходить його тут, публікує з хешем і переписує цей рядок.
  var THREE_URL = '/assets/vendor/three.min.js';
  var threeP = null;
  function loadThree() {
    if (root.THREE) return Promise.resolve(root.THREE);
    if (!threeP) {
      threeP = new Promise(function (resolve, reject) {
        var s = document.createElement('script'); s.src = THREE_URL; s.async = true;
        s.onload = function () { if (root.THREE) resolve(root.THREE); else { threeP = null; reject(new Error('three')); } };
        s.onerror = function () { threeP = null; s.remove(); reject(new Error('three')); };
        document.head.appendChild(s);
      });
    }
    return threeP;
  }
  function hasWebGL() {
    try {
      var c = document.createElement('canvas');
      return !!(root.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
    } catch (e) { return false; }
  }
  // opts: { product, size, finish, base, state, label, description, keysText, roleText, textures, onReady }
  // Помилка (немає WebGL — Error('webgl'), не завантажився three чи текстури) — відхилений Promise; текст показує сторінка.
  function mount(el, opts) {
    if (!hasWebGL()) return Promise.reject(new Error('webgl'));
    return loadThree().then(function (THREE) {
      var w = el.clientWidth || 800, h = el.clientHeight || 600;
      var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(2, root.devicePixelRatio || 1)); renderer.setSize(w, h);
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.VSMShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.domElement.style.cssText = 'display:block;width:100%;height:100%';
      // доступність (ת"י 5568 / WCAG 2.1 AA): полотно — лише картинка, керування — сам контейнер у фокусі,
      // текстова альтернатива — opts.label (назва) і opts.description (розміри й матеріал), стрілки обертають
      renderer.domElement.setAttribute('aria-hidden', 'true');
      el.appendChild(renderer.domElement);
      el.setAttribute('tabindex', '0'); el.setAttribute('role', 'img');
      el.setAttribute('aria-roledescription', opts.roleText || 'תצוגה תלת־ממדית');
      if (opts.label) el.setAttribute('aria-label', opts.label);
      var desc = document.createElement('p');
      desc.id = 'a3d-' + Math.random().toString(36).slice(2, 9);
      desc.textContent = (opts.description || '') + ' ' + (opts.keysText || 'החצים מסובבים את הדגם.');
      desc.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap';
      el.appendChild(desc); el.setAttribute('aria-describedby', desc.id);
      var scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(30, w / h, 0.05, 60), model = null, view = { az: 32, el: 18 };
      var cur = { size: opts.size, base: opts.base, state: opts.state || 'closed', finish: opts.finish || 'natural' };
      var alive = true, gen = 0, queued = false;
      function rebuild() {
        var my = ++gen;
        return build(THREE, { product: opts.product, size: cur.size, finish: cur.finish, base: cur.base, state: cur.state, textures: opts.textures, texDir: opts.texDir, texRes: opts.texRes }).then(function (m) {
          if (!alive || my !== gen) { m.dispose(); return; }   // поки вантажилось, вибір змінився або перегляд закрили
          if (model) { scene.remove(model.group); model.dispose(); }
          if (scene.environment) scene.environment.dispose();
          while (scene.children.length) scene.remove(scene.children[0]);
          model = m; scene.add(m.group); studio(THREE, scene, renderer, m, {});
          draw(); draw();   // VSM: другий прохід — тіні вже розмиті, як у рендерах
        });
      }
      function draw() {
        queued = false;
        if (!model || !alive) return;
        frame(THREE, camera, model.bounds(), { az: view.az, el: view.el, fov: 30, margin: 0.08, aspect: w / h });
        renderer.render(scene, camera);
      }
      function later() { if (!queued) { queued = true; root.requestAnimationFrame(draw); } }
      // обертання: палець і миша — pointer events; колесо не слухаємо — сторінка гортається як завжди.
      // touch-action: pan-y — вертикальний свайп гортає сторінку, горизонтальний обертає виріб
      var drag = null;
      el.addEventListener('pointerdown', function (e) {
        if (e.button) return;
        drag = [e.clientX, e.clientY, view.az, view.el];
        try { el.setPointerCapture(e.pointerId); } catch (x) {}
      });
      el.addEventListener('pointermove', function (e) {
        if (!drag) return;
        view.az = drag[2] - (e.clientX - drag[0]) * 0.4;
        view.el = Math.max(3, Math.min(60, drag[3] + (e.clientY - drag[1]) * 0.25));
        later();
      });
      function up() { drag = null; }
      el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
      el.style.touchAction = 'pan-y';
      // клавіатура: ←/→ — поворот на 15°, ↑/↓ — нахил; без анімацій і автоповороту (prefers-reduced-motion не порушується)
      el.addEventListener('keydown', function (e) {
        var k = e.key, rtl = getComputedStyle(el).direction === 'rtl' ? -1 : 1;
        if (k === 'ArrowLeft') view.az += 15 * rtl; else if (k === 'ArrowRight') view.az -= 15 * rtl;
        else if (k === 'ArrowUp') view.el = Math.min(60, view.el + 8); else if (k === 'ArrowDown') view.el = Math.max(3, view.el - 8);
        else return;
        e.preventDefault(); draw();
      });
      // розмір полотна — за контейнером (поворот телефона, зміна вікна)
      var ro = root.ResizeObserver ? new root.ResizeObserver(function () {
        var nw = el.clientWidth, nh = el.clientHeight;
        if (!alive || !nw || !nh || (nw === w && nh === h)) return;
        w = nw; h = nh; renderer.setSize(w, h); later();
      }) : null;
      if (ro) ro.observe(el);
      function dispose() {
        if (!alive) return;
        alive = false; gen++;
        if (ro) ro.disconnect();
        if (model) { scene.remove(model.group); model.dispose(); model = null; }
        if (scene.environment) scene.environment.dispose();
        renderer.dispose(); renderer.forceContextLoss();
        el.innerHTML = '';
      }
      return rebuild().then(function () {
        if (opts.onReady) opts.onReady();
        return {
          setFinish: function (f) { cur.finish = f; return model ? model.setFinish(f).then(function () { draw(); draw(); }) : Promise.resolve(); },
          setState: function (s) { cur.state = s; return rebuild(); },
          setSize: function (sz) { cur.size = sz; return rebuild(); },
          setBase: function (b) { cur.base = b; return rebuild(); },
          dispose: dispose
        };
      }, function (err) { dispose(); throw err; });
    });
  }

  root.Aluma3D = { build: build, studio: studio, interior: interior, frame: frame, swatch: swatch, mount: mount,
                   FINISHES: FINISHES, PRODUCTS: Object.keys(PRODUCTS) };
})(typeof window !== 'undefined' ? window : this);
