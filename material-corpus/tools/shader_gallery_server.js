#!/usr/bin/env node
"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const manifestPath = path.join(repoRoot, "material-corpus", "cloth_wind_hlsl_all_live", "hlsl_all_manifest.json");
const port = Number(process.env.PORT || process.argv[2] || 8787);
const host = "127.0.0.1";

function loadManifest() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const entries = manifest.entries.map((entry, index) => {
    const absPath = path.resolve(repoRoot, entry.path);
    const code = fs.readFileSync(absPath, "utf8");
    const lines = code.split(/\r?\n/);
    const category = entry.browser_rel_path.split("/")[0] || "hlsl";
    const family = entry.browser_rel_path.split("/")[1] || "core";
    const preview = lines
      .filter((line) => line.trim() && !line.trim().startsWith("//"))
      .slice(0, 7)
      .join("\n");
    return {
      number: index + 1,
      id: entry.id || `shader-${index + 1}`,
      title: entry.title || path.basename(absPath, ".hlsl"),
      path: entry.path,
      browserRelPath: entry.browser_rel_path,
      sourceRelPath: entry.source_rel_path,
      conversion: entry.conversion,
      license: entry.license,
      source: entry.source,
      category,
      family,
      size: code.length,
      lineCount: lines.length,
      symbols: entry.symbols || [],
      keywords: entry.keywords || [],
      tags: entry.tags || [],
      visual: visualProfile(entry),
      preview,
      code,
    };
  });
  return {
    createdAt: manifest.created_at,
    count: entries.length,
    entries,
    categories: Array.from(new Set(entries.map((entry) => entry.category))).sort(),
    families: Array.from(new Set(entries.map((entry) => entry.family))).sort(),
  };
}

let cache = loadManifest();

function json(res, value) {
  const body = JSON.stringify(value);
  res.writeHead(200, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(body);
}

function text(res, status, value) {
  res.writeHead(status, {"content-type": "text/plain; charset=utf-8"});
  res.end(value);
}

function html(res, value) {
  res.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(value);
}

function apiShaders(query) {
  const page = Math.max(1, Number(query.page || 1));
  const pageSize = Math.max(12, Math.min(120, Number(query.pageSize || 48)));
  const search = String(query.q || "").trim().toLowerCase();
  const searchTerms = search.split(/\s+/).filter(Boolean);
  const category = String(query.category || "");
  const family = String(query.family || "");

  let items = cache.entries;
  if (category) items = items.filter((entry) => entry.category === category);
  if (family) items = items.filter((entry) => entry.family === family);
  if (searchTerms.length) {
    items = items.filter((entry) => {
      const haystack = [
        entry.title,
        entry.browserRelPath,
        entry.sourceRelPath,
        entry.conversion,
        entry.category,
        entry.family,
        ...entry.symbols,
        ...entry.tags,
        ...entry.keywords.slice(0, 16),
      ].join(" ").toLowerCase();
      return searchTerms.every((term) => haystack.includes(term));
    });
  }

  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pageCount);
  const start = (safePage - 1) * pageSize;
  const pageItems = items.slice(start, start + pageSize);
  return {
    total,
    page: safePage,
    pageSize,
    pageCount,
    items: pageItems.map((entry) => ({
      number: entry.number,
      id: entry.id,
      title: entry.title,
      browserRelPath: entry.browserRelPath,
      conversion: entry.conversion,
      category: entry.category,
      family: entry.family,
      size: entry.size,
      lineCount: entry.lineCount,
      symbols: entry.symbols.slice(0, 8),
      visual: entry.visual,
      preview: entry.preview,
    })),
  };
}

