/* Ask PRISM: the help panel of MEIDNet Prism, shared by the landing page, the Studio and the documentation.
   Nothing is sent from this panel. A question or a bug report opens on Hugging Face or GitHub in a new tab, with
   the text pre-filled so that the visitor can read and edit it before posting. Technical details describe the
   software and the settings only: no table, structure or file is ever included. */
(function () {
  "use strict";
  if (window.__askPrism) return;
  window.__askPrism = true;

  var SPACE = "https://huggingface.co/spaces/Babu09/MEIDNet";
  var REPO = "https://github.com/ABnano/MEIDNet";
  var URL_MAX = 7000;   // GitHub refuses longer pre-filled links
  var PUBLIC = "https://babu09-meidnet.hf.space";
  var base = location.protocol === "file:" ? PUBLIC : "";

  var TOPICS = [
    {id: "data", title: "My dataset is not working",
     text: "MEIDNet reads one table with one row per material: the crystal structure of each row (CIF files) and one " +
           "numeric column per property. The Data block of the Studio checks every row and lists the rows it could " +
           "not use, with the reason.",
     limits: true,
     links: [["Bring your own dataset", "/docs/use/your-data.html"], ["What data do I need?", "/docs/start/what-data.html"],
             ["Open the Data block", "/studio/?panel=data"]]},
    {id: "modalities", title: "Which modalities can I use?",
     text: "MEIDNet aligns crystal structures with any number of scalar properties, such as a band gap, a formation " +
           "enthalpy or your own columns. Spectra (XRD, DOS), images and text are on the roadmap and not supported yet.",
     links: [["Capabilities", "/docs/explore/capabilities.html"], ["Learn multimodality", "/docs/learn/index.html"],
             ["Which architecture fits my data?", "/docs/learn/architectures.html"], ["Scope and roadmap", "/docs/understand/limits.html"]]},
    {id: "configure", title: "Help me configure MEIDNet",
     text: "Every setting of the Studio is saved in one file, meidnet.yaml, and the same file runs from the command line.",
     links: [["The configuration file", "/docs/use/config.html"], ["Configuration reference", "/docs/reference/config.html"],
             ["Recipes by problem", "/docs/learn/recipes.html"], ["Change the target properties", "/docs/recipes/change-targets.html"]]},
    {id: "result", title: "I don't understand a result",
     text: "Each candidate lists every rule with its measured value, and the predicted properties next to your targets. " +
           "Predictions are the model's estimates; targets outside the range of the training data are extrapolations.",
     links: [["Interpreting a candidate", "/docs/understand/interpretability.html"], ["Reading the reports", "/docs/use/reports.html"],
             ["How MEIDNet works", "/docs/understand/how-it-works.html"], ["Screen stability with MACE", "/docs/recipes/screen.html"]]},
    {id: "benchmark", title: "I cannot reproduce a benchmark",
     text: "Each benchmark page states its protocol and data split. When a number differs, include the command you ran " +
           "and the value you obtained in your question.",
     links: [["MEIDNet Benchmarks", "/docs/benchmarks/index.html"], ["Perov-5 benchmark", "/docs/benchmarks/perov5.html"],
             ["Perov-5 example", "/docs/examples/perov5.html"], ["Contribute a result", "/docs/community/contribute.html"]]},
    {id: "bug", title: "I found a bug"},
    {id: "ask", title: "Ask something else"}
  ];

  /* ── recent errors of this page (messages only) ── */
  var errors = [];
  function remember(msg) { msg = String(msg || "").split("\n")[0].slice(0, 200); if (msg) { errors.push(msg); if (errors.length > 3) errors.shift(); } }
  window.addEventListener("error", function (e) { remember(e.message); });
  window.addEventListener("unhandledrejection", function (e) { remember(e.reason && (e.reason.message || e.reason)); });

  /* ── styles ── */
  var CSS = [
    ".ap-btn{position:fixed;right:18px;bottom:18px;z-index:9990;display:inline-flex;align-items:center;gap:8px;border:0;border-radius:999px;",
    "  padding:10px 16px 10px 12px;background:#4f46e5;color:#fff;font:600 14.5px/1 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;",
    "  letter-spacing:.01em;cursor:pointer;box-shadow:0 8px 24px -10px rgba(30,27,75,.65)}",
    ".ap-btn:hover{background:#6d28d9}.ap-btn:focus-visible{outline:3px solid #a5b4fc;outline-offset:2px}.ap-btn svg{width:18px;height:18px}",
    ".ap-btn b{font-weight:800;letter-spacing:.04em}",
    ".ap-btn[aria-expanded=true]{display:none}",
    ".ap{--ap-bg:#fff;--ap-ink:#141414;--ap-muted:#55544f;--ap-line:#e2e1da;--ap-soft:#f4f4f1;--ap-link:#4338ca;",
    "  position:fixed;right:18px;bottom:18px;z-index:9991;width:390px;max-width:calc(100vw - 24px);max-height:min(640px,calc(100vh - 36px));",
    "  display:flex;flex-direction:column;background:var(--ap-bg);color:var(--ap-ink);border:1px solid var(--ap-line);border-radius:16px;",
    "  --ap-ff:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;box-shadow:0 18px 50px -18px rgba(0,0,0,.45);font:400 14.5px/1.5 var(--ap-ff);text-align:left}",
    ".ap[hidden]{display:none}",
    ".ap.ap-dark{--ap-bg:#1b1f24;--ap-ink:#f3f3f1;--ap-muted:#c3c2b7;--ap-line:#33373d;--ap-soft:#23282e;--ap-link:#a5b4fc}",
    ".ap *{box-sizing:border-box}",
    ".ap-head{display:flex;align-items:center;gap:10px;padding:14px 14px 12px 16px;border-bottom:1px solid var(--ap-line)}",
    ".ap-head svg{width:22px;height:22px;flex:none}",
    ".ap-head h2{margin:0;font:700 16px/1.2 var(--ap-ff);letter-spacing:.01em;color:var(--ap-ink);text-transform:none;padding:0;border:0}",
    ".ap-head p{margin:2px 0 0;font-size:12.5px;color:var(--ap-muted)}",
    ".ap-x,.ap-back{border:0;background:transparent;color:var(--ap-muted);cursor:pointer;border-radius:8px;font:inherit}",
    ".ap-x{margin-left:auto;font-size:20px;line-height:1;padding:4px 8px}.ap-x:hover,.ap-back:hover{background:var(--ap-soft);color:var(--ap-ink)}",
    ".ap-back{padding:4px 8px 4px 4px;font-size:13px;margin:0 0 6px -4px}",
    ".ap-body{padding:12px 16px 14px;overflow:auto}",
    ".ap-body h3{margin:0 0 6px;font:700 15px/1.3 var(--ap-ff);color:var(--ap-ink);text-transform:none;letter-spacing:normal}",
    ".ap-body p{margin:0 0 10px;color:var(--ap-muted)}",
    ".ap-topics{list-style:none;margin:0;padding:0;display:grid;gap:6px}",
    ".ap-topics button{width:100%;display:flex;align-items:center;gap:10px;text-align:left;border:1px solid var(--ap-line);border-radius:11px;",
    "  background:var(--ap-bg);color:var(--ap-ink);padding:9px 12px;font:600 14px/1.3 var(--ap-ff);cursor:pointer;margin:0;box-shadow:none}",
    ".ap-topics button:hover,.ap-topics button:focus-visible{border-color:#6366f1;background:var(--ap-soft);outline:none}",
    ".ap-topics button::after{content:'›';margin-left:auto;color:var(--ap-muted);font-size:18px;line-height:1}",
    ".ap-topics i{width:8px;height:8px;border-radius:2px;transform:rotate(45deg);flex:none;background:var(--k)}",
    ".ap-links{list-style:none;margin:0 0 12px;padding:0;display:grid;gap:4px}",
    ".ap-links a{color:var(--ap-link);font-weight:600;text-decoration:none}.ap-links a:hover{text-decoration:underline}",
    ".ap-links a::before{content:'→ ';color:var(--ap-muted)}",
    ".ap-more{border-top:1px solid var(--ap-line);padding-top:10px;margin-top:4px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px;color:var(--ap-muted)}",
    ".ap-b{border:1px solid var(--ap-line);background:var(--ap-bg);color:var(--ap-ink);border-radius:9px;padding:7px 12px;font:600 13.5px/1.2 var(--ap-ff);cursor:pointer;margin:0;box-shadow:none;text-decoration:none;display:inline-block}",
    ".ap-b:hover{background:var(--ap-soft)}.ap-b.ap-p{background:#4f46e5;border-color:#4f46e5;color:#fff}.ap-b.ap-p:hover{background:#6d28d9}",
    ".ap label{display:block;font:600 13px/1.4 var(--ap-ff);margin:8px 0 4px;color:var(--ap-ink);text-transform:none;letter-spacing:normal}",
    ".ap label small{font-weight:400;color:var(--ap-muted)}",
    ".ap textarea,.ap input[type=text]{width:100%;border:1px solid var(--ap-line);border-radius:9px;background:var(--ap-soft);color:var(--ap-ink);",
    "  font:400 13.5px/1.45 var(--ap-ff);padding:8px 10px;resize:vertical;min-height:0;height:auto;margin:0;box-shadow:none;max-width:none}",
    ".ap textarea:focus,.ap input:focus{outline:2px solid #818cf8;outline-offset:0;border-color:transparent}",
    ".ap textarea.ap-diag{font:400 12px/1.45 ui-monospace,'Cascadia Mono',Consolas,monospace;min-height:120px}",
    ".ap .ap-check{display:flex;gap:8px;align-items:flex-start;font-weight:400;color:var(--ap-muted)}",
    ".ap .ap-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}",
    ".ap-note{font-size:12px;color:var(--ap-muted);border-top:1px solid var(--ap-line);padding:9px 16px 11px;margin:0}",
    ".ap-msg{font-size:12.5px;color:var(--ap-muted);margin:8px 0 0}",
    "@media(max-width:520px){.ap{right:8px;left:8px;bottom:8px;width:auto;max-width:none;max-height:calc(100vh - 16px)}",
    "  .ap-btn{right:12px;bottom:12px;padding:9px 14px 9px 10px;font-size:14px}}",
    "@media print{.ap-btn,.ap{display:none!important}}"
  ].join("\n");

  function mark(id) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="' + id + '" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#60a5fa"/><stop offset=".55" stop-color="#a78bfa"/><stop offset="1" stop-color="#f472b6"/></linearGradient></defs>' +
    '<path d="M12 2.5 21 20H3z" fill="url(#' + id + ')" stroke="#fff" stroke-opacity=".85" stroke-width="1.2" stroke-linejoin="round"/>' +
    '<path d="M12 2.5v17.5" stroke="#fff" stroke-opacity=".5" stroke-width=".8" fill="none"/></svg>'; }
  var COLORS = ["#2a78d6", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#eb6834", "#4a3aa7"];

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function el(id) { return document.getElementById(id); }

  function isDark() {
    var t = document.documentElement.getAttribute("data-theme");
    if (t) return t === "dark";
    var md = document.body && document.body.getAttribute("data-md-color-scheme");
    if (md) return md === "slate";
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  /* ── technical details: software and settings, never data ── */
  var stateCache = null;
  function studioState() {
    try { if (typeof S !== "undefined" && S && S.state) return Promise.resolve(S.state); } catch (e) { /* not the Studio */ }
    if (window.MEIDNET_STATIC) return Promise.resolve(window.MEIDNET_STATIC.state);
    if (stateCache) return Promise.resolve(stateCache);
    if (location.protocol === "file:") return Promise.resolve(null);
    var sid = null;
    try { sid = sessionStorage.getItem("meidnet_sid"); } catch (e) { /* storage blocked */ }
    return fetch("/api/state" + (sid ? "?session=" + encodeURIComponent(sid) : ""), {headers: {Accept: "application/json"}})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { stateCache = j && j.version ? j : null; return stateCache; })
      .catch(function () { return null; });
  }
  function browser() {
    var ua = navigator.userAgent, m;
    var name = (m = ua.match(/Edg\/(\d+)/)) ? "Edge " + m[1] : (m = ua.match(/Firefox\/(\d+)/)) ? "Firefox " + m[1]
      : (m = ua.match(/Chrome\/(\d+)/)) ? "Chrome " + m[1] : (m = ua.match(/Version\/(\d+).*Safari/)) ? "Safari " + m[1] : "browser";
    var os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
    return name + (os ? " / " + os : "") + " · window " + window.innerWidth + "×" + window.innerHeight;
  }
  function lastLine(s) { s = String(s || "").trim().split("\n"); return s[s.length - 1].slice(0, 240); }
  function details() {
    return studioState().then(function (st) {
      var L = ["MEIDNet Prism: technical details (software and settings only, no data)",
               "page: " + location.pathname];
      if (st) {
        L.push("version: MEIDNet " + st.version + (window.MEIDNET_STATIC ? " (static demo)" : st.public ? " (hosted, public)" : " (local)"));
        var m = st.model || {};
        var props = (m.properties || []).map(function (p) { return p.column || p.label; }).join(", ");
        L.push("model: " + (m.own ? "trained in this session" : m.legacy ? "published Perov-5 model" : (m.path || "?")) +
               (props ? " · properties: " + props : "") + (m.latent_dim ? " · latent " + m.latent_dim : "") +
               (m.max_sites ? " · max sites " + m.max_sites : ""));
        var s = st.session;
        if (s && s.has_upload) L.push("uploaded table: " + s.n_rows + " rows, " + s.n_cifs + " CIFs, columns: " + (s.columns || []).join(", ") +
                                      " · checked: " + (s.checked ? "yes" : "no"));
      } else {
        L.push("version: not available on this page");
      }
      try {
        if (typeof S !== "undefined" && S && S.ui) {
          var t = S.ui.target || {}, tt = Object.keys(t).map(function (k) { return k + " = " + t[k]; }).join(", ");
          L.push("studio: block " + S.panel + " · family " + S.ui.family + (S.ui.variant ? " / " + S.ui.variant : "") +
                 (tt ? " · targets " + tt : "") + (S.ui.exclude && S.ui.exclude.size ? " · excluded " + Array.from(S.ui.exclude).join(" ") : ""));
          var tr = S.train;
          if (tr && tr.kind) L.push("training: " + (tr.running ? "running" : tr.error ? "failed: " + lastLine(tr.error) : "finished") +
                                    (tr.progress ? " (epoch " + tr.progress.epoch + "/" + tr.progress.epochs + ")" : ""));
          var se = S.search && S.search.status;
          if (se && se.kind) L.push("search: " + (se.running ? "running" : se.error ? "failed: " + lastLine(se.error) : "finished"));
        }
      } catch (e) { /* not the Studio */ }
      if (errors.length) L.push("page errors: " + errors.join(" | "));
      L.push("browser: " + browser());
      return L.join("\n");
    });
  }

  /* ── outgoing links (new tab: on Hugging Face the site runs inside a frame) ── */
  function clip(s, n) { return s.length > n ? s.slice(0, n - 20) + "\n… (shortened)" : s; }
  function hfUrl(title, body) {
    return SPACE + "/discussions/new?title=" + encodeURIComponent(title) + "&description=" + encodeURIComponent(clip(body, URL_MAX - 400));
  }
  /* The form's fields are filled by name; the same text also goes in `body`, which GitHub uses when the form is not
     available. The text is shortened until the link fits, never cut inside an escape. */
  function ghBugUrl(title, what, expected, diag) {
    for (var n = 2500; ; n = Math.round(n * 0.7)) {
      var w = clip(what, n), e = clip(expected, Math.round(n / 2)), d = clip(diag, n);
      var plain = "### What happened?\n\n" + w + (e ? "\n\n### What did you expect?\n\n" + e : "") +
                  "\n\n### Technical details\n\n```text\n" + d + "\n```";
      var u = REPO + "/issues/new?template=bug_report.yml&title=" + encodeURIComponent(title) +
              "&what_happened=" + encodeURIComponent(w) + "&expected=" + encodeURIComponent(e) +
              "&diagnostics=" + encodeURIComponent(d) + "&body=" + encodeURIComponent(plain);
      if (u.length <= URL_MAX || n < 100) return u;
    }
  }
  function copy(text) {
    try { if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); }); }
    catch (e) { /* fall through */ }
    return Promise.resolve(legacyCopy(text));
  }
  function legacyCopy(text) {
    var t = document.createElement("textarea"); t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select(); var ok = false; try { ok = document.execCommand("copy"); } catch (e) { /* no clipboard */ }
    document.body.removeChild(t); return ok;
  }
  function openTab(url) { var w = window.open(url, "_blank", "noopener"); return !!w; }

  /* ── views ── */
  var panel, btn, body, lastTopic = null;

  function home() {
    lastTopic = null;
    body.innerHTML = "<p>Help with datasets, modalities, configuration, results and benchmarks. Choose a topic:</p>" +
      '<ul class="ap-topics">' + TOPICS.map(function (t, i) {
        return '<li><button type="button" data-topic="' + t.id + '"><i style="--k:' + COLORS[i % COLORS.length] + '"></i>' + esc(t.title) + "</button></li>";
      }).join("") + "</ul>";
    body.querySelectorAll("[data-topic]").forEach(function (b) { b.addEventListener("click", function () { show(b.getAttribute("data-topic")); }); });
    focusFirst();
  }
  function back() { return '<button type="button" class="ap-back" data-back>‹ All topics</button>'; }
  function wireBack() { var b = body.querySelector("[data-back]"); if (b) b.addEventListener("click", home); }

  function show(id) {
    if (id === "bug") return bug();
    if (id === "ask") return ask(null);
    var t = TOPICS.filter(function (x) { return x.id === id; })[0];
    lastTopic = t;
    body.innerHTML = back() + "<h3>" + esc(t.title) + "</h3><p>" + esc(t.text) + '</p><p class="ap-lim" hidden></p>' +
      '<ul class="ap-links">' + t.links.map(function (l) { return '<li><a href="' + base + l[1] + '">' + esc(l[0]) + "</a></li>"; }).join("") + "</ul>" +
      '<div class="ap-more">Still stuck? <button type="button" class="ap-b" data-go="ask">Ask the community</button>' +
      '<button type="button" class="ap-b" data-go="bug">Report a bug</button></div>';
    wireBack();
    body.querySelectorAll("[data-go]").forEach(function (b) {
      b.addEventListener("click", function () { b.getAttribute("data-go") === "bug" ? bug() : ask(t); });
    });
    if (t.limits) studioState().then(function (st) {
      var lim = st && st.public && st.limits, p = body.querySelector(".ap-lim");
      if (lim && p) { p.textContent = "On this public Space, an upload may have up to " + lim.upload_mb + " MB and " + lim.rows.toLocaleString("en-US") +
                      " rows, and training stops after " + lim.epochs + " epochs. For larger datasets, run MEIDNet on your own computer."; p.hidden = false; }
    });
    focusFirst();
  }

  function ask(topic) {
    var subject = topic ? topic.title : "";
    body.innerHTML = back() + "<h3>Ask the community</h3>" +
      "<p>Questions are answered in the Space's public discussions, so that the answer helps the next person too.</p>" +
      '<label for="ap-t">Title</label><input id="ap-t" type="text" maxlength="120" placeholder="One line: what are you trying to do?" value="' + esc(subject) + '">' +
      '<label for="ap-q">Your question</label><textarea id="ap-q" rows="5" placeholder="What you are trying to do, what you tried, and what happened."></textarea>' +
      '<label class="ap-check"><input type="checkbox" id="ap-inc" checked> Include the technical details below (software and settings, no data)</label>' +
      '<textarea id="ap-d" class="ap-diag" rows="6" aria-label="Technical details" spellcheck="false">Collecting…</textarea>' +
      '<div class="ap-row"><button type="button" class="ap-b ap-p" id="ap-hf">Post on Hugging Face</button></div>' +
      '<p class="ap-msg" id="ap-m">Opens a new discussion with your text; a Hugging Face account is needed to post.</p>';
    wireBack();
    details().then(function (d) { var x = el("ap-d"); if (x) x.value = d; });
    el("ap-inc").addEventListener("change", function () { el("ap-d").hidden = !this.checked; });
    el("ap-hf").addEventListener("click", function () {
      var q = el("ap-q").value.trim(), title = el("ap-t").value.trim() || q.split("\n")[0].slice(0, 90);
      if (!q) { el("ap-q").focus(); el("ap-m").textContent = "Write your question first."; return; }
      var text = q + (el("ap-inc").checked ? "\n\n```text\n" + el("ap-d").value.trim() + "\n```" : "");
      copy(text).then(function (ok) {
        openTab(hfUrl(title, text));
        el("ap-m").textContent = "Opened in a new tab." + (ok ? " Your text is also on the clipboard, in case the form appears empty after signing in." : "");
      });
    });
    el("ap-t").focus();
  }

  function bug() {
    body.innerHTML = back() + "<h3>Report a bug</h3>" +
      "<p>Bugs are tracked on GitHub. Describe what happened; the technical details help to reproduce it.</p>" +
      '<label for="ap-w">What happened?</label><textarea id="ap-w" rows="4" placeholder="Steps, and the message you saw."></textarea>' +
      '<label for="ap-e">What did you expect? <small>(optional)</small></label><textarea id="ap-e" rows="2"></textarea>' +
      '<label for="ap-d">Technical details <small>(edit freely: software and settings, no data)</small></label>' +
      '<textarea id="ap-d" class="ap-diag" rows="7" spellcheck="false">Collecting…</textarea>' +
      '<div class="ap-row"><button type="button" class="ap-b ap-p" id="ap-gh">Open a GitHub issue</button>' +
      '<button type="button" class="ap-b" id="ap-hf">Post on Hugging Face instead</button></div>' +
      '<p class="ap-msg" id="ap-m">Opens a pre-filled form in a new tab; nothing is posted until you submit it there.</p>';
    wireBack();
    details().then(function (d) { var x = el("ap-d"); if (x) x.value = d; });
    function read() {
      var w = el("ap-w").value.trim();
      if (!w) { el("ap-w").focus(); el("ap-m").textContent = "Describe what happened first."; return null; }
      return {w: w, e: el("ap-e").value.trim(), d: el("ap-d").value.trim(), title: "[bug] " + w.split("\n")[0].slice(0, 80)};
    }
    el("ap-gh").addEventListener("click", function () {
      var r = read(); if (!r) return;
      openTab(ghBugUrl(r.title, r.w, r.e, r.d));
      el("ap-m").textContent = "Opened in a new tab. A GitHub account is needed to submit.";
    });
    el("ap-hf").addEventListener("click", function () {
      var r = read(); if (!r) return;
      var text = r.w + (r.e ? "\n\nExpected: " + r.e : "") + "\n\n```text\n" + r.d + "\n```";
      copy(text).then(function (ok) {
        openTab(hfUrl(r.title, text));
        el("ap-m").textContent = "Opened in a new tab." + (ok ? " Your text is also on the clipboard." : "");
      });
    });
    el("ap-w").focus();
  }

  function focusFirst() { var f = body.querySelector("button:not(.ap-back), a, textarea, input"); if (f) f.focus({preventScroll: true}); }

  function open() {
    panel.classList.toggle("ap-dark", isDark());
    panel.hidden = false; btn.setAttribute("aria-expanded", "true");
    home();
  }
  function close() { panel.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.focus({preventScroll: true}); }

  function mount() {
    if (el("ask-prism")) return;
    var style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
    btn = document.createElement("button");
    btn.type = "button"; btn.className = "ap-btn"; btn.id = "ask-prism-btn";
    btn.setAttribute("aria-haspopup", "dialog"); btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-controls", "ask-prism");
    btn.innerHTML = mark("ap-g1") + "<span>Ask <b>PRISM</b></span>";
    panel = document.createElement("section");
    panel.className = "ap"; panel.id = "ask-prism"; panel.hidden = true;
    panel.setAttribute("role", "dialog"); panel.setAttribute("aria-labelledby", "ap-title");
    panel.innerHTML = '<div class="ap-head">' + mark("ap-g2") + '<div><h2 id="ap-title">Ask PRISM</h2><p>MEIDNet Prism help</p></div>' +
      '<button type="button" class="ap-x" aria-label="Close">×</button></div><div class="ap-body"></div>' +
      '<p class="ap-note">Nothing is sent from this panel. Questions and reports open on Hugging Face or GitHub, where you can ' +
      "edit them before posting. No table, structure or file is included.</p>";
    body = panel.querySelector(".ap-body");
    btn.addEventListener("click", open);
    panel.querySelector(".ap-x").addEventListener("click", close);
    panel.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); close(); } });
    panel.addEventListener("click", function (e) {   // documentation links stay in this tab, the rest open a new one
      var a = e.target.closest && e.target.closest("a[href]");
      if (a && /^https?:/.test(a.getAttribute("href"))) a.target = "_blank";
    });
    document.body.appendChild(btn); document.body.appendChild(panel);
    if (!/^\/docs\//.test(location.pathname) && base === "")    // a local Studio without the documentation
      studioState().then(function (st) { if (st && !st.docs_url) base = PUBLIC; });
    window.askPrism = {open: open, close: close, topic: function (id) { open(); show(id); }};
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
