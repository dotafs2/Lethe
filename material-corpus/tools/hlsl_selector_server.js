#!/usr/bin/env node
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const host = "127.0.0.1";
const port = Number(process.env.PORT || process.argv[2] || 8792);
const corpusRoot = path.resolve(__dirname, "..");

const sources = [
  ["gpu_gems_water", "GPU Gems Ch.1 water height fields", "https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-1-effective-water-simulation-physical-models", "reference", "height fields, normals from derivatives, wave parameters"],
  ["gpu_gems_fluid", "GPU Gems Ch.38 GPU fluid simulation", "https://developer.nvidia.com/gpugems/gpugems/part-vi-beyond-triangles/chapter-38-fast-fluid-dynamics-simulation-gpu", "reference", "finite-difference GPU pass structure and source injection"],
  ["evan_water", "Evan Wallace WebGL Water", "https://github.com/evanw/webgl-water", "MIT", "height/velocity texture model, drop impulse, normal update reference"],
  ["pavel_fluid", "Pavel Dobryakov WebGL Fluid Simulation", "https://github.com/PavelDoGreat/WebGL-Fluid-Simulation", "MIT", "interaction sources and real-time browser shader organization"],
  ["shallow_paper", "GPU 2D shallow-water modeling paper", "https://arxiv.org/abs/1309.1230", "paper reference", "2D shallow-water context"],
  ["dg_paper", "GPU shallow-water DG paper", "https://arxiv.org/abs/1403.1661", "paper reference", "GPU shallow-water solver context"],
].map(([id, title, url, license, usedFor]) => ({id, title, url, license, usedFor}));

const referencePool = [
  ["ref_unity_wave_ripple", "Unity Wave Propagation Water Ripple", "https://github.com/yumayanagisawa/Unity-Wave-Propagation-Water-Ripple", "water ripple shader for Unity"],
  ["ref_godot_water_ripple", "Godot Water Ripple Simulation Shader", "https://github.com/CBerry22/Godot-Water-Ripple-Simulation-Shader", "Godot ripple simulation shader"],
  ["ref_cocos2dx_ripple_gallery", "cocos2d-x shader gallery water ripple", "https://github.com/zilongshanren/cocos2d-x-shader-gallery", "cocos2d-x water ripple effect"],
  ["ref_project_water", "ProjectWater OpenGL water rendering", "https://github.com/realkushagrakhare/ProjectWater", "OpenGL water inspired by Evan Wallace"],
  ["ref_water_ripple_shader_unity", "WaterRippleShader Unity", "https://github.com/5l4vm0/WaterRippleShader", "Unity object, mouse, raindrop, continuous ripple styles"],
  ["ref_terrain_erosion_swe", "UnityTerrainErosionGPU", "https://github.com/bshishov/UnityTerrainErosionGPU", "shallow-water equations in Unity compute shaders"],
  ["ref_shallow_water_webgpu", "ShallowWater WebGPU", "https://github.com/LaurenceWilkes/ShallowWater", "WebGPU shallow water equations"],
  ["ref_shallow_water_unity", "ShallowWaterUnity", "https://github.com/ShunqH/ShallowWaterUnity", "Unity GPU compute shallow water simulation"],
  ["ref_toon_water_effect", "Toon Water Effect", "https://github.com/AbdullahDotM/Toon-Water-Effect", "Unity URP toon water with foam and waves"],
  ["ref_bliss_rain_ripple", "Bliss Shader DH Raindrop Ripple", "https://github.com/Wzyzz5666666/Bliss-Shader-DH-Raindrop-Ripple-Effect", "raindrop ripple effect modification"],
  ["ref_ue4_raindrop_ripple", "RainDrop Ripple Shader UE4", "https://github.com/Zhifei-Li/RainDrop-Ripple_Shader_UE4", "UE4 raindrop ripple shader"],
  ["ref_liquid_shader_ui", "Liquid Shader UI", "https://github.com/Ashborn-047/liquid-shader-ui", "WebGL rainy pond and liquid shader UI"],
  ["ref_rain_urp", "Rain URP puddle shader", "https://github.com/daniel-ilett/rain-urp", "Unity URP rain puddles shader graph"],
  ["ref_puddle_shader_unity", "PuddleShader Unity", "https://github.com/Manurocker95/PuddleShader", "Unity puddle shader"],
  ["ref_chindianese_puddle", "Puddle shader", "https://github.com/Chindianese/Puddle", "puddle shader repository"],
  ["ref_unity_puddle_shader", "Unity puddle shader", "https://github.com/NI-yy/Unity-puddle-shader", "Unity puddle shader repository"],
  ["ref_puddle_game_jam", "Puddle Shader game jam", "https://github.com/ooooonnnnn/Puddle-Shader-game-jam", "game jam puddle shader"],
  ["ref_water2d_unity", "water2d-unity", "https://github.com/valryon/water2d-unity", "2D water surface with reflection"],
  ["ref_urp_water_shaders", "URP WaterShaders", "https://github.com/aniruddhahar/URP-WaterShaders", "procedural water and caustics for Unity URP"],
  ["ref_unity_water_surface", "UnityWaterSurface", "https://github.com/hecomi/UnityWaterSurface", "CustomRenderTexture water surface simulation"],
  ["ref_r3f_water_surface", "React Three Fiber WaterSurface", "https://github.com/nhtoby311/WaterSurface", "interactive water surface component"],
  ["ref_unity_surface_water", "unity-water-shader", "https://github.com/JakubSzark/unity-water-shader", "Unity surface water shader"],
  ["ref_fluid_sim_ghassaei", "FluidSimulation", "https://github.com/amandaghassaei/FluidSimulation", "WebGL mixed grid-particle fluid shader"],
  ["ref_compute_fluid_dynamic", "Compute Shaders Fluid Dynamic", "https://github.com/IRCSS/Compute-Shaders-Fluid-Dynamic-", "Unity compute shader fluid simulation"],
  ["ref_garrett_water_fft", "GarrettGunnell Water", "https://github.com/GarrettGunnell/Water", "sum-of-sines and FFT physically based water"],
  ["ref_inkbox_glsl_fluid", "inkbox GLSL fluid", "https://github.com/bassicali/inkbox", "GLSL fluid simulation"],
  ["ref_ofx_flow_tools", "ofxFlowTools", "https://github.com/moostrik/ofxFlowTools", "GLSL 2D fluid simulation and optical flow"],
  ["ref_wet_surface_hdrp", "WetSurfaceShader", "https://github.com/Ikaroon/WetSurfaceShader", "HDRP wet droplets using Shader Graph and VFX Graph"],
  ["ref_wet_surface_glsl", "wet-surface-glsl", "https://github.com/sayakbiswas/wet-surface-glsl", "GLSL wetness surface shader"],
  ["ref_vehicle_wetness", "VehicleWetness", "https://github.com/cem-akkaya/VehicleWetness", "Unreal GPU compute rain droplets and wetness masks"],
  ["ref_effect_wet_rain", "Effect-WetRain", "https://github.com/leaveoneblood/Effect-WetRain", "wet surface shader"],
  ["ref_wet_paint_system", "Advanced Wet Paint System", "https://github.com/yiitAykol/Advanced-Wet-Paint-System---HDRP-URP-", "GPU wetness, dirt, and paint compute shaders"],
  ["ref_unity_raindrops", "Unity Raindrops", "https://github.com/yumayanagisawa/Unity-Raindrops", "raindrops shader"],
  ["ref_raindrop_smkplus", "RainDrop", "https://github.com/smkplus/RainDrop", "Unity raindrop shader"],
  ["ref_raindrop_hlsl_heartfelt", "RaindropShader HDRP HLSL", "https://github.com/TwistedCircusGames/RaindropShader", "HDRP HLSL conversion of Heartfelt raindrop shader"],
  ["ref_raindrop_flocking", "Raindrop Simulation", "https://github.com/cyh726/Raindrop_Simulation", "Unity flocking and shader raindrop simulation"],
  ["ref_simple_water_waves", "simple-water-waves-shader", "https://github.com/gorodroz/simple-water-waves-shader", "WebGL water ripple shader with mouse interaction"],
  ["ref_three_water_ripple", "Water ripple effect", "https://github.com/arian00001/Water-ripple-effect", "Three.js interactive water ripple effect"],
  ["ref_webgl_slide_ripple", "WebGL slide water ripple", "https://github.com/Thakuma07/fromanother-WEBGLAnimation", "Three.js plane fragment shader water-like ripple"],
].map(([id, title, url, usedFor]) => ({id, title, url, license: "candidate", usedFor}));

const racks = ["Rain", "Water", "Flow", "Boundary", "Optical", "Solver", "Stylized", "Utility"];
const families = [
  ["green_impulse", "Green impulse rings", "Closed-form damped rings with c=sqrt(g*h)."],
  ["finite_difference", "Finite-difference normal", "Height sampled with central differences for stable normals."],
  ["poisson_sources", "Poisson source field", "Rain events are cell samples with randomized birth phase."],
  ["advected_sheet", "Slope advected sheet", "A thin water layer moves along a slope vector."],
  ["reflected_boundary", "Boundary reflection", "Curb or edge reflection mirrors the impulse field."],
  ["depth_speed", "Depth-varying speed", "Local depth changes c=sqrt(g*h) across the surface."],
  ["spectral_energy", "Rain energy spectrum", "Dense rain becomes a spectrum instead of discrete rings."],
  ["hybrid_cells", "Hybrid cells plus sheet", "Cell impulses ride on a continuous shallow sheet."],
  ["runoff_interference", "Runoff interference", "Cross-current sheet flow interferes with rain waves."],
  ["capillary_detail", "Capillary detail", "High frequency surface tension detail over broad waves."],
  ["curb_channel", "Curb channel flow", "Water is constrained to a gutter-like channel."],
  ["puddle_basin", "Puddle basin SDF", "The wave domain is masked by a basin distance field."],
  ["thin_film", "Thin-film puddle", "A thin reflective film reveals small normal changes."],
  ["storm_sheet", "Storm sheet turbulence", "Heavy rain collapses many impacts into sheet turbulence."],
  ["anisotropic_wind", "Wind stretched ripples", "Ring waves are stretched by wind direction."],
  ["micro_beads", "Micro bead field", "Small bead normals sit above shallow water height."],
  ["tile_grout", "Tile grout pooling", "Water collects along grid and grout channels."],
  ["road_camber", "Road camber runoff", "Road crown depth gradient pushes waves sideways."],
  ["wake_sweep", "Passing wake sweep", "A moving disturbance sweeps across shallow rainwater."],
  ["foam_threshold", "Foam threshold field", "Crests above a gradient threshold create foam and glints."],
];
const missions = [
  ["asphalt rain sheet", "Rain", "cold asphalt", "Asphalt microburst", "road-scale stochastic impact spacing with crown runoff"],
  ["parking lot puddle", "Water", "flat blacktop", "Parking basin", "elliptic basin depth and slow recirculation"],
  ["curbside runoff", "Flow", "wet curb", "Curb channel", "one-sided boundary reflection with gutter drift"],
  ["tile plaza puddle", "Boundary", "white grid tile", "Tile grout trap", "grout-line pooling mask with cell-wise breaks"],
  ["night reflection film", "Optical", "black mirror", "Night mirror film", "thin reflective film with glint-biased normals"],
];

