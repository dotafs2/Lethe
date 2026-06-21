#!/usr/bin/env node
"use strict";

const http = require("http");

const host = "127.0.0.1";
const port = Number(process.env.PORT || process.argv[2] || 8792);

const sources = [
  {
    id: "gpu_gems_water",
    title: "GPU Gems Chapter 1: Effective Water Simulation from Physical Models",
    url: "https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-1-effective-water-simulation-physical-models",
    license: "reference",
    usedFor: "height fields, derivative normals, physical wave parameters",
  },
  {
    id: "gpu_gems_fluid",
    title: "GPU Gems Chapter 38: Fast Fluid Dynamics Simulation on the GPU",
    url: "https://developer.nvidia.com/gpugems/gpugems/part-vi-beyond-triangles/chapter-38-fast-fluid-dynamics-simulation-gpu",
    license: "reference",
    usedFor: "finite difference GPU pass structure and source injection thinking",
  },
  {
    id: "evan_water",
    title: "Evan Wallace WebGL Water",
    url: "https://github.com/evanw/webgl-water",
    license: "MIT",
    usedFor: "height and velocity water texture, drop impulse, finite difference normal reference",
  },
  {
    id: "pavel_fluid",
    title: "Pavel Dobryakov WebGL Fluid Simulation",
    url: "https://github.com/PavelDoGreat/WebGL-Fluid-Simulation",
    license: "MIT",
    usedFor: "GPU interaction source fields and real-time browser shader organization",
  },
  {
    id: "shallow_paper",
    title: "A GPU Implementation for Two-Dimensional Shallow Water Modeling",
    url: "https://arxiv.org/abs/1309.1230",
    license: "paper reference",
    usedFor: "2D shallow-water model context",
  },
  {
    id: "dg_paper",
    title: "GPU Accelerated Discontinuous Galerkin Methods for Shallow Water Equations",
    url: "https://arxiv.org/abs/1403.1661",
    license: "paper reference",
    usedFor: "shallow-water equation context and GPU solver background",
  },
];

const families = [
  ["impulse_green", "Analytic Green impulse rings", 0, ["gpu_gems_water", "evan_water"]],
  ["finite_difference", "Finite-difference normal sample", 1, ["gpu_gems_water", "evan_water"]],
  ["poisson_rain", "Poisson rain source field", 2, ["evan_water", "pavel_fluid"]],
  ["slope_runoff", "Slope advected shallow sheet", 3, ["gpu_gems_fluid", "pavel_fluid"]],
  ["boundary_reflect", "Boundary reflected curb puddle", 4, ["gpu_gems_water", "shallow_paper"]],
  ["depth_varying", "Depth-varying c=sqrt(g*h)", 5, ["gpu_gems_water", "shallow_paper"]],
  ["spectrum", "Rain energy spectrum", 6, ["gpu_gems_water"]],
  ["hybrid_cells", "Hybrid cell source plus sheet", 7, ["evan_water", "pavel_fluid", "dg_paper"]],
  ["storm_runoff", "Storm runoff interference", 8, ["gpu_gems_fluid", "shallow_paper"]],
];

const palettes = [
  ["cold asphalt", [0.015, 0.019, 0.021], [0.05, 0.17, 0.21], [0.70, 0.92, 0.95]],
  ["green pavement", [0.018, 0.024, 0.021], [0.04, 0.16, 0.12], [0.60, 0.90, 0.76]],
  ["neon road", [0.014, 0.014, 0.022], [0.06, 0.10, 0.20], [0.90, 0.38, 0.80]],
  ["concrete puddle", [0.032, 0.033, 0.032], [0.08, 0.11, 0.12], [0.76, 0.84, 0.86]],
];

function makeMaterials() {
  const materials = [];
  let order = 1;
  for (const [familyId, familyName, kind, sourceIds] of families) {
    const palette = palettes[kind % palettes.length];
    const seed = 0.17 + kind * 11.31;
    const depth = +(0.035 + kind * 0.008).toFixed(3);
    const damping = +(1.15 + kind * 0.18).toFixed(3);
    const rain = +(0.72 + (kind % 3) * 0.08).toFixed(3);
    const flow = +((kind % 4) * 0.16).toFixed(3);
    materials.push({
      id: `srw_${String(order).padStart(3, "0")}_${familyId}`,
      order,
      title: `${String(order).padStart(3, "0")} ${familyName}`,
      familyId,
      familyName,
      kind,
      sourceIds,
      sourceSummary: sourceIds.map((id) => sources.find((s) => s.id === id).title).join(" | "),
      params: {seed, depth, damping, rain, flow, palette: palette[0]},
      colors: {ground: palette[1], water: palette[2], highlight: palette[3]},
      algorithm: algorithmText(familyId),
      glsl: snippetFor(familyId),
    });
    order++;
  }
  return materials;
}

