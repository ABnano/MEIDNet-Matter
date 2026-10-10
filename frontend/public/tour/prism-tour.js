/* The MEIDNet tour: the story of the method (data → model → family → rules → targets → search → candidates) as a
   live 3D animation. This copy plays on MEIDNet Matter's home page (the same scenes as MEIDNet Prism's landing). Two parts: the scenes (window.PrismScenes, also used by the documentation to show one block)
   and the player of the landing page (#tour3d). Every frame is a pure function of time, so playing, seeking, the
   chapter buttons and reduced motion all show the same pictures. The numbers are those of the Studio with its
   defaults: the published Perov-5 model, the cubic halide perovskite family, targets 2 eV and −0.1 eV/atom. */
(function () {
  "use strict";
  var P = window.Prism3D;
  if (!P) return;
  var T = P.T, ctx = null;               // the canvas being drawn: set by render() for each frame
  var VW = 960, VH = 540;

  var BLOCKS = [{id: "data", name: "Data", c: "#2a78d6"}, {id: "model", name: "Model", c: "#eb6834"}, {id: "family", name: "Family", c: "#1baf7a"},
                {id: "rules", name: "Rules", c: "#eda100"}, {id: "targets", name: "Targets", c: "#e87ba4"}, {id: "search", name: "Search", c: "#008300"},
                {id: "candidates", name: "Candidates", c: "#4a3aa7"}];
  var COL = {}; BLOCKS.forEach(function (b) { COL[b.id] = b.c; });
  var th = P.theme();
  function tc(id) {                                   // a block colour readable as text on this theme
    var c = P.rgbOf(COL[id] || COL.family);
    return P.css(th.dark ? P.mix(c, [255, 255, 255], 0.3) : P.mix(c, [0, 0, 0], id === "rules" ? 0.3 : id === "targets" ? 0.2 : 0.05));
  }
  var sub = function (f) { return String(f).replace(/\d/g, function (d) { return "₀₁₂₃₄₅₆₇₈₉"[+d]; }); };
  var fmt = function (v) { return (Math.round(v * 100) / 100).toString().replace("-", "−"); };

  /* ── the facts (read from the Studio with its defaults) ── */
  var ROWS = [{f: "SrTiO3", e: {A: "Sr", B: "Ti", X: "O"}, v: [-0.24, 4.3]}, {f: "KNbO3", e: {A: "K", B: "Nb", X: "O"}, v: [-0.42, 4.1]},
              {f: "LaTiNO2", e: {A: "La", B: "Ti", X: ["N", "O", "O"]}, v: [0.06, 2.5]}, {f: "SrZrNOF", e: {A: "Sr", B: "Zr", X: ["N", "O", "F"]}, v: [0.54, 3.2]}];
  var GROUPS = [{g: "A", sample: ["Ba", "Sr", "Ca", "Na", "K", "Rb", "Cs", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"]},
                {g: "B", sample: ["Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Sn", "Pb", "Sc", "Cr", "V"]}, {g: "X", sample: ["F", "Cl", "Br", "I"]}];
  var RULES = [{name: "charges balance", lost: 796}, {name: "tolerance factor", lost: 60}, {name: "octahedral factor", lost: 41}];
  // compositions on the conveyor: the rule that stops each one (gate index), or -1 when it passes every rule
  var FLOW = [{f: "BaMnF3", e: {A: "Ba", B: "Mn", X: "F"}, gate: 0}, {f: "NaFeI3", e: {A: "Na", B: "Fe", X: "I"}, gate: -1},
              {f: "NaPbF3", e: {A: "Na", B: "Pb", X: "F"}, gate: 1}, {f: "NaMnF3", e: {A: "Na", B: "Mn", X: "F"}, gate: 2},
              {f: "KFeI3", e: {A: "K", B: "Fe", X: "I"}, gate: -1}, {f: "BaMnCl3", e: {A: "Ba", B: "Mn", X: "Cl"}, gate: 0},
              {f: "KCoI3", e: {A: "K", B: "Co", X: "I"}, gate: -1}, {f: "BaFeF3", e: {A: "Ba", B: "Fe", X: "F"}, gate: 0}];
  // the 27 compositions that pass every rule: predicted formation enthalpy (eV/atom) and direct band gap (eV)
  var ALIVE = [["CsMnI3", 1.9, 1.57], ["CsPbI3", 2.05, 3.19], ["CsZnI3", 2.07, 2.58], ["KCoI3", 1.29, 1.82], ["KCuI3", 1.85, 1.44],
               ["KFeI3", 0.96, 1.74], ["KMnI3", 1.71, 0.59], ["KNiI3", 1.86, 1.04], ["KPbI3", 2.01, 2.02], ["KSnI3", 1.72, 1.87],
               ["KZnI3", 2.09, 1.87], ["NaCoBr3", 0.96, 2.82], ["NaCoI3", 0.95, 2.69], ["NaCuI3", 1.45, 3.49], ["NaFeI3", 0.95, 2.08],
               ["NaMnI3", 1.84, 1.66], ["NaNiBr3", 1.31, 3.04], ["NaNiI3", 1.18, 2.92], ["NaSnI3", 1.71, 2.98], ["NaZnI3", 1.98, 1.51],
               ["RbCoI3", 1.71, 1.18], ["RbCuI3", 2.09, 2.07], ["RbFeI3", 1.46, 1.49], ["RbMnI3", 1.74, 2.41], ["RbPbI3", 2.01, 2.32],
               ["RbSnI3", 1.91, 1.83], ["RbZnI3", 2.02, 2.81]];
  var RANKED = ["NaFeI3", "KFeI3", "KCoI3"];
  // a search with the Studio defaults (seed 937): the three crystals it returned, with their predicted properties
  var FOUND = [{f: "NaNiI3", e: {A: "Na", B: "Ni", X: "I"}, gap: 1.97, dh: -0.05, flag: false},
               {f: "NaSnI3", e: {A: "Na", B: "Sn", X: "I"}, gap: 1.98, dh: -1.37, flag: true},
               {f: "NaMnI3", e: {A: "Na", B: "Mn", X: "I"}, gap: 2.37, dh: 14.3, flag: true}];
  var STOPPED = [{e: {A: "Ba", B: "Mn", X: "F"}}, {e: {A: "Na", B: "Pb", X: "F"}}, {e: {A: "Na", B: "Mn", X: "F"}}, {e: {A: "Ba", B: "Mn", X: "Cl"}}, {e: {A: "Ba", B: "Fe", X: "F"}}];
  var cells = {};
  function cell(e) { var k = JSON.stringify(e); return cells[k] || (cells[k] = P.perovskite(e)); }

  /* ── flat helpers in the 960 × 540 stage ── */
  function card(x, y, w, h, o) {
    o = o || {};
    ctx.save(); if (o.alpha !== undefined) ctx.globalAlpha *= T.clamp(o.alpha);
    P.rrect(ctx, x, y, w, h, o.r === undefined ? 14 : o.r);
    ctx.fillStyle = o.fill || (th.dark ? "rgba(27,31,36,.86)" : "rgba(255,255,255,.88)"); ctx.fill();
    if (o.stroke !== null) { ctx.lineWidth = o.sw || 1.5; ctx.strokeStyle = o.stroke || th.line; ctx.stroke(); }
    ctx.restore();
  }
  function tint(id, a) { return P.css(P.rgbOf(COL[id]), a); }
  function label(str, x, y, o) { o = o || {}; P.text(ctx, str, x, y, {size: o.size || 18, weight: o.weight || 600, color: o.color || th.ink, align: o.align, alpha: o.alpha, family: o.family, italic: o.italic, baseline: o.baseline}); }
  function cam(cx, cy, scale, yaw, pitch) { return P.camera({cx: cx, cy: cy, scale: scale, yaw: yaw, pitch: pitch === undefined ? -0.38 : pitch}); }
  function chip(x, y, str, id, on, o) {
    o = o || {}; var w = o.w || Math.max(46, 12 * str.length + 26), h = o.h || 32;
    card(x - w / 2, y - h / 2, w, h, {r: h / 2, fill: on ? COL[id] : (th.dark ? "#1b1f24" : "#fff"), stroke: COL[id], sw: 2, alpha: o.alpha});
    label(str, x, y + 6, {align: "center", size: o.size || 17, weight: 700, color: on ? "#fff" : tc(id), alpha: o.alpha});
  }
  function star(x, y, r, color, a) {
    ctx.save(); ctx.globalAlpha *= a === undefined ? 1 : a; ctx.beginPath();
    for (var i = 0; i < 10; i++) { var rr = i % 2 ? r * 0.45 : r, an = -Math.PI / 2 + i * Math.PI / 5; ctx.lineTo(x + rr * Math.cos(an), y + rr * Math.sin(an)); }
    ctx.closePath(); ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 12; ctx.fill(); ctx.restore();
  }
  function dot(cm, p, r, color, a) {
    var q = cm.proj(p); ctx.save(); ctx.globalAlpha *= a === undefined ? 1 : a;
    ctx.beginPath(); ctx.arc(q[0], q[1], Math.max(1, r * q[3]), 0, 2 * Math.PI); ctx.fillStyle = color; ctx.fill(); ctx.restore(); return q;
  }
  function cloud(seed, n, radius) {
    var R = T.rng(seed), pts = [];
    while (pts.length < n) { var p = [R() * 2 - 1, R() * 2 - 1, R() * 2 - 1]; if (p[0] * p[0] + p[1] * p[1] + p[2] * p[2] <= 1) pts.push(p.map(function (v) { return v * radius; })); }
    return pts;
  }
  var DATA_CLOUD = cloud(21, 320, 1.25), MAP_CLOUD = cloud(5, 170, 1.7);

  /* ── scenes ── */
  var SCENES = [
    {block: "intro", title: "Start", ms: 4800,
     cap: "Tell MEIDNet the properties you want and it suggests crystals that should have them. Here is how, block by block.",
     draw: function (t) {
       var a = T.out(T.seg(t, 0, 0.22));
       ctx.save(); ctx.translate(-50 * (1 - a), 0);
       card(64, 168, 316, 196, {fill: th.dark ? "rgba(232,123,164,.12)" : "rgba(253,237,243,.92)", stroke: COL.targets, sw: 2.5, r: 20, alpha: a});
       label("You want", 92, 216, {size: 24, color: th.muted, alpha: a});
       label("Direct band gap", 92, 266, {size: 31, weight: 800, color: tc("targets"), alpha: a});
       label("≈ 2 eV", 92, 324, {size: 42, weight: 800, alpha: a});
       ctx.restore();
       label("MEIDNet", 500, 238, {size: 30, weight: 800, color: tc("family"), align: "center", alpha: T.seg(t, 0.22, 0.4)});
       P.arrow(ctx, 402, 266, 600, 266, T.ease(T.seg(t, 0.22, 0.46)), COL.family, 4.5);
       var c = cam(770, 268, 80, -0.7 + 1.2 * t);
       P.crystal(ctx, c, cell(FOUND[0].e), {s: 1, explode: 1 - T.ease(T.seg(t, 0.32, 0.72)), glass: T.seg(t, 0.62, 0.82), edges: T.seg(t, 0.62, 0.82),
                                            labels: t > 0.6, dark: th.dark, alpha: T.seg(t, 0.28, 0.4)});
       label("NaNiI₃", 770, 420, {size: 20, weight: 700, color: th.muted, align: "center", alpha: T.seg(t, 0.75, 0.9)});
       label("inverse design: from properties to crystals", 480, 492, {size: 25, color: th.muted, align: "center", alpha: T.seg(t, 0.6, 0.82)});
     }},

    {block: "data", title: "Data", ms: 7000,
     cap: "MEIDNet learns from known materials: a table in which each row is a crystal structure with its properties. Here, 11,356 materials.",
     draw: function (t) {
       card(32, 60, 600, 420);
       var hd = {size: 15, weight: 700, color: th.muted};
       label("structure", 56, 98, hd); label("formula", 168, 98, hd); label("formation enthalpy", 330, 90, hd); label("eV/atom", 330, 110, {size: 13, color: th.faint});
       label("band gap", 510, 90, hd); label("eV", 510, 110, {size: 13, color: th.faint});
       ctx.fillStyle = th.line; ctx.fillRect(48, 124, 568, 1.5);
       ROWS.forEach(function (r, k) {
         var p = T.out(T.seg(t, 0.05 + k * 0.1, 0.27 + k * 0.1)), y = 130 + k * 80;
         ctx.save(); ctx.translate(70 * (1 - p), 0); ctx.globalAlpha *= p;
         P.crystal(ctx, cam(96, y + 40, 22, -0.6 + 1.1 * t + k), cell(r.e), {dark: th.dark});
         label(sub(r.f), 168, y + 48, {size: 25, weight: 700});
         label(fmt(r.v[0]), 330, y + 48, {size: 24, family: P.MATH}); label(fmt(r.v[1]), 510, y + 48, {size: 24, family: P.MATH});
         ctx.fillStyle = th.line; ctx.fillRect(48, y + 79, 568, 1);
         ctx.restore();
       });
       label("four real rows of the Perov-5 training set", 56, 466, {size: 14, color: th.faint, alpha: T.seg(t, 0.4, 0.6)});
       // the whole table: one point per material
       var c = cam(800, 220, 82, -0.5 + 0.9 * t, -0.3), n = Math.round(DATA_CLOUD.length * T.ease(T.seg(t, 0.38, 0.85)));
       var pts = DATA_CLOUD.slice(0, n).map(function (p) { return [c.proj(p), p]; }).sort(function (a, b) { return a[0][2] - b[0][2]; });
       pts.forEach(function (q) { var d = (q[0][2] + 1.3) / 2.6; dot(c, q[1], 0.045, P.css(P.mix(P.rgbOf(COL.data), [255, 255, 255], 0.5 * (1 - d))), 0.55 + 0.45 * d); });
       label((Math.round(11356 * T.ease(T.seg(t, 0.4, 0.85)))).toLocaleString("en-US"), 800, 420, {size: 52, weight: 800, color: tc("data"), align: "center", alpha: T.seg(t, 0.38, 0.45)});
       label("materials · 2 properties each", 800, 456, {size: 20, weight: 600, align: "center", color: th.muted, alpha: T.seg(t, 0.7, 0.88)});
     }},

    {block: "model", title: "Model", ms: 7800,
     cap: "Two encoders place each crystal and its properties on one shared map. Training pulls the two points of the same material together.",
     draw: function (t) {
       var col = COL.model, a1 = T.ease(T.seg(t, 0.05, 0.2)), a2 = T.ease(T.seg(t, 0.18, 0.34));
       P.crystal(ctx, cam(96, 150, 36, -0.5 + 0.8 * t), cell(ROWS[0].e), {dark: th.dark});
       label("crystal", 96, 238, {size: 16, weight: 700, color: th.muted, align: "center"});
       card(40, 296, 112, 70, {r: 12});
       label("4.3 eV", 96, 326, {size: 21, weight: 800, align: "center"}); label("−0.24 eV/atom", 96, 350, {size: 13, color: th.muted, align: "center"});
       label("properties", 96, 392, {size: 16, weight: 700, color: th.muted, align: "center"});
       P.arrow(ctx, 158, 150, 206, 150, a1, col, 3.5); P.arrow(ctx, 158, 331, 206, 331, a1, col, 3.5);
       [[115, "crystal encoder", "graph network"], [296, "property encoder", "dense network"]].forEach(function (b) {
         card(210, b[0], 180, 70, {fill: th.dark ? "rgba(235,104,52,.14)" : "rgba(253,236,228,.95)", stroke: col, sw: 2.5});
         label(b[1], 300, b[0] + 33, {size: 18, weight: 800, color: tc("model"), align: "center"});
         label(b[2], 300, b[0] + 55, {size: 13, color: th.muted, align: "center", family: P.MONO});
       });
       P.arrow(ctx, 394, 150, 470, 205, a2, col, 3.5); P.arrow(ctx, 394, 331, 470, 290, a2, col, 3.5);
       // the shared map as a 3D space
       var c = cam(700, 262, 108, -0.65 + 0.55 * t, -0.32), box = 1.15, show = T.seg(t, 0.28, 0.4), pull = T.ease(T.seg(t, 0.42, 0.86));
       ctx.save(); ctx.globalAlpha *= show;
       [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (u) {
         P.line3(ctx, c, [-box, u[0] * box, u[1] * box], [box, u[0] * box, u[1] * box], th.dark ? "rgba(148,163,184,.35)" : "rgba(100,116,139,.35)", 1);
         P.line3(ctx, c, [u[0] * box, -box, u[1] * box], [u[0] * box, box, u[1] * box], th.dark ? "rgba(148,163,184,.35)" : "rgba(100,116,139,.35)", 1);
         P.line3(ctx, c, [u[0] * box, u[1] * box, -box], [u[0] * box, u[1] * box, box], th.dark ? "rgba(148,163,184,.35)" : "rgba(100,116,139,.35)", 1);
       });
       var R = T.rng(7), pairs = [];
       for (var k = 0; k < 8; k++) {
         var m = [R() * 1.6 - 0.8, R() * 1.6 - 0.8, R() * 1.6 - 0.8], d = [R() - 0.5, R() - 0.5, R() - 0.5], s = 0.55 * (1 - pull);
         pairs.push({a: [m[0] + d[0] * s, m[1] + d[1] * s, m[2] + d[2] * s], b: [m[0] - d[0] * s, m[1] - d[1] * s, m[2] - d[2] * s]});
       }
       pairs.forEach(function (pr) { P.line3(ctx, c, pr.a, pr.b, th.dark ? "rgba(203,213,225,.55)" : "rgba(100,116,139,.6)", 1.4, [4, 4]); });
       pairs.forEach(function (pr) {
         P.sphere(ctx, c, pr.a, 0.07, COL.data, {dark: th.dark});
         var q = c.proj(pr.b); ctx.beginPath(); ctx.arc(q[0], q[1], 0.08 * q[3], 0, 2 * Math.PI); ctx.lineWidth = 3; ctx.strokeStyle = COL.targets; ctx.stroke();
       });
       ctx.restore();
       label("shared map (latent space)", 520, 84, {size: 17, weight: 800, color: th.muted, alpha: show});
       label("crystal", 538, 474, {size: 15, color: th.muted, alpha: show}); dotFlat(526, 469, 6, COL.data, show);
       ringFlat(612, 469, 7, COL.targets, show); label("its properties", 626, 474, {size: 15, color: th.muted, alpha: show});
       label("pulled together", 930, 474, {size: 15, weight: 800, color: tc("model"), align: "right", alpha: T.seg(t, 0.8, 0.92)});
     }},

    {block: "family", title: "Family", ms: 7000,
     cap: "You choose a crystal type, here the cubic ABX₃ halide perovskite, and the elements allowed on each site: 924 compositions.",
     draw: function (t) {
       var step = Math.min(5, Math.floor(t * 7)), combo = {};
       GROUPS.forEach(function (g, j) { var vis = g.sample.slice(0, 6); combo[g.g] = vis[(step * (j + 2) + j) % vis.length]; });
       P.crystal(ctx, cam(232, 262, 96, -0.9 + 1.25 * t), cell(combo), {dark: th.dark, labels: true});
       label("cubic ABX₃ perovskite", 232, 478, {size: 21, weight: 800, color: tc("family"), align: "center"});
       label(sub(combo.A + combo.B + combo.X + "3"), 232, 506, {size: 17, weight: 600, color: th.muted, align: "center"});
       var x0 = 480, W = 450;
       GROUPS.forEach(function (g, j) {
         var x = x0 + W / 3 * (j + 0.5), a = T.out(T.seg(t, 0.05 + j * 0.08, 0.25 + j * 0.08));
         chip(x, 84, g.g + " site", "family", true, {w: 104, h: 34, size: 18, alpha: a});
         g.sample.slice(0, 6).forEach(function (el, m) { chip(x, 132 + m * 40, el, "family", el === combo[g.g], {w: 72, alpha: a}); });
         if (g.sample.length > 6) label("+" + (g.sample.length - 6) + " more", x, 132 + 6 * 40 + 2, {size: 15, color: th.muted, align: "center", alpha: a});
       });
       label("21 × 11 × 4 = " + Math.round(924 * T.ease(T.seg(t, 0.42, 0.85))).toLocaleString("en-US") + " compositions", x0 + W / 2, 470,
             {size: 26, weight: 800, color: tc("family"), align: "center", alpha: T.seg(t, 0.4, 0.48)});
     }},

    {block: "rules", title: "Rules", ms: 8000,
     cap: "Simple chemistry rules remove impossible combinations: charges must balance and ions must fit. 27 of 924 pass every rule.",
     draw: function (t) {
       var c = cam(470, 300, 66, -0.42, -0.42), GX = [-2.6, -0.6, 1.4], EXIT = 3.9, START = -6.2;
       label(Math.round(T.lerp(924, 27, T.ease(T.seg(t, 0.1, 0.92)))).toLocaleString("en-US"), 40, 96, {size: 40, weight: 800});
       label("compositions left", 40, 122, {size: 15, color: th.muted});
       // the belt
       var shade = th.dark ? "rgba(148,163,184,.35)" : "rgba(100,116,139,.38)";
       P.line3(ctx, c, [START, -0.75, -1.05], [EXIT + 0.4, -0.75, -1.05], shade, 1.5); P.line3(ctx, c, [START, -0.75, 1.05], [EXIT + 0.4, -0.75, 1.05], shade, 1.5);
       for (var s = 0; s < 22; s++) { var x = START + ((s * 0.5 + t * 6) % 11); if (x < EXIT + 0.4) P.line3(ctx, c, [x, -0.75, -1.05], [x, -0.75, 1.05], shade, 1); }
       // the gates: glass panes
       GX.forEach(function (gx, j) {
         var a = [gx, -0.75, -1.2], b = [gx, -0.75, 1.2], d = [gx, 1.45, 1.2], e = [gx, 1.45, -1.2];
         var q = [a, b, d, e].map(c.proj);
         ctx.save(); ctx.beginPath(); q.forEach(function (p, i) { i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }); ctx.closePath();
         ctx.fillStyle = tint("rules", th.dark ? 0.16 : 0.2); ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = tint("rules", 0.85); ctx.stroke(); ctx.restore();
         var top = c.proj([gx, 1.6, 0]), words = RULES[j].name.split(" ");
         label(words[0], top[0], top[1] - 24, {size: 16, weight: 800, color: tc("rules"), align: "center"});
         label(words.slice(1).join(" "), top[0], top[1] - 6, {size: 16, weight: 800, color: tc("rules"), align: "center"});
         var bot = c.proj([gx, -0.75, 1.35]);
         label("−" + RULES[j].lost, bot[0], bot[1] + 26, {size: 19, weight: 800, color: th.bad, align: "center", alpha: T.seg(t, 0.25 + j * 0.13, 0.35 + j * 0.13)});
       });
       var ex = c.proj([EXIT + 0.4, 1.6, 0]);
       label("pass every", ex[0] + 26, ex[1] - 24, {size: 16, weight: 800, color: th.good, align: "center"});
       label("rule", ex[0] + 26, ex[1] - 6, {size: 16, weight: 800, color: th.good, align: "center"});
       var passed = 0, span = 0.36;
       FLOW.forEach(function (it, k) {
         var st = 0.03 + k * 0.085, stop = it.gate >= 0 ? GX[it.gate] - 0.55 : EXIT, tStop = st + span * (stop - START) / (EXIT - START);
         if (t < st) return;
         var lane = k % 2 ? 0.6 : -0.6, x = t < tStop ? T.lerp(START, EXIT, (t - st) / span) : stop, y = -0.25, alpha = 1, fall = 0;
         if (t >= tStop && it.gate >= 0) { fall = T.ease(T.seg(t, tStop + 0.04, tStop + 0.13)); alpha = 1 - fall; y -= 1.4 * fall; }
         if (t >= tStop && it.gate < 0) { var slot = passed++, f = T.ease(T.seg(t, tStop, tStop + 0.08));
           var to = [870, 228 + slot * 70], from = c.proj([EXIT, y, lane]);
           var cx2 = T.lerp(from[0], to[0], f), cy2 = T.lerp(from[1], to[1], f);
           P.crystal(ctx, cam(cx2, cy2, 15, t * 3 + k, -0.35), cell(it.e), {dark: th.dark, glass: 0.8});
           label(sub(it.f), cx2 + 24, cy2 + 6, {size: 16, weight: 800, alpha: f});
           P.check(ctx, cx2 - 22, cy2 - 20, true, T.seg(t, tStop, tStop + 0.04), th);
           return; }
         if (alpha <= 0.02) return;
         P.crystal(ctx, c, cell(it.e), {at: [x, y, lane], s: 0.32, spin: t * 3 + k, dark: th.dark, alpha: alpha, glass: 0.8});
         var q = c.proj([x, y + 0.55, lane]);
         label(sub(it.f), q[0], q[1] - 4, {size: 14, weight: 800, align: "center", alpha: alpha});
         if (t >= tStop && it.gate >= 0) P.check(ctx, q[0] + 30, q[1] + 8, false, T.seg(t, tStop, tStop + 0.04), th);
       });
     }},

    {block: "targets", title: "Targets", ms: 7400,
     cap: "You say what you want, for example a direct band gap of 2 eV. The model predicts every composition and ranks the closest.",
     draw: function (t) {
       var c = cam(330, 282, 76, -0.32 + 0.18 * Math.sin(t * 2.2), -0.3);
       var xl = -0.3, xh = 2.4, yl = 0.3, yh = 3.8, X = function (v) { return -2.4 + (v - xl) / (xh - xl) * 4.8; }, Y = function (v) { return -1.7 + (v - yl) / (yh - yl) * 3.4; };
       var ax = th.dark ? "rgba(203,213,225,.6)" : "rgba(71,85,105,.6)", gr = th.dark ? "rgba(148,163,184,.14)" : "rgba(100,116,139,.15)";
       for (var g = 0; g <= 4; g++) { P.line3(ctx, c, [-2.4 + g * 1.2, -1.7, 0], [-2.4 + g * 1.2, 1.7, 0], gr, 1); P.line3(ctx, c, [-2.4, -1.7 + g * 0.85, 0], [2.4, -1.7 + g * 0.85, 0], gr, 1); }
       P.line3(ctx, c, [-2.4, -1.7, 0], [2.6, -1.7, 0], ax, 2); P.line3(ctx, c, [-2.4, -1.7, 0], [-2.4, 1.9, 0], ax, 2);
       var xa = c.proj([0, -2.15, 0]), ya = c.proj([-2.85, 0, 0]);
       label("predicted formation enthalpy (eV/atom)", xa[0], xa[1] + 10, {size: 14, color: th.muted, align: "center"});
       ctx.save(); ctx.translate(ya[0] - 6, ya[1]); ctx.rotate(-Math.PI / 2); label("predicted direct band gap (eV)", 0, 0, {size: 14, color: th.muted, align: "center"}); ctx.restore();
       var tg = [X(-0.1), Y(2.0), 0], tq = c.proj(tg), ta = T.seg(t, 0.16, 0.26);
       ctx.save(); ctx.globalAlpha *= ta; ctx.setLineDash([6, 5]); ctx.strokeStyle = COL.targets; ctx.lineWidth = 2;
       var v1 = c.proj([tg[0], -1.7, 0]), v2 = c.proj([tg[0], 1.7, 0]), h1 = c.proj([-2.4, tg[1], 0]), h2 = c.proj([2.4, tg[1], 0]);
       ctx.beginPath(); ctx.moveTo(v1[0], v1[1]); ctx.lineTo(v2[0], v2[1]); ctx.moveTo(h1[0], h1[1]); ctx.lineTo(h2[0], h2[1]); ctx.stroke(); ctx.setLineDash([]);
       ctx.beginPath(); ctx.arc(tq[0], tq[1], 15, 0, 2 * Math.PI); ctx.lineWidth = 3.5; ctx.stroke(); ctx.restore();
       label("your target", tq[0] + 18, tq[1] + 36, {size: 16, weight: 800, color: tc("targets"), alpha: T.seg(t, 0.3, 0.42)});
       var pts = ALIVE.map(function (r, k) { return {r: r, k: k, p: [X(r[1]), Y(r[2]), 0], rank: RANKED.indexOf(r[0])}; });
       pts.forEach(function (o) { if (o.rank < 0) P.sphere(ctx, c, o.p, 0.075, COL.family, {dark: th.dark, alpha: T.seg(t, 0.02 + o.k * 0.006, 0.12 + o.k * 0.006) * 0.8}); });
       pts.filter(function (o) { return o.rank >= 0; }).sort(function (a, b) { return b.rank - a.rank; }).forEach(function (o) {
         var rise = T.ease(T.seg(t, 0.5 + o.rank * 0.07, 0.64 + o.rank * 0.07)), top = [o.p[0], o.p[1], 0.9 * rise];
         P.line3(ctx, c, o.p, top, P.css(P.rgbOf(COL.candidates), 0.7), 2);
         var q = P.sphere(ctx, c, top, 0.13, COL.candidates, {dark: th.dark, alpha: T.seg(t, 0.48, 0.52)});
         label(String(o.rank + 1), q[0], q[1] + 5, {size: 13, weight: 800, color: "#fff", align: "center", alpha: rise});
       });
       var a = T.seg(t, 0.55, 0.68);
       card(650, 84, 280, 330, {alpha: a});
       label("closest to your target", 670, 118, {size: 17, weight: 800, color: tc("targets"), alpha: a});
       RANKED.forEach(function (f, k) {
         var r = ALIVE.filter(function (x) { return x[0] === f; })[0], y = 170 + k * 78, b = T.seg(t, 0.6 + k * 0.08, 0.7 + k * 0.08);
         ctx.save(); ctx.globalAlpha *= b; ctx.beginPath(); ctx.arc(686, y - 7, 14, 0, 2 * Math.PI); ctx.fillStyle = COL.candidates; ctx.fill(); ctx.restore();
         label(String(k + 1), 686, y - 1, {size: 15, weight: 800, color: "#fff", align: "center", alpha: b});
         label(sub(f), 712, y, {size: 22, weight: 800, alpha: b});
         label(fmt(r[2]) + " eV · " + fmt(r[1]) + " eV/atom", 712, y + 24, {size: 15, color: th.muted, alpha: b});
       });
       label("27 compositions that pass every rule", 670, 400, {size: 13, color: th.faint, alpha: a});
     }},

    {block: "search", title: "Search", ms: 8800,
     cap: "Starting at your target’s point on the map, the search moves points until the model predicts your targets, turns each into a crystal and keeps those that pass every rule.",
     draw: function (t) {
       var c = cam(330, 280, 104, -0.4 + 0.5 * t, -0.3);
       card(690, 64, 240, 412);
       label("found", 712, 98, {size: 20, weight: 800, color: tc("search")}); label("pass every rule", 712, 120, {size: 15, color: th.muted});
       MAP_CLOUD.map(function (p) { return [c.proj(p), p]; }).sort(function (a, b) { return a[0][2] - b[0][2]; })
         .forEach(function (q) { dot(c, q[1], 0.03, th.dark ? "#94a3b8" : "#94a3b8", 0.25 + 0.25 * (q[0][2] + 1.7) / 3.4); });
       var o = c.proj([0, 0, 0]);
       star(o[0], o[1], 16, COL.targets);
       label("your target", o[0], o[1] + 36, {size: 15, weight: 800, color: tc("targets"), align: "center"});
       var who = [{ok: false, e: STOPPED[0].e}, {ok: true, i: 0}, {ok: false, e: STOPPED[1].e}, {ok: false, e: STOPPED[2].e},
                  {ok: true, i: 1}, {ok: false, e: STOPPED[3].e}, {ok: true, i: 2}, {ok: false, e: STOPPED[4].e}];
       function pos(k, u) {
         var th0 = k * 0.785 + 0.3, ph = 0.6 * Math.sin(k * 1.7), r = 0.18 + 1.25 * T.ease(T.seg(u, 0.06, 0.58)) * (0.6 + 0.4 * ((k * 37) % 10) / 10);
         return [r * Math.cos(th0 + 0.8 * u) * Math.cos(ph), r * Math.sin(ph) + 0.08 * Math.sin(u * 9 + k), r * Math.sin(th0 + 0.8 * u) * Math.cos(ph)];
       }
       var slot = 0;
       who.forEach(function (w, k) {
         var p = pos(k, Math.min(t, 0.6));
         if (t < 0.6) {
           ctx.save(); ctx.strokeStyle = P.css(P.rgbOf(COL.search), 0.5); ctx.lineWidth = 2.5; ctx.beginPath();
           for (var q = 8; q >= 0; q--) { var pp = c.proj(pos(k, Math.max(0, t - q * 0.015))); q === 8 ? ctx.moveTo(pp[0], pp[1]) : ctx.lineTo(pp[0], pp[1]); }
           ctx.stroke(); ctx.restore();
           P.sphere(ctx, c, p, 0.07, th.dark ? "#22c55e" : COL.search, {dark: th.dark, alpha: T.seg(t, 0.03, 0.1)});
           return;
         }
         var pop = T.pop(T.seg(t, 0.6, 0.68)), chk = T.seg(t, 0.7, 0.76), fade = w.ok ? 0 : T.seg(t, 0.8, 0.88), fly = w.ok ? T.ease(T.seg(t, 0.84, 0.97)) : 0;
         var my = w.ok ? slot++ : 0, q = c.proj(p), X = T.lerp(q[0], 740, fly), Y = T.lerp(q[1], 190 + my * 92, fly);
         var e = w.ok ? FOUND[w.i].e : w.e;
         if (fade >= 1) return;
         ctx.save(); ctx.globalAlpha *= 1 - fade;
         P.crystal(ctx, cam(X, Y, 19 * Math.max(0.05, pop), -0.6 + t * 2, -0.35), cell(e), {dark: th.dark, glass: 0.8});
         if (chk > 0) P.check(ctx, X + 24, Y - 24, w.ok, chk, th);
         ctx.restore();
         if (w.ok) label(sub(FOUND[w.i].f), 782, 197 + my * 92, {size: 21, weight: 800, alpha: T.seg(t, 0.92, 0.99)});
       });
     }},

    {block: "candidates", title: "Candidates", ms: 7800,
     cap: "Each new material comes with its crystal, the rules it passed and its predicted properties. Confirm the best ones with calculations or experiments.",
     draw: function (t) {
       label("example: a search with the default settings", 930, 52, {size: 13, weight: 700, color: th.muted, align: "right", alpha: T.seg(t, 0.1, 0.25)});
       FOUND.forEach(function (f, k) {
         var x0 = 34 + k * 302, a = T.out(T.seg(t, 0.04 + k * 0.12, 0.3 + k * 0.12));
         ctx.save(); ctx.translate(0, 50 * (1 - a)); ctx.globalAlpha *= a;
         card(x0, 70, 286, 330, {stroke: COL.candidates, sw: 2.2});
         P.crystal(ctx, cam(x0 + 70, 146, 34, -0.6 + 0.8 * t + k), cell(f.e), {dark: th.dark});
         label(sub(f.f), x0 + 134, 132, {size: 25, weight: 800});
         label("✓ every rule", x0 + 134, 158, {size: 15, weight: 700, color: th.good});
         if (f.flag) label("⚠ extrapolating", x0 + 134, 180, {size: 13, weight: 700, color: th.warn});
         [["Direct band gap", f.gap, 2.0, "eV", [0, 7.9]], ["Formation enthalpy", f.dh, -0.1, "eV/atom", [-0.64, 5.16]]].forEach(function (b, j) {
           var y = 232 + j * 82, lo = Math.min(b[4][0], b[1], b[2]), hi = Math.max(b[4][1], b[1], b[2]), G = function (v) { return x0 + 22 + (v - lo) / ((hi - lo) || 1) * 242; };
           label(b[0], x0 + 22, y, {size: 14, color: th.muted});
           label(fmt(b[1]) + " " + b[3], x0 + 22, y + 22, {size: 17, weight: 800});
           ctx.fillStyle = th.line; P.rrect(ctx, x0 + 22, y + 32, 242, 7, 3.5); ctx.fill();
           ctx.save(); ctx.setLineDash([3, 2]); ctx.strokeStyle = COL.targets; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(G(b[2]), y + 27); ctx.lineTo(G(b[2]), y + 44); ctx.stroke(); ctx.restore();
           label("target " + fmt(b[2]), T.clamp(G(b[2]), x0 + 50, x0 + 236), y + 60, {size: 12, weight: 700, color: tc("targets"), align: "center"});
           ctx.beginPath(); ctx.arc(G(b[1]), y + 35.5, 6.5, 0, 2 * Math.PI); ctx.fillStyle = COL.candidates; ctx.fill();
         });
         ctx.restore();
       });
       var a2 = T.seg(t, 0.62, 0.74);
       card(245, 428, 470, 42, {r: 21, fill: COL.candidates, stroke: null, alpha: a2});
       label("next: confirm with DFT or an experiment", 480, 455, {size: 19, weight: 700, color: "#fff", align: "center", alpha: a2});
     }},

    {block: "outro", title: "Your turn", ms: 4600,
     cap: "Your turn: explore the data, train a small model and generate candidates for a band gap of your choice, with the evidence for each.",
     draw: function (t) {
       P.crystal(ctx, cam(480, 250, 120, -0.6 + 0.9 * t, -0.35), cell(FOUND[0].e), {dark: th.dark, alpha: th.dark ? 0.07 : 0.1, glass: 0.6});
       var a = T.out(T.seg(t, 0, 0.25));
       label("Your turn", 480, 178, {size: 54, weight: 800, align: "center", alpha: a});
       label("Explore, train, generate: each step feeds the next,", 480, 226, {size: 23, color: th.muted, align: "center", alpha: T.seg(t, 0.15, 0.35)});
       label("and every result carries its evidence.", 480, 258, {size: 23, color: th.muted, align: "center", alpha: T.seg(t, 0.2, 0.4)});
       var wave = (t * 2.2) % 1;
       BLOCKS.forEach(function (b, k) {
         var x = 165 + k * 105, on = Math.abs(wave * 7 - k - 0.5) < 0.8, al = T.seg(t, 0.25 + k * 0.03, 0.35 + k * 0.03);
         if (k < 6) { ctx.save(); ctx.globalAlpha *= T.seg(t, 0.3, 0.4); ctx.strokeStyle = th.faint; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(x + 20, 330); ctx.lineTo(x + 85, 330); ctx.stroke(); ctx.restore(); }
         ctx.save(); ctx.globalAlpha *= al; ctx.beginPath(); ctx.arc(x, 330, on ? 17 : 12, 0, 2 * Math.PI); ctx.fillStyle = b.c; ctx.shadowColor = b.c; ctx.shadowBlur = on ? 14 : 0; ctx.fill(); ctx.restore();
         label(b.name, x, 372, {size: 14, weight: 700, color: tc(b.id), align: "center", alpha: al});
       });
     }}
  ];
  function dotFlat(x, y, r, color, a) { ctx.save(); ctx.globalAlpha *= a; ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fillStyle = color; ctx.fill(); ctx.restore(); }
  function ringFlat(x, y, r, color, a) { ctx.save(); ctx.globalAlpha *= a; ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.lineWidth = 2.5; ctx.strokeStyle = color; ctx.stroke(); ctx.restore(); }

  /* ── one frame of one scene, on any canvas: the 960 × 540 stage scaled to its width and centred ── */
  function render(c2d, i, t, W, H, dpr) {
    ctx = c2d; th = P.theme();
    var k = W / VW;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, (H - VH * k) / 2 * dpr);
    try { SCENES[i].draw(T.clamp(t)); } catch (e) { if (window.console) console.error(e); }
  }
  window.PrismScenes = {
    blocks: BLOCKS, render: render, ratio: VW / VH,
    list: SCENES.map(function (s) { return {block: s.block, title: s.title, ms: s.ms, cap: s.cap}; }),
    index: function (block) { return SCENES.map(function (s) { return s.block; }).indexOf(block); }
  };

  /* ── the player of the landing page ── */
  var root = document.getElementById("tour3d");
  if (!root) return;
  var canvas = root.querySelector("canvas"), tctx = canvas.getContext("2d");
  var TOTAL = SCENES.reduce(function (a, s) { return a + s.ms; }, 0);
  var S = {ms: 0, playing: false, last: 0, raf: 0, i: -1, visible: false, started: false, W: 0, H: 0, dpr: 1};
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (sel) { return root.querySelector(sel); };
  var strip = $(".t3-strip"), cap = $(".t3-cap"), prog = $(".t3-prog"), playBtn = $("[data-t3=play]"), open = $(".t3-open"), time = $(".t3-time");
  prog.setAttribute("aria-valuemax", String(Math.round(TOTAL / 1000)));
  strip.innerHTML = BLOCKS.map(function (b) {
    return '<li><button type="button" data-block="' + b.id + '" style="--bc:' + b.c + '"><span>' + b.name + "</span><i></i></button></li>";
  }).join("");
  function at(ms) { var a = 0; for (var i = 0; i < SCENES.length; i++) { if (ms < a + SCENES[i].ms || i === SCENES.length - 1) return {i: i, t: T.clamp((ms - a) / SCENES[i].ms), start: a}; a += SCENES[i].ms; } }
  function startOf(i) { var a = 0; for (var k = 0; k < i; k++) a += SCENES[k].ms; return a; }
  function clock(ms) { var s = Math.round(ms / 1000); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  function resize() {
    var r = canvas.getBoundingClientRect();
    S.dpr = Math.min(2, window.devicePixelRatio || 1); S.W = Math.max(1, r.width); S.H = Math.max(1, r.height);
    canvas.width = Math.round(S.W * S.dpr); canvas.height = Math.round(S.H * S.dpr);
    draw();
  }
  function draw() {
    if (!S.W) return;
    var w = at(S.ms), sc = SCENES[w.i];
    render(tctx, w.i, w.t, S.W, S.H, S.dpr);
    prog.firstElementChild.style.width = (100 * S.ms / TOTAL).toFixed(2) + "%";
    prog.setAttribute("aria-valuenow", String(Math.round(S.ms / 1000)));
    time.textContent = clock(S.ms) + " / " + clock(TOTAL);
    var bi = BLOCKS.map(function (b) { return b.id; }).indexOf(sc.block);
    strip.querySelectorAll("button").forEach(function (b, j) {
      b.classList.toggle("on", j === bi); b.classList.toggle("done", (bi >= 0 && j < bi) || sc.block === "outro");
      b.querySelector("i").style.width = j === bi ? (100 * w.t).toFixed(1) + "%" : "0";
    });
    if (w.i !== S.i) {
      S.i = w.i;
      var blk = BLOCKS[bi];
      cap.innerHTML = (blk ? '<b style="color:' + tc(blk.id) + '">' + blk.name + ".</b> " : "") + sc.cap;
      root.style.setProperty("--t3c", blk ? blk.c : COL.family);
      var dest = {data: ["/explore", "Explore the data →"], model: ["/train", "Train a small model →"], family: ["/p/perov5-demo/goal", "Search within a family →"],
                  rules: ["/p/perov5-demo/goal", "Set rules and targets →"], targets: ["/generate", "Generate for a band gap →"],
                  search: ["/generate", "Generate for a band gap →"], candidates: ["/studies", "See the case studies →"]}[blk ? blk.id : ""] || ["/explore", "Start exploring →"];
      open.setAttribute("href", dest[0]); open.textContent = dest[1];
    }
  }
  function loop(now) {
    S.raf = 0; if (!S.playing) return;
    var dt = S.last ? Math.min(120, now - S.last) : 0; S.last = now;
    if (S.visible && !document.hidden) {
      S.ms = Math.min(TOTAL, S.ms + dt); draw();
      if (S.ms >= TOTAL) { pause(); playBtn.textContent = "↺ Replay"; playBtn.setAttribute("aria-label", "Play the tour again"); return; }
    }
    S.raf = requestAnimationFrame(loop);
  }
  function play() {
    if (S.ms >= TOTAL - 1) S.ms = 0;
    S.playing = true; S.last = 0; S.started = true;
    playBtn.textContent = "❚❚ Pause"; playBtn.setAttribute("aria-label", "Pause the tour");
    if (!S.raf) S.raf = requestAnimationFrame(loop);
  }
  function pause() { S.playing = false; playBtn.textContent = "▶ Play"; playBtn.setAttribute("aria-label", "Play the tour"); }
  function go(i) {          // a chapter: from its start while playing, its finished picture while paused
    i = Math.max(0, Math.min(SCENES.length - 1, i));
    S.ms = startOf(i) + (S.playing ? 0 : SCENES[i].ms - 1); S.i = -1; draw();
  }
  playBtn.addEventListener("click", function () { S.playing ? pause() : play(); });
  $("[data-t3=prev]").addEventListener("click", function () { go(at(S.ms).i - 1); });
  $("[data-t3=next]").addEventListener("click", function () { go(at(S.ms).i + 1); });
  strip.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-block]"); if (!b) return;
    var i = SCENES.map(function (s) { return s.block; }).indexOf(b.getAttribute("data-block")); if (i >= 0) go(i);
  });
  function seek(e) { var r = prog.getBoundingClientRect(); S.ms = T.clamp((e.clientX - r.left) / r.width) * TOTAL; S.i = -1; draw(); }
  prog.addEventListener("click", seek);
  prog.addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight") { S.ms = Math.min(TOTAL, S.ms + 5000); draw(); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { S.ms = Math.max(0, S.ms - 5000); draw(); e.preventDefault(); }
  });
  root.addEventListener("keydown", function (e) {
    if (e.target.closest && e.target.closest(".t3-prog")) return;
    if (e.key === "k" || (e.key === " " && e.target === canvas)) { e.preventDefault(); S.playing ? pause() : play(); }
  });
  var th0 = document.getElementById("theme");
  if (th0) th0.addEventListener("click", function () { setTimeout(function () { S.i = -1; draw(); }, 0); });
  if (window.ResizeObserver) new ResizeObserver(resize).observe(canvas); else window.addEventListener("resize", resize);
  if (window.IntersectionObserver) new IntersectionObserver(function (es) {
    S.visible = es[0].isIntersecting;
    if (S.visible && !S.started && !reduce) { S.ms = 0; S.i = -1; play(); }   // starts the first time it is seen
  }, {threshold: 0.35}).observe(canvas);
  else { S.visible = true; if (!reduce) { S.ms = 0; play(); } }
  S.ms = SCENES[0].ms - 1;            // before it plays (or with reduced motion): the finished opening picture
  resize();
  window.prismTour = {play: play, pause: pause, go: go, seek: function (ms) { S.ms = T.clamp(ms, 0, TOTAL); S.i = -1; draw(); },
                      scenes: SCENES.map(function (s) { return {block: s.block, title: s.title, ms: s.ms}; })};
})();