function sourceById(id) {
  return sources.find((source) => source.id === id) || sources[0];
}
function referenceById(id) {
  return referencePool.find((reference) => reference.id === id) || null;
}
function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}
function pickSources(index, familyId) {
  if (/runoff|sheet|fluid/.test(familyId)) return ["gpu_gems_fluid", "pavel_fluid", "shallow_paper"];
  if (/boundary|depth|camber|curb/.test(familyId)) return ["gpu_gems_water", "shallow_paper"];
  if (/spectrum|capillary/.test(familyId)) return ["gpu_gems_water", "dg_paper"];
  if (index % 3 === 0) return ["gpu_gems_water", "evan_water"];
  if (index % 3 === 1) return ["evan_water", "pavel_fluid"];
  return ["gpu_gems_water", "gpu_gems_fluid"];
}
function sourceComment(sourceIds) {
  return sourceIds.map((id) => {
    const s = sourceById(id);
    return `// Source: ${s.title} | ${s.license} | ${s.url}\n// Use: ${s.usedFor}`;
  }).join("\n");
}
function variantSetup(m) {
  switch (m.variantName) {
    case "Parking basin":
      return [
        "float2 p = uv * 2.0 - 1.0;",
        "float basin = smoothstep(1.08, 0.18, length(p * float2(1.18, 0.72)));",
        "p += float2(sin(time * 0.23 + p.y * 2.1), cos(time * 0.19 + p.x * 1.7)) * basin * 0.055;",
        "float domainMask = basin;",
        "float2 localFlow = normalize(flowDir + float2(-p.y, p.x) * 0.28);",
        "float substrateRoughness = 0.055;",
        "float variantFoam = basin;"
      ].join("\n    ");
    case "Curb channel":
      return [
        "float2 p = uv * 2.0 - 1.0;",
        "float channel = exp(-abs(p.y + 0.28) * 3.4);",
        "p.x += time * flow * 0.34;",
        "p.y += sin(p.x * 3.2 + time) * 0.035 * channel;",
        "float domainMask = saturate(channel);",
        "float2 localFlow = normalize(float2(1.0, -0.18) + flowDir * 0.25);",
        "float substrateRoughness = 0.075;",
        "float variantFoam = channel;"
      ].join("\n    ");
    case "Tile grout trap":
      return [
        "float2 p = uv * 2.0 - 1.0;",
        "float2 grid = abs(frac(uv * 5.0) - 0.5);",
        "float grout = 1.0 - smoothstep(0.025, 0.09, min(grid.x, grid.y));",
        "p += (grout - 0.5) * 0.045;",
        "float domainMask = saturate(0.42 + grout * 0.75);",
        "float2 localFlow = normalize(flowDir + float2(grout * 0.4, -grout * 0.2));",
        "float substrateRoughness = 0.09;",
        "float variantFoam = grout;"
      ].join("\n    ");
    case "Night mirror film":
      return [
        "float2 p = uv * 2.0 - 1.0;",
        "float film = smoothstep(-0.95, -0.15, -abs(p.y)) * smoothstep(1.18, 0.62, length(p));",
        "p *= float2(1.0, 0.82);",
        "float domainMask = saturate(0.25 + film);",
        "float2 localFlow = normalize(flowDir + float2(0.15, 0.55));",
        "float substrateRoughness = 0.025;",
        "float variantFoam = film * 0.45;"
      ].join("\n    ");
    default:
      return [
        "float2 p = uv * 2.0 - 1.0;",
        "float camber = p.x * 0.18 + p.y * 0.045;",
        "p.x += camber;",
        "float domainMask = saturate(1.0 - smoothstep(1.25, 1.6, length(p)));",
        "float2 localFlow = normalize(flowDir + float2(0.32, -0.08));",
        "float substrateRoughness = 0.065;",
        "float variantFoam = saturate(0.25 + camber);"
      ].join("\n    ");
  }
}
function familyHeightBody(m, fn) {
  switch (m.baseFamilyId) {
    case "finite_difference":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 q = p + flowDir * time * 0.07;
    float coarse = sin(q.x * 7.0 + time * 1.8) * sin(q.y * 5.0 - time * 1.2);
    float fine = Hash12_${fn}(floor(q * 18.0)) - 0.5;
    return (coarse * 0.018 + fine * 0.012 * rain) * domainMask / (1.0 + damping * 0.24);
}`;
    case "poisson_sources":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float h = 0.0;
    float2 cell = floor(p * 6.0);
    float2 local = frac(p * 6.0) - 0.5;
    [unroll] for (int x = -1; x <= 1; ++x)
    [unroll] for (int y = -1; y <= 1; ++y)
    {
        float2 c = cell + float2(x, y);
        float2 rnd = Hash22_${fn}(c + float2(seed, seed));
        float age = frac(time * rain + rnd.x * 2.7);
        float2 d = local - float2(x, y) - (rnd - 0.5);
        float r = length(d);
        h += sin((r - age * sqrt(depth * 9.81) * 0.52) * 48.0) * exp(-abs(r - age * 0.55) * 10.0) * exp(-damping * age);
    }
    return h * 0.018 * domainMask;
}`;
    case "advected_sheet":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 q = p + flowDir * (time * flow * 0.62);
    float sheet = sin(dot(q, flowDir) * 18.0 - time * 2.2) * 0.012;
    float cross = sin(dot(q, float2(-flowDir.y, flowDir.x)) * 11.0 + time * 1.4) * 0.008;
    float rainNoise = (Hash12_${fn}(floor(q * 22.0 + time)) - 0.5) * rain * 0.018;
    return (sheet + cross + rainNoise) * domainMask / (1.0 + damping * 0.18);
}`;
    case "reflected_boundary":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float c = sqrt(depth * 9.81);
    float direct = Ring_${fn}(p - float2(0.34, 0.22), time, c, damping);
    float mirrorA = Ring_${fn}(p - float2(0.34, -0.22), time + 0.11, c, damping) * 0.72;
    float mirrorB = Ring_${fn}(p - float2(-0.86, 0.22), time + 0.19, c, damping) * 0.48;
    return (direct + mirrorA + mirrorB) * rain * 0.034 * domainMask;
}`;
    case "depth_speed":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float depthField = depth * (0.55 + 0.8 * smoothstep(-0.7, 0.8, p.x + p.y * 0.25));
    float c = sqrt(depthField * 9.81);
    float h = sin(length(p) * 24.0 - time * c * 9.0) * exp(-length(p) * 1.2);
    h += sin(dot(p, flowDir) * 19.0 - time * c * 6.0) * 0.38;
    return h * 0.022 * rain * domainMask / (1.0 + damping * 0.14);
}`;
    case "spectral_energy":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float h = 0.0;
    [unroll] for (int i = 1; i <= 7; ++i)
    {
        float fi = (float)i;
        float2 dir = normalize(float2(sin(fi * 2.17 + seed), cos(fi * 1.73 - seed)));
        float energy = rain / (fi * fi + damping * 0.35);
        h += sin(dot(p, dir) * (4.0 + fi * 5.2) - time * sqrt(depth * 9.81) * fi) * energy;
    }
    return h * 0.015 * domainMask;
}`;
    case "hybrid_cells":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 q = p + flowDir * time * flow * 0.18;
    float sheet = sin(dot(q, flowDir) * 15.0 - time * 1.8) * 0.012;
    float cells = (Hash12_${fn}(floor(q * 9.0 + time * rain)) - 0.5) * 0.02;
    float impulse = Ring_${fn}(frac(q * 2.5) - 0.5, time, sqrt(depth * 9.81), damping) * 0.028;
    return (sheet + cells + impulse) * domainMask;
}`;
    case "runoff_interference":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 tangent = float2(-flowDir.y, flowDir.x);
    float a = sin(dot(p, flowDir) * 21.0 - time * 3.0);
    float b = sin(dot(p, tangent) * 17.0 + time * 2.1);
    float interference = a * b * 0.018;
    float streak = smoothstep(0.9, 0.1, abs(sin(dot(p, tangent) * 5.0))) * 0.01;
    return (interference + streak) * rain * domainMask / (1.0 + damping * 0.2);
}`;
    case "capillary_detail":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float broad = sin(length(p) * 18.0 - time * 2.0) * 0.012;
    float capillary = sin(p.x * 71.0 + p.y * 29.0 - time * 9.0) * sin(p.y * 63.0 + time * 6.0) * 0.004;
    float speckle = (Hash12_${fn}(floor(p * 42.0 + time * 3.0)) - 0.5) * 0.008 * rain;
    return (broad + capillary + speckle) * domainMask / (1.0 + damping * 0.1);
}`;
    case "curb_channel":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float channel = exp(-abs(p.y + 0.2) * 5.0);
    float downstream = sin((p.x + time * flow) * 24.0) * 0.012;
    float bank = sin(abs(p.y + 0.2) * 35.0 - time * 2.0) * 0.006;
    return (downstream + bank) * channel * domainMask * rain / (1.0 + damping * 0.16);
}`;
    case "puddle_basin":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float sdf = length(p * float2(1.2, 0.72)) - 0.72;
    float basin = smoothstep(0.08, -0.16, sdf);
    float edgeWave = sin(sdf * 55.0 - time * 2.4) * exp(-abs(sdf) * 4.5);
    float centerRain = Ring_${fn}(p, time, sqrt(depth * 9.81), damping);
    return (edgeWave * 0.014 + centerRain * 0.024 * rain) * basin * domainMask;
}`;
    case "thin_film":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float film = sin(dot(p, flowDir) * 10.0 + time * 0.8) * 0.004;
    float opticalRipple = sin(p.x * 31.0 + sin(p.y * 7.0) - time * 2.2) * 0.006;
    float microRain = (Hash12_${fn}(floor(p * 28.0 + time * rain)) - 0.5) * 0.006;
    return (film + opticalRipple + microRain) * domainMask / (1.0 + damping * 0.08);
}`;
    case "storm_sheet":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 q = p + flowDir * time * 0.35;
    float turbulence = 0.0;
    turbulence += sin(q.x * 19.0 + time * 3.7) * 0.012;
    turbulence += sin(q.y * 27.0 - time * 4.1) * 0.010;
    turbulence += sin((q.x + q.y) * 43.0 + time * 5.3) * 0.006;
    return turbulence * saturate(rain * 1.4) * domainMask / (1.0 + damping * 0.12);
}`;
    case "anisotropic_wind":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 tangent = float2(-flowDir.y, flowDir.x);
    float stretched = length(float2(dot(p, flowDir) * 0.46, dot(p, tangent) * 1.42));
    float front = sqrt(depth * 9.81) * frac(time * 0.62 + seed * 0.07);
    float wave = sin((stretched - front) * 52.0) * exp(-abs(stretched - front) * 8.0);
    return wave * 0.03 * rain * domainMask / (1.0 + damping * 0.18);
}`;
    case "micro_beads":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 cell = floor(p * 18.0);
    float2 bead = Hash22_${fn}(cell) - 0.5;
    float2 local = frac(p * 18.0) - 0.5;
    float beadMask = exp(-dot(local - bead * 0.35, local - bead * 0.35) * 82.0);
    float drift = sin(dot(p, flowDir) * 12.0 - time * 1.5) * 0.004;
    return (beadMask * 0.012 * rain + drift) * domainMask / (1.0 + damping * 0.1);
}`;
    case "tile_grout":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float2 grid = abs(frac(p * 2.6) - 0.5);
    float grout = 1.0 - smoothstep(0.025, 0.12, min(grid.x, grid.y));
    float pooled = sin((grid.x + grid.y) * 46.0 - time * 2.1) * 0.012;
    float cellRain = (Hash12_${fn}(floor(p * 6.0 + time)) - 0.5) * 0.016;
    return (pooled * grout + cellRain * (0.25 + grout)) * rain * domainMask / (1.0 + damping * 0.12);
}`;
    case "road_camber":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float camberDepth = depth * (0.5 + abs(p.x) * 1.4);
    float downhill = sin((p.y + p.x * 0.35 + time * flow) * 20.0) * 0.012;
    float sideRunoff = sin(abs(p.x) * 28.0 - time * sqrt(camberDepth * 9.81) * 4.0) * 0.014;
    return (downhill + sideRunoff) * rain * domainMask / (1.0 + damping * 0.15);
}`;
    case "wake_sweep":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float sweep = dot(p, flowDir) - frac(time * 0.28 + seed * 0.05) * 2.4 + 1.2;
    float wake = sin(sweep * 54.0) * exp(-abs(sweep) * 5.8);
    float cross = sin(dot(p, float2(-flowDir.y, flowDir.x)) * 18.0 + time) * exp(-abs(sweep) * 2.4);
    return (wake * 0.026 + cross * 0.01) * rain * domainMask / (1.0 + damping * 0.2);
}`;
    case "foam_threshold":
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float base = sin(length(p) * 24.0 - time * 2.8) * 0.016;
    float streak = sin(dot(p, flowDir) * 37.0 + time * 3.0) * 0.011;
    float crest = max(0.0, base + streak - 0.012) * 2.5;
    return (base + streak + crest) * rain * domainMask / (1.0 + damping * 0.16);
}`;
    default:
      return `float HeightCore_${fn}(float2 p, float time, float2 flowDir, float depth, float rain, float damping, float domainMask)
{
    float c = sqrt(9.81 * depth);
    float h = 0.0;
    [unroll] for (int i = 0; i < 12; ++i)
    {
        float age = frac(time * rain + seed * 0.013 + (float)i * 0.173);
        float2 center = Hash22_${fn}(float2((float)i, seed)) * 2.0 - 1.0;
        float r = length(p - center);
        h += sin((r - c * age * 0.42) * 44.0) * exp(-abs(r - c * age * 0.42) * 8.0) * exp(-damping * age);
    }
    return h * 0.018 * domainMask;
}`;
  }
}
function buildHlsl(m) {
  const fn = `Lethe_${m.familyId}_${slug(m.mission)}`;
  const body = familyHeightBody(m, fn);
  const setup = variantSetup(m);
  return `// HLSL Selector MaterialTemplate ${m.order}