function algorithmText(familyId) {
  return {
    impulse_green: "Closed-form damped impulse shells. Wave speed is c=sqrt(g*depth), each deterministic raindrop contributes an expanding ring.",
    finite_difference: "Height is sampled at uv +/- epsilon and converted to normals by central differences, mirroring height-field water practice.",
    poisson_rain: "Randomized source cells approximate a Poisson rain process. Each cell chooses a drop center and birth phase.",
    slope_runoff: "A shallow sheet is advected along a slope vector while rain impulses ride on top of the moving coordinate field.",
    boundary_reflect: "Curb boundaries mirror impulse positions, giving reflected ripples inside a puddle basin.",
    depth_varying: "Depth changes across the plane. Local speed c=sqrt(g*h(x,y)) makes ripples slow down in thin regions.",
    spectrum: "Many small rain impacts become a wave-energy spectrum instead of visible single drops.",
    hybrid_cells: "Cell-based source injection plus a continuous sheet wave, useful for dense rain without obvious repetition.",
    storm_runoff: "Heavy rain combines cross-current runoff, sheet flow, and high-frequency capillary detail.",
  }[familyId];
}

function snippetFor(familyId) {
  return {
    impulse_green: "height += exp(-abs(r - sqrt(9.81 * depth) * age) / width) * sin((r - front) * 70.0) * exp(-damping * age);",
    finite_difference: "normal = normalize(vec3(-(h(uv+eps)-h(uv-eps))/(2.0*eps), 1.0, -(h(v+eps)-h(v-eps))/(2.0*eps)));",
    poisson_rain: "cell = floor(world * density); center = hash22(cell + birth); height += dropImpulse(world - center, age);",
    slope_runoff: "advected = world + slopeDir * time * flow; height = rainImpulse(advected) + sheetWave(advected);",
    boundary_reflect: "height = impulse(p - source) + impulse(p - reflectedSourceAcrossCurb);",
    depth_varying: "localDepth = baseDepth + puddleMask * depthVariation; c = sqrt(9.81 * localDepth);",
    spectrum: "height += sum_i amplitude_i * sin(dot(world, dir_i) * freq_i - time * sqrt(g*h) * freq_i);",
    hybrid_cells: "height = poissonImpulses(world) + advectedSheet(world) + cellFoamMask(world);",
    storm_runoff: "height = strongRainImpulses + runoffInterference + capillaryNoise;",
  }[familyId];
}

const materials = makeMaterials();

