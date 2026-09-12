/* GOREN — the table as a 3D model. One source of truth for the render harness
   (tools/render3d.html) and the on-page viewer. Loads only when the visitor asks to
   rotate the table; the page itself ships pre-rendered images.

   window.Goren.build(THREE, opts)   -> model { group, ready, setTone, setState, lights, environment, bounds, dispose }
   window.Goren.frame(THREE, camera, box, viewName|spec, aspect) -> deterministic fit-to-view framing
   window.Goren.mount(el, opts)      -> Promise<{ setTone, setState, dispose }>   (loads three.js from cdnjs)

   opts for build: { tone, state, textures(tone) -> {albedo, normal, rough, end}, hdr: url|null,
                     anisotropy, shadowMap, bg, onProgress(fraction) }
   opts for mount: { tone, state, bg, onProgress(fraction), onReady(), texturePath, hdr, view }
   window.Goren.prefetch()           -> optional <link rel=prefetch> of three.js for the page to call after load

   Materials are photo-scanned oak (CC0, Poly Haven "oak_veneer_01") baked by tools/bake_textures.py:
   albedo per tone, an end-grain albedo per tone, one shared normal map, one shared packed map
   (R = AO, G = roughness). Five oak materials (face veneer, underside balancing veneer, lipping,
   solid frame, end grain) bind the same maps and share one shader program; the steel and the
   joint filler (no maps) share a second.
   Nothing is generated on the main thread; the only CPU work is a 32x32 contact-shadow gradient.
*/
(function (root) {
  "use strict";

  // ---- spec, in metres. Frozen. ------------------------------------------
  var L_CLOSED = 1.60, LEAF = 0.60, WID = 0.90, HGT = 0.75;
  var TOP_T = 0.040;                       // 40 mm top: oak veneer on plywood, solid oak lipping
  var CH_V = 0.020, CH_H = 0.026;          // underside chamfer: 20 mm up, 26 mm in, outer edges only
  var SEAM = 0.0016;                       // joint gap between slabs / leaf: 1.6 mm, ~2 px at 2400 px (at 0.8-1.2 mm the dark joint aliased into a dotted line on the top face)
  var FRAME_INSET = 0.26, RAIL_W = 0.36, FOOT_W = 0.60;
  var STOCK = 0.06, STOCK_X = 0.075, BEAM_H = 0.05, BEAM_W = 0.04;
  var SINK = 0.0005;                       // parts that share a plane overlap by 0.5 mm so the planes cannot z-fight (rail head into the top, beam into the heads)
  var UNDER_ACROSS = 2.2;                  // underside: a plain balancing veneer, straight grain sampled 2.2x denser across (no cathedral figure stretched into streaks)
  var TILE = 1.20;                         // metres of wood per texture repeat on solid parts
  var TILE_FACE = 2.40;                    // veneer faces: one repeat per 2.4 m, longer than the open top (2.2 m) — no column of veneer ever repeats
  var LEAF_FLITCH = [0.50, 0.31];          // the leaf is its own veneer flitch: a different strip of the map, not the halves' continuation
  var EDGE_ACROSS = 2.5;                   // lipping profile samples the map 2.5x denser across the grain: a rift-sawn solid edge, tight straight grain
  var CHAM_LEN = Math.hypot(CH_V, CH_H);   // width of the chamfer face along the profile (32.8 mm)
  var TILE_END = 0.30;                     // end-grain map (bake_textures.py): 30 cm per repeat
  var BG_DEFAULT = '#efeeea';              // page paper colour; render3d.js --bg overrides

  var TONES = {
    natural: { base: '#a07c58', rough: 0.56, edge: 0.94, name: 'natural' },
    smoked:  { base: '#66584c', rough: 0.54, edge: 0.93, name: 'smoked' },
    white:   { base: '#c9b7a4', rough: 0.60, edge: 0.95, name: 'white' }
  };
  var SCRIPT_BASE = (function () {
    var s = document.currentScript && document.currentScript.src;
    return s ? s.replace(/[^\/]*$/, '') : '/assets/';
  })();

  // ---- geometry builder: quads with an outward hint, world-space UVs ------
  function Builder() { this.p = []; this.n = []; this.uv = []; }
  Builder.prototype.tri = function (a, b, c, uvf, hint) {
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    var len = Math.hypot(nx, ny, nz) || 1; nx /= len; ny /= len; nz /= len;
    if (hint && nx * hint[0] + ny * hint[1] + nz * hint[2] < 0) { var t = b; b = c; c = t; nx = -nx; ny = -ny; nz = -nz; }
    var self = this;
    [a, b, c].forEach(function (p) {
      self.p.push(p[0], p[1], p[2]); self.n.push(nx, ny, nz);
      var t = uvf(p); self.uv.push(t[0], t[1]);
    });
  };
  Builder.prototype.quad = function (a, b, c, d, uvf, hint) { this.tri(a, b, c, uvf, hint); this.tri(a, c, d, uvf, hint); };
  Builder.prototype.geometry = function (THREE) {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    return g;
  };

  // Axis-aligned box in world coords. grain: 'x' | 'y' | 'z' = direction the wood runs.
  // UV = (across, along) / TILE so texel density is identical on every face of every part.
  // The two faces the grain runs into are end grain: they go to endBd (the end-grain material).
  function box(bd, cx, cy, cz, w, h, d, grain, off, endBd) {
    var x0 = cx - w / 2, x1 = cx + w / 2, y0 = cy - h / 2, y1 = cy + h / 2, z0 = cz - d / 2, z1 = cz + d / 2;
    off = off || [0, 0];
    function uvFor(axis) {  // face normal axis -> uv function
      var others = ['x', 'y', 'z'].filter(function (k) { return k !== axis; });
      var idx = { x: 0, y: 1, z: 2 };
      var along = others.indexOf(grain) >= 0 ? grain : null;
      if (along) {
        var across = others[0] === along ? others[1] : others[0];
        return function (p) { return [p[idx[across]] / TILE + off[0], p[idx[along]] / TILE + off[1]]; };
      }
      // end grain: growth rings on their own (non-periodic) map, sampled from a window inside the
      // tile — part-local, so a face never straddles the tile border
      var c = [cx, cy, cz];
      return function (p) { return [(p[idx[others[0]]] - c[idx[others[0]]]) / TILE_END + 0.5 + off[0] * 0.3, (p[idx[others[1]]] - c[idx[others[1]]]) / TILE_END + 0.42 + off[1] * 0.3]; };
    }
    var ux = uvFor('x'), uy = uvFor('y'), uz = uvFor('z'), ends = endBd || bd;
    var bx = grain === 'x' ? ends : bd, by = grain === 'y' ? ends : bd, bz = grain === 'z' ? ends : bd;
    bx.quad([x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], ux, [-1, 0, 0]);
    bx.quad([x1, y0, z0], [x1, y0, z1], [x1, y1, z1], [x1, y1, z0], ux, [1, 0, 0]);
    by.quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], uy, [0, -1, 0]);
    by.quad([x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1], uy, [0, 1, 0]);
    bz.quad([x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], uz, [0, 0, -1]);
    bz.quad([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], uz, [0, 0, 1]);
  }

  // One slab of the top: the veneer face, the underside (a plain balancing veneer, its own
  // builder/material) and the solid lipping (long sides, outer ends, and the underside chamfer —
  // mitred where two chamfers meet). Local x along the length, centred; the top surface is y = 0.
  // outerL / outerR: is that end an outer end of the table (lipped and chamfered) or a seam
  // (square cut: the chamfer is on the outer edges only)? A seam's end section goes to `joint`,
  // the dark joint material: inside a 1.6 mm gap nothing is lit, and a lit wood end face read as
  // a light hairline through the seam. uvx0 is the slab's closed-state offset, so the grain stays
  // on its half when the table opens; flitch moves the leaf onto its own strip of the veneer map.
  function slab(face, under, edge, joint, L, W, uvx0, outerL, outerR, flitch) {
    var T = TOP_T, yc = -(T - CH_V), hx = L / 2, hz = W / 2, iz = hz - CH_H;
    var xl = outerL ? -(hx - CH_H) : -hx, xr = outerR ? hx - CH_H : hx;   // underside extent
    var fu = flitch ? flitch[0] : 0, fv = flitch ? flitch[1] : 0;
    var veneer = function (p) { return [p[2] / TILE_FACE + 0.15 + fu, (p[0] + uvx0) / TILE_FACE + 0.5 + fv]; };
    var balance = function (p) { return [p[2] * UNDER_ACROSS / TILE + 0.05, (p[0] + uvx0) / TILE + 0.3 + fv]; };
    // profile coordinate: 0 at the top arris, CH_V at the chamfer arris, CH_V + CHAM_LEN at the
    // underside — the grain runs unbroken from the lipping face round the arris and down the bevel, unstretched
    var prof = function (p) { return (p[1] > yc - 1e-6 ? -p[1] : CH_V + CHAM_LEN) * EDGE_ACROSS / TILE; };
    var longEdge = function (p) { return [prof(p) + 0.52, (p[0] + uvx0) / TILE + 0.5]; };
    var endEdge = function (p) { return [prof(p) + 0.71, p[2] / TILE + 0.23 + uvx0 * 0.1]; };
    face.quad([-hx, 0, -hz], [-hx, 0, hz], [hx, 0, hz], [hx, 0, -hz], veneer, [0, 1, 0]);
    under.quad([xl, -T, -iz], [xl, -T, iz], [xr, -T, iz], [xr, -T, -iz], balance, [0, -1, 0]);
    // long lipping and its chamfer: the chamfer runs straight out to a seam end, mitred at an outer end
    edge.quad([-hx, 0, hz], [hx, 0, hz], [hx, yc, hz], [-hx, yc, hz], longEdge, [0, 0, 1]);
    edge.quad([-hx, 0, -hz], [hx, 0, -hz], [hx, yc, -hz], [-hx, yc, -hz], longEdge, [0, 0, -1]);
    edge.quad([-hx, yc, hz], [hx, yc, hz], [xr, -T, iz], [xl, -T, iz], longEdge, [0, -1, 1]);
    edge.quad([-hx, yc, -hz], [hx, yc, -hz], [xr, -T, -iz], [xl, -T, -iz], longEdge, [0, -1, -1]);
    // ends
    [[-1, outerL, -hx, xl], [1, outerR, hx, xr]].forEach(function (e) {
      var s = e[0], x = e[2], xi = e[3], hint = [s, 0, 0];
      if (e[1]) {
        edge.quad([x, 0, -hz], [x, 0, hz], [x, yc, hz], [x, yc, -hz], endEdge, hint);
        edge.quad([x, yc, -hz], [x, yc, hz], [xi, -T, iz], [xi, -T, -iz], endEdge, [s, -1, 0]);
      } else {
        // seam end: the full section, square — a hexagon, the long chamfers clip its lower corners
        var a = [x, 0, -hz], ring = [[x, 0, hz], [x, yc, hz], [x, -T, iz], [x, -T, -iz], [x, yc, -hz]];
        for (var i = 0; i + 1 < ring.length; i++) joint.tri(a, ring[i], ring[i + 1], endEdge, hint);
      }
    });
  }

  // A splayed leg: a parallelogram prism with horizontal cuts top and bottom, so the foot
  // sits flat on the floor and the head butts flat against the rail. Grain along the leg.
  function leg(bd, x, zTop, zBot, yTop, off, endBd) {
    var dz = zBot - zTop, ang = Math.atan2(dz, yTop), cosA = Math.cos(ang), hw = STOCK / 2 / cosA, sx = STOCK_X / 2;
    var zc = function (y) { return zTop + dz * (y / yTop); };
    var along = function (p) { return p[1] / cosA / TILE + off; };
    var sideUV = function (p) { return [(p[2] - zc(p[1])) * cosA / TILE + 0.33, along(p)]; };
    var faceUV = function (p) { return [(p[0] - x) / TILE + 0.62, along(p)]; };
    var endUV = function (p) { return [(p[0] - x) / TILE_END + 0.5 + off * 0.2, (p[2] - zTop) / TILE_END + 0.45]; };
    var ends = endBd || bd;
    var B = [[x - sx, 0, zBot - hw], [x + sx, 0, zBot - hw], [x + sx, 0, zBot + hw], [x - sx, 0, zBot + hw]];
    var Tt = [[x - sx, yTop, zTop - hw], [x + sx, yTop, zTop - hw], [x + sx, yTop, zTop + hw], [x - sx, yTop, zTop + hw]];
    ends.quad(B[0], B[1], B[2], B[3], endUV, [0, -1, 0]);
    ends.quad(Tt[0], Tt[1], Tt[2], Tt[3], endUV, [0, 1, 0]);
    bd.quad(B[0], B[3], Tt[3], Tt[0], sideUV, [-1, 0, 0]);
    bd.quad(B[1], B[2], Tt[2], Tt[1], sideUV, [1, 0, 0]);
    bd.quad(B[0], B[1], Tt[1], Tt[0], faceUV, [0, 0, -1]);
    bd.quad(B[3], B[2], Tt[2], Tt[3], faceUV, [0, 0, 1]);
  }

  // ---- textures ------------------------------------------------------------
  function defaultTextures(size) {
    size = size || 1024;
    return function (tone) {
      return {
        albedo: SCRIPT_BASE + 'textures/' + tone + '-albedo-' + size + '.jpg',
        normal: SCRIPT_BASE + 'textures/oak-normal-' + size + '.jpg',
        rough: SCRIPT_BASE + 'textures/oak-rough-' + size + '.jpg',
        end: SCRIPT_BASE + 'textures/endgrain-' + tone + '-512.jpg'
      };
    };
  }

  // Downloads started before three.js has arrived (mount() calls warm() for the first tone's maps
  // and the HDR, so the ~430 KB of maps overlap the ~650 KB three.min.js instead of queueing
  // behind it). loadImageTexture / xhrBuffer consume the blob; over file:// there is no fetch.
  var warmCache = {};
  function warm(url) {
    if (!url || warmCache[url] || location.protocol === 'file:' || !root.fetch) return;
    var p = root.fetch(url, { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url); return r.blob(); });
    p.catch(function () { if (warmCache[url] === p) delete warmCache[url]; });
    warmCache[url] = p;
  }
  function takeWarm(url) { var p = warmCache[url]; delete warmCache[url]; return p || null; }

  function loadImageTexture(THREE, url, srgb, anisotropy) {
    return new Promise(function (resolve, reject) {
      var done = function (tex) {
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        tex.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
        tex.anisotropy = anisotropy || 4;
        tex.needsUpdate = true;
        resolve(tex);
      };
      var bitmapOpts = { imageOrientation: 'flipY', premultiplyAlpha: 'none' };
      // ImageBitmapLoader decodes off the main thread; imageOrientation 'flipY' reproduces
      // TextureLoader's flipY=true so both paths sample the maps identically.
      // (fetch() refuses file:// even with --allow-file-access-from-files; the harness takes the <img> path)
      function viaLoader() {
        if (root.createImageBitmap && THREE.ImageBitmapLoader && location.protocol !== 'file:') {
          var l = new THREE.ImageBitmapLoader(); l.setOptions(bitmapOpts);
          l.load(url, function (bmp) { var t = new THREE.Texture(bmp); t.flipY = false; done(t); }, undefined,
            function () { new THREE.TextureLoader().load(url, done, undefined, reject); });
        } else {
          new THREE.TextureLoader().load(url, done, undefined, reject);
        }
      }
      var pre = takeWarm(url);
      if (pre && root.createImageBitmap) {
        pre.then(function (blob) { return root.createImageBitmap(blob, bitmapOpts); })
          .then(function (bmp) { var t = new THREE.Texture(bmp); t.flipY = false; done(t); }, viaLoader);
      } else viaLoader();
    });
  }

  // XHR rather than fetch(): identical over http(s), and it also works from file:// in the render harness
  function xhrBuffer(url) {
    var pre = takeWarm(url);
    function xhr() {
      return new Promise(function (resolve, reject) {
        var x = new XMLHttpRequest(); x.open('GET', url, true); x.responseType = 'arraybuffer';
        x.onload = function () { if (x.status === 200 || (x.status === 0 && x.response && x.response.byteLength)) resolve(x.response); else reject(new Error('HTTP ' + x.status + ' ' + url)); };
        x.onerror = function () { reject(new Error('network error ' + url)); };
        x.send();
      });
    }
    if (!pre) return xhr();
    return pre.then(function (blob) { return new Response(blob).arrayBuffer(); }).catch(xhr);
  }

  // Radiance .hdr -> half-float equirect DataTexture (the only piece of RGBELoader we need)
  function parseRGBE(THREE, buf) {
    var u8 = new Uint8Array(buf), pos = 0, line, w = 0, h = 0;
    function readLine() { var s = ''; while (pos < u8.length && u8[pos] !== 10) s += String.fromCharCode(u8[pos++]); pos++; return s; }
    if (readLine().indexOf('#?') !== 0) throw new Error('not a Radiance file');
    while ((line = readLine()) !== '') { /* header */ }
    var m = /-Y (\d+) \+X (\d+)/.exec(readLine()); if (!m) throw new Error('unsupported HDR layout');
    h = +m[1]; w = +m[2];
    var rgbe = new Uint8Array(w * h * 4), scan = new Uint8Array(w * 4);
    for (var y = 0; y < h; y++) {
      var o = y * w * 4;
      if (u8[pos] === 2 && u8[pos + 1] === 2 && ((u8[pos + 2] << 8) | u8[pos + 3]) === w) {
        pos += 4;
        for (var c = 0; c < 4; c++) {
          for (var x = 0; x < w;) {
            var n = u8[pos++];
            if (n > 128) { n -= 128; var v = u8[pos++]; for (var i = 0; i < n; i++) scan[(x++) * 4 + c] = v; }
            else { for (var j = 0; j < n; j++) scan[(x++) * 4 + c] = u8[pos++]; }
          }
        }
        rgbe.set(scan, o);
      } else { rgbe.set(u8.subarray(pos, pos + w * 4), o); pos += w * 4; }
    }
    var half = THREE.DataUtils && THREE.DataUtils.toHalfFloat, type = half ? THREE.HalfFloatType : THREE.FloatType;
    var out = half ? new Uint16Array(w * h * 4) : new Float32Array(w * h * 4), one = half ? half(1) : 1;
    for (var k = 0; k < w * h; k++) {
      var e = rgbe[k * 4 + 3], f = e ? Math.pow(2, e - 136) : 0;
      var r = rgbe[k * 4] * f, g = rgbe[k * 4 + 1] * f, b = rgbe[k * 4 + 2] * f;
      if (half) { out[k * 4] = half(r); out[k * 4 + 1] = half(g); out[k * 4 + 2] = half(b); }
      else { out[k * 4] = r; out[k * 4 + 1] = g; out[k * 4 + 2] = b; }
      out[k * 4 + 3] = one;
    }
    var tex = new THREE.DataTexture(out, w, h, THREE.RGBAFormat, type);
    tex.mapping = THREE.EquirectangularReflectionMapping; tex.colorSpace = THREE.LinearSRGBColorSpace;
    tex.flipY = true; tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter; tex.generateMipmaps = false;
    tex.needsUpdate = true;
    return tex;
  }

  // Zero-download fallback environment: a warm studio box with three soft panels
  function roomScene(THREE) {
    var s = new THREE.Scene();
    var shell = new THREE.Mesh(new THREE.BoxGeometry(10, 6, 10), new THREE.MeshStandardMaterial({ color: 0x8c877e, roughness: 1, side: THREE.BackSide }));
    shell.position.y = 2.5; s.add(shell);
    function panel(w, h, x, y, z, ry, c, i) {
      var m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(i) }));
      m.position.set(x, y, z); m.rotation.y = ry; m.lookAt(0, 1, 0); s.add(m);
    }
    panel(3, 2, -3.5, 3.5, 3.5, 0, 0xfff1dc, 9);   // key side
    panel(4, 3, 4.2, 2.2, -1.5, 0, 0xe8eefc, 3);   // cool fill
    panel(5, 1.5, 0, 5.6, -3, 0, 0xffffff, 4);     // overhead strip
    s.add(new THREE.AmbientLight(0xffffff, 1.2));
    return s;
  }

  // ---- model ---------------------------------------------------------------
  function build(THREE, opts) {
    opts = opts || {};
    var tone = TONES[opts.tone] ? opts.tone : 'natural', state = opts.state === 'open' ? 'open' : 'closed';
    var texturesFor = opts.textures || defaultTextures(opts.textureSize);
    var aniso = opts.anisotropy || 8;
    var progress = opts.onProgress || function () {};
    var albedoCache = {}, shared = null, sharedPromise = null, disposed = false;

    var faceMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.56, metalness: 0, envMapIntensity: 1.0 });
    var edgeMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.62, metalness: 0, envMapIntensity: 0.95 });
    var legMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.60, metalness: 0, envMapIntensity: 0.95 });
    var endMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.70, metalness: 0, envMapIntensity: 0.8 });
    var underMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.70, metalness: 0, envMapIntensity: 0.7 });
    // matte black powder coat: a dark grey base, not black — a black base has no diffuse response,
    // so the softbox and the floor bounce never registered on the beam's top and bottom edges and it
    // read as a cut-out; low metalness keeps it matte steel rather than a mirror
    var steel = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.42, metalness: 0.30, envMapIntensity: 1.3 });
    // the inside of a joint: a dark brown, not black — what a 1.6 mm gap between two oiled oak
    // parts looks like in a photograph (no maps, so it shares the steel's shader program)
    var jointMat = new THREE.MeshStandardMaterial({ color: 0x3a2c1f, roughness: 0.95, metalness: 0, envMapIntensity: 0.3 });
    var oakMats = [faceMat, edgeMat, legMat, endMat, underMat];
    // the veneer keeps the scan's pore relief; the machined lipping is planed and oiled, so its
    // relief is a third of that (at a grazing key the full normal map made the arris wave)
    faceMat.normalScale = new THREE.Vector2(1, 1);
    edgeMat.normalScale = new THREE.Vector2(0.35, 0.35);
    legMat.normalScale = new THREE.Vector2(0.8, 0.8);
    endMat.normalScale = new THREE.Vector2(0, 0);
    underMat.normalScale = new THREE.Vector2(0.15, 0.15);   // sanded balancing veneer under oil: almost no relief, so grazing light cannot smear it

    var group = new THREE.Group();
    var meshes = [];

    function frameX() { return L_CLOSED / 2 - FRAME_INSET + (state === 'open' ? LEAF / 2 : 0); }

    function assemble() {
      meshes.forEach(function (m) { group.remove(m); m.geometry.dispose(); });
      meshes.length = 0;
      var face = new Builder(), under = new Builder(), edge = new Builder(), solid = new Builder(), ends = new Builder(), metal = new Builder(), joint = new Builder();
      var shift = state === 'open' ? LEAF / 2 : 0, half = L_CLOSED / 2;
      // slabs: [length, x position, closed-state uv offset, outer end at -x, outer end at +x, flitch]
      // two halves — one veneered top cut in two, so their grain continues across the closed joint —
      // plus the leaf in the middle when open, a separate flitch with its own figure
      var slabs = [[half - SEAM, -(half / 2 + shift), -half / 2, true, false, null], [half - SEAM, half / 2 + shift, half / 2, false, true, null]];
      if (state === 'open') slabs.splice(1, 0, [LEAF - SEAM, 0, 0, false, false, LEAF_FLITCH]);
      slabs.forEach(function (s) {
        var f = new Builder(), u = new Builder(), e = new Builder(), j = new Builder();
        slab(f, u, e, j, s[0], WID, s[2], s[3], s[4], s[5]);
        [[f, face], [u, under], [e, edge], [j, joint]].forEach(function (pair) {
          var src = pair[0], dst = pair[1];
          for (var i = 0; i < src.p.length; i += 3) { dst.p.push(src.p[i] + s[1], src.p[i + 1] + HGT, src.p[i + 2]); }
          Array.prototype.push.apply(dst.n, src.n); Array.prototype.push.apply(dst.uv, src.uv);
        });
      });
      // joint filler: the extension hardware inside each seam, so the joint reads as a hairline shadow
      // and never shows the floor through the gap (the top view drew a light line without it);
      // two boxes following the section: full width behind the lipping band, inset behind the chamfer
      (state === 'open' ? [-LEAF / 2, LEAF / 2] : [0]).forEach(function (sx) {
        box(joint, sx, HGT - CH_V / 2 - 0.001, 0, SEAM * 2 + 0.0006, CH_V - 0.002, WID - 0.003, 'x');
        box(joint, sx, HGT - TOP_T + (TOP_T - CH_V) / 2 + 0.001, 0, SEAM * 2 + 0.0006, TOP_T - CH_V - 0.001, WID - 2 * CH_H - 0.004, 'x');
      });
      // trestles: the head rail sits flush against the underside of the top (the extension slides
      // live inside the top's thickness — nothing between rail and top); the legs butt the rail
      var fx = frameX(), railTop = HGT - TOP_T + SINK, railLen = RAIL_W + STOCK;
      [-1, 1].forEach(function (s, i) {
        var x = s * fx;
        box(solid, x, railTop - STOCK / 2, 0, STOCK_X, STOCK, railLen, 'z', [0.2 * i, 0.4], ends);
        [-1, 1].forEach(function (t, j) { leg(solid, x, t * RAIL_W / 2, t * FOOT_W / 2, railTop - STOCK, 0.15 * (i * 2 + j), ends); });
      });
      // the one steel beam: its top face flush under the trestle heads (0.5 mm into them, so the
      // shared plane cannot z-fight); it runs out to the heads' outer faces
      box(metal, 0, railTop - STOCK - BEAM_H / 2 + SINK, 0, fx * 2 + STOCK_X, BEAM_H, BEAM_W, 'x');
      [[face, faceMat], [under, underMat], [edge, edgeMat], [solid, legMat], [ends, endMat], [metal, steel], [joint, jointMat]].forEach(function (pair) {
        var m = new THREE.Mesh(pair[0].geometry(THREE), pair[1]);
        m.castShadow = m.receiveShadow = true; group.add(m); meshes.push(m);
      });
    }

    function loadShared() {
      if (sharedPromise) return sharedPromise;
      var urls = texturesFor(tone);
      sharedPromise = Promise.all([
        loadImageTexture(THREE, urls.normal, false, aniso),
        loadImageTexture(THREE, urls.rough, false, aniso)
      ]).then(function (t) {
        shared = { normal: t[0], rough: t[1] };
        oakMats.forEach(function (m) {
          // every oak material binds the same set of maps so all four share ONE shader program
          // (a second program cost ~300 ms of compile on the viewer's first frame). The end-grain
          // faces zero the normal and AO contributions instead: the veneer's relief and occlusion
          // maps are along-grain streaks, which at the end-grain UV scale read as vertical stripes.
          m.normalMap = shared.normal; m.roughnessMap = shared.rough; m.aoMap = shared.rough;
          m.aoMapIntensity = m === endMat ? 0 : m === underMat ? 0.3 : 0.8;
          m.needsUpdate = true;
        });
        progress(0.6);
        return shared;
      });
      return sharedPromise;
    }
    function loadAlbedo(t) {
      if (!albedoCache[t]) {
        var u = texturesFor(t);
        albedoCache[t] = Promise.all([loadImageTexture(THREE, u.albedo, true, aniso), loadImageTexture(THREE, u.end, true, aniso)])
          .then(function (r) { return { albedo: r[0], end: r[1] }; });
      }
      return albedoCache[t];
    }
    function applyTone(t, tex) {
      if (disposed) return;
      tone = t;
      var spec = TONES[t];
      faceMat.map = tex.albedo; faceMat.roughness = spec.rough; faceMat.color.set(0xffffff);
      edgeMat.map = tex.albedo; edgeMat.roughness = spec.rough + 0.06; edgeMat.color.set(0xffffff).multiplyScalar(spec.edge);
      legMat.map = tex.albedo; legMat.roughness = spec.rough + 0.04; legMat.color.set(0xffffff).multiplyScalar(0.98);
      endMat.map = tex.end; endMat.roughness = spec.rough + 0.14; endMat.color.set(0xffffff).multiplyScalar(0.92);
      underMat.map = tex.albedo; underMat.roughness = spec.rough + 0.12; underMat.color.set(0xffffff).multiplyScalar(0.9);
      oakMats.forEach(function (m) { m.needsUpdate = true; });
    }

    // fallback colour until the maps arrive (keeps the harness honest if a file is missing)
    oakMats.forEach(function (m) { m.color.set(TONES[tone].base); });
    assemble();
    var ready = Promise.all([loadShared(), loadAlbedo(tone)]).then(function (r) { applyTone(tone, r[1]); progress(0.8); return model; });

    var model = {
      group: group,
      ready: ready,
      frameX: frameX,
      tone: function () { return tone; },
      state: function () { return state; },
      bounds: function () { return new THREE.Box3().setFromObject(group); },
      setTone: function (t) {
        t = TONES[t] ? t : 'natural';
        return loadAlbedo(t).then(function (tex) { applyTone(t, tex); return model; });
      },
      prefetchTones: function () { Object.keys(TONES).forEach(loadAlbedo); },
      setState: function (s) { state = s === 'open' ? 'open' : 'closed'; assemble(); },
      // key light + floor shadow + contact occlusion. Image-based fill comes from environment().
      lights: function (scene, o) {
        o = o || {};
        var key = new THREE.DirectionalLight(0xfff3e4, o.keyIntensity || 2.4);
        // near-overhead softbox, front-left: the front lipping is lit ~18° off grazing (at 11° the
        // pore relief made the arris wave), and the cast shadow falls behind the table, where the
        // hero cameras mostly cannot see it
        key.position.set(-1.2, 4.4, 1.5);
        key.target.position.set(0, 0.4, 0); scene.add(key.target);
        key.castShadow = o.shadows !== false;
        var sm = o.shadowMap || 2048;
        key.shadow.mapSize.set(sm, sm); key.shadow.bias = -0.0002; key.shadow.normalBias = 0.015;
        key.shadow.radius = o.shadowRadius || 80; key.shadow.blurSamples = o.blurSamples || 24;   // VSM blur in shadow-map texels: a softbox penumbra, not a spotlight
        key.shadow.camera.left = -2.4; key.shadow.camera.right = 2.4; key.shadow.camera.top = 2.0; key.shadow.camera.bottom = -2.0;   // room for the blur to spread
        key.shadow.camera.near = 1.0; key.shadow.camera.far = 9;
        scene.add(key);
        // RENDER-BRIEF R1: no shadow except a soft contact shadow. The key's cast shadow is kept
        // only as a faint wash (0.12) so the table does not float; the grounding is the contact blobs.
        var floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.ShadowMaterial({ color: 0x2a2419, opacity: o.shadowOpacity || 0.12 }));
        floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; floor.name = 'floor'; scene.add(floor);
        // bounce: the pale paper floor throws warm light back up onto the underside, the chamfer
        // and the beam (without it the underside was a flat grey plane in the detail view)
        var bounce = new THREE.HemisphereLight(0x000000, o.bounceColor || 0xefeeea, o.bounce === undefined ? 0.55 : o.bounce);
        bounce.position.set(0, 1, 0); scene.add(bounce);
        // contact occlusion: a soft radial blob under each foot and a faint one under the top.
        // 32x32 gradient computed once (~1k operations) — the one texture made on the CPU.
        var N = 32, data = new Uint8Array(N * N * 4);
        for (var y = 0; y < N; y++) for (var x = 0; x < N; x++) {
          var dx = (x + 0.5) / N - 0.5, dy = (y + 0.5) / N - 0.5, r = Math.min(1, Math.hypot(dx, dy) * 2);
          var a = Math.pow(1 - r, 2.2), i = (y * N + x) * 4;
          data[i] = 30; data[i + 1] = 24; data[i + 2] = 16; data[i + 3] = Math.round(255 * a);
        }
        var blob = new THREE.DataTexture(data, N, N, THREE.RGBAFormat); blob.needsUpdate = true;
        blob.minFilter = blob.magFilter = THREE.LinearFilter;
        var contacts = new THREE.Group(); contacts.name = 'contacts'; scene.add(contacts);
        function place() {
          while (contacts.children.length) contacts.remove(contacts.children[0]);
          var fx = frameX();
          function blobMesh(w, d, x, z, op, y) {
            var m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshBasicMaterial({ map: blob, transparent: true, opacity: op, depthWrite: false }));
            m.rotation.x = -Math.PI / 2; m.position.set(x, y || 0.0008, z); m.renderOrder = 1; contacts.add(m);
          }
          [-1, 1].forEach(function (s) { [-1, 1].forEach(function (t) { blobMesh(0.40, 0.34, s * fx, t * FOOT_W / 2, 0.8); }); });
          var len = (state === 'open' ? L_CLOSED + LEAF : L_CLOSED);
          blobMesh(len * 1.35, WID * 1.6, 0, 0, 0.18, 0.0004);
        }
        place();
        model.relayoutShadows = place;
        model.key = key;
        return { key: key, floor: floor, contacts: contacts, bounce: bounce };
      },
      // image-based lighting from the studio HDRI; falls back to a procedural room.
      environment: function (renderer, hdrUrl) {
        var pmrem = new THREE.PMREMGenerator(renderer); pmrem.compileEquirectangularShader();
        var fallback = function () { var env = pmrem.fromScene(roomScene(THREE), 0.04).texture; pmrem.dispose(); return env; };
        if (hdrUrl === null) return Promise.resolve(fallback());
        var url = hdrUrl || (SCRIPT_BASE + 'textures/studio-256.hdr');
        return xhrBuffer(url).then(function (buf) { var eq = parseRGBE(THREE, buf); var env = pmrem.fromEquirectangular(eq).texture; eq.dispose(); pmrem.dispose(); return env; })
          .catch(function (e) { if (root.console) console.warn('Goren: HDRI unavailable, using room fallback', e); return fallback(); });
      },
      materials: { face: faceMat, edge: edgeMat, leg: legMat, end: endMat, under: underMat, steel: steel, joint: jointMat },
      dispose: function () {
        disposed = true;
        meshes.forEach(function (m) { m.geometry.dispose(); });
        oakMats.concat([steel, jointMat]).forEach(function (m) { m.dispose(); });
        if (shared) { shared.normal.dispose(); shared.rough.dispose(); }
        Object.keys(albedoCache).forEach(function (k) { albedoCache[k].then(function (t) { t.albedo.dispose(); t.end.dispose(); }); });
      }
    };
    return model;
  }

  // ---- deterministic framing ------------------------------------------------
  // Each view: azimuth/elevation in degrees, vertical fov (45 mm ~ 30°, 50 mm ~ 27° on 3:2),
  // margin as a fraction of the frame. 'detail' is a fixed close-up on the trestle corner.
  var VIEWS = {
    hero:   { az: 38,  el: 13, fov: 30, margin: 0.085, lift: 0.02 },
    hero2:  { az: -42, el: 12, fov: 30, margin: 0.085, lift: 0.02 },
    front:  { az: 0,   el: 7,  fov: 27, margin: 0.09, lift: 0.0 },
    // end: 10° off the axis, so the far trestle reads as a second trestle instead of a sliver
    // peeking past the near leg (which at exactly 90° looked like a split in the leg)
    end:    { az: 80,  el: 8,  fov: 27, margin: 0.08, lift: 0.0 },
    top:    { az: 0,   el: 89.5, fov: 22, margin: 0.06, lift: 0 },
    detail: { detail: true, fov: 30 },
    // ---- product set (site/assets/product/, tools/render3d.js --product, tools/product_assets.py) ----
    // studio: the desktop hero on 2.2:1. A 50 mm feel: vertical fov 18.6° on 2.2:1 is 39.6° across; the
    // hero's azimuth; the elevation lands the eye ~1.05 m above the floor at the fitted distance. The
    // AABB corners project wider than the silhouette, so margin 0.14 puts the table's pixels at ~83 %
    // of the width; the negative lift leaves room under the feet for the contact shadow.
    // On 2.2:1 the fit is bound VERTICALLY (the silhouette from eye level is ~1.8:1), so the width the
    // table can take is set by the elevation, not the margin: 12.5° -> geometry ~70 % of the width,
    // 82 % with the cast shadow's tail. The near virtual AABB corner binds the fit, so a lift of -0.15
    // balances the gaps above the far top corner and under the contact shadow; shift 0.02 centres the
    // table + shadow mass (the key's cast shadow always trails to the right).
    studio:  { az: 38, el: 12.5, fov: 18.6, margin: 0.10, lift: -0.15, shift: 0.01 },
    // studioM: the same standpoint on 3:2 — fov 27 vertical is the same 39.6° across, so the fit lands
    // the camera in (nearly) the same place; here the horizontal binds, so the margin sets the width
    // (the cast shadow's ~0.28 m tail has to fit too: geometry ~74 % of the width, 86 % with the tail)
    studioM: { az: 38, el: 12.5, fov: 27, margin: 0.255, lift: -0.16, shift: 0.03 },
    // compare: one locked camera for both states — render3d.html fits it on the OPEN bounds (&fit=open)
    // and renders either state with it, so the closed table is physically shorter in the same frame
    compare: { az: 34, el: 11, fov: 27, margin: 0.215, lift: -0.16, shift: 0.035 },
    // edge: an actual outer corner of the top (+x, +z, closed): the veneer face at grazing, the lipping
    // band, the underside chamfer and the 40 mm section. 85–100 mm feel (fov 15), eye 14° above the
    // plane, 0.72 m off the corner, from 50° between the end and the long edge (frame ≈ 19 cm across,
    // so the 40 mm section is ~20 % of the height).
    edge:  { fov: 15, eye: function (b) { return [b.max.x + 0.50, HGT + 0.155, b.max.z + 0.42]; },
                      target: function (b) { return [b.max.x - 0.03, HGT - 0.02, b.max.z - 0.03]; } },
    // frame: low three-quarter view of the near trestle: head rail, legs, the beam and the underside
    // of the top as one structure, eye 20 cm below the top plane, 2.1 m off (4:3)
    frame: { fov: 30, eye: function (b) { return [b.max.x - FRAME_INSET + 1.35, HGT - 0.20, 1.55]; },
                      target: function (b) { return [b.max.x - FRAME_INSET - 0.05, HGT - 0.30, 0.0]; } }
  };

  // Places `camera` so the box fits the frame at the view's angles. Returns {position, target, distance}.
  function frame(THREE, camera, box, view, aspect) {
    var v = typeof view === 'string' ? VIEWS[view] || VIEWS.hero : view;
    aspect = aspect || camera.aspect || 1.6;
    camera.fov = v.fov || 30; camera.aspect = aspect;
    var size = new THREE.Vector3(), centre = new THREE.Vector3();
    box.getSize(size); box.getCenter(centre);
    if (v.detail) {
      // close-up (RENDER-BRIEF R7): the corner where the head rail, the leg and the steel beam meet,
      // from just below the top and to one side. The eye is 25 mm under the underside plane, so the
      // underside is a grazing band (~10 % of the frame) under the lipping and chamfer, and the
      // head's end grain, the leg's shoulder and the beam's edges take the frame.
      var fx = box.max.x - FRAME_INSET;                            // the near trestle's x
      var target = new THREE.Vector3(fx + 0.02, HGT - 0.105, 0.16);
      var eye = new THREE.Vector3(fx + 0.52, HGT - TOP_T - 0.025, 0.92);
      camera.position.copy(eye);
      camera.lookAt(target); camera.near = 0.05; camera.far = 40; camera.updateProjectionMatrix();
      return { position: camera.position.clone(), target: target, distance: eye.distanceTo(target) };
    }
    if (v.eye) {
      // explicit camera (product close-ups): eye / target as [x, y, z] or a function of the box
      var ep = typeof v.eye === 'function' ? v.eye(box) : v.eye, tp = typeof v.target === 'function' ? v.target(box) : v.target;
      var eyeX = new THREE.Vector3().fromArray(ep), targetX = new THREE.Vector3().fromArray(tp);
      camera.position.copy(eyeX);
      camera.lookAt(targetX); camera.near = 0.05; camera.far = 40; camera.updateProjectionMatrix();
      return { position: camera.position.clone(), target: targetX, distance: eyeX.distanceTo(targetX) };
    }
    var az = v.az * Math.PI / 180, el = v.el * Math.PI / 180;
    var dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)); // target -> camera
    var target = centre.clone(); target.y += (v.lift || 0) * size.y;
    var f = dir.clone().negate(), r = new THREE.Vector3().crossVectors(f, new THREE.Vector3(0, 1, 0)).normalize();
    var tanH = Math.tan(camera.fov * Math.PI / 360) * aspect, d = 0;
    camera.near = 0.05; camera.far = 60;
    // fit, then centre: perspective pushes the near corner outward, so a box fitted about its own
    // centre sits off-centre by up to ~8 % of the frame (13 % margin one side, 5 % the other).
    // Shift the target sideways by the projected imbalance and refit; three passes converge to < 0.1 %.
    for (var pass = 0; pass < 3; pass++) {
      d = fitDistance(THREE, box, target, dir, camera.fov, aspect, v.margin || 0.06);
      camera.position.copy(target).addScaledVector(dir, d);
      camera.lookAt(target); camera.updateProjectionMatrix(); camera.updateMatrixWorld();
      var minX = 1, maxX = -1;
      for (var i = 0; i < 8; i++) {
        var c = new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).project(camera);
        minX = Math.min(minX, c.x); maxX = Math.max(maxX, c.x);
      }
      target.addScaledVector(r, (minX + maxX) / 2 * tanH * d);
    }
    // optional sideways shift, a fraction of the frame width (+ = the table moves left in the frame)
    if (v.shift) target.addScaledVector(r, v.shift * 2 * tanH * d);
    camera.position.copy(target).addScaledVector(dir, d);
    camera.lookAt(target); camera.updateProjectionMatrix();
    return { position: camera.position.clone(), target: target, distance: d };
  }
  function fitDistance(THREE, box, target, dir, fov, aspect, margin) {
    var f = dir.clone().negate(), up = new THREE.Vector3(0, 1, 0);
    var r = new THREE.Vector3().crossVectors(f, up).normalize(), u = new THREE.Vector3().crossVectors(r, f).normalize();
    var tanV = Math.tan(fov * Math.PI / 360) * (1 - margin), tanH = tanV * aspect, D = 0;
    for (var i = 0; i < 8; i++) {
      var c = new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).sub(target);
      var x = c.dot(r), y = c.dot(u), z = c.dot(f);
      D = Math.max(D, Math.abs(y) / tanV - z, Math.abs(x) / tanH - z);
    }
    return D;
  }

  // ---- on-page viewer ------------------------------------------------------
  var THREE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js';
  var loading = null;
  function loadThree() {
    if (root.THREE) return Promise.resolve(root.THREE);
    if (loading) return loading;
    loading = new Promise(function (res, rej) {
      var s = document.createElement('script'); s.src = THREE_URL; s.async = true; s.crossOrigin = 'anonymous';
      s.onload = function () { res(root.THREE); }; s.onerror = function () { loading = null; rej(new Error('three.js failed to load')); };
      document.head.appendChild(s);
    });
    return loading;
  }

  function boxSize(el) {
    var w = el.clientWidth, h = el.clientHeight;
    if ((!w || !h) && el.parentElement) { var r = el.parentElement.getBoundingClientRect(); w = w || r.width; h = h || r.height; }
    w = Math.max(200, Math.round(w || 600)); h = Math.round(h || w / 1.6);
    return [w, h];
  }

  function mount(el, opts) {
    opts = opts || {};
    var progress = opts.onProgress || function () {};
    var bg = opts.bg || BG_DEFAULT;
    // visible busy state inside the element (the page may also style #rotate[aria-busy])
    var bar = document.createElement('div');
    bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
    bar.style.cssText = 'position:absolute;left:0;bottom:0;height:3px;width:0;background:currentColor;opacity:.5;transition:width .2s';
    if (root.getComputedStyle && getComputedStyle(el).position === 'static') el.style.position = 'relative';   // never override the page's absolute #viewer
    el.innerHTML = ''; el.appendChild(bar);
    var shown = 0;
    function report(f) { f = Math.max(shown, Math.min(1, f)); if (f === shown && f < 1) return; shown = f; bar.style.width = (f * 100).toFixed(0) + '%'; bar.setAttribute('aria-valuenow', (f * 100).toFixed(0)); progress(f); }
    report(0.02);

    // the box is known before three.js is: start the first tone's maps and the HDR downloading now
    var size = boxSize(el), w = size[0], h = size[1];
    var dpr = Math.min(opts.maxDpr || 1.5, root.devicePixelRatio || 1);
    var phone = (w * dpr) < 900;
    var texFn = opts.textures || defaultTextures(phone ? 512 : 1024);
    var firstTone = TONES[opts.tone] ? opts.tone : 'natural';
    var hdrUrl = opts.hdr === null ? null : (opts.hdr || (SCRIPT_BASE + 'textures/studio-256.hdr'));
    (function (u) { warm(u.normal); warm(u.rough); warm(u.albedo); warm(u.end); })(texFn(firstTone));
    if (hdrUrl) warm(hdrUrl);

    var mark = function (n) { if (root.performance && performance.mark) performance.mark('goren:' + n); };
    mark('mount');
    return loadThree().then(function (THREE) {
      report(0.25); mark('three');
      var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.setClearColor(new THREE.Color(bg), 1);
      renderer.setPixelRatio(dpr); renderer.setSize(w, h);
      renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.VSMShadowMap;
      // the light and the table are static while the visitor orbits: draw (and VSM-blur) the
      // shadow map once, and again only when the geometry changes (setState)
      renderer.shadowMap.autoUpdate = false; renderer.shadowMap.needsUpdate = true;
      renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = opts.exposure || 1.0;
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      var c = renderer.domElement; c.style.display = 'block'; c.style.touchAction = 'pan-y'; c.style.cursor = 'grab';
      c.tabIndex = 0; c.setAttribute('role', 'img'); c.setAttribute('aria-label', el.getAttribute('aria-label') || '');

      var scene = new THREE.Scene(); scene.background = new THREE.Color(bg);
      var model = build(THREE, {
        tone: firstTone, state: opts.state, textures: texFn,
        anisotropy: Math.min(8, renderer.capabilities.getMaxAnisotropy()),
        onProgress: function (f) { report(0.25 + f * 0.55); }
      });
      scene.add(model.group);
      // the still uses radius 80 on a 2048 map (19 cm penumbra); the viewer's 1024 map with radius 40
      // gives the same penumbra, and its cast shadow is only a 0.12 wash, so a bigger map buys nothing
      // the eye can see while its VSM blur costs first-frame time on weak GPUs
      model.lights(scene, { shadowMap: 1024, shadowRadius: 40, blurSamples: 8 });

      var cam = new THREE.PerspectiveCamera(30, w / h, 0.05, 60);
      var view = VIEWS[opts.view || 'hero'] || VIEWS.hero;
      var theta = view.az * Math.PI / 180, phi = Math.PI / 2 - view.el * Math.PI / 180, radius = 3.5, target = new THREE.Vector3();
      function refit() {
        var fit = frame(THREE, cam, model.bounds(), { az: theta * 180 / Math.PI, el: (Math.PI / 2 - phi) * 180 / Math.PI, fov: view.fov, margin: view.margin, lift: view.lift }, cam.aspect);
        radius = fit.distance; target.copy(fit.target);
      }
      function place() {
        cam.position.set(target.x + radius * Math.sin(phi) * Math.sin(theta), target.y + radius * Math.cos(phi), target.z + radius * Math.sin(phi) * Math.cos(theta));
        cam.lookAt(target);
      }
      refit(); place();

      // render on demand only
      var raf = 0, needs = false, vel = 0, dragging = false, lx = 0, ly = 0, lt = 0, spinUntil = 0, ready = false;
      function render() { raf = 0; if (!ready) return; renderer.render(scene, cam); needs = false; if (Math.abs(vel) > 0.0004 || performance.now() < spinUntil) invalidate(); }
      function invalidate() { needs = true; if (!raf) raf = requestAnimationFrame(tick); }
      function tick() {
        if (!dragging) {
          if (performance.now() < spinUntil && Math.abs(vel) < 0.0004) theta += 0.0022;
          else if (Math.abs(vel) > 0.0004) { theta += vel; vel *= 0.92; } else vel = 0;
          place();
        }
        render();
      }
      function down(x, y) { dragging = true; lx = x; ly = y; lt = performance.now(); vel = 0; spinUntil = 0; }
      function move(x, y) {
        if (!dragging) return;
        var now = performance.now(), dt = Math.max(8, now - lt), dth = -(x - lx) * 0.008;
        theta += dth; phi = Math.max(0.6, Math.min(1.45, phi + (y - ly) * 0.006));
        vel = dth * 16 / dt; lx = x; ly = y; lt = now; place(); invalidate();
      }
      function up() { dragging = false; c.style.cursor = 'grab'; if (Math.abs(vel) > 0.0004) invalidate(); }
      c.addEventListener('pointerdown', function (e) { down(e.clientX, e.clientY); c.setPointerCapture(e.pointerId); c.style.cursor = 'grabbing'; });
      c.addEventListener('pointermove', function (e) { move(e.clientX, e.clientY); });
      c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up);
      c.addEventListener('keydown', function (e) {
        var step = 0.12;
        if (e.key === 'ArrowLeft') theta += step; else if (e.key === 'ArrowRight') theta -= step;
        else if (e.key === 'ArrowUp') phi = Math.max(0.6, phi - step * 0.6); else if (e.key === 'ArrowDown') phi = Math.min(1.45, phi + step * 0.6);
        else return;
        e.preventDefault(); spinUntil = 0; vel = 0; place(); invalidate();
      });

      var ro = null;
      function resize() {
        var s = boxSize(el); if (s[0] === w && s[1] === h) return;
        w = s[0]; h = s[1]; renderer.setSize(w, h); cam.aspect = w / h; refit(); place(); invalidate();
      }
      if (root.ResizeObserver) { ro = new ResizeObserver(resize); ro.observe(el); if (el.parentElement) ro.observe(el.parentElement); }
      root.addEventListener('resize', resize);

      var envReady = model.environment(renderer, hdrUrl).then(function (env) { scene.environment = env; report(0.9); mark('env'); });
      model.ready.then(function () { mark('maps'); });
      return Promise.all([model.ready, envReady]).then(function () {
        var compile = renderer.compileAsync ? renderer.compileAsync(scene, cam) : Promise.resolve();
        return compile;
      }).then(function () {
        mark('compiled');
        el.appendChild(c); ready = true;
        renderer.render(scene, cam);           // first frame, synchronously, before we resolve
        mark('frame');
        bar.remove(); report(1);
        spinUntil = performance.now() + (opts.spin === undefined ? 3500 : opts.spin);
        if (spinUntil > performance.now()) invalidate();
        var later = root.requestIdleCallback || function (f) { setTimeout(f, 1200); };
        later(function () { model.prefetchTones(); });
        if (opts.onReady) opts.onReady();
        return {
          setTone: function (t) { return model.setTone(t).then(function () { invalidate(); }); },
          setState: function (s) { model.setState(s); if (model.relayoutShadows) model.relayoutShadows(); renderer.shadowMap.needsUpdate = true; refit(); place(); invalidate(); },
          setBackground: function (col) { bg = col; scene.background.set(col); renderer.setClearColor(new THREE.Color(col), 1); invalidate(); },
          invalidate: invalidate,
          dispose: function () {
            ready = false; if (raf) cancelAnimationFrame(raf);
            if (ro) ro.disconnect(); root.removeEventListener('resize', resize);
            model.dispose(); if (scene.environment) scene.environment.dispose(); renderer.dispose(); el.innerHTML = '';
          }
        };
      });
    }).catch(function (e) { bar.remove(); throw e; });
  }

  // Optional, for the page: a low-priority prefetch of three.js (650 KB from cdnjs) after load, so
  // a later tap on "rotate" starts from the HTTP cache. Not automatic — the page decides whether
  // every visitor should pay for it. Respects Save-Data.
  function prefetch() {
    if (root.THREE || (navigator.connection && navigator.connection.saveData)) return false;
    if (document.querySelector('link[href="' + THREE_URL + '"]')) return true;
    var l = document.createElement('link'); l.rel = 'prefetch'; l.as = 'script'; l.href = THREE_URL; l.crossOrigin = 'anonymous';
    document.head.appendChild(l);
    return true;
  }

  root.Goren = {
    build: build, mount: mount, frame: frame, fitDistance: fitDistance, parseRGBE: parseRGBE, prefetch: prefetch, warm: warm,
    VIEWS: VIEWS, TONES: TONES, BG: BG_DEFAULT,
    spec: { L_CLOSED: L_CLOSED, LEAF: LEAF, WID: WID, HGT: HGT, TOP_T: TOP_T, CHAMFER: [CH_V, CH_H] }
  };
})(window);