// Name: ${m.familyName}
// Scenario: ${m.mission} / ${m.substrate}
// Outputs: height, normal, roughness, foam, flow for a rain-on-shallow-water material.
${sourceComment(m.sourceIds)}

float Hash12_${fn}(float2 p)
{
    float3 p3 = frac(float3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}

float2 Hash22_${fn}(float2 p)
{
    float n = Hash12_${fn}(p);
    return float2(n, Hash12_${fn}(p + n + 17.13));
}

struct LetheWaterSurface_${fn}
{
    float Height;
    float3 NormalWS;
    float Roughness;
    float Foam;
    float2 Flow;
};

static const float seed = ${m.params.seed.toFixed(3)};
static const float rain = ${m.params.rain.toFixed(3)};
static const float depth = ${m.params.depth.toFixed(3)};
static const float damping = ${m.params.damping.toFixed(3)};
static const float flow = ${m.params.flow.toFixed(3)};
static const float baseRoughness = ${m.params.roughness.toFixed(3)};
static const float heightScale = ${m.params.scale.toFixed(3)};

float Ring_${fn}(float2 p, float time, float c, float damping)
{
    float age = frac(time + seed * 0.011);
    float r = length(p);
    float front = c * age * 0.46;
    return sin((r - front) * 50.0) * exp(-abs(r - front) * 9.0) * exp(-damping * age);
}

${body}

LetheWaterSurface_${fn} Evaluate_${fn}(float2 uv, float time)
{
    float2 flowDir = normalize(float2(${(0.37 + (m.order % 5) * 0.19).toFixed(3)}, ${(0.21 + (m.order % 7) * 0.13).toFixed(3)}));
    ${setup}
    float h = HeightCore_${fn}(p, time, localFlow, depth, rain, damping, domainMask) * heightScale;
    float eps = 0.003 + depth * 0.035;
    float hx = HeightCore_${fn}(p + float2(eps, 0.0), time, localFlow, depth, rain, damping, domainMask)
             - HeightCore_${fn}(p - float2(eps, 0.0), time, localFlow, depth, rain, damping, domainMask);
    float hy = HeightCore_${fn}(p + float2(0.0, eps), time, localFlow, depth, rain, damping, domainMask)
             - HeightCore_${fn}(p - float2(0.0, eps), time, localFlow, depth, rain, damping, domainMask);

    LetheWaterSurface_${fn} o;
    o.Height = h;
    o.NormalWS = normalize(float3(-hx, 1.0, -hy));
    o.Roughness = saturate(baseRoughness + substrateRoughness + abs(hx + hy) * 0.7);
    o.Foam = saturate((abs(h) + length(float2(hx, hy)) * 1.85) * rain * variantFoam);
    o.Flow = localFlow * flow;
    return o;
}`;
}

function makeMaterials() {
  const materials = [];
  let order = 1;
  for (let batch = 0; batch < missions.length; batch++) {
    for (const [familyIndex, family] of families.entries()) {
      const [mission, rack, substrate, variantName, variantSummary] = missions[(familyIndex + batch) % missions.length];
      const [familyId, baseName, summary] = family;
      const index = order - 1;
      const methodName = `${variantName} ${baseName}`;
      const params = {
        seed: +(0.113 + index * 3.791).toFixed(3),
        rain: +(0.45 + (index % 9) * 0.065).toFixed(3),
        depth: +(0.024 + (index % 13) * 0.0065).toFixed(3),
        damping: +(0.8 + (index % 11) * 0.19).toFixed(3),
        flow: +((index % 7) * 0.105).toFixed(3),
        roughness: +(0.04 + (index % 10) * 0.022).toFixed(3),
        scale: +(0.72 + (index % 8) * 0.11).toFixed(3),
      };
      const reference = index < referencePool.length ? referencePool[index] : null;
      const material = {
        id: `hlsl_${String(order).padStart(3, "0")}_${familyId}_${slug(variantName)}`,
        order,
        title: `${String(order).padStart(3, "0")} ${methodName}`,
        familyId: `${familyId}_${slug(variantName)}`,
        familyName: methodName,
        baseFamilyId: familyId,
        baseFamilyName: baseName,
        variantName,
        rack,
        mission,
        substrate,
        classIndex: (familyIndex + (index % 5) * 7) % 16,
        sourceIds: pickSources(index, familyId),
        referenceIds: reference ? [reference.id] : [],
        referenceStatus: reference ? "verified-candidate" : "needs-specific-reference",
        params,
        tags: [rack, substrate, baseName, variantName, "shallow water", "rain surface", reference ? reference.title : "needs reference"],
        complexity: familyIndex % 4 === 0 ? "cheap" : familyIndex % 4 === 1 ? "mid" : familyIndex % 4 === 2 ? "heavy" : "experimental",
        exportStatus: "manifest-ready",
        licensePolicy: "source-annotated; verify license before commercial redistribution",
        outputChannels: ["Height", "NormalWS", "Roughness", "Foam", "Flow"],
        parameterSchema: [
          {name: "rain", label: "Rain", type: "float", min: 0, max: 1.5, step: 0.01, unit: "impact density", default: params.rain},
          {name: "depth", label: "Depth", type: "float", min: 0.015, max: 0.2, step: 0.001, unit: "meters", default: params.depth},
          {name: "damping", label: "Damping", type: "float", min: 0.25, max: 4.5, step: 0.01, unit: "wave loss", default: params.damping},
          {name: "flow", label: "Flow", type: "float", min: 0, max: 1.2, step: 0.01, unit: "surface drift", default: params.flow},
          {name: "roughness", label: "Rough", type: "float", min: 0.02, max: 0.6, step: 0.01, unit: "BRDF roughness", default: params.roughness},
          {name: "scale", label: "Scale", type: "float", min: 0.45, max: 2.0, step: 0.01, unit: "height gain", default: params.scale},
        ],
        ueImport: {
          assetType: "MaterialFunction",
          suggestedPath: `/Game/Lethe/HLSLSelector/MF_${familyId}_${slug(variantName)}`,
          customNodeEntry: `Evaluate_Lethe_${familyId}_${slug(variantName)}_${slug(mission)}`,
          compatibleTargets: ["UE Custom node", "DCC shader translator", "offline HLSL library"],
          textureSlots: [],
        },
        algorithm: `${summary} Scenario transform: ${variantSummary}. Tuned as one distinct mother material for ${mission} on ${substrate}.`,
      };
      material.hlsl = buildHlsl(material);
      materials.push(material);
      order++;
    }
  }
  return materials;
}
const materials = makeMaterials();
function materialSummary(m) {
  const {hlsl, parameterSchema, ueImport, ...rest} = m;
  return rest;
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => {
      if (!body.trim()) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(new Error(`invalid JSON body: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
}