function visualProfile(entry) {
  const text = `${entry.title} ${entry.browser_rel_path} ${entry.source_rel_path}`.toLowerCase();
  const has = (word) => text.includes(word);
  let kind = "cloth";
  if (has("flag") || has("hoist")) kind = "flag";
  else if (has("curtain")) kind = "curtain";
  else if (has("cape")) kind = "cape";
  else if (has("scarf")) kind = "scarf";
  else if (has("skirt")) kind = "skirt";
  else if (has("sleeve")) kind = "sleeve";
  else if (has("tablecloth")) kind = "tablecloth";
  else if (has("tent")) kind = "tent";
  else if (has("sail")) kind = "sail";
  else if (has("micro") || has("wrinkle") || has("normal")) kind = "wrinkle";
  else if (has("gust")) kind = "gust";
  else if (has("banner")) kind = "banner";

  let style = "breezy";
  if (has("storm")) style = "storm";
  else if (has("gusty")) style = "gusty";
  else if (has("calm")) style = "calm";
  else if (has("toon")) style = "toon";
  else if (has("silk")) style = "silk";

  let scale = "medium";
  if (has("small")) scale = "small";
  else if (has("large")) scale = "large";
  else if (has("hero")) scale = "hero";

  const styleParams = {
    calm: {amp: 0.28, speed: 0.75, color: "#7fc7d8", accent: "#d5f7ff"},
    breezy: {amp: 0.44, speed: 1.0, color: "#82d1bd", accent: "#dcfff1"},
    gusty: {amp: 0.65, speed: 1.35, color: "#d5c36a", accent: "#fff1a8"},
    storm: {amp: 0.9, speed: 1.75, color: "#9bb2d9", accent: "#eef5ff"},
    toon: {amp: 0.55, speed: 1.15, color: "#75d9f0", accent: "#ffffff"},
    silk: {amp: 0.34, speed: 0.92, color: "#d89be8", accent: "#fff0ff"},
  };
  const scaleAmp = {small: 0.78, medium: 1.0, large: 1.22, hero: 1.42};
  const p = styleParams[style] || styleParams.breezy;
  return {
    kind,
    style,
    scale,
    amp: +(p.amp * (scaleAmp[scale] || 1)).toFixed(3),
    speed: p.speed,
    color: p.color,
    accent: p.accent,
    textureUrl: "https://cdn.polyhaven.com/asset_img/thumbs/rough_linen.png?width=512&height=512",
    textureSource: "Poly Haven rough_linen thumbnail, CC0 fabric reference",
    seed: hashString(text) % 10000,
  };
}

