#!/usr/bin/env node
"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const manifestPath = path.join(repoRoot, "material-corpus", "underwater_wave_hlsl", "underwater_wave_manifest.json");
const reviewPath = path.join(repoRoot, "material-corpus", "underwater_wave_hlsl", "dedupe_review.json");
const port = Number(process.env.PORT || process.argv[2] || 8789);
const host = "127.0.0.1";

function loadData() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const review = JSON.parse(fs.readFileSync(reviewPath, "utf8"));
  const entries = manifest.entries.map((entry) => {
    const absPath = path.resolve(path.join(repoRoot, "material-corpus"), entry.path);
    const code = fs.readFileSync(absPath, "utf8");
    return {
      ...entry,
      code,
      size: code.length,
      lineCount: code.split(/\r?\n/).length,
      visual: visualProfile(entry),
    };
  });
  return {
    count: entries.length,
    entries,
    review,
    families: [...new Set(entries.map((e) => e.family))].sort(),
    caustics: [...new Set(entries.map((e) => e.caustic))].sort(),
    depths: [...new Set(entries.map((e) => e.depth))].sort(),
    colors: [...new Set(entries.map((e) => e.color))].sort(),
  };
}

function visualProfile(entry) {
  const colorMap = {
    cyan: ["#0bbbea", "#d8ffff"],
    tropical: ["#00d1a8", "#e0fff4"],
    deep_blue: ["#1d4fd7", "#bcd6ff"],
    green_lagoon: ["#16996c", "#d3ffe7"],
    moonlit: ["#6385ff", "#f0f5ff"],
    murky_teal: ["#1b706c", "#c6e4d8"],
  };
  const motionAmp = {calm: 0.35, drifting: 0.48, tidal: 0.62, surging: 0.78, storm_underwater: 1.0}[entry.motion] || 0.55;
  const scaleAmp = {macro: 0.75, medium: 1.0, fine: 1.28}[entry.scale] || 1;
  const causticAmp = entry.caustic === "none" ? 0.05 : entry.caustic.includes("sharp") ? 0.95 : 0.62;
  const depth = {shallow: 0.22, midwater: 0.48, deep: 0.72, abyss_fade: 0.9}[entry.depth] || 0.5;
  return {
    family: entry.family,
    caustic: entry.caustic,
    depth: entry.depth,
    distortion: entry.distortion,
    color: entry.color,
    motion: entry.motion,
    scale: entry.scale,
    base: colorMap[entry.color]?.[0] || "#0bbbea",
    highlight: colorMap[entry.color]?.[1] || "#e0ffff",
    waveAmp: +(motionAmp * scaleAmp).toFixed(3),
    causticAmp,
    depthAmount: depth,
    speed: +(0.45 + motionAmp * 1.2).toFixed(3),
    refraction: entry.distortion === "screen_refraction" ? 0.9 : entry.distortion === "vortex_shear" ? 0.72 : 0.5,
    seed: hash(`${entry.title}|${entry.fingerprint}`) % 10000,
  };
}

function hash(value) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

let cache = loadData();

