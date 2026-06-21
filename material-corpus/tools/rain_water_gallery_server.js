#!/usr/bin/env node
"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const corpusRoot = path.join(repoRoot, "material-corpus");
const manifestPath = path.join(corpusRoot, "rain_water_surface_hlsl", "rain_water_surface_manifest.json");
const reviewPath = path.join(corpusRoot, "rain_water_surface_hlsl", "algorithm_review.json");
const agentReviewPath = path.join(corpusRoot, "rain_water_surface_hlsl", "agent_review_report.json");
const port = Number(process.env.PORT || process.argv[2] || 8790);
const host = "127.0.0.1";

function hash(value) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function loadData() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const review = JSON.parse(fs.readFileSync(reviewPath, "utf8"));
  const agentReview = fs.existsSync(agentReviewPath)
    ? JSON.parse(fs.readFileSync(agentReviewPath, "utf8"))
    : null;
  const entries = manifest.entries.map((entry) => {
    const codePath = path.join(corpusRoot, entry.path);
    const code = fs.readFileSync(codePath, "utf8");
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
    agentReview,
    agents: [...new Set(entries.map((e) => e.agent))].sort(),
    families: [...new Set(entries.map((e) => e.family))].sort(),
    previewKinds: [...new Set(entries.map((e) => e.preview_kind))].sort(),
  };
}

function visualProfile(entry) {
  const palettes = {
    impact: ["#071015", "#2a90a8", "#d9fbff"],
    puddle: ["#111315", "#38555a", "#e5f8ff"],
    flow: ["#08100f", "#247c74", "#d5fff2"],
    wave: ["#071018", "#2b67b4", "#d9edff"],
    reflection: ["#090b12", "#b84cff", "#ffdf8a"],
    splash: ["#081216", "#4bb3cb", "#ffffff"],
    context: ["#101313", "#697a72", "#e6fff3"],
    stylized: ["#0b1020", "#4cc9ff", "#ff6bd6"],
    temporal: ["#090e13", "#3ab2ff", "#fff7c5"],
    hybrid: ["#080d10", "#42d6b2", "#ffcf70"],
  };
  const seed = hash(`${entry.order}|${entry.algorithm_id}|${entry.signature}`);
  const palette = palettes[entry.preview_kind] || palettes.puddle;
  return {
    seed,
    base: palette[0],
    mid: palette[1],
    high: palette[2],
    kind: entry.preview_kind,
    speed: 0.55 + (seed % 70) / 100,
    density: 0.35 + ((seed >>> 5) % 65) / 100,
    ripple: 0.45 + ((seed >>> 10) % 80) / 100,
    reflection: entry.preview_kind === "reflection" || entry.preview_kind === "hybrid" ? 0.95 : 0.55,
    flow: entry.preview_kind === "flow" || entry.preview_kind === "hybrid" ? 0.95 : 0.35,
    splash: entry.preview_kind === "splash" ? 0.95 : 0.42,
  };
}

let cache = loadData();

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  res.end(body);
}

function filterEntries(url) {
  const q = (url.searchParams.get("q") || "").trim().toLowerCase();
  const family = url.searchParams.get("family") || "";
  const agent = url.searchParams.get("agent") || "";
  const kind = url.searchParams.get("kind") || "";
  let entries = cache.entries;
  if (q) {
    entries = entries.filter((entry) => {
      const hay = `${entry.title} ${entry.algorithm_id} ${entry.family} ${entry.agent} ${entry.code}`.toLowerCase();
      return q.split(/\s+/).every((token) => hay.includes(token));
    });
  }
  if (family) entries = entries.filter((entry) => entry.family === family);
  if (agent) entries = entries.filter((entry) => entry.agent === agent);
  if (kind) entries = entries.filter((entry) => entry.preview_kind === kind);
  return entries;
}

