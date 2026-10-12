/* Prism3D: the small 3D toolkit of the MEIDNet Prism landing page (hero scene and the live tour).
   A perspective camera, glossy atoms, glass faces and the cubic ABX3 perovskite cell, drawn on a 2D canvas with the
   painter's algorithm. No libraries. */
(function () {
  "use strict";
  var FONT = "'Plus Jakarta Sans', system-ui, 'Segoe UI', sans-serif";
  var MONO = "'IBM Plex Mono', ui-monospace, monospace";
  var MATH = "'STIX Two Text', 'Cambria Math', serif";
  var SITE = {A: "#8b5cf6", B: "#3b82f6", X: "#14b8a6"};          // atoms are coloured by site, labelled by element
  var RADIUS = {A: 0.31, B: 0.29, X: 0.23};

  function isDark() {      // the landing page's switch, then the documentation's (Material) colour scheme, then the system
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t === "dark";
    var md = document.body && document.body.getAttribute("data-md-color-scheme");
    if (md) return md === "slate";
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  function theme() {
    var cs = getComputedStyle(document.body || document.documentElement), v = function (n, d) { return (cs.getPropertyValue(n) || "").trim() || d; };
    var dark = isDark();
    return {dark: dark, bg: v("--bg", dark ? "#111417" : "#f6f7f5"), card: v("--card", dark ? "#1b1f24" : "#fff"),
            ink: v("--ink", dark ? "#fff" : "#0b0b0b"), muted: v("--muted", dark ? "#c3c2b7" : "#52514e"),
            faint: v("--faint", "#898781"), line: v("--line", dark ? "#2c2c2a" : "#e1e0d9"),
            good: dark ? "#4ade80" : "#16a34a", bad: dark ? "#f87171" : "#dc2626", warn: dark ? "#fbbf24" : "#b45309"};
  }

  /* colours */
  function rgbOf(hex) { var h = hex.replace("#", ""); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; }
  function mix(a, b, t) { return a.map(function (v, i) { return Math.round(v + (b[i] - v) * t); }); }
  function css(c, a) { return a === undefined ? "rgb(" + c.join(",") + ")" : "rgba(" + c.join(",") + "," + a + ")"; }

  /* timing */
  var T = {
    clamp: function (x, a, b) { a = a === undefined ? 0 : a; b = b === undefined ? 1 : b; return Math.max(a, Math.min(b, x)); },
    seg: function (t, a, b) { return Math.max(0, Math.min(1, (t - a) / (b - a))); },
    ease: function (x) { x = Math.max(0, Math.min(1, x)); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
    out: function (x) { x = Math.max(0, Math.min(1, x)); return 1 - Math.pow(1 - x, 3); },
    pop: function (x) { x = Math.max(0, Math.min(1, x)); var c = 1.70158; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); },
    lerp: function (a, b, x) { return a + (b - a) * x; },
    rng: function (seed) { return function () { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }; }
  };

  /* a perspective camera: screen centre (cx, cy), pixels per world unit at the origin, yaw about y, pitch about x */
  function camera(o) {
    var cy = Math.cos(o.yaw || 0), sy = Math.sin(o.yaw || 0), cp = Math.cos(o.pitch || 0), sp = Math.sin(o.pitch || 0);
    var D = o.dist || 9, F = o.scale * D;
    function view(p) { var x1 = p[0] * cy + p[2] * sy, z1 = -p[0] * sy + p[2] * cy; return [x1, p[1] * cp - z1 * sp, p[1] * sp + z1 * cp]; }
    return {
      view: view,
      proj: function (p) { var v = view(p), k = F / (D - v[2]); return [o.cx + v[0] * k, o.cy - v[1] * k, v[2], k]; }
    };
  }

  /* drawing */
  function sphere(ctx, cam, p, r, hex, o) {
    o = o || {};
    var q = cam.proj(p), R = r * q[3], c = rgbOf(hex), dark = o.dark;
    if (R < 0.4) return q;
    ctx.save();
    if (o.alpha !== undefined) ctx.globalAlpha *= o.alpha;
    var g = ctx.createRadialGradient(q[0] - R * 0.38, q[1] - R * 0.42, R * 0.06, q[0], q[1], R);
    g.addColorStop(0, "rgba(255,255,255,.96)"); g.addColorStop(0.24, css(mix(c, [255, 255, 255], 0.45)));
    g.addColorStop(0.72, css(c)); g.addColorStop(1, css(mix(c, [0, 0, 0], 0.5)));
    ctx.beginPath(); ctx.arc(q[0], q[1], R, 0, 2 * Math.PI); ctx.fillStyle = g; ctx.fill();
    ctx.lineWidth = Math.max(0.5, R * 0.04); ctx.strokeStyle = dark ? "rgba(0,0,0,.35)" : "rgba(15,23,42,.14)"; ctx.stroke();
    if (o.label && R > 6.5) {
      ctx.font = "800 " + Math.min(22, R * 0.82).toFixed(1) + "px " + FONT;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.lineWidth = Math.max(1.5, R * 0.12); ctx.strokeStyle = "rgba(15,23,42,.45)"; ctx.strokeText(o.label, q[0], q[1] + 0.5);
      ctx.fillStyle = "#fff"; ctx.fillText(o.label, q[0], q[1] + 0.5);
    }
    ctx.restore();
    return q;
  }
  var LIGHT = [-0.45, 0.7, 0.55];
  function glass(ctx, cam, tri, o) {
    o = o || {};
    var q = tri.map(cam.proj), v = tri.map(cam.view);
    var e1 = [v[1][0] - v[0][0], v[1][1] - v[0][1], v[1][2] - v[0][2]], e2 = [v[2][0] - v[0][0], v[2][1] - v[0][1], v[2][2] - v[0][2]];
    var n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]], l = Math.hypot(n[0], n[1], n[2]) || 1;
    var lit = Math.abs((n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]) / l), a = o.alpha === undefined ? 1 : o.alpha, dark = o.dark;
    var tint = rgbOf(o.tint || "#81a1fa");
    ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); ctx.lineTo(q[1][0], q[1][1]); ctx.lineTo(q[2][0], q[2][1]); ctx.closePath();
    var g = ctx.createLinearGradient(q[0][0], q[0][1], q[2][0], q[2][1]);
    g.addColorStop(0, dark ? css(mix(tint, [255, 255, 255], 0.35), (0.1 + 0.22 * lit) * a) : css([255, 255, 255], (0.25 + 0.45 * lit) * a));
    g.addColorStop(1, css(tint, (dark ? 0.08 + 0.16 * lit : 0.12 + 0.24 * lit) * a));
    ctx.fillStyle = g; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = dark ? "rgba(191,219,254," + 0.5 * a + ")" : "rgba(255,255,255," + 0.95 * a + ")"; ctx.stroke();
    ctx.lineWidth = 0.6; ctx.strokeStyle = dark ? "rgba(96,165,250," + 0.35 * a + ")" : "rgba(99,102,241," + 0.25 * a + ")"; ctx.stroke();
  }
  function line3(ctx, cam, a, b, color, width, dash) {
    var p = cam.proj(a), q = cam.proj(b);
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = width || 1; if (dash) ctx.setLineDash(dash);
    ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); ctx.restore();
  }

  /* the cubic ABX3 cell, half edge 1: A on the corners, B in the centre, X on the face centres.
     el = {A: 'Na', B: 'Ni', X: 'I'}; X may be a list of three (the anions on the x, y and z faces). */
  function perovskite(el) {
    var X = Array.isArray(el.X) ? el.X : [el.X, el.X, el.X], atoms = [], edges = [], faces = [];
    [-1, 1].forEach(function (x) { [-1, 1].forEach(function (y) { [-1, 1].forEach(function (z) { atoms.push({p: [x, y, z], site: "A", el: el.A}); }); }); });
    atoms.push({p: [0, 0, 0], site: "B", el: el.B});
    var xs = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
    xs.forEach(function (p, i) { atoms.push({p: p, site: "X", el: X[Math.floor(i / 2)]}); });
    var corners = atoms.slice(0, 8);
    corners.forEach(function (a, i) { corners.forEach(function (b, j) {
      if (j > i && Math.abs(a.p[0] - b.p[0]) + Math.abs(a.p[1] - b.p[1]) + Math.abs(a.p[2] - b.p[2]) === 2) edges.push([a.p, b.p]);
    }); });
    [[0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]].forEach(function (f) {
      faces.push([xs[f[0]], xs[f[1]], xs[f[2]]]);
    });
    return {atoms: atoms, edges: edges, faces: faces};
  }

  /* a crystal at `at`, size `s` (world units per half edge), turned by `spin` about its own vertical axis.
     o.explode (0..1) scatters the atoms (assembly animations), o.glass sets the octahedron's opacity, o.labels names atoms. */
  function crystal(ctx, cam, cell, o) {
    o = o || {};
    var s = o.s || 1, at = o.at || [0, 0, 0], cs = Math.cos(o.spin || 0), sn = Math.sin(o.spin || 0), ex = o.explode || 0;
    var R = T.rng(o.seed || 3);
    function place(p, i) {
      var x = p[0] * cs + p[2] * sn, z = -p[0] * sn + p[2] * cs, y = p[1];
      if (ex) { var j = [R() - 0.5, R() - 0.5, R() - 0.5]; x = x * (1 + 1.6 * ex) + j[0] * 3 * ex; y = y * (1 + 1.6 * ex) + j[1] * 3 * ex; z = z * (1 + 1.6 * ex) + j[2] * 3 * ex; }
      return [at[0] + x * s, at[1] + y * s, at[2] + z * s];
    }
    var items = [], ga = o.glass === undefined ? 1 : o.glass, ea = o.edges === undefined ? 1 : o.edges, placed = {};
    var key = function (p) { return p.join(","); }, at_ = function (p) { return placed[key(p)]; };   // faces and edges follow their atoms
    cell.atoms.forEach(function (a, i) {
      var p = place(a.p, i);
      placed[key(a.p)] = p;
      items.push({z: cam.proj(p)[2], atom: a, p: p});
    });
    if (ga > 0.01) cell.faces.forEach(function (f) {
      var tri = f.map(at_);
      items.push({z: (cam.proj(tri[0])[2] + cam.proj(tri[1])[2] + cam.proj(tri[2])[2]) / 3, tri: tri});
    });
    if (ea > 0.01) cell.edges.forEach(function (e) {
      var a = at_(e[0]), b = at_(e[1]);
      items.push({z: (cam.proj(a)[2] + cam.proj(b)[2]) / 2 - 0.3 * s, edge: [a, b]});
    });
    items.sort(function (m, n) { return m.z - n.z; });
    var alpha = o.alpha === undefined ? 1 : o.alpha;
    ctx.save(); ctx.globalAlpha *= alpha;
    items.forEach(function (it) {
      if (it.atom) sphere(ctx, cam, it.p, RADIUS[it.atom.site] * s * (o.atomScale || 1), (o.colors && o.colors[it.atom.site]) || SITE[it.atom.site],
                          {dark: o.dark, label: o.labels ? it.atom.el : null});
      else if (it.tri) glass(ctx, cam, it.tri, {dark: o.dark, alpha: ga});
      else line3(ctx, cam, it.edge[0], it.edge[1], o.dark ? "rgba(148,163,184," + 0.5 * ea + ")" : "rgba(100,116,139," + 0.5 * ea + ")", 1.1);
    });
    ctx.restore();
  }

  /* flat pieces */
  function rrect(ctx, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function text(ctx, str, x, y, o) {
    o = o || {};
    ctx.save();
    if (o.alpha !== undefined) ctx.globalAlpha *= T.clamp(o.alpha);
    ctx.font = (o.italic ? "italic " : "") + (o.weight || 600) + " " + (o.size || 20) + "px " + (o.family || FONT);
    ctx.textAlign = o.align || "left"; ctx.textBaseline = o.baseline || "alphabetic";
    ctx.fillStyle = o.color || "#000"; ctx.fillText(str, x, y);
    ctx.restore();
  }
  function arrow(ctx, x1, y1, x2, y2, p, color, w) {
    if (p <= 0) return;
    var x = T.lerp(x1, x2, p), y = T.lerp(y1, y2, p), a = Math.atan2(y2 - y1, x2 - x1), k = 4 + (w || 3) * 2.6;
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = w || 3; ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x, y);
    ctx.moveTo(x - k * Math.cos(a - 0.45), y - k * Math.sin(a - 0.45)); ctx.lineTo(x, y); ctx.lineTo(x - k * Math.cos(a + 0.45), y - k * Math.sin(a + 0.45));
    ctx.stroke(); ctx.restore();
  }
  function check(ctx, x, y, ok, p, th) {
    if (p <= 0) return;
    var s = T.pop(p);
    ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
    ctx.beginPath(); ctx.arc(0, 0, 13, 0, 2 * Math.PI); ctx.fillStyle = ok ? th.good : th.bad; ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 3.2; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.beginPath();
    if (ok) { ctx.moveTo(-5.5, 0); ctx.lineTo(-1.5, 4.5); ctx.lineTo(6, -5); } else { ctx.moveTo(-5, -5); ctx.lineTo(5, 5); ctx.moveTo(5, -5); ctx.lineTo(-5, 5); }
    ctx.stroke(); ctx.restore();
  }

  window.Prism3D = {FONT: FONT, MONO: MONO, MATH: MATH, SITE: SITE, T: T, isDark: isDark, theme: theme, rgbOf: rgbOf, mix: mix, css: css,
                    camera: camera, sphere: sphere, glass: glass, line3: line3, perovskite: perovskite, crystal: crystal,
                    rrect: rrect, text: text, arrow: arrow, check: check};
})();