function hashString(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function apiShader(number) {
  const entry = cache.entries[Number(number) - 1];
  if (!entry) return null;
  return entry;
}

const server = http.createServer((req, res) => {
  const parsed = new URL(req.url, `http://${host}:${port}`);
  const query = Object.fromEntries(parsed.searchParams.entries());
  if (parsed.pathname === "/") return html(res, pageHtml());
  if (parsed.pathname === "/api/meta") {
    return json(res, {
      count: cache.count,
      createdAt: cache.createdAt,
      categories: cache.categories,
      families: cache.families,
    });
  }
  if (parsed.pathname === "/api/shaders") return json(res, apiShaders(query));
  const shaderMatch = parsed.pathname.match(/^\/api\/shader\/(\d+)$/);
  if (shaderMatch) {
    const shader = apiShader(shaderMatch[1]);
    if (!shader) return text(res, 404, "shader not found");
    return json(res, shader);
  }
  if (parsed.pathname === "/api/reload") {
    cache = loadManifest();
    return json(res, {ok: true, count: cache.count});
  }
  return text(res, 404, "not found");
});

server.listen(port, host, () => {
  console.log(`Lethe shader gallery: http://${host}:${port}/`);
  console.log(`Loaded ${cache.count} HLSL shaders`);
});

function pageHtml() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lethe HLSL Shader Gallery</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #101312; color: #edf4f0; }
    .app { height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header { display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; padding: 14px 18px; border-bottom: 1px solid #2d3934; background: #151b18; }
    h1 { margin: 0; font-size: 18px; letter-spacing: 0; }
    .bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    input, select, button { height: 36px; border: 1px solid #3b4c45; border-radius: 6px; background: #0d1210; color: #edf4f0; padding: 0 10px; font-size: 13px; }
    input { width: min(34vw, 420px); }
    button { cursor: pointer; min-width: 38px; }
    button:hover { background: #1f2a25; border-color: #5c7d70; }
    button:disabled { opacity: 0.35; cursor: default; }
    .pill { min-height: 28px; display: inline-flex; align-items: center; padding: 4px 8px; border: 1px solid #385047; background: #18231f; border-radius: 6px; color: #b9c9c1; font-size: 12px; }
    main { min-height: 0; display: grid; grid-template-columns: minmax(460px, 58%) 1fr; }
    .gallery { min-width: 0; overflow: auto; padding: 14px; background: #101512; border-right: 1px solid #2d3934; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
    .card { text-align: left; min-height: 228px; border: 1px solid #2e423a; border-radius: 8px; background: #151d1a; color: #e7f0eb; padding: 10px; display: grid; grid-template-rows: auto auto 118px auto; gap: 7px; }
    .card.active { border-color: #84b89f; background: #1a2722; }
    .card-title { font-size: 13px; font-weight: 700; overflow-wrap: anywhere; }
    .card-path { font-size: 11px; color: #9fb0a8; overflow-wrap: anywhere; }
    .cloth-preview { width: 100%; height: 118px; border: 1px solid #263832; border-radius: 6px; background: #0a0f0d; display: block; }
    .card-meta { display: flex; gap: 5px; flex-wrap: wrap; }
    .tag { color: #bed0c8; border: 1px solid #334a41; border-radius: 5px; padding: 2px 5px; font-size: 10px; }
    .viewer { min-width: 0; display: grid; grid-template-rows: auto 250px 1fr; background: #080c0b; }
    .viewer-head { padding: 14px 16px; border-bottom: 1px solid #2d3934; background: #111714; display: grid; gap: 8px; }
    .viewer-title { font-size: 18px; font-weight: 750; overflow-wrap: anywhere; }
    .viewer-meta { display: flex; gap: 7px; flex-wrap: wrap; }
    .hero-preview-wrap { border-bottom: 1px solid #2d3934; background: #0c1110; padding: 12px; }
    .hero-preview { width: 100%; height: 100%; border: 1px solid #2e423a; border-radius: 8px; background: #08100d; display: block; }
    pre { margin: 0; overflow: auto; padding: 16px; font: 12px/1.55 Consolas, Cascadia Mono, monospace; color: #d7efe4; }
    .footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 0 0; }
    @media (max-width: 980px) {
      header { grid-template-columns: 1fr; }
      input { width: 100%; }
      main { grid-template-columns: 1fr; grid-template-rows: 52vh 1fr; }
      .gallery { border-right: 0; border-bottom: 1px solid #2d3934; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div>
        <h1>Lethe Cloth Wind HLSL Gallery</h1>
        <div class="bar" style="margin-top:8px">
          <span class="pill" id="totalPill">Loading...</span>
          <span class="pill">HLSL only</span>
          <span class="pill">Arrow page browser</span>
        </div>
      </div>
      <div class="bar">
        <input id="query" placeholder="Search flag, cape, curtain, storm, wrinkle">
        <select id="category"></select>
        <select id="family"></select>
        <select id="pageSize">
          <option value="24">24/page</option>
          <option value="48" selected>48/page</option>
          <option value="72">72/page</option>
          <option value="96">96/page</option>
        </select>
        <button id="prev" title="Previous page">←</button>
        <button id="next" title="Next page">→</button>
      </div>
    </header>
    <main>
      <section class="gallery">
        <div class="grid" id="grid"></div>
        <div class="footer">
          <span class="pill" id="pageInfo">Page 1</span>
          <span class="pill">Tip: ← / → flip pages, Enter focuses search</span>
        </div>
      </section>
      <section class="viewer">
        <div class="viewer-head">
          <div class="viewer-title" id="shaderTitle">Select a shader</div>
          <div class="viewer-meta" id="shaderMeta"></div>
        </div>
        <div class="hero-preview-wrap">
          <canvas class="hero-preview" id="heroPreview" width="760" height="250"></canvas>
        </div>
        <pre><code id="shaderCode"></code></pre>
      </section>
    </main>
  </div>
  <script>
    const state = { page: 1, pageSize: 48, q: '', category: '', family: '', selected: null };
    const cameraState = { yaw: 0.72, pitch: -0.16, distance: 4.6, dragging: false, lastX: 0, lastY: 0 };
    const els = {
      query: document.getElementById('query'),
      category: document.getElementById('category'),
      family: document.getElementById('family'),
      pageSize: document.getElementById('pageSize'),
      grid: document.getElementById('grid'),
      prev: document.getElementById('prev'),
      next: document.getElementById('next'),
      pageInfo: document.getElementById('pageInfo'),
      totalPill: document.getElementById('totalPill'),
      shaderTitle: document.getElementById('shaderTitle'),
      shaderMeta: document.getElementById('shaderMeta'),
      shaderCode: document.getElementById('shaderCode'),
      heroPreview: document.getElementById('heroPreview'),
    };
    let currentItems = [];
    let currentShader = null;
    let hero3d = null;
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    async function getJson(path) {
      const res = await fetch(path, {cache: 'no-store'});
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }
    async function init() {
      const meta = await getJson('/api/meta');
      els.totalPill.textContent = meta.count + ' shaders';
      fillSelect(els.category, 'All categories', meta.categories);
      fillSelect(els.family, 'All families', meta.families);
      await loadPage();
    }
    function fillSelect(select, label, values) {
      select.innerHTML = '<option value="">' + esc(label) + '</option>' + values.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join('');
    }
    async function loadPage() {
      const params = new URLSearchParams({page: state.page, pageSize: state.pageSize, q: state.q, category: state.category, family: state.family});
      const data = await getJson('/api/shaders?' + params.toString());
      state.page = data.page;
      renderGrid(data.items);
      els.pageInfo.textContent = 'Page ' + data.page + ' / ' + data.pageCount + ' · ' + data.total + ' matches';
      els.prev.disabled = data.page <= 1;
      els.next.disabled = data.page >= data.pageCount;
      if (data.items.length && (!state.selected || !data.items.some(item => item.number === state.selected))) {
        await selectShader(data.items[0].number);
      }
    }
    function renderGrid(items) {
      currentItems = items;
      els.grid.innerHTML = items.map(item => '<button class="card ' + (item.number === state.selected ? 'active' : '') + '" data-number="' + item.number + '">' +
        '<div class="card-title">' + String(item.number).padStart(4, '0') + '. ' + esc(item.title) + '</div>' +
        '<div class="card-path">' + esc(item.browserRelPath) + '</div>' +
        '<canvas class="cloth-preview" width="260" height="118" data-number="' + item.number + '"></canvas>' +
        '<div class="card-meta"><span class="tag">' + esc(item.category) + '</span><span class="tag">' + esc(item.family) + '</span><span class="tag">' + item.lineCount + ' lines</span></div>' +
      '</button>').join('');
      for (const card of els.grid.querySelectorAll('.card')) {
        card.addEventListener('click', () => selectShader(Number(card.dataset.number)));
      }
    }
    async function selectShader(number) {
      const item = await getJson('/api/shader/' + number);
      state.selected = item.number;
      currentShader = item;
      els.shaderTitle.textContent = String(item.number).padStart(4, '0') + '. ' + item.title;
      els.shaderMeta.innerHTML = [item.browserRelPath, item.conversion, item.license, item.size + ' bytes', item.lineCount + ' lines', item.visual.textureSource || 'procedural cloth mesh']
        .map(v => '<span class="pill">' + esc(v) + '</span>').join('');
      els.shaderCode.textContent = item.code;
      for (const card of els.grid.querySelectorAll('.card')) {
        card.classList.toggle('active', Number(card.dataset.number) === number);
      }
      if (hero3d) hero3d.profile = item.visual;
    }
    function drawPreview(canvas, item, t, large = false) {
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;
      const p = item.visual || {kind:'cloth', amp:0.5, speed:1, color:'#82d1bd', accent:'#dcfff1', seed:1};
      ctx.clearRect(0, 0, w, h);
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, '#09110f');
      bg.addColorStop(1, '#13201c');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
      drawWindStreaks(ctx, w, h, p, t);
      const shape = clothShape(p.kind, w, h, large);
      drawClothMesh(ctx, shape, p, t, large);
      drawPins(ctx, shape, p.kind);
    }
    function clothShape(kind, w, h, large) {
      const pad = large ? 34 : 18;
      if (kind === 'scarf' || kind === 'sleeve') return {x: pad, y: h * 0.33, width: w - pad * 2, height: h * 0.28, cols: 18, rows: 4};
      if (kind === 'skirt') return {x: w * 0.22, y: pad, width: w * 0.56, height: h - pad * 1.5, cols: 14, rows: 12};
      if (kind === 'cape') return {x: w * 0.25, y: pad, width: w * 0.5, height: h - pad * 1.5, cols: 13, rows: 14};
      if (kind === 'curtain' || kind === 'banner') return {x: pad, y: pad, width: w - pad * 2, height: h - pad * 1.7, cols: 18, rows: 11};
      if (kind === 'tent') return {x: w * 0.18, y: pad, width: w * 0.64, height: h - pad * 1.6, cols: 14, rows: 10};
      if (kind === 'sail') return {x: w * 0.2, y: pad, width: w * 0.58, height: h - pad * 1.5, cols: 13, rows: 13};
      return {x: pad, y: h * 0.23, width: w - pad * 2, height: h * 0.56, cols: 18, rows: 10};
    }
    function clothPoint(shape, p, c, r, t) {
      const u = c / shape.cols;
      const v = r / shape.rows;
      let x = shape.x + u * shape.width;
      let y = shape.y + v * shape.height;
      const phase = t * p.speed + p.seed * 0.013;
      let pin = u;
      if (p.kind === 'curtain' || p.kind === 'banner') pin = v;
      if (p.kind === 'cape') pin = v * (0.65 + Math.abs(u - 0.5));
      if (p.kind === 'scarf' || p.kind === 'sleeve') pin = Math.abs(u - 0.08);
      if (p.kind === 'skirt') pin = v;
      if (p.kind === 'tent') pin = Math.min(v * 1.2, Math.abs(u - 0.5) * 1.8);
      if (p.kind === 'sail') pin = u * 0.75 + v * 0.25;
      const free = smooth(0.04, 0.42, pin);
      const wave = Math.sin(u * 10.0 + v * 4.2 + phase * 2.2) * 0.65
        + Math.sin(u * 24.0 - phase * 3.1 + p.seed) * 0.22
        + Math.sin((u - v) * 15.0 + phase * 1.4) * 0.18;
      const amp = p.amp * free;
      if (p.kind === 'curtain') {
        x += wave * amp * 18;
        y += Math.sin(u * 34 + phase) * amp * 3;
      } else if (p.kind === 'cape') {
        x += wave * amp * 16;
        y += Math.sin(u * 7 - phase) * amp * 9 * v;
      } else if (p.kind === 'scarf' || p.kind === 'sleeve') {
        y += wave * amp * 20;
        x += Math.sin(v * 9 + phase) * amp * 5;
      } else if (p.kind === 'skirt') {
        const spread = (u - 0.5) * v * 36;
        x += spread + wave * amp * 9;
        y += Math.sin(u * 28 + phase) * amp * 6 * v;
      } else if (p.kind === 'tent') {
        y -= Math.sin(u * Math.PI) * shape.height * 0.22;
        x += wave * amp * 10;
      } else if (p.kind === 'sail') {
        x += wave * amp * 18 + Math.sin(v * Math.PI) * 12;
        y += Math.sin(u * 8 + phase) * amp * 5;
      } else {
        y += wave * amp * 18;
        x += Math.sin(v * 8 + phase) * amp * 8 * u;
      }
      return {x, y, u, v, free};
    }
    function drawClothMesh(ctx, shape, p, t, large) {
      const points = [];
      for (let r = 0; r <= shape.rows; r++) {
        const row = [];
        for (let c = 0; c <= shape.cols; c++) row.push(clothPoint(shape, p, c, r, t));
        points.push(row);
      }
      for (let r = 0; r < shape.rows; r++) {
        for (let c = 0; c < shape.cols; c++) {
          const a = points[r][c], b = points[r][c + 1], d = points[r + 1][c], e = points[r + 1][c + 1];
          const shade = 0.62 + 0.22 * Math.sin(a.u * 18 + t * p.speed * 2) + 0.16 * a.free;
          ctx.fillStyle = mixColor(p.color, '#ffffff', Math.max(0, Math.min(0.34, shade - 0.58)));
          ctx.beginPath();
          ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(e.x, e.y); ctx.lineTo(d.x, d.y); ctx.closePath();
          ctx.fill();
        }
      }
      ctx.strokeStyle = 'rgba(235,255,246,0.26)';
      ctx.lineWidth = large ? 1.0 : 0.75;
      for (let r = 0; r <= shape.rows; r++) {
        ctx.beginPath();
        points[r].forEach((pt, i) => i ? ctx.lineTo(pt.x, pt.y) : ctx.moveTo(pt.x, pt.y));
        ctx.stroke();
      }
      for (let c = 0; c <= shape.cols; c += large ? 1 : 2) {
        ctx.beginPath();
        for (let r = 0; r <= shape.rows; r++) {
          const pt = points[r][c];
          r ? ctx.lineTo(pt.x, pt.y) : ctx.moveTo(pt.x, pt.y);
        }
        ctx.stroke();
      }
      ctx.strokeStyle = p.accent;
      ctx.globalAlpha = 0.75;
      ctx.lineWidth = large ? 2 : 1.2;
      ctx.beginPath();
      points[Math.floor(shape.rows * 0.5)].forEach((pt, i) => i ? ctx.lineTo(pt.x, pt.y) : ctx.moveTo(pt.x, pt.y));
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    function drawPins(ctx, shape, kind) {
      ctx.fillStyle = '#f5f1c2';
      const pins = [];
      if (kind === 'curtain' || kind === 'banner') {
        for (let i = 0; i <= 8; i++) pins.push({x: shape.x + shape.width * i / 8, y: shape.y});
      } else if (kind === 'cape') {
        pins.push({x: shape.x + shape.width * 0.35, y: shape.y}, {x: shape.x + shape.width * 0.65, y: shape.y});
      } else {
        for (let i = 0; i <= 5; i++) pins.push({x: shape.x, y: shape.y + shape.height * i / 5});
      }
      for (const pin of pins) {
        ctx.beginPath();
        ctx.arc(pin.x, pin.y, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    function drawWindStreaks(ctx, w, h, p, t) {
      ctx.strokeStyle = 'rgba(190, 238, 222, 0.16)';
      ctx.lineWidth = 1;
      for (let i = 0; i < 9; i++) {
        const y = (i + 1) * h / 10 + Math.sin(t * p.speed + i) * 4;
        const x = ((t * 36 * p.speed + i * 71 + p.seed) % (w + 80)) - 80;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.bezierCurveTo(x + 25, y - 8, x + 55, y + 8, x + 85, y);
        ctx.stroke();
      }
    }
    function smooth(a, b, x) {
      const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
      return t * t * (3 - 2 * t);
    }
    function mixColor(a, b, t) {
      const ca = parseColor(a), cb = parseColor(b);
      const v = ca.map((x, i) => Math.round(x + (cb[i] - x) * t));
      return 'rgb(' + v[0] + ',' + v[1] + ',' + v[2] + ')';
    }
    function parseColor(hex) {
      const s = hex.replace('#', '');
      return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
    }
    function initHero3D(canvas) {
      const gl = canvas.getContext('webgl', {antialias: true, alpha: false});
      if (!gl) return null;
      const vs = 'attribute vec3 aPos; attribute vec3 aNormal; attribute vec2 aUv; uniform mat4 uMvp; varying vec3 vNormal; varying vec2 vUv; varying vec3 vPos; void main(){ vNormal=aNormal; vUv=aUv; vPos=aPos; gl_Position=uMvp*vec4(aPos,1.0); }';
      const fs = 'precision mediump float; varying vec3 vNormal; varying vec2 vUv; varying vec3 vPos; uniform vec3 uBase; uniform vec3 uAccent; uniform vec3 uLight; void main(){ vec3 n=normalize(vNormal); float diff=max(dot(n,normalize(uLight)),0.0); float weave=(sin(vUv.x*95.0)+sin(vUv.y*130.0))*0.035; float stripe=smoothstep(0.46,0.54,fract(vUv.x*18.0))*0.08; float rim=pow(1.0-max(abs(n.z),0.0),2.0)*0.18; vec3 col=mix(uBase,uAccent,0.16+stripe+rim)+weave; col*=0.34+diff*0.78; gl_FragColor=vec4(col,1.0); }';
      const program = makeProgram(gl, vs, fs);
      const loc = {
        pos: gl.getAttribLocation(program, 'aPos'),
        normal: gl.getAttribLocation(program, 'aNormal'),
        uv: gl.getAttribLocation(program, 'aUv'),
        mvp: gl.getUniformLocation(program, 'uMvp'),
        base: gl.getUniformLocation(program, 'uBase'),
        accent: gl.getUniformLocation(program, 'uAccent'),
        light: gl.getUniformLocation(program, 'uLight'),
      };
      const cols = 42, rows = 26;
      const vertexCount = (cols + 1) * (rows + 1);
      const positions = new Float32Array(vertexCount * 3);
      const normals = new Float32Array(vertexCount * 3);
      const uvs = new Float32Array(vertexCount * 2);
      const indices = [];
      const lineIndices = [];
      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const i = r * (cols + 1) + c;
          uvs[i * 2] = c / cols;
          uvs[i * 2 + 1] = r / rows;
          if (c < cols && r < rows) {
            const a = i, b = i + 1, d = i + cols + 1, e = d + 1;
            indices.push(a, d, b, b, d, e);
          }
          if (c < cols) lineIndices.push(i, i + 1);
          if (r < rows) lineIndices.push(i, i + cols + 1);
        }
      }
      const posBuffer = gl.createBuffer();
      const normalBuffer = gl.createBuffer();
      const uvBuffer = gl.createBuffer();
      const indexBuffer = gl.createBuffer();
      const lineBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, uvs, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, lineBuffer);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(lineIndices), gl.STATIC_DRAW);
      attachHeroControls(canvas);
      return {gl, program, loc, cols, rows, positions, normals, uvs, indices, lineIndices, posBuffer, normalBuffer, uvBuffer, indexBuffer, lineBuffer, profile: null};
    }
    function makeProgram(gl, vsSource, fsSource) {
      const vs = compileShader(gl, gl.VERTEX_SHADER, vsSource);
      const fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSource);
      const program = gl.createProgram();
      gl.attachShader(program, vs); gl.attachShader(program, fs); gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
      return program;
    }
    function compileShader(gl, type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    }
    function attachHeroControls(canvas) {
      canvas.addEventListener('pointerdown', (event) => {
        cameraState.dragging = true;
        cameraState.lastX = event.clientX;
        cameraState.lastY = event.clientY;
        canvas.setPointerCapture(event.pointerId);
      });
      canvas.addEventListener('pointermove', (event) => {
        if (!cameraState.dragging) return;
        const dx = event.clientX - cameraState.lastX;
        const dy = event.clientY - cameraState.lastY;
        cameraState.lastX = event.clientX;
        cameraState.lastY = event.clientY;
        cameraState.yaw += dx * 0.008;
        cameraState.pitch = Math.max(-0.9, Math.min(0.65, cameraState.pitch + dy * 0.006));
      });
      canvas.addEventListener('pointerup', () => { cameraState.dragging = false; });
      canvas.addEventListener('wheel', (event) => {
        event.preventDefault();
        cameraState.distance = Math.max(2.6, Math.min(8.5, cameraState.distance + event.deltaY * 0.004));
      }, {passive: false});
    }
    function drawHero3D(scene, item, t) {
      const gl = scene.gl;
      const canvas = gl.canvas;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      if (!cameraState.dragging) cameraState.yaw += 0.0028;
      const p = item.visual || {kind:'cloth', amp:0.5, speed:1, color:'#82d1bd', accent:'#dcfff1', seed:1};
      updateHeroMesh(scene, p, t);
      const eye = [
        Math.sin(cameraState.yaw) * Math.cos(cameraState.pitch) * cameraState.distance,
        Math.sin(cameraState.pitch) * cameraState.distance + 0.15,
        Math.cos(cameraState.yaw) * Math.cos(cameraState.pitch) * cameraState.distance,
      ];
      const proj = mat4Perspective(42 * Math.PI / 180, width / height, 0.1, 100);
      const view = mat4LookAt(eye, [0, 0, 0], [0, 1, 0]);
      const mvp = mat4Multiply(proj, view);
      const base = parseColor(p.color).map(v => v / 255);
      const accent = parseColor(p.accent).map(v => v / 255);
      gl.viewport(0, 0, width, height);
      gl.enable(gl.DEPTH_TEST);
      gl.clearColor(0.035, 0.055, 0.047, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(scene.program);
      gl.bindBuffer(gl.ARRAY_BUFFER, scene.posBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, scene.positions, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(scene.loc.pos);
      gl.vertexAttribPointer(scene.loc.pos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, scene.normalBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, scene.normals, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(scene.loc.normal);
      gl.vertexAttribPointer(scene.loc.normal, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, scene.uvBuffer);
      gl.enableVertexAttribArray(scene.loc.uv);
      gl.vertexAttribPointer(scene.loc.uv, 2, gl.FLOAT, false, 0, 0);
      gl.uniformMatrix4fv(scene.loc.mvp, false, new Float32Array(mvp));
      gl.uniform3fv(scene.loc.base, new Float32Array(base));
      gl.uniform3fv(scene.loc.accent, new Float32Array(accent));
      gl.uniform3fv(scene.loc.light, new Float32Array([0.35, 0.8, 0.55]));
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, scene.indexBuffer);
      gl.drawElements(gl.TRIANGLES, scene.indices.length, gl.UNSIGNED_SHORT, 0);
      gl.uniform3fv(scene.loc.base, new Float32Array([0.82, 0.95, 0.88]));
      gl.uniform3fv(scene.loc.accent, new Float32Array([0.9, 1.0, 0.96]));
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, scene.lineBuffer);
      gl.drawElements(gl.LINES, scene.lineIndices.length, gl.UNSIGNED_SHORT, 0);
    }
    function updateHeroMesh(scene, p, t) {
      const cols = scene.cols, rows = scene.rows;
      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const i = r * (cols + 1) + c;
          const u = c / cols, v = r / rows;
          const pos = cloth3DPoint(u, v, p, t);
          scene.positions[i * 3] = pos[0];
          scene.positions[i * 3 + 1] = pos[1];
          scene.positions[i * 3 + 2] = pos[2];
        }
      }
      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const i = r * (cols + 1) + c;
          const c0 = Math.max(0, c - 1), c1 = Math.min(cols, c + 1);
          const r0 = Math.max(0, r - 1), r1 = Math.min(rows, r + 1);
          const ix0 = (r * (cols + 1) + c0) * 3, ix1 = (r * (cols + 1) + c1) * 3;
          const iy0 = (r0 * (cols + 1) + c) * 3, iy1 = (r1 * (cols + 1) + c) * 3;
          const tx = [scene.positions[ix1] - scene.positions[ix0], scene.positions[ix1+1] - scene.positions[ix0+1], scene.positions[ix1+2] - scene.positions[ix0+2]];
          const ty = [scene.positions[iy1] - scene.positions[iy0], scene.positions[iy1+1] - scene.positions[iy0+1], scene.positions[iy1+2] - scene.positions[iy0+2]];
          const n = normalize3(cross3(tx, ty));
          scene.normals[i * 3] = n[0]; scene.normals[i * 3 + 1] = n[1]; scene.normals[i * 3 + 2] = n[2];
        }
      }
    }
    function cloth3DPoint(u, v, p, t) {
      const phase = t * p.speed + p.seed * 0.021;
      let x = (u - 0.5) * 3.2;
      let y = (0.5 - v) * 2.0;
      let z = 0;
      let pin = u;
      if (p.kind === 'curtain' || p.kind === 'banner') pin = v;
      if (p.kind === 'cape') pin = v * (0.65 + Math.abs(u - 0.5));
      if (p.kind === 'scarf' || p.kind === 'sleeve') pin = Math.abs(u - 0.08);
      if (p.kind === 'skirt') pin = v;
      if (p.kind === 'tent') pin = Math.min(v * 1.2, Math.abs(u - 0.5) * 1.8);
      if (p.kind === 'sail') pin = u * 0.75 + v * 0.25;
      const free = smooth(0.04, 0.42, pin);
      const wave = Math.sin(u * 10 + v * 3.1 + phase * 2.1) * 0.55
        + Math.sin(u * 23 - phase * 3.0 + p.seed) * 0.25
        + Math.sin((u - v) * 16 + phase * 1.35) * 0.2;
      z = wave * p.amp * free * 0.44;
      if (p.kind === 'curtain') {
        x += wave * p.amp * 0.18;
        z += Math.sin(u * 42 + phase) * p.amp * 0.08 * free;
      } else if (p.kind === 'cape') {
        y -= v * v * 0.35;
        x += wave * p.amp * 0.12;
      } else if (p.kind === 'scarf' || p.kind === 'sleeve') {
        y = (0.5 - v) * 0.75;
        z += Math.sin(u * 18 + phase) * p.amp * 0.35 * free;
      } else if (p.kind === 'skirt') {
        const flare = v * 0.8;
        x *= 0.45 + flare;
        y = 0.95 - v * 2.1;
        z += Math.sin(u * 30 + phase) * p.amp * 0.14 * v;
      } else if (p.kind === 'tent') {
        y += Math.sin(u * Math.PI) * 0.75;
        z += wave * p.amp * 0.2;
      } else if (p.kind === 'sail') {
        x += Math.sin(v * Math.PI) * 0.45;
        z += Math.sin(v * Math.PI) * p.amp * 0.55 * free;
      }
      return [x, y, z];
    }
    function cross3(a, b) { return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]; }
    function normalize3(a) { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0]/l, a[1]/l, a[2]/l]; }
    function mat4Perspective(fovy, aspect, near, far) {
      const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
      return [f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0];
    }
    function mat4LookAt(eye, center, up) {
      const z = normalize3([eye[0]-center[0], eye[1]-center[1], eye[2]-center[2]]);
      const x = normalize3(cross3(up, z));
      const y = cross3(z, x);
      return [x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0, -dot3(x,eye),-dot3(y,eye),-dot3(z,eye),1];
    }
    function mat4Multiply(a, b) {
      const out = new Array(16).fill(0);
      for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) for (let k = 0; k < 4; k++) out[c*4+r] += a[k*4+r] * b[c*4+k];
      return out;
    }
    function dot3(a, b) { return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]; }
    function animationLoop(ms) {
      const t = ms / 1000;
      const byNumber = new Map(currentItems.map(item => [item.number, item]));
      for (const canvas of els.grid.querySelectorAll('canvas.cloth-preview')) {
        const item = byNumber.get(Number(canvas.dataset.number));
        if (item) drawPreview(canvas, item, t, false);
      }
      if (currentShader && hero3d) drawHero3D(hero3d, currentShader, t);
      else if (currentShader) drawPreview(els.heroPreview, currentShader, t, true);
      requestAnimationFrame(animationLoop);
    }
    let timer = null;
    els.query.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.q = els.query.value; state.page = 1; loadPage(); }, 120);
    });
    els.category.addEventListener('change', () => { state.category = els.category.value; state.page = 1; loadPage(); });
    els.family.addEventListener('change', () => { state.family = els.family.value; state.page = 1; loadPage(); });
    els.pageSize.addEventListener('change', () => { state.pageSize = Number(els.pageSize.value); state.page = 1; loadPage(); });
    els.prev.addEventListener('click', () => { state.page = Math.max(1, state.page - 1); loadPage(); });
    els.next.addEventListener('click', () => { state.page += 1; loadPage(); });
    window.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft') els.prev.click();
      if (event.key === 'ArrowRight') els.next.click();
      if (event.key === 'Enter' && document.activeElement !== els.query) els.query.focus();
    });
    hero3d = initHero3D(els.heroPreview);
    init().catch(err => {
      els.grid.innerHTML = '<div class="pill">Failed to load: ' + esc(err.message) + '</div>';
      console.error(err);
    });
    requestAnimationFrame(animationLoop);
  </script>
</body>
</html>`;
}