function handleApi(req, res, url) {
  if (url.pathname === "/api/reload") {
    cache = loadData();
    return sendJson(res, 200, {ok: true, count: cache.count});
  }
  if (url.pathname === "/api/meta") {
    return sendJson(res, 200, {
      count: cache.count,
      families: cache.families,
      agents: cache.agents,
      previewKinds: cache.previewKinds,
      review: cache.review,
      agentReview: cache.agentReview && {
        strict_pass: cache.agentReview.strict_pass,
        present_files: cache.agentReview.present_files,
        total_items: cache.agentReview.total_items,
        global_unique_families: cache.agentReview.global_unique_families,
        global_unique_code_signatures: cache.agentReview.global_unique_code_signatures,
      },
    });
  }
  if (url.pathname === "/api/shaders") {
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(50, Math.max(1, Number(url.searchParams.get("pageSize") || 20)));
    const entries = filterEntries(url);
    const start = (page - 1) * pageSize;
    return sendJson(res, 200, {
      total: entries.length,
      page,
      pageSize,
      pages: Math.max(1, Math.ceil(entries.length / pageSize)),
      entries: entries.slice(start, start + pageSize).map((entry) => ({
        order: entry.order,
        title: entry.title,
        family: entry.family,
        agent: entry.agent,
        algorithm_id: entry.algorithm_id,
        preview_kind: entry.preview_kind,
        signature: entry.signature,
        path: entry.path,
        size: entry.size,
        lineCount: entry.lineCount,
        visual: entry.visual,
      })),
    });
  }
  const match = url.pathname.match(/^\/api\/shader\/(\d+)$/);
  if (match) {
    const order = Number(match[1]);
    const entry = cache.entries.find((item) => item.order === order);
    if (!entry) return sendJson(res, 404, {error: "shader not found"});
    return sendJson(res, 200, entry);
  }
  return sendJson(res, 404, {error: "unknown api route"});
}