function sendJson(res, value) {
  res.writeHead(200, {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"});
  res.end(JSON.stringify(value));
}

function sendHtml(res, value) {
  res.writeHead(200, {"content-type": "text/html; charset=utf-8", "cache-control": "no-store"});
  res.end(value);
}

function shaders(query) {
  const page = Math.max(1, Number(query.page || 1));
  const pageSize = Math.max(12, Math.min(100, Number(query.pageSize || 40)));
  const terms = String(query.q || "").toLowerCase().split(/\s+/).filter(Boolean);
  const family = String(query.family || "");
  const caustic = String(query.caustic || "");
  let items = cache.entries;
  if (family) items = items.filter((e) => e.family === family);
  if (caustic) items = items.filter((e) => e.caustic === caustic);
  if (terms.length) {
    items = items.filter((e) => {
      const hay = [e.title, e.family, e.caustic, e.depth, e.distortion, e.color, e.motion, e.scale].join(" ").toLowerCase();
      return terms.every((term) => hay.includes(term));
    });
  }
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, pageCount);
  const chunk = items.slice((safePage - 1) * pageSize, safePage * pageSize);
  return {
    total,
    page: safePage,
    pageSize,
    pageCount,
    items: chunk.map((e) => ({
      order: e.order,
      title: e.title,
      family: e.family,
      caustic: e.caustic,
      depth: e.depth,
      distortion: e.distortion,
      color: e.color,
      motion: e.motion,
      scale: e.scale,
      lineCount: e.lineCount,
      visual: e.visual,
    })),
  };
}

function shader(order) {
  return cache.entries.find((entry) => entry.order === Number(order));
}

const server = http.createServer((req, res) => {
  const parsed = new URL(req.url, `http://${host}:${port}`);
  const query = Object.fromEntries(parsed.searchParams.entries());
  if (parsed.pathname === "/") return sendHtml(res, page());
  if (parsed.pathname === "/api/meta") return sendJson(res, {count: cache.count, families: cache.families, caustics: cache.caustics, depths: cache.depths, colors: cache.colors, review: cache.review});
  if (parsed.pathname === "/api/shaders") return sendJson(res, shaders(query));
  const match = parsed.pathname.match(/^\/api\/shader\/(\d+)$/);
  if (match) {
    const item = shader(match[1]);
    if (!item) {
      res.writeHead(404, {"content-type": "text/plain; charset=utf-8"});
      res.end("shader not found");
      return;
    }
    return sendJson(res, item);
  }
  res.writeHead(404, {"content-type": "text/plain; charset=utf-8"});
  res.end("not found");
});

server.listen(port, host, () => {
  console.log(`Underwater wave gallery: http://${host}:${port}/`);
  console.log(`Loaded ${cache.count} reviewed shaders`);
});

function page() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lethe Underwater Wave Gallery</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #071015; color: #edf8ff; }
    .app { height: 100vh; display: grid; grid-template-rows: auto 1fr; }
    header { padding: 14px 18px; border-bottom: 1px solid #183846; background: #0b1820; display: grid; gap: 10px; }
    h1 { margin: 0; font-size: 18px; }
    .bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input, select, button { height: 34px; border: 1px solid #245064; background: #061117; color: #effaff; border-radius: 6px; padding: 0 10px; }
    input { width: min(34vw, 420px); }
    button { cursor: pointer; }
    button:hover { background: #102733; }
    .pill { display: inline-flex; min-height: 26px; align-items: center; border: 1px solid #245064; background: #0c2029; color: #b8dcea; border-radius: 6px; padding: 3px 8px; font-size: 12px; }
    main { min-height: 0; display: grid; grid-template-columns: minmax(460px, 56%) 1fr; }
    .gallery { overflow: auto; padding: 14px; border-right: 1px solid #183846; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
    .card { min-height: 210px; border: 1px solid #164154; border-radius: 8px; background: #0b1a22; color: #e6f8ff; text-align: left; padding: 10px; display: grid; grid-template-rows: auto auto 112px auto; gap: 7px; }
    .card.active { border-color: #8be9ff; background: #102b38; }
    .card-title { font-weight: 750; font-size: 13px; overflow-wrap: anywhere; }
    .card-sub { font-size: 11px; color: #9ec9d8; overflow-wrap: anywhere; }
    canvas.mini { width: 100%; height: 112px; border: 1px solid #163545; border-radius: 6px; background: #020b10; display: block; }
    .tagline { display: flex; gap: 5px; flex-wrap: wrap; }
    .viewer { min-width: 0; display: grid; grid-template-rows: auto 340px auto 1fr; background: #02090d; }
    .viewer-head { padding: 13px 15px; border-bottom: 1px solid #183846; background: #08141a; display: grid; gap: 7px; }
    .viewer-title { font-size: 18px; font-weight: 800; overflow-wrap: anywhere; }
    .hero { width: 100%; height: 100%; display: block; background: #020b10; border-bottom: 1px solid #183846; }
    .params { padding: 12px 15px; border-bottom: 1px solid #183846; background: #071117; display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 10px; }
    label { font-size: 12px; color: #add6e5; display: grid; gap: 5px; }
    input[type=range] { width: 100%; padding: 0; }
    pre { margin: 0; overflow: auto; padding: 14px; font: 12px/1.55 Consolas, Cascadia Mono, monospace; color: #d7f4ff; }
    .footer { padding-top: 10px; display: flex; justify-content: space-between; gap: 10px; }
    @media (max-width: 980px) { main { grid-template-columns: 1fr; grid-template-rows: 52vh 1fr; } .gallery { border-right: 0; border-bottom: 1px solid #183846; } }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="bar">
        <h1>Lethe Underwater Wave Gallery</h1>
        <span class="pill" id="total">Loading...</span>
        <span class="pill" id="review">review pending</span>
      </div>
      <div class="bar">
        <input id="query" placeholder="Search caustic, abyss, tropical, wake...">
        <select id="family"></select>
        <select id="caustic"></select>
        <select id="pageSize"><option>20</option><option selected>40</option><option>60</option><option>80</option></select>
        <button id="prev">←</button>
        <button id="next">→</button>
        <span class="pill" id="pageInfo">Page</span>
      </div>
    </header>
    <main>
      <section class="gallery"><div class="grid" id="grid"></div><div class="footer"><span class="pill">Click cards, use ← → pages</span></div></section>
      <section class="viewer">
        <div class="viewer-head"><div class="viewer-title" id="title">Select a shader</div><div class="bar" id="meta"></div></div>
        <canvas class="hero" id="hero" width="860" height="340"></canvas>
        <div class="params">
          <label>Wave Strength <input id="waveStrength" type="range" min="0" max="2" step="0.01" value="1"></label>
          <label>Speed <input id="speed" type="range" min="0" max="3" step="0.01" value="1"></label>
          <label>Caustics <input id="caustics" type="range" min="0" max="2" step="0.01" value="1"></label>
          <label>Depth <input id="depth" type="range" min="0" max="1" step="0.01" value="0.45"></label>
          <label>Refraction <input id="refraction" type="range" min="0" max="2" step="0.01" value="1"></label>
          <label>Turbidity <input id="turbidity" type="range" min="0" max="1" step="0.01" value="0.18"></label>
        </div>
        <pre><code id="code"></code></pre>
      </section>
    </main>
  </div>
  <script>
    const state = {page:1, pageSize:40, q:'', family:'', caustic:'', selected:null};
    const els = Object.fromEntries(['query','family','caustic','pageSize','prev','next','pageInfo','grid','title','meta','hero','code','total','review','waveStrength','speed','caustics','depth','refraction','turbidity'].map(id => [id, document.getElementById(id)]));
    let currentItems = [], currentShader = null;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    async function json(path){ const r = await fetch(path, {cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
    async function init(){
      const meta = await json('/api/meta');
      els.total.textContent = meta.count + ' shaders';
      els.review.textContent = 'review: ' + meta.review.generated_candidates + ' generated, ' + meta.review.rejected_similar + ' similar removed';
      fill(els.family, 'All families', meta.families);
      fill(els.caustic, 'All caustics', meta.caustics);
      await loadPage();
    }
    function fill(sel, label, items){ sel.innerHTML = '<option value="">' + esc(label) + '</option>' + items.map(x => '<option value="'+esc(x)+'">'+esc(x)+'</option>').join(''); }
    async function loadPage(){
      const qs = new URLSearchParams({page:state.page,pageSize:state.pageSize,q:state.q,family:state.family,caustic:state.caustic});
      const data = await json('/api/shaders?' + qs);
      state.page = data.page; currentItems = data.items; renderGrid(data.items);
      els.pageInfo.textContent = 'Page ' + data.page + ' / ' + data.pageCount + ' · ' + data.total + ' matches';
      els.prev.disabled = data.page <= 1; els.next.disabled = data.page >= data.pageCount;
      if(data.items.length && (!state.selected || !data.items.some(x => x.order === state.selected))) selectShader(data.items[0].order);
    }
    function renderGrid(items){
      els.grid.innerHTML = items.map(item => '<button class="card '+(item.order===state.selected?'active':'')+'" data-order="'+item.order+'">' +
        '<div class="card-title">'+String(item.order).padStart(3,'0')+'. '+esc(item.title)+'</div>' +
        '<div class="card-sub">'+esc(item.family)+' · '+esc(item.caustic)+' · '+esc(item.depth)+'</div>' +
        '<canvas class="mini" width="260" height="112" data-order="'+item.order+'"></canvas>' +
        '<div class="tagline"><span class="pill">'+esc(item.color)+'</span><span class="pill">'+esc(item.motion)+'</span><span class="pill">'+esc(item.distortion)+'</span></div></button>').join('');
      for(const c of els.grid.querySelectorAll('.card')) c.onclick = () => selectShader(Number(c.dataset.order));
    }
    async function selectShader(order){
      const item = await json('/api/shader/' + order); currentShader = item; state.selected = item.order;
      els.title.textContent = String(item.order).padStart(3,'0') + '. ' + item.title;
      els.meta.innerHTML = [item.family,item.caustic,item.depth,item.distortion,item.color,item.motion,item.lineCount+' lines'].map(x => '<span class="pill">'+esc(x)+'</span>').join('');
      els.code.textContent = item.code;
      els.depth.value = item.visual.depthAmount;
      els.caustics.value = Math.max(0.05, item.visual.causticAmp);
      els.waveStrength.value = item.visual.waveAmp;
      els.speed.value = item.visual.speed;
      els.refraction.value = item.visual.refraction;
      for(const c of els.grid.querySelectorAll('.card')) c.classList.toggle('active', Number(c.dataset.order) === item.order);
    }
    function drawWater(ctx, w, h, profile, t, big){
      const waveStrength = Number(els.waveStrength.value || 1);
      const speed = Number(els.speed.value || 1);
      const caustics = Number(els.caustics.value || 1);
      const depth = Number(els.depth.value || profile.depthAmount || 0.5);
      const refraction = Number(els.refraction.value || 1);
      const turbidity = Number(els.turbidity.value || 0.18);
      const base = parseColor(profile.base), hi = parseColor(profile.highlight);
      const grd = ctx.createLinearGradient(0,0,0,h);
      grd.addColorStop(0, rgb(mix(base, hi, 0.22)));
      grd.addColorStop(0.55, rgb(mix(base, [0,20,38], depth*0.55)));
      grd.addColorStop(1, rgb(mix(base, [0,5,14], 0.55 + depth*0.35)));
      ctx.fillStyle = grd; ctx.fillRect(0,0,w,h);
      const phase = t * speed * profile.speed + profile.seed * 0.01;
      ctx.globalAlpha = 0.16 + turbidity * 0.28;
      ctx.fillStyle = '#dfffff';
      for(let i=0;i<28;i++){
        const x = (Math.sin(i*11.7+phase*0.31)*0.5+0.5)*w;
        const y = (i/28*h + Math.sin(phase+i)*28) % h;
        const r = (big?42:20) * (0.4 + refraction*0.45);
        ctx.beginPath(); ctx.ellipse(x,y,r,r*0.18,Math.sin(i)*1.7,0,Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 0.75;
      ctx.lineWidth = big ? 1.5 : 1;
      for(let k=0;k<18;k++){
        ctx.strokeStyle = k%2 ? 'rgba(220,255,245,0.34)' : 'rgba(70,220,255,0.22)';
        ctx.beginPath();
        for(let x=0;x<=w;x+=8){
          const u = x/w;
          const y = h*(0.16 + k/22) + Math.sin(u*10 + phase*1.8 + k)*18*waveStrength + Math.sin(u*31 - phase*1.1)*6*refraction;
          x ? ctx.lineTo(x,y) : ctx.moveTo(x,y);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = Math.min(1, caustics * profile.causticAmp);
      ctx.lineWidth = big ? 2.0 : 1.2;
      for(let k=0;k<16;k++){
        ctx.strokeStyle = 'rgba(255,255,210,0.42)';
        ctx.beginPath();
        for(let x=0;x<=w;x+=7){
          const u=x/w, y=h*(0.25 + 0.5*((k*37)%100)/100) + Math.sin(u*24 + phase*2.2 + k)*10 + Math.cos(u*9 - phase + k)*8;
          x ? ctx.lineTo(x,y) : ctx.moveTo(x,y);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if(big) drawDepthGrid(ctx,w,h,phase,waveStrength,refraction);
    }
    function drawDepthGrid(ctx,w,h,phase,waveStrength,refraction){
      ctx.strokeStyle='rgba(180,240,255,0.18)'; ctx.lineWidth=1;
      for(let z=0;z<9;z++){
        const y=h*0.42+z*z*3.2;
        ctx.beginPath();
        for(let x=0;x<=w;x+=10){ const yy=y+Math.sin(x*0.02+phase+z)*4*waveStrength; x?ctx.lineTo(x,yy):ctx.moveTo(x,yy); }
        ctx.stroke();
      }
      for(let i=0;i<13;i++){
        const x=w*(i/12);
        ctx.beginPath();
        ctx.moveTo(w/2 + (x-w/2)*0.18, h*0.35);
        ctx.lineTo(x + Math.sin(phase+i)*10*refraction, h);
        ctx.stroke();
      }
    }
    function loop(ms){
      const t=ms/1000;
      const map=new Map(currentItems.map(i=>[i.order,i]));
      for(const c of els.grid.querySelectorAll('canvas.mini')){ const item=map.get(Number(c.dataset.order)); if(item) drawWater(c.getContext('2d'),c.width,c.height,item.visual,t,false); }
      if(currentShader) drawWater(els.hero.getContext('2d'),els.hero.width,els.hero.height,currentShader.visual,t,true);
      requestAnimationFrame(loop);
    }
    function parseColor(hex){ const s=hex.replace('#',''); return [parseInt(s.slice(0,2),16),parseInt(s.slice(2,4),16),parseInt(s.slice(4,6),16)]; }
    function mix(a,b,t){ return a.map((x,i)=>Math.round(x+(b[i]-x)*t)); }
    function rgb(v){ return 'rgb('+v[0]+','+v[1]+','+v[2]+')'; }
    let timer=null;
    els.query.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{state.q=els.query.value;state.page=1;loadPage();},120)};
    els.family.onchange=()=>{state.family=els.family.value;state.page=1;loadPage()};
    els.caustic.onchange=()=>{state.caustic=els.caustic.value;state.page=1;loadPage()};
    els.pageSize.onchange=()=>{state.pageSize=Number(els.pageSize.value);state.page=1;loadPage()};
    els.prev.onclick=()=>{state.page=Math.max(1,state.page-1);loadPage()};
    els.next.onclick=()=>{state.page+=1;loadPage()};
    window.onkeydown=e=>{if(e.key==='ArrowLeft')els.prev.click(); if(e.key==='ArrowRight')els.next.click();};
    init(); requestAnimationFrame(loop);
  </script>
</body>
</html>`;
}