function sendJson(res, payload) {
  res.writeHead(200, {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"});
  res.end(JSON.stringify(payload));
}

function routeApi(req, res, url) {
  if (url.pathname === "/api/meta") {
    return sendJson(res, {
      count: materials.length,
      families: families.map(([id, name]) => ({id, name})),
      sources,
    });
  }
  if (url.pathname === "/api/materials") {
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(24, Math.max(4, Number(url.searchParams.get("pageSize") || 12)));
    const family = url.searchParams.get("family") || "";
    const q = (url.searchParams.get("q") || "").toLowerCase().trim();
    let rows = materials;
    if (family) rows = rows.filter((m) => m.familyId === family);
    if (q) {
      rows = rows.filter((m) => `${m.title} ${m.familyName} ${m.algorithm} ${m.sourceSummary}`.toLowerCase().includes(q));
    }
    const start = (page - 1) * pageSize;
    return sendJson(res, {
      total: rows.length,
      page,
      pageSize,
      pages: Math.max(1, Math.ceil(rows.length / pageSize)),
      entries: rows.slice(start, start + pageSize),
    });
  }
  const match = url.pathname.match(/^\/api\/material\/([^/]+)$/);
  if (match) {
    const material = materials.find((m) => m.id === match[1]);
    if (!material) {
      res.writeHead(404, {"content-type": "application/json"});
      res.end(JSON.stringify({error: "not found"}));
      return;
    }
    return sendJson(res, {...material, sources: material.sourceIds.map((id) => sources.find((s) => s.id === id))});
  }
  res.writeHead(404, {"content-type": "application/json"});
  res.end(JSON.stringify({error: "unknown api route"}));
}

function html() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lethe Shallow Rain Water Materials</title>
<style>
:root{color-scheme:dark;--bg:#070a0b;--panel:#0e1415;--line:#263434;--text:#edf7f4;--muted:#98aca8;--accent:#63dcc9;--gold:#e2bc72}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;letter-spacing:0}button,input,select{font:inherit}
button{border:1px solid var(--line);background:#121d1e;color:var(--text);border-radius:6px;padding:9px 12px;cursor:pointer}button:hover{border-color:var(--accent)}
.app{display:grid;grid-template-columns:minmax(560px,1.02fr) minmax(560px,.98fr);height:100vh;overflow:hidden}.left{border-right:1px solid var(--line);display:flex;flex-direction:column;min-width:0}.top{padding:18px 20px;border-bottom:1px solid var(--line);background:#0b1011}
h1{font-size:24px;margin:0 0 12px}.badges{display:flex;gap:8px;flex-wrap:wrap}.badge{border:1px solid #2d4844;background:#10201e;color:#c8e7df;border-radius:6px;padding:6px 9px;font-size:13px}
.filters{display:grid;grid-template-columns:1fr 180px 90px;gap:10px;margin-top:14px}.filters input,.filters select{border:1px solid var(--line);background:#090f10;color:var(--text);border-radius:6px;padding:10px;width:100%}
.grid{padding:14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;overflow:auto}.card{border:1px solid #223131;background:#0d1414;border-radius:8px;overflow:hidden;cursor:pointer;min-height:238px}.card.active{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}.thumb{display:block;width:100%;height:128px;background:#030506}.cardBody{padding:10px}.cardTitle{font-size:14px;line-height:1.25;min-height:36px}.meta{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.38}.pager{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);padding:12px 14px;background:#0b1011;color:var(--muted)}
.right{display:grid;grid-template-rows:auto minmax(360px,48vh) auto minmax(220px,1fr);min-width:0}.head{padding:18px 24px;border-bottom:1px solid var(--line);background:#0b1011}.head h2{font-size:24px;line-height:1.2;margin:0}.sub{margin-top:8px;color:var(--muted);font-size:13px}
.stageWrap{position:relative;background:#020405;overflow:hidden}.stage{width:100%;height:100%;display:block}.overlay{position:absolute;left:14px;bottom:14px;display:flex;gap:8px;flex-wrap:wrap}.overlay span{background:rgba(5,9,10,.78);border:1px solid rgba(255,255,255,.13);border-radius:6px;padding:6px 8px;font-size:12px;color:#daf4ef}
.params{display:grid;grid-template-columns:repeat(2,1fr);gap:12px 18px;padding:14px 24px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:#0e1515}.param label{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-bottom:5px}.param input{width:100%;accent-color:var(--accent)}
.details{display:grid;grid-template-columns:1fr 1fr;min-height:0}.panel{min-height:0;overflow:auto;border-right:1px solid var(--line);padding:16px 20px}.panel:last-child{border-right:0}.panel h3{font-size:14px;margin:0 0 10px;color:#dff7f1}.panel p,.panel li{color:var(--muted);font-size:13px;line-height:1.45}.code{white-space:pre-wrap;font:12px/1.48 Consolas,Menlo,monospace;color:#dcf2ec;background:#070b0c;border:1px solid #1b2828;border-radius:6px;padding:12px;margin:10px 0 0}
a{color:#83e8d9;text-decoration:none}a:hover{text-decoration:underline}
@media(max-width:1050px){.app{grid-template-columns:1fr;height:auto;overflow:visible}.left{border-right:0}.right{min-height:900px}.filters{grid-template-columns:1fr 1fr}.details{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="app">
  <section class="left">
    <header class="top">
      <h1>Lethe Shallow Rain Water Materials</h1>
      <div class="badges">
        <span class="badge" id="countBadge">9 materials</span>
        <span class="badge">WebGL shader previews</span>
        <span class="badge">shallow-wave model</span>
        <span class="badge">source annotated</span>
      </div>
      <div class="filters">
        <input id="search" placeholder="Search impulse, runoff, curb, depth...">
        <select id="family"><option value="">All families</option></select>
        <select id="pageSize"><option>12</option><option>16</option><option>24</option></select>
      </div>
    </header>
    <div id="grid" class="grid"></div>
    <footer class="pager">
      <button id="prev">Prev</button>
      <span id="pageInfo">Page 1</span>
      <button id="next">Next</button>
    </footer>
  </section>
  <section class="right">
    <header class="head">
      <h2 id="title">Loading...</h2>
      <div class="sub" id="subtitle"></div>
    </header>
    <div class="stageWrap">
      <canvas id="stage" class="stage"></canvas>
      <div id="overlay" class="overlay"></div>
    </div>
    <section class="params">
      <div class="param"><label><span>Rain</span><b id="vRain">0.90</b></label><input id="rain" type="range" min="0" max="1.4" step="0.01" value="0.90"></div>
      <div class="param"><label><span>Depth</span><b id="vDepth">0.08</b></label><input id="depth" type="range" min="0.015" max="0.20" step="0.001" value="0.08"></div>
      <div class="param"><label><span>Damping</span><b id="vDamping">1.80</b></label><input id="damping" type="range" min="0.4" max="4.5" step="0.01" value="1.80"></div>
      <div class="param"><label><span>Flow</span><b id="vFlow">0.20</b></label><input id="flow" type="range" min="0" max="1.2" step="0.01" value="0.20"></div>
    </section>
    <section class="details">
      <div class="panel">
        <h3>Algorithm</h3>
        <p id="algorithm"></p>
        <pre id="snippet" class="code"></pre>
      </div>
      <div class="panel">
        <h3>Sources</h3>
        <ul id="sources"></ul>
      </div>
    </section>
  </section>
</main>
<script>
const vertexShaderSource=\`
attribute vec2 a_pos;
varying vec2 v_uv;
void main(){v_uv=a_pos*0.5+0.5;gl_Position=vec4(a_pos,0.0,1.0);}
\`;
const fragmentShaderSource=\`
precision highp float;
varying vec2 v_uv;
uniform float u_time;
uniform float u_seed;
uniform float u_depth;
uniform float u_damping;
uniform float u_rain;
uniform float u_flow;
uniform int u_kind;
uniform vec3 u_ground;
uniform vec3 u_water;
uniform vec3 u_highlight;

float hash12(vec2 p){vec3 p3=fract(vec3(p.xyx)*0.1031);p3+=dot(p3,p3.yzx+33.33);return fract((p3.x+p3.y)*p3.z);}
vec2 hash22(vec2 p){float n=hash12(p);return vec2(n,hash12(p+n+17.13));}
float impulse(vec2 p,float t,float seed,float depth,float damping){
  float c=sqrt(max(0.003,9.81*depth));
  float birth=floor(t*u_rain*4.0+seed*7.1);
  float age=fract(t*u_rain*4.0+seed*7.1);
  vec2 center=hash22(vec2(seed*13.1,birth*.37))*2.0-1.0;
  vec2 d=p-center;
  float r=length(d);
  float front=c*age*.65;
  float width=mix(.018,.070,age);
  float shell=exp(-abs(r-front)/width);
  float carrier=sin((r-front)*58.0);
  float gate=smoothstep(.02,.12,age)*(1.0-smoothstep(.76,1.0,age));
  return shell*carrier*exp(-damping*age)/(1.0+r*2.1)*gate;
}
float poisson(vec2 p,float t,float density,float seed){
  vec2 cell=floor(p*density);
  vec2 local=fract(p*density)-.5;
  float h=0.0;
  for(int x=-1;x<=1;x++){
    for(int y=-1;y<=1;y++){
      vec2 c=cell+vec2(float(x),float(y));
      vec2 rnd=hash22(c+seed);
      float phase=fract(t*u_rain+rnd.x*3.7);
      vec2 d=local-vec2(float(x),float(y))-(rnd-.5);
      float r=length(d);
      h+=sin((r-phase*.55)*44.0)*exp(-abs(r-phase*.55)*9.0)*exp(-phase*u_damping)*step(.35,rnd.y);
    }
  }
  return h*.045;
}
float waveSpectrum(vec2 p,float t,float depth){
  float c=sqrt(max(.003,9.81*depth));
  float h=0.0;
  for(int i=0;i<7;i++){
    float fi=float(i)+1.0;
    vec2 dir=normalize(vec2(sin(fi*2.17+u_seed),cos(fi*1.73-u_seed)));
    float freq=mix(4.0,28.0,fi/7.0);
    h+=sin(dot(p,dir)*freq-t*c*freq*.17+u_seed*fi)*(.024/fi);
  }
  return h*u_rain;
}
float heightField(vec2 p,float t){
  float depth=max(.003,u_depth);
  float h=0.0;
  vec2 slopeDir=normalize(vec2(.82,.31));
  if(u_kind==0){
    for(int i=0;i<14;i++)h+=impulse(p,t,u_seed+float(i)*.17,depth,u_damping)*.030;
  } else if(u_kind==1){
    h=poisson(p,t,4.5,u_seed)+waveSpectrum(p,t,depth)*.45;
  } else if(u_kind==2){
    h=poisson(p+vec2(sin(t*.2),cos(t*.13))*.12,t,7.5,u_seed)*1.4;
  } else if(u_kind==3){
    vec2 q=p+slopeDir*t*u_flow*.35;
    h=poisson(q,t,5.0,u_seed)+sin(dot(q,slopeDir)*16.0-t*2.0)*.018;
  } else if(u_kind==4){
    vec2 src=vec2(.38,.24);
    h=impulse(p-src,t,u_seed,depth,u_damping)*.04+impulse(p-vec2(src.x,-src.y),t,u_seed+2.0,depth,u_damping)*.026;
  } else if(u_kind==5){
    float mask=smoothstep(.9,.12,length(p*vec2(1.0,.72)));
    float d=mix(.018,depth*2.6,mask);
    h=poisson(p,t,4.2,u_seed)+waveSpectrum(p,t,d)*mask;
  } else if(u_kind==6){
    h=waveSpectrum(p,t,depth)+poisson(p*1.7,t,10.0,u_seed)*.55;
  } else if(u_kind==7){
    vec2 q=p+slopeDir*t*u_flow*.2;
    h=poisson(q,t,6.0,u_seed)+impulse(p,t,u_seed+1.7,depth,u_damping)*.035+sin(q.y*22.0-t*3.0)*.012;
  } else {
    vec2 q=p+vec2(sin(p.y*2.2+t*.7),cos(p.x*2.0-t*.4))*.10*u_flow;
    h=poisson(q,t,8.0,u_seed)*1.1+waveSpectrum(q,t,depth)*.8;
  }
  return h;
}
void main(){
  vec2 screen=v_uv*2.0-1.0;
  float persp=1.0/(.34+v_uv.y*1.35);
  vec2 p=vec2(screen.x*persp*1.7,(1.0-v_uv.y)*4.8-1.4);
  float t=u_time*.55;
  float eps=.018;
  float h=heightField(p,t);
  float hx=heightField(p+vec2(eps,0.0),t)-heightField(p-vec2(eps,0.0),t);
  float hy=heightField(p+vec2(0.0,eps),t)-heightField(p-vec2(0.0,eps),t);
  vec3 n=normalize(vec3(-hx*18.0,1.0,-hy*18.0));
  vec3 light=normalize(vec3(-.4,.85,.32));
  float diff=max(dot(n,light),0.0);
  float spec=pow(max(reflect(-light,n).y,0.0),42.0);
  float foam=smoothstep(.025,.11,abs(h)+length(vec2(hx,hy))*2.0);
  float grid=step(.985,fract(p.x*1.4))+step(.988,fract(p.y*1.4));
  float rainLine=step(.985,fract((screen.x*.8+screen.y*1.9+t*2.5+hash12(floor(screen*18.0)))*16.0))*u_rain;
  vec3 base=mix(u_ground,u_water,.68+.16*sin(h*22.0));
  vec3 col=base*(.38+.62*diff)+u_highlight*(spec*.95+foam*.20)+grid*.018+rainLine*.10;
  col=mix(col,vec3(.018,.025,.027),smoothstep(.90,.12,v_uv.y)*.15);
  gl_FragColor=vec4(pow(clamp(col,0.0,1.0),vec3(.82)),1.0);
}
\`;
const state={meta:null,page:1,pages:1,entries:[],selected:null,main:null};
const $=id=>document.getElementById(id);
const paramIds=["rain","depth","damping","flow"];
paramIds.forEach(id=>$(id).addEventListener("input",()=>{$("v"+id[0].toUpperCase()+id.slice(1)).textContent=(+$(id).value).toFixed(id==="depth"?3:2)}));
["search","family","pageSize"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{state.page=1;loadList()}));
$("prev").onclick=()=>{if(state.page>1){state.page--;loadList();}};
$("next").onclick=()=>{if(state.page<state.pages){state.page++;loadList();}};
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));}
async function loadMeta(){
  state.meta=await (await fetch("/api/meta")).json();
  $("countBadge").textContent=state.meta.count+" materials";
  $("family").innerHTML='<option value="">All families</option>'+state.meta.families.map(f=>'<option value="'+esc(f.id)+'">'+esc(f.name)+'</option>').join("");
}
async function loadList(){
  const qs=new URLSearchParams({page:state.page,pageSize:$("pageSize").value,q:$("search").value,family:$("family").value});
  const data=await (await fetch("/api/materials?"+qs)).json();
  state.entries=data.entries; state.pages=data.pages; state.page=data.page;
  $("pageInfo").textContent="Page "+data.page+" / "+data.pages+" - "+data.total+" materials";
  $("grid").innerHTML=data.entries.map(cardHtml).join("");
  document.querySelectorAll(".card").forEach(el=>el.onclick=()=>selectMaterial(el.dataset.id));
  if(!state.selected && data.entries[0]) await selectMaterial(data.entries[0].id);
  data.entries.forEach(drawThumb2D);
}
function cardHtml(m){
  return '<article class="card '+(state.selected&&state.selected.id===m.id?'active':'')+'" data-id="'+m.id+'"><canvas class="thumb" id="thumb_'+m.id+'"></canvas><div class="cardBody"><div class="cardTitle">'+esc(m.title)+'</div><div class="meta">'+esc(m.familyName)+'<br>'+esc(m.params.palette)+' - depth '+m.params.depth+' - damping '+m.params.damping+'</div></div></article>';
}
function drawThumb2D(m){
  const canvas=$("thumb_"+m.id);
  if(!canvas) return;
  const rect=canvas.getBoundingClientRect();
  const d=Math.min(2,window.devicePixelRatio||1);
  canvas.width=Math.max(1,Math.floor(rect.width*d));
  canvas.height=Math.max(1,Math.floor(rect.height*d));
  const ctx=canvas.getContext("2d");
  const w=canvas.width,h=canvas.height;
  const toRgb=(c)=>"rgb("+c.map(v=>Math.round(v*255)).join(",")+")";
  const g=ctx.createLinearGradient(0,0,0,h);
  g.addColorStop(0,toRgb(m.colors.water));
  g.addColorStop(1,toRgb(m.colors.ground));
  ctx.fillStyle=g;
  ctx.fillRect(0,0,w,h);
  ctx.globalAlpha=.22;
  ctx.strokeStyle=toRgb(m.colors.highlight);
  for(let i=0;i<26;i++){
    const x=((i*67+m.params.seed*113)%100)/100*w;
    const y=((i*43+m.kind*19)%100)/100*h*.78+h*.06;
    const r=(10+((i*7+m.kind*5)%34))*d;
    ctx.beginPath();
    ctx.ellipse(x,y,r,r*.32,0,0,Math.PI*2);
    ctx.stroke();
  }
  ctx.globalAlpha=.32;
  ctx.fillStyle=toRgb(m.colors.highlight);
  for(let i=0;i<220;i++){
    const x=((i*31+m.kind*11)%100)/100*w;
    const y=((i*47+m.params.seed*7)%100)/100*h;
    ctx.fillRect(x,y,d,d);
  }
  ctx.globalAlpha=1;
}
async function selectMaterial(id){
  state.selected=await (await fetch("/api/material/"+id)).json();
  document.querySelectorAll(".card").forEach(el=>el.classList.toggle("active",el.dataset.id===id));
  $("title").textContent=state.selected.title;
  $("subtitle").textContent=state.selected.familyName+" - "+state.selected.params.palette+" - "+state.selected.id;
  $("algorithm").textContent=state.selected.algorithm;
  $("snippet").textContent=state.selected.glsl;
  $("sources").innerHTML=state.selected.sources.map(s=>'<li><a href="'+esc(s.url)+'" target="_blank">'+esc(s.title)+'</a><br>'+esc(s.license)+' - '+esc(s.usedFor)+'</li>').join("");
  $("overlay").innerHTML=["kind "+state.selected.kind,"depth "+state.selected.params.depth,"rain "+state.selected.params.rain,"sources "+state.selected.sourceIds.length].map(x=>"<span>"+esc(x)+"</span>").join("");
  try{
    if(!state.main) state.main=makeRenderer($("stage"),state.selected);
    state.main.material=state.selected;
  }catch(err){
    $("overlay").innerHTML="<span>WebGL renderer failed: "+esc(err.message||err)+"</span>";
  }
}
function makeRenderer(canvas,material){
  const gl=canvas.getContext("webgl",{antialias:false,preserveDrawingBuffer:false});
  if(!gl) return {draw(){}};
  const program=createProgram(gl,vertexShaderSource,fragmentShaderSource);
  const buf=gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER,buf);
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
  const pos=gl.getAttribLocation(program,"a_pos");
  const uniforms={};
  ["u_time","u_seed","u_depth","u_damping","u_rain","u_flow","u_kind","u_ground","u_water","u_highlight"].forEach(n=>uniforms[n]=gl.getUniformLocation(program,n));
  return {canvas,gl,program,pos,uniforms,buf,material,draw(time){drawRenderer(this,time);}};
}
function createProgram(gl,vs,fs){
  const v=compile(gl,gl.VERTEX_SHADER,vs), f=compile(gl,gl.FRAGMENT_SHADER,fs), p=gl.createProgram();
  gl.attachShader(p,v); gl.attachShader(p,f); gl.linkProgram(p);
  if(!gl.getProgramParameter(p,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  return p;
}
function compile(gl,type,src){
  const s=gl.createShader(type); gl.shaderSource(s,src); gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}
function resize(canvas){
  const d=Math.min(2,window.devicePixelRatio||1), r=canvas.getBoundingClientRect();
  const w=Math.max(1,Math.floor(r.width*d)), h=Math.max(1,Math.floor(r.height*d));
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
}
function drawRenderer(r,time){
  const m=r.material; if(!m || !r.gl) return;
  resize(r.canvas); const gl=r.gl; gl.viewport(0,0,r.canvas.width,r.canvas.height); gl.useProgram(r.program);
  gl.bindBuffer(gl.ARRAY_BUFFER,r.buf);
  gl.enableVertexAttribArray(r.pos); gl.vertexAttribPointer(r.pos,2,gl.FLOAT,false,0,0);
  const rain=Number($("rain").value)||m.params.rain, depth=Number($("depth").value)||m.params.depth, damping=Number($("damping").value)||m.params.damping, flow=Number($("flow").value)||m.params.flow;
  gl.uniform1f(r.uniforms.u_time,time*.001);
  gl.uniform1f(r.uniforms.u_seed,m.params.seed);
  gl.uniform1f(r.uniforms.u_depth,r.canvas.id==="stage"?depth:m.params.depth);
  gl.uniform1f(r.uniforms.u_damping,r.canvas.id==="stage"?damping:m.params.damping);
  gl.uniform1f(r.uniforms.u_rain,r.canvas.id==="stage"?rain:m.params.rain);
  gl.uniform1f(r.uniforms.u_flow,r.canvas.id==="stage"?flow:m.params.flow);
  gl.uniform1i(r.uniforms.u_kind,m.kind);
  gl.uniform3fv(r.uniforms.u_ground,new Float32Array(m.colors.ground));
  gl.uniform3fv(r.uniforms.u_water,new Float32Array(m.colors.water));
  gl.uniform3fv(r.uniforms.u_highlight,new Float32Array(m.colors.highlight));
  gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
}
function frame(t){
  if(state.main) state.main.draw(t);
  requestAnimationFrame(frame);
}
loadMeta().then(loadList).then(()=>requestAnimationFrame(frame));
</script>
</body>
</html>`;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  if (url.pathname.startsWith("/api/")) return routeApi(req, res, url);
  res.writeHead(200, {"content-type": "text/html; charset=utf-8", "cache-control": "no-store"});
  res.end(html());
});

server.listen(port, host, () => {
  console.log(`Shallow rain water browser: http://${host}:${port}/`);
  console.log(`Loaded ${materials.length} material methods; one WebGL renderer is used for the selected method`);
});