function html() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lethe Rainy Water Surface HLSL</title>
<style>
:root{color-scheme:dark;--bg:#080b0c;--panel:#101617;--line:#273534;--text:#edf8f3;--muted:#9fb2ad;--accent:#55d6c2;--warm:#f2b66d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;letter-spacing:0}
button,input,select{font:inherit}button{border:1px solid var(--line);background:#14201f;color:var(--text);border-radius:6px;padding:9px 12px;cursor:pointer}button:hover{border-color:#5a817a}
.app{display:grid;grid-template-columns:minmax(480px,1.05fr) minmax(520px,.95fr);min-height:100vh}
.left{border-right:1px solid var(--line);display:flex;flex-direction:column;min-width:0}.top{padding:18px 20px;border-bottom:1px solid var(--line);background:#0c1112;position:sticky;top:0;z-index:5}
h1{font-size:24px;line-height:1.15;margin:0 0 12px}.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{border:1px solid #2d4843;background:#10201d;color:#c7e4dc;border-radius:6px;padding:6px 9px;font-size:13px}
.filters{display:grid;grid-template-columns:1fr 150px 130px 120px;gap:10px;margin-top:14px}.filters input,.filters select{width:100%;border:1px solid var(--line);background:#0a1111;color:var(--text);border-radius:6px;padding:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:12px;padding:14px;align-content:start}.card{border:1px solid #22302f;background:#0d1415;border-radius:8px;overflow:hidden;cursor:pointer;min-height:220px}.card.active{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}.thumb{display:block;width:100%;height:108px;background:#050808}.cardBody{padding:11px}.cardTitle{font-size:14px;line-height:1.25;min-height:36px}.meta{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.35}.pager{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-top:1px solid var(--line);background:#0c1112}.pager span{color:var(--muted);font-size:13px}
.right{display:grid;grid-template-rows:auto minmax(320px,48vh) auto minmax(260px,1fr);min-width:0}.detailHead{padding:18px 24px;border-bottom:1px solid var(--line);background:#0b1011}.detailHead h2{margin:0;font-size:24px;line-height:1.2}.detailSub{margin-top:8px;color:var(--muted);font-size:13px}.stageWrap{position:relative;background:#030607;overflow:hidden}.stage{width:100%;height:100%;display:block}.hud{position:absolute;left:14px;bottom:14px;display:flex;gap:8px;flex-wrap:wrap}.hud span{background:rgba(4,9,10,.74);border:1px solid rgba(255,255,255,.12);border-radius:6px;padding:6px 8px;font-size:12px;color:#d8f4ee}
.params{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 18px;padding:14px 24px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:#0e1516}.param label{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:5px}.param input{width:100%;accent-color:var(--accent)}
.codePane{min-height:0;display:flex;flex-direction:column}.codeTools{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 24px;border-bottom:1px solid var(--line);background:#0c1112;color:var(--muted);font-size:13px}.code{margin:0;min-height:0;overflow:auto;padding:18px 24px;background:#080c0d;color:#d6ece6;font:12px/1.48 Consolas,Menlo,monospace;white-space:pre}
@media (max-width:980px){.app{grid-template-columns:1fr}.right{min-height:92vh}.left{border-right:0}.filters{grid-template-columns:1fr 1fr}.params{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<main class="app">
  <section class="left">
    <header class="top">
      <h1>Lethe Rainy Water Surface HLSL</h1>
      <div class="badges">
        <span class="badge" id="countBadge">100 shaders</span>
        <span class="badge" id="reviewBadge">strict review</span>
        <span class="badge">10 agents x 10</span>
        <span class="badge">no duplicate signatures</span>
      </div>
      <div class="filters">
        <input id="search" placeholder="Search puddle, neon, ripple, runoff...">
        <select id="family"><option value="">All families</option></select>
        <select id="kind"><option value="">All previews</option></select>
        <select id="pageSize"><option>20</option><option>30</option><option>50</option></select>
      </div>
    </header>
    <div class="grid" id="grid"></div>
    <footer class="pager">
      <button id="prev" title="Previous batch">←</button>
      <span id="pageInfo">Page 1</span>
      <button id="next" title="Next batch">→</button>
    </footer>
  </section>
  <section class="right">
    <header class="detailHead">
      <h2 id="title">Loading...</h2>
      <div class="detailSub" id="subtitle"></div>
    </header>
    <div class="stageWrap">
      <canvas class="stage" id="stage"></canvas>
      <div class="hud" id="hud"></div>
    </div>
    <section class="params">
      <div class="param"><label><span>Rain Intensity</span><b id="vRain">0.86</b></label><input id="rain" type="range" min="0" max="1" step="0.01" value="0.86"></div>
      <div class="param"><label><span>Ripple Scale</span><b id="vRipple">0.72</b></label><input id="ripple" type="range" min="0" max="1.5" step="0.01" value="0.72"></div>
      <div class="param"><label><span>Water Level</span><b id="vWater">0.68</b></label><input id="water" type="range" min="0" max="1" step="0.01" value="0.68"></div>
      <div class="param"><label><span>Wind</span><b id="vWind">0.42</b></label><input id="wind" type="range" min="0" max="1" step="0.01" value="0.42"></div>
      <div class="param"><label><span>Reflection</span><b id="vReflection">0.74</b></label><input id="reflection" type="range" min="0" max="1.2" step="0.01" value="0.74"></div>
      <div class="param"><label><span>Roughness</span><b id="vRoughness">0.29</b></label><input id="roughness" type="range" min="0.02" max="1" step="0.01" value="0.29"></div>
    </section>
    <section class="codePane">
      <div class="codeTools"><span id="pathLabel"></span><button id="reload">Reload</button></div>
      <pre class="code" id="code"></pre>
    </section>
  </section>
</main>
<script>
const state={meta:null,page:1,pages:1,total:0,entries:[],selected:null,selectedOrder:null,t:0};
const $=(id)=>document.getElementById(id);
const params=["rain","ripple","water","wind","reflection","roughness"];
params.forEach(id=>$(id).addEventListener("input",()=>{$("v"+id[0].toUpperCase()+id.slice(1)).textContent=(+$(id).value).toFixed(2)}));
$("search").addEventListener("input", debounce(()=>{state.page=1;loadList()},180));
$("family").addEventListener("change",()=>{state.page=1;loadList()});
$("kind").addEventListener("change",()=>{state.page=1;loadList()});
$("pageSize").addEventListener("change",()=>{state.page=1;loadList()});
$("prev").onclick=()=>{if(state.page>1){state.page--;loadList()}};
$("next").onclick=()=>{if(state.page<state.pages){state.page++;loadList()}};
$("reload").onclick=async()=>{await fetch("/api/reload"); await loadMeta(); await loadList();};

function debounce(fn,ms){let h;return()=>{clearTimeout(h);h=setTimeout(fn,ms)}}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]))}
async function loadMeta(){
  state.meta=await (await fetch("/api/meta")).json();
  $("countBadge").textContent=state.meta.count+" shaders";
  $("reviewBadge").textContent=state.meta.agentReview?.strict_pass?"strict review passed":"review pending";
  $("family").innerHTML='<option value="">All families</option>'+state.meta.families.map(f=>'<option>'+esc(f)+'</option>').join("");
  $("kind").innerHTML='<option value="">All previews</option>'+state.meta.previewKinds.map(f=>'<option>'+esc(f)+'</option>').join("");
  const initial = new URLSearchParams(location.search);
  if (initial.has("q")) $("search").value = initial.get("q");
  if (initial.has("family") && state.meta.families.includes(initial.get("family"))) $("family").value = initial.get("family");
  if (initial.has("kind") && state.meta.previewKinds.includes(initial.get("kind"))) $("kind").value = initial.get("kind");
}
async function loadList(){
  const qs=new URLSearchParams({page:state.page,pageSize:$("pageSize").value,q:$("search").value,family:$("family").value,kind:$("kind").value});
  const data=await (await fetch("/api/shaders?"+qs)).json();
  Object.assign(state,{entries:data.entries,total:data.total,pages:data.pages,page:data.page});
  $("pageInfo").textContent=\`Page \${data.page} / \${data.pages} · \${data.total} shaders\`;
  $("grid").innerHTML=data.entries.map(cardHtml).join("");
  data.entries.forEach(entry=>drawThumb(entry));
  document.querySelectorAll(".card").forEach(el=>el.onclick=()=>selectShader(Number(el.dataset.order)));
  if(!state.selectedOrder && data.entries[0]) selectShader(data.entries[0].order);
}
function cardHtml(entry){
  return \`<article class="card \${entry.order===state.selectedOrder?'active':''}" data-order="\${entry.order}">
    <canvas class="thumb" id="thumb\${entry.order}" width="420" height="216"></canvas>
    <div class="cardBody"><div class="cardTitle">\${String(entry.order).padStart(3,"0")} · \${esc(entry.title)}</div>
    <div class="meta">\${esc(entry.preview_kind)} · \${esc(entry.agent)}<br>\${esc(entry.signature)} · \${entry.lineCount} lines</div></div>
  </article>\`;
}
async function selectShader(order){
  state.selectedOrder=order;
  document.querySelectorAll(".card").forEach(el=>el.classList.toggle("active",Number(el.dataset.order)===order));
  const entry=await (await fetch("/api/shader/"+order)).json();
  state.selected=entry;
  $("title").textContent=String(entry.order).padStart(3,"0")+" · "+entry.title;
  $("subtitle").textContent=entry.family+" · "+entry.agent+" · "+entry.algorithm_id+" · signature "+entry.signature;
  $("pathLabel").textContent=entry.path;
  $("code").textContent=entry.code;
  $("hud").innerHTML=["kind: "+entry.preview_kind,"family: "+entry.family,"lines: "+entry.lineCount].map(x=>"<span>"+esc(x)+"</span>").join("");
}
function drawThumb(entry){
  const canvas=$("thumb"+entry.order); if(!canvas)return;
  drawRainScene(canvas, entry.visual, (performance.now()/1000)*0.35, true);
}
function drawRainScene(canvas, visual, time, thumb=false){
  const ctx=canvas.getContext("2d"), w=canvas.width, h=canvas.height;
  const rain=+$("rain").value, ripple=+$("ripple").value, water=+$("water").value, wind=+$("wind").value, refl=+$("reflection").value, rough=+$("roughness").value;
  const seed=visual.seed||1, kind=visual.kind||"puddle";
  const grd=ctx.createLinearGradient(0,0,0,h); grd.addColorStop(0,visual.base); grd.addColorStop(1,"#020404"); ctx.fillStyle=grd; ctx.fillRect(0,0,w,h);
  ctx.globalAlpha=0.5+water*0.35; ctx.fillStyle="#081214"; ctx.beginPath();
  for(let i=0;i<18;i++){ const x=i/17*w; const y=h*(0.48+0.07*Math.sin(i*1.7+seed)); i?ctx.lineTo(x,y):ctx.moveTo(x,y); }
  ctx.lineTo(w,h); ctx.lineTo(0,h); ctx.closePath(); ctx.fill(); ctx.globalAlpha=1;
  drawReflections(ctx,w,h,visual,time,refl,rough,kind);
  drawFlow(ctx,w,h,visual,time,wind,kind);
  drawRipples(ctx,w,h,visual,time,rain,ripple,kind,thumb);
  drawRainStreaks(ctx,w,h,visual,time,rain,wind,thumb);
  if(kind==="splash"||kind==="hybrid"||kind==="impact") drawSplashes(ctx,w,h,visual,time,rain);
  if(kind==="stylized") drawStylized(ctx,w,h,time,visual);
  ctx.globalAlpha=0.22; ctx.fillStyle=visual.mid; for(let y=0;y<h;y+=18){ctx.fillRect(0,y,w,1)} ctx.globalAlpha=1;
}
function drawReflections(ctx,w,h,v,t,refl,rough,kind){
  const count=kind==="reflection"?9:kind==="hybrid"?7:4;
  for(let i=0;i<count;i++){
    const x=((i*97+v.seed)%w)+Math.sin(t+i)*18;
    const width=8+((v.seed>>i)%24)*(1-rough*0.45);
    const g=ctx.createLinearGradient(x, h*.18, x, h);
    g.addColorStop(0, i%3===0?"#ff5ad6":i%3===1?"#52d7ff":"#ffd06b"); g.addColorStop(1,"rgba(0,0,0,0)");
    ctx.globalAlpha=(0.05+refl*0.16)*(kind==="reflection"?1.5:1);
    ctx.fillStyle=g; ctx.fillRect(x-width/2,h*.16,width,h*.82);
  }
  ctx.globalAlpha=1;
}
function drawFlow(ctx,w,h,v,t,wind,kind){
  const n=kind==="flow"||kind==="hybrid"?34:14;
  ctx.strokeStyle=v.mid; ctx.lineWidth=1.2; ctx.globalAlpha=(kind==="flow"?0.42:0.2)+wind*.18;
  for(let i=0;i<n;i++){
    const y=h*(.42+((i*37+v.seed)%55)/100);
    const off=((t*55*(.4+wind)+i*31+v.seed)%w);
    ctx.beginPath();
    for(let x=-80;x<w+80;x+=24){ctx.lineTo(x, y+Math.sin((x+off)*.022+i)*7)}
    ctx.stroke();
  }
  ctx.globalAlpha=1;
}
function drawRipples(ctx,w,h,v,t,rain,ripple,kind,thumb){
  const n=Math.floor((thumb?8:18)+(rain*28)*(kind==="impact"?1.5:1));
  for(let i=0;i<n;i++){
    const x=((i*131+v.seed)%w), y=h*(.38+(((i*71+v.seed)>>2)%56)/100);
    const phase=(t*(.55+v.speed)+i*.23)%1;
    const rx=(8+phase*52*ripple)*(kind==="flow"?1.8:1), ry=rx*(kind==="impact"?0.62:0.32+rain*.35);
    ctx.strokeStyle=i%3===0?v.high:v.mid; ctx.globalAlpha=(1-phase)*(.18+.25*rain); ctx.lineWidth=1.1;
    ctx.beginPath(); ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2); ctx.stroke();
  }
  ctx.globalAlpha=1;
}
function drawRainStreaks(ctx,w,h,v,t,rain,wind,thumb){
  const n=Math.floor((thumb?45:130)*rain);
  ctx.strokeStyle="#d9faff"; ctx.lineWidth=1; ctx.globalAlpha=.22+.22*rain;
  for(let i=0;i<n;i++){
    const x=((i*57+v.seed+t*90*(.3+wind))%w), y=((i*149+v.seed+t*380)%h);
    ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x+wind*18+6,y+18+wind*8); ctx.stroke();
  }
  ctx.globalAlpha=1;
}
function drawSplashes(ctx,w,h,v,t,rain){
  ctx.fillStyle="#f4ffff"; ctx.globalAlpha=.22+.28*rain;
  for(let i=0;i<26;i++){const x=(i*83+v.seed)%w, y=h*(.5+((i*29+v.seed)%42)/100); const r=1+((i+v.seed)%5); ctx.beginPath(); ctx.arc(x+Math.sin(t*3+i)*5,y,r,0,Math.PI*2); ctx.fill();}
  ctx.globalAlpha=1;
}
function drawStylized(ctx,w,h,t,v){
  ctx.globalAlpha=.28; ctx.fillStyle="#ff68d8";
  for(let i=0;i<9;i++){ctx.beginPath(); ctx.arc((i*97+v.seed)%w,h*(.38+((i*31)%44)/100),14+Math.sin(t+i)*8,0,Math.PI*2); ctx.fill();}
  ctx.globalAlpha=1;
}
async function boot(){await loadMeta(); await loadList(); requestAnimationFrame(tick)}
function tick(ms){
  state.t=ms/1000;
  if(state.selected) drawRainScene($("stage"), state.selected.visual, state.t, false);
  state.entries.forEach(e=>drawThumb(e));
  requestAnimationFrame(tick);
}
new ResizeObserver(entries=>{for(const e of entries){const c=e.target; const r=c.getBoundingClientRect(); const d=Math.min(2,window.devicePixelRatio||1); c.width=Math.max(1,Math.floor(r.width*d)); c.height=Math.max(1,Math.floor(r.height*d));}}).observe($("stage"));
boot();
</script>
</body>
</html>`;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  if (url.pathname.startsWith("/api/")) return handleApi(req, res, url);
  res.writeHead(200, {"content-type": "text/html; charset=utf-8", "cache-control": "no-store"});
  res.end(html());
});

server.listen(port, host, () => {
  console.log(`Rain water gallery: http://${host}:${port}/`);
  console.log(`Loaded ${cache.count} reviewed shaders`);
});