function errorJson(res, status, message, extra = {}) {
  res.writeHead(status, {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"});
  res.end(JSON.stringify({error: message, ...extra}));
}

function sendJson(res, payload) {
  res.writeHead(200, {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"});
  res.end(JSON.stringify(payload));
}

function ueSymbol(value) {
  const text = String(value || "shader").replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  return /^[A-Za-z_]/.test(text) ? text : `S_${text}`;
}

function pyString(value) {
  return JSON.stringify(String(value));
}

function importParams(m, overrides = {}) {
  const base = {...m.params};
  for (const key of ["rain", "depth", "damping", "flow", "roughness", "scale"]) {
    const value = Number(overrides[key]);
    if (Number.isFinite(value)) base[key] = value;
  }
  return base;
}

function selectorFunctionId(m) {
  return m.ueImport.customNodeEntry.replace(/^Evaluate_/, "");
}

function dynamicSelectorHlsl(m) {
  const fn = selectorFunctionId(m);
  const typeName = `LetheWaterSurface_${fn}`;
  let code = m.hlsl;
  code = code.replace(/^static const float (rain|depth|damping|flow|baseRoughness|heightScale) = .*;\r?\n/gm, "");
  code = code.replace(
    `${typeName} Evaluate_${fn}(float2 uv, float time)`,
    `${typeName} Evaluate_${fn}(float2 uv, float time, float rain, float depth, float damping, float flow, float baseRoughness, float heightScale)`,
  );
  return code;
}

function loadCommonUsh() {
  const file = path.join(corpusRoot, "common_hlsl", "LetheUEImportCommon.ush");
  try {
    return fs.readFileSync(file, "utf8");
  } catch {
    return [
      "#ifndef LETHE_UE_IMPORT_COMMON_USH",
      "#define LETHE_UE_IMPORT_COMMON_USH",
      "float3 LetheSelectorWetBaseColor(float foam, float roughness, float facing)",
      "{",
      "    float fresnel = pow(saturate(1.0 - facing), 4.0);",
      "    float3 asphalt = float3(0.012, 0.013, 0.015);",
      "    float3 water = float3(0.18, 0.20, 0.22);",
      "    float3 glint = float3(0.82, 0.86, 0.90);",
      "    return lerp(lerp(asphalt, water, saturate(fresnel + (1.0 - roughness) * 0.18)), glint, saturate(foam * 0.62));",
      "}",
      "#endif",
    ].join("\n");
  }
}

function buildGeneratedUsh(m) {
  const fn = selectorFunctionId(m);
  const typeName = `LetheWaterSurface_${fn}`;
  const symbol = ueSymbol(m.id);
  const guard = `LETHE_SELECTOR_${symbol.toUpperCase()}_USH`;
  return `#ifndef ${guard}
#define ${guard}

#include "/Project/Lethe/HLSLSelector/Common.ush"

${dynamicSelectorHlsl(m)}

float3 LetheSelector_${symbol}_BaseColor(float2 UV, float Time, float Rain, float Depth, float Damping, float Flow, float Roughness, float Scale, float3 Normal, float3 CameraVector)
{
    ${typeName} S = Evaluate_${fn}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale);
    float facing = saturate(dot(normalize(Normal), normalize(-CameraVector)));
    return LetheSelectorWetBaseColor(S.Foam, S.Roughness, facing);
}

float LetheSelector_${symbol}_Roughness(float2 UV, float Time, float Rain, float Depth, float Damping, float Flow, float Roughness, float Scale)
{
    ${typeName} S = Evaluate_${fn}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale);
    return saturate(S.Roughness);
}

float3 LetheSelector_${symbol}_Emissive(float2 UV, float Time, float Rain, float Depth, float Damping, float Flow, float Roughness, float Scale)
{
    ${typeName} S = Evaluate_${fn}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale);
    return float3(0.42, 0.46, 0.50) * saturate(S.Foam) * 0.035;
}

float3 LetheSelector_${symbol}_WorldPositionOffset(float2 UV, float Time, float Rain, float Depth, float Damping, float Flow, float Roughness, float Scale)
{
    ${typeName} S = Evaluate_${fn}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale);
    return float3(0.0, 0.0, S.Height * 100.0);
}

#endif
`;
}

function customNodeCode(shaderFile, symbol, channel) {
  const include = `/Project/Lethe/HLSLSelector/Generated/${shaderFile}`;
  const prefix = `LetheSelector_${symbol}_${channel}`;
  if (channel === "BaseColor") {
    return `#include "${include}"
return ${prefix}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale, Normal, CameraVector);`;
  }
  return `#include "${include}"
return ${prefix}(UV, Time, Rain, Depth, Damping, Flow, Roughness, Scale);`;
}

function buildCandidateForImport(m, adjustedParams) {
  return {
    schema: "hlsl-selector.ue-custom-import.v1",
    id: m.id,
    name: m.title,
    prompt: `${m.mission} ${m.baseFamilyName}`,
    description: m.algorithm,
    tags: m.tags,
    parameters: adjustedParams,
    source_refs: [
      ...m.referenceIds.map(referenceById).filter(Boolean),
      ...m.sourceIds.map(sourceById),
    ],
    hlsl: m.hlsl,
    ue: {
      importMode: "custom-node-ush",
      packagePath: "/Game/Lethe/HLSLSelector",
      materialName: `M_${ueSymbol(m.id).slice(0, 54)}`,
      shaderIncludeRoot: "Project/Shaders/Lethe/HLSLSelector",
    },
  };
}

function buildUeImportScript(m, adjustedParams, commonUsh, generatedUsh, shaderFile) {
  const symbol = ueSymbol(m.id);
  const materialName = `M_${symbol.slice(0, 54)}`;
  const metadata = buildCandidateForImport(m, adjustedParams);
  const includePath = `/Project/Lethe/HLSLSelector/Generated/${shaderFile}`;
  const channelCodes = {
    BaseColor: customNodeCode(shaderFile, symbol, "BaseColor"),
    Roughness: customNodeCode(shaderFile, symbol, "Roughness"),
    Emissive: customNodeCode(shaderFile, symbol, "Emissive"),
    WorldPositionOffset: customNodeCode(shaderFile, symbol, "WorldPositionOffset"),
  };

  return `import json
import os
import unreal

PACKAGE_PATH = "/Game/Lethe/HLSLSelector"
MATERIAL_NAME = ${pyString(materialName)}
COMMON_USH = ${pyString(commonUsh)}
GENERATED_USH = ${pyString(generatedUsh)}
SHADER_FILE = ${pyString(shaderFile)}
INCLUDE_PATH = ${pyString(includePath)}
METADATA = json.loads(${pyString(JSON.stringify(metadata))})
CHANNEL_CODES = json.loads(${pyString(JSON.stringify(channelCodes))})
PARAMS = json.loads(${pyString(JSON.stringify(adjustedParams))})

def write_text_if_changed(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            old = handle.read()
    if old != text:
        with open(path, "w", encoding="utf-8", newline="\\n") as handle:
            handle.write(text)

project_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
shader_root = os.path.join(project_dir, "Shaders", "Lethe", "HLSLSelector")
generated_root = os.path.join(shader_root, "Generated")
write_text_if_changed(os.path.join(shader_root, "Common.ush"), COMMON_USH)
write_text_if_changed(os.path.join(generated_root, SHADER_FILE), GENERATED_USH)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
factory = unreal.MaterialFactoryNew()
mat = asset_tools.create_asset(MATERIAL_NAME, PACKAGE_PATH, unreal.Material, factory)
if mat is None:
    mat = unreal.EditorAssetLibrary.load_asset(PACKAGE_PATH + "/" + MATERIAL_NAME)
if mat is None:
    raise RuntimeError("Could not create or load material asset")

mel = unreal.MaterialEditingLibrary
if hasattr(mel, "delete_all_material_expressions"):
    mel.delete_all_material_expressions(mat)

mat.set_editor_property("use_material_attributes", False)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)

uv = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -980, -340)
time_node = mel.create_material_expression(mat, unreal.MaterialExpressionTime, -980, -210)
normal = mel.create_material_expression(mat, unreal.MaterialExpressionPixelNormalWS, -980, -80)
camera = mel.create_material_expression(mat, unreal.MaterialExpressionCameraVectorWS, -980, 50)

def scalar_param(name, default, x, y):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    node.set_editor_property("parameter_name", name)
    node.set_editor_property("default_value", float(default))
    return node

param_nodes = {
    "Rain": scalar_param("Rain", PARAMS["rain"], -760, -310),
    "Depth": scalar_param("Depth", PARAMS["depth"], -760, -190),
    "Damping": scalar_param("Damping", PARAMS["damping"], -760, -70),
    "Flow": scalar_param("Flow", PARAMS["flow"], -760, 50),
    "Roughness": scalar_param("Roughness", PARAMS["roughness"], -760, 170),
    "Scale": scalar_param("Scale", PARAMS["scale"], -760, 290),
}

def set_input_name(inp, name):
    try:
        inp.set_editor_property("input_name", name)
    except Exception:
        inp.input_name = name

def make_custom(name, code, output_type, x, y, include_normal_camera=False):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, x, y)
    node.set_editor_property("description", "HLSL Selector " + name)
    node.set_editor_property("code", code)
    node.set_editor_property("output_type", output_type)
    try:
        node.set_editor_property("include_file_paths", [INCLUDE_PATH])
    except Exception:
        pass
    input_names = ["UV", "Time", "Rain", "Depth", "Damping", "Flow", "Roughness", "Scale"]
    if include_normal_camera:
        input_names += ["Normal", "CameraVector"]
    inputs = []
    for input_name in input_names:
        inp = unreal.CustomInput()
        set_input_name(inp, input_name)
        inputs.append(inp)
    node.set_editor_property("inputs", inputs)
    mel.connect_material_expressions(uv, "", node, "UV")
    mel.connect_material_expressions(time_node, "", node, "Time")
    for input_name, src in param_nodes.items():
        mel.connect_material_expressions(src, "", node, input_name)
    if include_normal_camera:
        mel.connect_material_expressions(normal, "", node, "Normal")
        mel.connect_material_expressions(camera, "", node, "CameraVector")
    return node

base = make_custom("BaseColor", CHANNEL_CODES["BaseColor"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -360, -260, True)
rough = make_custom("Roughness", CHANNEL_CODES["Roughness"], unreal.CustomMaterialOutputType.CMOT_FLOAT1, -360, -20, False)
emissive = make_custom("Emissive", CHANNEL_CODES["Emissive"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -360, 210, False)
wpo = make_custom("WorldPositionOffset", CHANNEL_CODES["WorldPositionOffset"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -360, 430, False)

mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
try:
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
except Exception as exc:
    unreal.log_warning("HLSL Selector WPO connection skipped: " + str(exc))

unreal.EditorAssetLibrary.set_metadata_tag(mat, "LetheSelectorId", METADATA["id"])
unreal.EditorAssetLibrary.set_metadata_tag(mat, "LetheSelectorImportMode", METADATA["ue"]["importMode"])
unreal.EditorAssetLibrary.set_metadata_tag(mat, "LetheSelectorManifest", json.dumps(METADATA, ensure_ascii=True))

mel.layout_material_expressions(mat)
unreal.EditorAssetLibrary.save_loaded_asset(mat)

print("LETHE_HLSL_SELECTOR_IMPORT::" + json.dumps({
    "ok": True,
    "asset": mat.get_path_name(),
    "shader_file": os.path.join(generated_root, SHADER_FILE),
    "common_file": os.path.join(shader_root, "Common.ush"),
    "include": INCLUDE_PATH,
    "material": MATERIAL_NAME,
}, ensure_ascii=True))
`.trim();
}

function writeUeImportPackage(m, overrides = {}) {
  const adjustedParams = importParams(m, overrides);
  const symbol = ueSymbol(m.id);
  const shaderFile = `${symbol}.ush`;
  const commonUsh = loadCommonUsh();
  const generatedUsh = buildGeneratedUsh(m);
  const script = buildUeImportScript(m, adjustedParams, commonUsh, generatedUsh, shaderFile);
  const outDir = path.join(corpusRoot, "ue_imports", m.id);
  const shaderDir = path.join(outDir, "Shaders", "Lethe", "HLSLSelector");
  const generatedDir = path.join(shaderDir, "Generated");
  fs.mkdirSync(generatedDir, {recursive: true});

  const manifest = {
    schema: "hlsl-selector.ue-import-package.v1",
    materialId: m.id,
    title: m.title,
    createdAt: new Date().toISOString(),
    importMode: "custom-node-ush",
    packagePath: "/Game/Lethe/HLSLSelector",
    files: {
      manifest: path.join(outDir, "manifest.json"),
      candidate: path.join(outDir, "candidate.json"),
      uePythonScript: path.join(outDir, "create_material.py"),
      commonUsh: path.join(shaderDir, "Common.ush"),
      generatedUsh: path.join(generatedDir, shaderFile),
    },
    params: adjustedParams,
    notes: [
      "Open an Unreal project with Python Editor Script Plugin enabled.",
      "Run create_material.py through Lethe execute_python or UE Python execution.",
      "The script writes Project/Shaders/Lethe/HLSLSelector files before creating the material.",
    ],
  };
  const candidate = buildCandidateForImport(m, adjustedParams);
  fs.writeFileSync(manifest.files.manifest, JSON.stringify(manifest, null, 2), "utf8");
  fs.writeFileSync(manifest.files.candidate, JSON.stringify(candidate, null, 2), "utf8");
  fs.writeFileSync(manifest.files.uePythonScript, script + "\n", "utf8");
  fs.writeFileSync(manifest.files.commonUsh, commonUsh.endsWith("\n") ? commonUsh : `${commonUsh}\n`, "utf8");
  fs.writeFileSync(manifest.files.generatedUsh, generatedUsh, "utf8");
  fs.writeFileSync(path.join(outDir, "README.md"), [
    `# ${m.title}`,
    "",
    "This is a stage-1 HLSL Selector import package.",
    "",
    "- Import mode: UE Material with Custom nodes and Project/Shaders `.ush` includes.",
    "- Core conversion: deterministic script, no model required.",
    "- Current graph: BaseColor, Roughness, Emissive, WorldPositionOffset.",
    "- Later graph mode can replace Custom nodes with native UE material expressions.",
    "",
    "Run `create_material.py` inside Unreal Editor Python, or paste it into Lethe `execute_python`.",
  ].join("\n"), "utf8");
  return {
    ok: true,
    mode: "script-package",
    materialId: m.id,
    title: m.title,
    packageDir: outDir,
    files: manifest.files,
    ueAsset: `/Game/Lethe/HLSLSelector/M_${symbol.slice(0, 54)}.M_${symbol.slice(0, 54)}`,
    runHint: "Run create_material.py in a UE project with Python Editor Script Plugin enabled.",
    scriptPreview: script.slice(0, 1400),
  };
}

async function routeApi(req, res, url) {
  if (url.pathname === "/api/meta") return sendJson(res, {count: materials.length, racks: [...new Set(materials.map((m) => m.rack))], sources, referenceCount: referencePool.length, referenceTarget: materials.length});
  if (url.pathname === "/api/materials") {
    const page = Math.max(1, Number(url.searchParams.get("page") || 1));
    const pageSize = Math.min(40, Math.max(10, Number(url.searchParams.get("pageSize") || 20)));
    const rack = url.searchParams.get("rack") || "";
    const q = (url.searchParams.get("q") || "").trim().toLowerCase();
    let rows = materials;
    if (rack) rows = rows.filter((m) => m.rack === rack);
    if (q) {
      const tokens = q.split(/\s+/);
      rows = rows.filter((m) => tokens.every((token) => `${m.title} ${m.rack} ${m.mission} ${m.substrate} ${m.algorithm} ${m.tags.join(" ")} ${m.referenceStatus} ${m.referenceIds.join(" ")} ${m.complexity} ${m.outputChannels.join(" ")} ${m.parameterSchema.map((p) => `${p.name} ${p.label}`).join(" ")}`.toLowerCase().includes(token)));
    }
    const start = (page - 1) * pageSize;
    return sendJson(res, {total: rows.length, page, pageSize, pages: Math.max(1, Math.ceil(rows.length / pageSize)), entries: rows.slice(start, start + pageSize).map(materialSummary)});
  }
  const match = url.pathname.match(/^\/api\/material\/([^/]+)$/);
  if (match) {
    const material = materials.find((m) => m.id === match[1]);
    if (!material) {
      res.writeHead(404, {"content-type": "application/json"});
      res.end(JSON.stringify({error: "not found"}));
      return;
    }
    return sendJson(res, {...material, sources: material.sourceIds.map(sourceById), references: material.referenceIds.map(referenceById).filter(Boolean)});
  }
  const importMatch = url.pathname.match(/^\/api\/import-to-ue\/([^/]+)$/);
  if (importMatch) {
    if (req.method !== "POST") return errorJson(res, 405, "POST required");
    const material = materials.find((m) => m.id === importMatch[1]);
    if (!material) return errorJson(res, 404, "material not found");
    const body = await readJsonBody(req);
    return sendJson(res, writeUeImportPackage(material, body.params || {}));
  }
  res.writeHead(404, {"content-type": "application/json"});
  res.end(JSON.stringify({error: "unknown route"}));
}

function html() {
  const firstPage = {
    total: materials.length,
    page: 1,
    pageSize: 20,
    pages: Math.ceil(materials.length / 20),
    entries: materials.slice(0, 20).map(materialSummary),
  };
  const boot = JSON.stringify({
    meta: {count: materials.length, racks: [...new Set(materials.map((m) => m.rack))], sources, referenceCount: referencePool.length, referenceTarget: materials.length},
    firstPage,
    firstMaterial: {...materials[0], sources: materials[0].sourceIds.map(sourceById), references: materials[0].referenceIds.map(referenceById).filter(Boolean)},
  }).replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HLSL Selector</title>
<style>
:root{color-scheme:dark;--bg:#09090b;--panel:#111113;--panel2:#17171a;--line:#2a2a2f;--text:#f5f5f6;--muted:#9a9aa2;--soft:#d7d7dc;--accent:#fff}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;letter-spacing:0;overflow:hidden}button,input,select{font:inherit;color:inherit}button{height:36px;border:1px solid var(--line);background:#131316;border-radius:6px;padding:0 12px;cursor:pointer;color:#f4f4f5}button:hover{border-color:#666;background:#1d1d21}.actions button:first-child{background:#fff;color:#08080a;border-color:#fff;font-weight:700}.actions button:first-child:hover{background:#e9e9ec}.app{display:grid;grid-template-columns:minmax(520px,1fr) 520px;height:100dvh;min-height:0;overflow:hidden;background:var(--bg)}.left{display:grid;grid-template-rows:auto minmax(0,1fr) auto;min-width:0;min-height:0;border-right:1px solid var(--line);background:#0b0b0d}.top{position:sticky;top:0;z-index:3;padding:18px 20px 16px;background:rgba(11,11,13,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.brand{display:grid;grid-template-columns:1fr auto;align-items:start;gap:18px;margin-bottom:14px}.brand h1{font-size:24px;margin:0;line-height:1;font-weight:760}.brand p{margin:0;color:var(--muted);font-size:12px;line-height:1.45;text-align:right}.stats{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}.pill{border:1px solid var(--line);background:#151518;border-radius:999px;padding:6px 10px;font-size:12px;color:#d9d9df}.filters{display:grid;grid-template-columns:minmax(260px,1fr) 160px 92px;gap:10px}.filters input,.filters select{width:100%;height:40px;border:1px solid var(--line);background:#111113;border-radius:8px;padding:0 12px;color:#fff;outline:none}.filters input:focus,.filters select:focus{border-color:#777}.filters input::placeholder{color:#72727b}.shelf{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));align-content:start;gap:14px;padding:16px;overflow-y:auto;overflow-x:hidden;min-height:0;background:#09090b;scrollbar-gutter:stable}.card{background:var(--panel);border:1px solid #25252a;border-radius:8px;min-height:260px;cursor:pointer;display:flex;flex-direction:column;overflow:hidden;transition:border-color .16s,background .16s,transform .16s}.card:hover{border-color:#6f6f78;background:#151519;transform:translateY(-1px)}.card.active{border-color:#fff;box-shadow:0 0 0 1px #fff inset}.thumb{width:100%;height:122px;display:block;background:#050506;border-bottom:1px solid #232327}.cardBody{padding:12px;display:flex;flex-direction:column;gap:9px}.cardTitle{font-size:14px;font-weight:700;line-height:1.25;min-height:36px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.cardMeta{color:var(--muted);font-size:12px;line-height:1.45}.cardTags{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}.tag{border:1px solid #33343a;background:#0c0c0e;border-radius:999px;padding:4px 7px;color:#d8d8de;font-size:11px}.pager{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);padding:12px 16px;background:#101012;color:#c7c7cc;min-height:61px}.right{display:grid;grid-template-rows:auto minmax(260px,38vh) auto minmax(0,1fr);min-width:0;min-height:0;background:#0c0c0e;overflow:hidden}.detailHead{padding:18px 20px;border-bottom:1px solid var(--line);background:#101012}.detailHead h2{margin:0;font-size:20px;line-height:1.2;font-weight:760}.sub{margin-top:7px;color:var(--muted);font-size:12px;line-height:1.4;word-break:break-word}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.actions button{font-size:12px}.stageWrap{position:relative;background:#050506;overflow:hidden;border-bottom:1px solid var(--line)}.stage{width:100%;height:100%;display:block}.stageBadge{position:absolute;left:14px;bottom:14px;display:flex;gap:7px;flex-wrap:wrap}.stageBadge span{background:rgba(8,8,10,.78);border:1px solid #424248;border-radius:999px;padding:6px 9px;font-size:11px;color:#ededf0}.params{border-bottom:1px solid var(--line);padding:14px 20px;background:#111113;display:grid;grid-template-columns:repeat(3,1fr);gap:13px 16px}.param label{display:flex;justify-content:space-between;color:#c6c6cd;font-size:11px;margin-bottom:7px}.param b{color:#fff}.param input{width:100%;accent-color:#fff}.info{display:grid;grid-template-columns:1fr;min-height:0;overflow-y:auto;scrollbar-gutter:stable}.panel{min-height:0;padding:18px 20px;border-bottom:1px solid var(--line)}.panel h3{font-size:13px;margin:0 0 10px;color:#fff}.panel p,.panel li{font-size:12px;line-height:1.55;color:#c8c8cf}.contract{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}.kv{border:1px solid #26262b;background:#101012;border-radius:8px;padding:10px}.kv b{display:block;font-size:11px;color:#fff;margin-bottom:5px}.kv span{color:#aaaab2;font-size:11px;line-height:1.4;word-break:break-word}.code{white-space:pre-wrap;font:11px/1.45 Consolas,Menlo,monospace;color:#eeeeef;background:#09090b;border:1px solid #25252a;border-radius:8px;padding:12px;margin:10px 0 0;max-height:260px;overflow:auto}details{margin-top:12px}summary{cursor:pointer;font-size:12px;color:#fff;list-style:none}summary::before{content:"Code";display:inline-block;margin-right:8px;color:#aaa}summary::-webkit-details-marker{display:none}a{color:#fff;text-decoration:underline;text-decoration-color:#555;text-underline-offset:2px}@media(max-width:1180px){.app{grid-template-columns:1fr}.right{position:fixed;right:0;top:0;bottom:0;width:min(520px,100vw);box-shadow:-20px 0 50px rgba(0,0,0,.35)}.left{border-right:0}.filters{grid-template-columns:1fr 150px 88px}}@media(max-width:760px){body{overflow:auto}.app{display:block;height:auto;overflow:visible}.left{display:block}.shelf{max-height:none;overflow:visible;grid-template-columns:1fr;padding:12px}.right{position:static;width:auto;min-height:900px}.params{grid-template-columns:1fr 1fr}.contract{grid-template-columns:1fr}.filters{grid-template-columns:1fr}.brand{grid-template-columns:1fr}.brand p{text-align:left}.info{overflow:visible}}
</style>
<style>
summary{border:1px solid #29292f;border-radius:8px;padding:10px 12px;background:#111113}
summary::before{content:""!important;margin:0!important}
summary::after{content:"Open";float:right;color:#aaa}
details[open] summary::after{content:"Close"}
.shelf{padding-bottom:96px!important}
.info::after{content:"Scroll for more details";display:block;position:sticky;bottom:0;margin:12px 0 0;padding:10px 12px;background:linear-gradient(180deg,rgba(12,12,14,0),#0c0c0e 22%);color:#85858d;font-size:12px;text-align:center}
.panel p,.panel li{font-size:13px!important}.cardMeta{font-size:12.5px!important}.kv span{font-size:12px!important}
@media(max-width:1180px){body{overflow:auto!important}.app{display:block!important;height:auto!important;overflow:visible!important}.left{display:block!important}.shelf{overflow:visible!important}.right{position:static!important;width:auto!important;min-height:900px!important;box-shadow:none!important}}
.right{grid-template-rows:auto minmax(300px,42vh) auto minmax(0,1fr)!important}
.tuneBlock{margin:0!important;border-bottom:1px solid var(--line);background:#101012;padding:12px 20px}.tuneBlock summary{max-width:100%}
.params{border:0!important;border-radius:8px!important;margin-top:10px!important;padding:12px!important;background:#0d0d10!important;grid-template-columns:repeat(2,1fr)!important}
.importStatus{display:none;margin-top:10px;border:1px solid #303038;background:#0b0b0d;border-radius:8px;padding:10px 12px;color:#d7d7dc;font-size:12px;line-height:1.45;word-break:break-word}.importStatus.show{display:block}.importStatus b{color:#fff}.importStatus code{font:11px/1.35 Consolas,Menlo,monospace;color:#fff}
.stageBadge span:nth-child(1){display:none}
.stats .pill:nth-child(n+3){display:none}
</style>
</head>
<body>
<main class="app">
  <section class="left">
    <header class="top">
      <div class="brand"><h1>HLSL Selector</h1><p>Find a base material like shopping for clothes.<br>Pick, tune, export as a template.</p></div>
      <div class="stats"><span class="pill" id="countPill">100 methods</span><span class="pill" id="refPill">references</span><span class="pill">rain water</span><span class="pill">template manifest</span><span class="pill">HLSL source</span></div>
      <div class="filters"><input id="search" placeholder="Search shallow water, runoff, curb, foam..."><select id="rack"><option value="">All racks</option></select><select id="pageSize" title="Materials per page"><option>20 / page</option><option>30 / page</option><option>40 / page</option></select></div>
    </header>
    <section class="shelf" id="shelf"></section>
    <footer class="pager"><button id="prev">Prev</button><span id="pageInfo">Page 1</span><button id="next">Next</button></footer>
  </section>
  <section class="right">
    <header class="detailHead"><h2 id="title">Loading...</h2><div class="sub" id="subtitle"></div><div class="actions"><button id="importUe">Import to UE</button><button id="copyHlsl">Copy HLSL</button><button id="downloadManifest">Download Manifest</button></div><div class="importStatus" id="importStatus"></div></header>
    <div class="stageWrap"><canvas id="stage" class="stage"></canvas><div id="stageBadge" class="stageBadge"></div></div>
    <details class="tuneBlock"><summary>Tune preview</summary><section class="params">
      <div class="param"><label><span>Rain</span><b id="vRain">0.80</b></label><input id="rain" type="range" min="0" max="1.5" step="0.01" value="0.80"></div>
      <div class="param"><label><span>Depth</span><b id="vDepth">0.070</b></label><input id="depth" type="range" min="0.015" max="0.20" step="0.001" value="0.07"></div>
      <div class="param"><label><span>Damping</span><b id="vDamping">1.45</b></label><input id="damping" type="range" min="0.25" max="4.5" step="0.01" value="1.45"></div>
      <div class="param"><label><span>Flow</span><b id="vFlow">0.20</b></label><input id="flow" type="range" min="0" max="1.2" step="0.01" value="0.20"></div>
      <div class="param"><label><span>Rough</span><b id="vRoughness">0.12</b></label><input id="roughness" type="range" min="0.02" max="0.6" step="0.01" value="0.12"></div>
      <div class="param"><label><span>Scale</span><b id="vScale">1.00</b></label><input id="scale" type="range" min="0.45" max="2.0" step="0.01" value="1.00"></div>
    </section></details>
    <section class="info"><div class="panel"><h3>Material Method</h3><p id="algorithm"></p><div class="contract" id="contract"></div><details><summary>HLSL Code</summary><pre class="code" id="code"></pre></details><details><summary>Sources and Manifest</summary><ul id="sources"></ul><pre class="code" id="manifest"></pre></details></div></section>
  </section>
</main>
<script id="bootData" type="application/json">${boot}</script>
<script>
const vertexShaderSource=\`attribute vec2 a_pos;varying vec2 v_uv;void main(){v_uv=a_pos*0.5+0.5;gl_Position=vec4(a_pos,0.0,1.0);}\`;
const fragmentShaderSource=\`
precision highp float;
varying vec2 v_uv;
uniform float u_time,u_seed,u_depth,u_damping,u_rain,u_flow,u_roughness,u_scale;
uniform int u_class;
float hash12(vec2 p){vec3 p3=fract(vec3(p.xyx)*0.1031);p3+=dot(p3,p3.yzx+33.33);return fract((p3.x+p3.y)*p3.z);}
vec2 hash22(vec2 p){float n=hash12(p);return vec2(n,hash12(p+n+17.13));}
float impulse(vec2 p,float t,float seed,float depth,float damping){float c=sqrt(max(.003,9.81*depth));float birth=floor(t*u_rain*4.0+seed*7.7);float age=fract(t*u_rain*4.0+seed*7.7);vec2 center=hash22(vec2(seed*12.1,birth*.41))*2.0-1.0;float r=length(p-center);float front=c*age*.62;float width=mix(.014,.06,age);return exp(-abs(r-front)/width)*sin((r-front)*56.0)*exp(-damping*age)*(1.0-smoothstep(.82,1.0,age));}
float poisson(vec2 p,float t,float density,float seed){vec2 cell=floor(p*density),local=fract(p*density)-.5;float h=0.0;for(int x=-1;x<=1;x++){for(int y=-1;y<=1;y++){vec2 c=cell+vec2(float(x),float(y));vec2 rnd=hash22(c+seed);float age=fract(t*u_rain+rnd.x*3.1);vec2 d=local-vec2(float(x),float(y))-(rnd-.5);h+=sin((length(d)-age*.55)*44.0)*exp(-abs(length(d)-age*.55)*9.0)*exp(-age*u_damping)*step(.38,rnd.y);}}return h*.045;}
float spectrum(vec2 p,float t,float depth){float c=sqrt(max(.003,9.81*depth)),h=0.0;for(int i=0;i<7;i++){float fi=float(i)+1.0;vec2 dir=normalize(vec2(sin(fi*2.17+u_seed),cos(fi*1.73-u_seed)));float freq=mix(3.5,30.0,fi/7.0);h+=sin(dot(p,dir)*freq-t*c*freq*.16+u_seed*fi)*(.024/fi);}return h*u_rain;}
float heightField(vec2 p,float t){vec2 slope=normalize(vec2(.82,.31));float h=0.0;if(u_class==0){for(int i=0;i<14;i++)h+=impulse(p,t,u_seed+float(i)*.17,u_depth,u_damping)*.030;}else if(u_class==1){h=poisson(p,t,4.5,u_seed)+spectrum(p,t,u_depth)*.45;}else if(u_class==2){h=poisson(p+vec2(sin(t*.2),cos(t*.13))*.12,t,7.5,u_seed)*1.3;}else if(u_class==3){vec2 q=p+slope*t*u_flow*.34;h=poisson(q,t,5.0,u_seed)+sin(dot(q,slope)*16.0-t*2.0)*.018;}else if(u_class==4){vec2 src=vec2(.38,.24);h=impulse(p-src,t,u_seed,u_depth,u_damping)*.04+impulse(p-vec2(src.x,-src.y),t,u_seed+2.0,u_depth,u_damping)*.026;}else if(u_class==5){float mask=smoothstep(.9,.12,length(p*vec2(1.0,.72)));h=poisson(p,t,4.2,u_seed)+spectrum(p,t,mix(.018,u_depth*2.6,mask))*mask;}else if(u_class==6){h=spectrum(p,t,u_depth)+poisson(p*1.7,t,10.0,u_seed)*.50;}else if(u_class==7){vec2 q=p+slope*t*u_flow*.2;h=poisson(q,t,6.0,u_seed)+impulse(p,t,u_seed+1.7,u_depth,u_damping)*.035+sin(q.y*22.0-t*3.0)*.012;}else if(u_class==8){vec2 q=p+vec2(sin(p.y*2.2+t*.7),cos(p.x*2.0-t*.4))*.10*u_flow;h=poisson(q,t,8.0,u_seed)*1.1+spectrum(q,t,u_depth)*.8;}else if(u_class==9){h=spectrum(p*1.8,t,u_depth)*.55+poisson(p*2.0,t,14.0,u_seed)*.22;}else if(u_class==10){float channel=exp(-abs(p.y+.2)*3.0);h=(poisson(p+slope*t*u_flow,t,5.0,u_seed)+sin(p.x*18.0-t*3.0)*.02)*channel;}else if(u_class==11){float basin=smoothstep(1.1,.25,length(p*vec2(1.2,.72)));h=(poisson(p,t,4.0,u_seed)+spectrum(p,t,u_depth))*basin;}else if(u_class==12){h=poisson(p,t,3.0,u_seed)*.35+spectrum(p*.7,t,u_depth)*.25;}else if(u_class==13){h=poisson(p,t,12.0,u_seed)*1.25+sin(p.x*28.0+p.y*7.0-t*4.0)*.012;}else if(u_class==14){vec2 q=vec2(p.x*.62,p.y*1.32);h=poisson(q,t,5.5,u_seed)+spectrum(q,t,u_depth)*.45;}else{h=poisson(p,t,16.0,u_seed)*.18+spectrum(p,t,u_depth)*.22;}return h*u_scale;}
void main(){vec2 screen=v_uv*2.0-1.0;vec3 bg=mix(vec3(0.0),vec3(.035),smoothstep(0.0,1.0,v_uv.y));float grid=(step(.992,fract(v_uv.x*12.0))+step(.992,fract(v_uv.y*8.0)))*.06;float planeMask=smoothstep(.03,.18,v_uv.y)*(1.0-smoothstep(.98,1.0,v_uv.y));float persp=1.0/(.28+v_uv.y*1.36);vec2 p=vec2(screen.x*persp*1.95,(1.0-v_uv.y)*5.2-1.62);float t=u_time*.55,eps=.018;float h=heightField(p,t);float hx=heightField(p+vec2(eps,0.0),t)-heightField(p-vec2(eps,0.0),t);float hy=heightField(p+vec2(0.0,eps),t)-heightField(p-vec2(0.0,eps),t);vec3 n=normalize(vec3(-hx*18.0,1.0,-hy*18.0));vec3 light=normalize(vec3(-.45,.9,.25));float diff=max(dot(n,light),0.0);float spec=pow(max(reflect(-light,n).y,0.0),mix(22.0,90.0,1.0-u_roughness));float foam=smoothstep(.025,.11,abs(h)+length(vec2(hx,hy))*2.0);float rainLine=step(.986,fract((screen.x*.8+screen.y*1.9+t*2.6+hash12(floor(screen*22.0)))*16.0))*u_rain;float horizon=smoothstep(.44,.72,v_uv.y);vec3 water=vec3(.028)+vec3(.72)*(spec*.95+foam*.15)+vec3(.12)*diff+rainLine*.12+vec3(.035)*horizon;vec3 col=mix(bg+grid,water+grid*.45,planeMask);gl_FragColor=vec4(clamp(col,0.0,1.0),1.0);}
\`;
const bootData=JSON.parse(document.getElementById("bootData").textContent);
const state={meta:null,page:1,pages:1,entries:[],selected:null,main:null,thumbMain:null,lastFrame:0,lastThumbFrame:0,usedBootList:false,visibleThumbs:new Set()};window.hlslSelectorState=state;const $=id=>document.getElementById(id);const params=["rain","depth","damping","flow","roughness","scale"];
function labelId(id){return "v"+id[0].toUpperCase()+id.slice(1);}
function setParamLabel(id,value){$(labelId(id)).textContent=(+value).toFixed(id==="depth"?3:2);}
function syncParams(m){params.forEach(id=>{const value=m.params[id];$(id).value=value;setParamLabel(id,value);});}
params.forEach(id=>$(id).addEventListener("input",()=>{setParamLabel(id,$(id).value);if(state.selected)renderContract(state.selected);}));["search","rack","pageSize"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{state.page=1;loadList();}));$("prev").onclick=()=>{if(state.page>1){state.page--;loadList();}};$("next").onclick=()=>{if(state.page<state.pages){state.page++;loadList();}};
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));}
function displayName(m){return String(m.title).replace(/^\\d+\\s+/,"").replace("Green impulse rings","Rain rings").replace("Finite-difference normal","Stable normals").replace("Poisson source field","Random rain field").replace("Slope advected sheet","Flowing rain sheet").replace("Boundary reflection","Edge reflections").replace("Depth-varying speed","Depth waves").replace("Rain energy spectrum","Rain spectrum").replace("Hybrid cells plus sheet","Layered sheet").replace("Runoff interference","Runoff pattern").replace("Capillary detail","Fine ripples").replace("Puddle basin SDF","Puddle basin").replace("Foam threshold field","Foam highlights");}
function pageSizeValue(){return parseInt($("pageSize").value,10)||20;}
async function loadMeta(){state.meta=bootData.meta;$("countPill").textContent=state.meta.count+" methods";$("refPill").textContent=state.meta.referenceCount+" / "+state.meta.referenceTarget+" refs";$("rack").innerHTML='<option value="">All racks</option>'+state.meta.racks.map(d=>'<option>'+esc(d)+'</option>').join("");}
async function loadList(){const size=pageSizeValue();const canBoot=!state.usedBootList&&state.page===1&&size===20&&!$("search").value&&!$("rack").value;const data=canBoot?bootData.firstPage:await(await fetch("/api/materials?"+new URLSearchParams({page:state.page,pageSize:size,q:$("search").value,rack:$("rack").value}))).json();state.usedBootList=true;state.entries=data.entries;state.page=data.page;state.pages=data.pages;state.visibleThumbs.clear();$("pageInfo").textContent="Page "+data.page+" / "+data.pages+" - "+data.total+" methods";$("shelf").innerHTML=data.entries.map(cardHtml).join("");document.querySelectorAll(".card").forEach(el=>el.onclick=()=>selectMaterial(el.dataset.id));observeThumbs();if(!data.entries.length){clearDetail();return;}if(!state.selected||!data.entries.some(m=>m.id===state.selected.id)){if(canBoot)applyMaterial(bootData.firstMaterial);else await selectMaterial(data.entries[0].id);}data.entries.slice(0,12).forEach(drawThumb);}
function cardHtml(m){return '<article class="card '+(state.selected&&state.selected.id===m.id?'active':'')+'" data-id="'+m.id+'"><canvas class="thumb" id="thumb_'+m.id+'"></canvas><div class="cardBody"><div class="cardTitle">'+esc(displayName(m))+'</div><div class="cardMeta">'+esc(m.rack)+' / '+esc(m.mission)+'<br>'+esc(m.complexity)+' / '+(m.referenceStatus==="verified-candidate"?"ref checked":"needs ref")+'</div><div class="cardTags"><span class="tag">'+esc(m.substrate)+'</span><span class="tag">'+esc(m.outputChannels.length)+' outputs</span></div></div></article>';}
function drawThumb(m){drawThumbPreview(m,performance.now());}
let thumbObserver=null;function observeThumbs(){if(thumbObserver)thumbObserver.disconnect();thumbObserver=new IntersectionObserver(entries=>{entries.forEach(entry=>{const id=entry.target.id.replace("thumb_","");if(entry.isIntersecting)state.visibleThumbs.add(id);else state.visibleThumbs.delete(id);});},{root:$("shelf"),rootMargin:"160px"});document.querySelectorAll(".thumb").forEach(c=>thumbObserver.observe(c));}
function makeThumbRenderer(){const c=document.createElement("canvas");c.style.cssText="position:absolute;left:-9999px;top:0;width:192px;height:104px;pointer-events:none";c.dataset.previewWidth="192";c.dataset.previewHeight="104";document.body.appendChild(c);return makeRenderer(c,state.entries[0]||bootData.firstMaterial);}
function drawThumbPreview(m,time){const c=$("thumb_"+m.id);if(!c)return;if(!state.thumbMain)state.thumbMain=makeThumbRenderer();const r=c.getBoundingClientRect(),d=Math.min(2,devicePixelRatio||1),bw=Math.max(1,Math.floor(r.width*d)),bh=Math.max(1,Math.floor(r.height*d)),cssW=Math.max(1,Math.floor(r.width)),cssH=Math.max(1,Math.floor(r.height));if(c.width!==bw||c.height!==bh){c.width=bw;c.height=bh;}if(state.thumbMain.canvas.dataset.previewWidth!==String(cssW)||state.thumbMain.canvas.dataset.previewHeight!==String(cssH)){state.thumbMain.canvas.style.width=cssW+"px";state.thumbMain.canvas.style.height=cssH+"px";state.thumbMain.canvas.dataset.previewWidth=String(cssW);state.thumbMain.canvas.dataset.previewHeight=String(cssH);}state.thumbMain.material=m;state.thumbMain.draw(time);const x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.drawImage(state.thumbMain.canvas,0,0,c.width,c.height);}
function manifestFor(m){if(!m)return{};const adjusted={};params.forEach(id=>adjusted[id]=Number($(id).value));return{schema:"hlsl-selector.material-template.v1",id:m.id,title:m.title,rack:m.rack,mission:m.mission,substrate:m.substrate,baseFamily:m.baseFamilyName,complexity:m.complexity,exportStatus:m.exportStatus,referenceStatus:m.referenceStatus,referenceIds:m.referenceIds,references:m.references||[],licensePolicy:m.licensePolicy,params:adjusted,parameterSchema:m.parameterSchema,outputs:m.outputChannels,ueImport:m.ueImport,sourceIds:m.sourceIds,hlsl:m.hlsl};}
function renderContract(m){$("contract").innerHTML=[["Use case",m.mission+" on "+m.substrate],["Complexity",m.complexity],["Reference",m.referenceStatus==="verified-candidate"?(m.references&&m.references[0]?m.references[0].title:"checked"):"needs specific reference"],["UE target",m.ueImport.assetType+" / Custom node"],["Path",m.ueImport.suggestedPath],["License",m.licensePolicy]].map(([k,v])=>'<div class="kv"><b>'+esc(k)+'</b><span>'+esc(v)+'</span></div>').join("");$("manifest").textContent=JSON.stringify(manifestFor(m),null,2);}
function setImportStatus(html,show=true){$("importStatus").innerHTML=html;$("importStatus").classList.toggle("show",show);}
function clearDetail(){state.selected=null;$("title").textContent="No material";$("subtitle").textContent="No matching template in this shelf.";$("algorithm").textContent="";$("code").textContent="";$("sources").innerHTML="";$("contract").innerHTML="";$("manifest").textContent="";$("stageBadge").innerHTML="";setImportStatus("",false);if(state.main)state.main.material=null;}
function applyMaterial(m){state.selected=m;syncParams(state.selected);setImportStatus("",false);document.querySelectorAll(".card").forEach(el=>el.classList.toggle("active",el.dataset.id===m.id));$("title").textContent=m.title;$("subtitle").textContent=m.rack+" rack / "+m.mission+" / "+m.id;$("algorithm").textContent=m.algorithm;$("code").textContent=m.hlsl;renderContract(m);$("sources").innerHTML=[...(m.references||[]).map(r=>'<li><a href="'+esc(r.url)+'" target="_blank">'+esc(r.title)+'</a><br>reference candidate / '+esc(r.usedFor)+'</li>'),...m.sources.map(s=>'<li><a href="'+esc(s.url)+'" target="_blank">'+esc(s.title)+'</a><br>'+esc(s.license)+' / '+esc(s.usedFor)+'</li>')].join("");$("stageBadge").innerHTML=[m.referenceStatus==="verified-candidate"?"ref checked":"needs ref",m.complexity,"outputs "+m.outputChannels.length].map(t=>"<span>"+esc(t)+"</span>").join("");if(!state.main)state.main=makeRenderer($("stage"),m);state.main.material=m;state.main.draw(performance.now());}
async function selectMaterial(id){applyMaterial(await(await fetch("/api/material/"+id)).json());}
$("copyHlsl").onclick=async()=>{if(!state.selected)return;await navigator.clipboard.writeText(state.selected.hlsl);const b=$("copyHlsl");const old=b.textContent;b.textContent="Copied";setTimeout(()=>b.textContent=old,1100);};
$("downloadManifest").onclick=()=>{if(!state.selected)return;const blob=new Blob([JSON.stringify(manifestFor(state.selected),null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=state.selected.id+".json";a.click();URL.revokeObjectURL(url);};
$("importUe").onclick=async()=>{if(!state.selected)return;const b=$("importUe"),old=b.textContent;try{b.disabled=true;b.textContent="Building...";setImportStatus("Building UE import package...",true);const manifest=manifestFor(state.selected);const resp=await fetch("/api/import-to-ue/"+encodeURIComponent(state.selected.id),{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({params:manifest.params})});const data=await resp.json();if(!resp.ok||!data.ok)throw new Error(data.error||"Import package failed");setImportStatus('<b>UE package ready</b><br>Script: <code>'+esc(data.files.uePythonScript)+'</code><br>Shader: <code>'+esc(data.files.generatedUsh)+'</code><br>Asset target: <code>'+esc(data.ueAsset)+'</code><br>'+esc(data.runHint),true);b.textContent="Ready";setTimeout(()=>b.textContent=old,1200);}catch(e){setImportStatus('<b>Import package failed</b><br>'+esc(e.message),true);b.textContent="Failed";setTimeout(()=>b.textContent=old,1600);}finally{b.disabled=false;}};
function makeRenderer(canvas,material){try{const gl=canvas.getContext("webgl",{antialias:false,preserveDrawingBuffer:false,powerPreference:"low-power"});if(!gl)throw new Error("WebGL unavailable");const program=createProgram(gl,vertexShaderSource,fragmentShaderSource);const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);const pos=gl.getAttribLocation(program,"a_pos");const uniforms={};["u_time","u_seed","u_depth","u_damping","u_rain","u_flow","u_roughness","u_scale","u_class"].forEach(n=>uniforms[n]=gl.getUniformLocation(program,n));return{canvas,gl,program,buf,pos,uniforms,material,draw(time){try{drawRenderer(this,time);}catch(e){console.warn("preview fallback",e.message);this.gl=null;drawFallback(this.canvas,this.material,time);}}};}catch(e){console.warn("preview fallback",e.message);return{canvas,gl:null,material,draw(time){drawFallback(canvas,this.material,time);}};}}
function createProgram(gl,vs,fs){const v=compile(gl,gl.VERTEX_SHADER,vs),f=compile(gl,gl.FRAGMENT_SHADER,fs),p=gl.createProgram();gl.attachShader(p,v);gl.attachShader(p,f);gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));return p;}function compile(gl,type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}function resize(c){const d=Math.min(2,devicePixelRatio||1),r=c.getBoundingClientRect(),cssW=Number(c.dataset.previewWidth)||r.width,cssH=Number(c.dataset.previewHeight)||r.height,w=Math.max(1,Math.floor(cssW*d)),h=Math.max(1,Math.floor(cssH*d));if(c.width!==w||c.height!==h){c.width=w;c.height=h;}}
function drawRenderer(r,time){const m=r.material;if(!m||!r.gl)return;resize(r.canvas);const gl=r.gl;gl.viewport(0,0,r.canvas.width,r.canvas.height);gl.useProgram(r.program);gl.bindBuffer(gl.ARRAY_BUFFER,r.buf);gl.enableVertexAttribArray(r.pos);gl.vertexAttribPointer(r.pos,2,gl.FLOAT,false,0,0);for(const id of params){const raw=Number($(id).value);const value=Number.isFinite(raw)?raw:m.params[id];gl.uniform1f(r.uniforms["u_"+id],r.canvas.id==="stage"?value:m.params[id]);}gl.uniform1f(r.uniforms.u_time,time*.001);gl.uniform1f(r.uniforms.u_seed,m.params.seed);gl.uniform1i(r.uniforms.u_class,m.classIndex);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);}
function drawFallback(canvas,m,time){if(!m)return;resize(canvas);const x=canvas.getContext("2d"),w=canvas.width,h=canvas.height,d=Math.min(2,devicePixelRatio||1);x.fillStyle="#050505";x.fillRect(0,0,w,h);const g=x.createLinearGradient(0,0,0,h);g.addColorStop(0,"#343434");g.addColorStop(.64,"#151515");g.addColorStop(1,"#000");x.fillStyle=g;x.fillRect(0,0,w,h);x.strokeStyle="rgba(255,255,255,.08)";x.lineWidth=d;for(let i=0;i<13;i++){x.beginPath();x.moveTo(w*i/12,0);x.lineTo(w*i/12,h);x.stroke();}x.strokeStyle="rgba(255,255,255,.52)";x.lineWidth=1.2*d;for(let i=0;i<24;i++){const px=((i*73+m.params.seed*41)%100)/100*w,py=((i*37+m.order*11+(time*.01))%100)/100*h*.72,rx=(20+(i%7)*13)*d,ry=rx*.22;x.beginPath();x.ellipse(px,py,rx,ry,0,0,Math.PI*2);x.stroke();}x.fillStyle="rgba(255,255,255,.32)";for(let i=0;i<160;i++){const px=((i*29+m.order*17)%100)/100*w,py=((i*47+m.order*7+time*.02)%100)/100*h;x.fillRect(px,py,d,d);}}
function frame(t){if(state.main&&t-state.lastFrame>42){state.main.draw(t);state.lastFrame=t;}if(state.entries.length&&t-state.lastThumbFrame>1000){state.entries.filter(m=>state.visibleThumbs.has(m.id)).forEach(m=>drawThumbPreview(m,t));state.lastThumbFrame=t;}requestAnimationFrame(frame);}loadMeta().then(loadList).then(()=>requestAnimationFrame(frame)).catch(e=>{console.error(e);$("title").textContent="Load failed";$("subtitle").textContent=e.message;});
</script>
</body>
</html>`;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  if (url.pathname.startsWith("/api/")) {
    routeApi(req, res, url).catch((error) => errorJson(res, 500, error.message));
    return;
  }
  res.writeHead(200, {"content-type": "text/html; charset=utf-8", "cache-control": "no-store"});
  res.end(html());
});

server.listen(port, host, () => {
  console.log(`HLSL Selector: http://${host}:${port}/`);
  console.log(`Loaded ${materials.length} base material methods`);
});
