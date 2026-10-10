/* The crystal of the MEIDNet Prism landing page, for MEIDNet Matter: a cubic ABX3 perovskite turning slowly, with three
   panels behind it (its crystal graph, the shared latent space, a band-gap curve). Copied from Prism's prism-hero.js
   with two changes: the headline lettering of that page is left out, and the scene is a function the app calls on each
   canvas it renders (PrismHero.mount), because this single-page app renders a new canvas whenever the home page opens.
   The handle it returns redraws the scene after a theme change (redraw) and stops it when the page is left (destroy).
   Needs prism3d.js (window.Prism3D), loaded first. No libraries: a small canvas renderer (painter's algorithm). */
(function () {
  "use strict";
  var P3 = window.Prism3D;
  if (!P3) return;
  var isDark = P3.isDark;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ═══════════ the 3D scene: an ABX3 perovskite and what MEIDNet makes of it ═══════════ */
  // the cubic ABX3 cell (A on the corners, the BX6 octahedron in the centre), half edge 1.25 in this scene
  var CELL = P3.perovskite({A: "A", B: "B", X: "X"});

  // panels behind the crystal: centre, half sizes, rotation about y, what they show
  var r = P3.T.rng(7), LATENT = [];
  for (var i = 0; i < 90; i++) {                 // paired points: a structure (teal) and its properties (violet), close together
    var t = r() * 2 - 1, u = r() * 2 - 1, cx = 0.75 * t, cy = 0.55 * Math.sin(2.2 * t) * 0.8 + 0.25 * u;
    LATENT.push({u: cx, v: cy, du: (r() - 0.5) * 0.09, dv: (r() - 0.5) * 0.09, c: t});
  }
  var GRAPH = {n: [[-0.62, -0.35], [-0.22, 0.42], [0.18, -0.12], [0.6, 0.38], [0.52, -0.5], [-0.05, -0.62], [-0.68, 0.38]],
               e: [[0, 1], [1, 2], [2, 3], [2, 4], [0, 5], [5, 2], [1, 6], [6, 0], [3, 4]]};
  var PANELS = [
    {c: [-2.2, 1.5, -2.4], h: [0.95, 0.68], ry: 0.5, kind: "graph", label: "crystal graph"},
    {c: [1.45, 2.0, -2.9], h: [1.15, 0.75], ry: -0.32, kind: "latent", label: "latent space z ∈ ℝ¹²⁸"},
    {c: [2.25, -1.25, -1.6], h: [0.8, 0.56], ry: -0.62, kind: "property", label: "property: band gap"}
  ];
  function panelPoint(P, u, v, w) {        // panel-local (u, v in [-1, 1]) to world
    var c = Math.cos(P.ry), sn = Math.sin(P.ry), x = u * P.h[0], y = v * P.h[1];
    return [P.c[0] + x * c + (w || 0) * sn, P.c[1] + y, P.c[2] - x * sn + (w || 0) * c];
  }

  function mount(canvas) {
    if (!canvas || !canvas.getContext) return null;
    if (canvas.__prismHero) return canvas.__prismHero;
    var ctx = canvas.getContext("2d");
    if (!ctx) return null;

    var W = 0, H = 0, DPR = 1, yaw = 0, pitch = 0, dragYaw = 0, dragPitch = 0, t0 = performance.now(), cam = null;
    function resize() {
      var b = canvas.getBoundingClientRect();
      DPR = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(1, b.width); H = Math.max(1, b.height);
      canvas.width = Math.round(W * DPR); canvas.height = Math.round(H * DPR);
      draw();
    }
    function proj(p) { return cam.proj(p); }
    function poly(pts) { ctx.beginPath(); pts.forEach(function (p, j) { j ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }); ctx.closePath(); }

    function drawPanel(P, dark) {
      var corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(function (c) { return proj(panelPoint(P, c[0], c[1])); });
      poly(corners);
      var g = ctx.createLinearGradient(corners[3][0], corners[3][1], corners[1][0], corners[1][1]);
      g.addColorStop(0, dark ? "rgba(51,65,85,.55)" : "rgba(255,255,255,.78)");
      g.addColorStop(1, dark ? "rgba(30,41,59,.28)" : "rgba(226,232,255,.42)");
      ctx.fillStyle = g; ctx.fill();
      ctx.lineWidth = 1; ctx.strokeStyle = dark ? "rgba(148,163,184,.45)" : "rgba(148,163,184,.55)"; ctx.stroke();
      var L = function (u, v) { return proj(panelPoint(P, u, v)); };
      if (P.kind === "graph") {
        ctx.lineWidth = 1.4; ctx.strokeStyle = dark ? "rgba(148,163,184,.75)" : "rgba(100,116,139,.6)";
        GRAPH.e.forEach(function (e) { var a = L(GRAPH.n[e[0]][0] * 0.8, GRAPH.n[e[0]][1] * 0.8), b = L(GRAPH.n[e[1]][0] * 0.8, GRAPH.n[e[1]][1] * 0.8);
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); });
        GRAPH.n.forEach(function (n, j) { var q = L(n[0] * 0.8, n[1] * 0.8);
          ctx.beginPath(); ctx.arc(q[0], q[1], Math.max(2.5, 0.07 * q[3]), 0, 2 * Math.PI);
          ctx.fillStyle = ["#3b82f6", "#14b8a6", "#8b5cf6"][j % 3]; ctx.fill(); });
      } else if (P.kind === "latent") {
        LATENT.forEach(function (p) {
          var a = L(p.u, p.v), b = L(p.u + p.du, p.v + p.dv), rad = Math.max(1.4, 0.028 * a[3]);
          ctx.strokeStyle = dark ? "rgba(203,213,225,.3)" : "rgba(100,116,139,.28)"; ctx.lineWidth = 0.8;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
          var h = 175 + (p.c + 1) * 50;
          ctx.fillStyle = "hsla(" + h + ",70%," + (dark ? 62 : 48) + "%,.9)";
          ctx.beginPath(); ctx.arc(a[0], a[1], rad, 0, 2 * Math.PI); ctx.fill();
          ctx.fillStyle = "hsla(" + (h + 80) + ",70%," + (dark ? 70 : 58) + "%,.85)";
          ctx.beginPath(); ctx.arc(b[0], b[1], rad * 0.85, 0, 2 * Math.PI); ctx.fill();
        });
      } else {
        ctx.strokeStyle = dark ? "rgba(148,163,184,.6)" : "rgba(100,116,139,.55)"; ctx.lineWidth = 1;
        var o = L(-0.85, -0.7), xe = L(0.85, -0.7), ye = L(-0.85, 0.75);
        ctx.beginPath(); ctx.moveTo(ye[0], ye[1]); ctx.lineTo(o[0], o[1]); ctx.lineTo(xe[0], xe[1]); ctx.stroke();
        ctx.beginPath();
        for (var j = 0; j <= 60; j++) {
          var u = -0.85 + 1.7 * j / 60, xg = (u + 0.85) * 3,      // band gap axis, 0 to ~5 eV
              yv = Math.exp(-Math.pow((xg - 1.6) / 0.6, 2)) + 0.55 * Math.exp(-Math.pow((xg - 3.4) / 0.8, 2)),
              q = L(u, -0.7 + 1.3 * yv);
          j ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]);
        }
        ctx.strokeStyle = "#8b5cf6"; ctx.lineWidth = 2; ctx.stroke();
        var tu = -0.85 + 2.0 / 3, a = L(tu, -0.7), b = L(tu, 0.7);   // the target, 2 eV
        ctx.setLineDash([4, 3]); ctx.strokeStyle = "#e87ba4"; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); ctx.setLineDash([]);
      }
      var tl = corners[3];
      ctx.font = "500 " + Math.round(Math.max(10, Math.min(12.5, W / 46))) + "px 'IBM Plex Mono', ui-monospace, monospace";
      ctx.fillStyle = dark ? "rgba(203,213,225,.85)" : "rgba(71,85,105,.9)";
      ctx.fillText(P.label, Math.max(4, Math.min(tl[0] + 2, W - ctx.measureText(P.label).width - 4)), tl[1] - 7);   // inside the canvas
    }

    function draw() {
      if (!W) return;
      var dark = isDark();
      cam = P3.camera({cx: W * 0.52, cy: H * 0.5, scale: Math.min(W, H * 1.1) / 8.3, yaw: yaw, pitch: pitch});
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);
      // floor grid
      ctx.lineWidth = 1; ctx.strokeStyle = dark ? "rgba(148,163,184,.12)" : "rgba(100,116,139,.14)";
      for (var g = -3; g <= 3; g += 0.75) {
        var a = proj([g, -2.05, -3]), b = proj([g, -2.05, 3]), c = proj([-3, -2.05, g]), d = proj([3, -2.05, g]);
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.moveTo(c[0], c[1]); ctx.lineTo(d[0], d[1]); ctx.stroke();
      }
      // the cation's shadow on the floor
      var f = proj([0, -2.05, 0]), sh = ctx.createRadialGradient(f[0], f[1], 0, f[0], f[1], 2.0 * f[3]);
      sh.addColorStop(0, dark ? "rgba(0,0,0,.35)" : "rgba(30,41,90,.07)"); sh.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = sh; ctx.beginPath(); ctx.ellipse(f[0], f[1], 2.0 * f[3], 0.62 * f[3], 0, 0, 2 * Math.PI); ctx.fill();
      // panels, far first
      PANELS.slice().sort(function (p, q) { return proj(p.c)[2] - proj(q.c)[2]; }).forEach(function (P) { drawPanel(P, dark); });
      P3.crystal(ctx, cam, CELL, {s: 1.25, atomScale: 0.6, dark: dark});
    }

    var running = false, visible = true;
    function frame(now) {
      var t = (now - t0) / 1000;
      yaw = -0.5 + 0.38 * Math.sin(t * 0.21) + dragYaw;
      pitch = -0.33 + 0.05 * Math.sin(t * 0.16) + dragPitch;
      draw();
      if (running) requestAnimationFrame(frame);
    }
    function start() { if (reduce || running || !visible || document.hidden) return; running = true; requestAnimationFrame(frame); }
    function stop() { running = false; }
    if (reduce) { yaw = -0.5; pitch = -0.33; }

    var drag = null;
    canvas.addEventListener("pointerdown", function (e) { drag = {x: e.clientX, y: e.clientY, yaw: dragYaw, pitch: dragPitch}; canvas.setPointerCapture(e.pointerId); canvas.classList.add("grabbing"); });
    canvas.addEventListener("pointermove", function (e) {
      if (!drag) return;
      dragYaw = drag.yaw + (e.clientX - drag.x) * 0.008;
      dragPitch = Math.max(-0.5, Math.min(0.45, drag.pitch + (e.clientY - drag.y) * 0.005));
      if (reduce) { yaw = -0.5 + dragYaw; pitch = -0.33 + dragPitch; draw(); }
    });
    function endDrag() { drag = null; canvas.classList.remove("grabbing"); }
    canvas.addEventListener("pointerup", endDrag); canvas.addEventListener("pointercancel", endDrag);

    var ro = null, io = null;
    if (window.ResizeObserver) { ro = new ResizeObserver(resize); ro.observe(canvas); } else window.addEventListener("resize", resize);
    if (window.IntersectionObserver) { io = new IntersectionObserver(function (es) { visible = es[0].isIntersecting; visible ? start() : stop(); }); io.observe(canvas); }
    function onVisibility() { document.hidden ? stop() : start(); }
    document.addEventListener("visibilitychange", onVisibility);
    resize();
    start();

    var api = {redraw: draw, destroy: function () {     // the page is left: stop turning and let go of the observers
      visible = false; stop();
      if (ro) ro.disconnect(); else window.removeEventListener("resize", resize);
      if (io) io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      if (canvas.__prismHero === api) delete canvas.__prismHero;
    }};
    canvas.__prismHero = api;
    return api;
  }
  window.PrismHero = {mount: mount};
  mount(document.getElementById("hero3d"));
})();
