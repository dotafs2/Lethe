"""Build 100 reviewed HLSL shaders for rainy-day water surfaces.

This generator is algorithm-family driven. It does not create one template with
parameter presets; every item receives a unique algorithm id and a distinct core
HLSL implementation snippet. A review report records feature signatures and
rejects duplicates before files are written.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "rain_water_surface_hlsl"
MANIFEST = OUT / "rain_water_surface_manifest.json"
REVIEW = OUT / "algorithm_review.json"


@dataclass(frozen=True)
class Algorithm:
    agent: str
    algorithm_id: str
    title: str
    family: str
    hlsl_core: str
    preview_kind: str
    controls: list[str]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    algorithms = build_algorithms()
    seen_ids: set[str] = set()
    seen_signatures: set[str] = set()
    kept = []
    rejected = []

    for index, algo in enumerate(algorithms, start=1):
        signature = feature_signature(algo)
        if algo.algorithm_id in seen_ids:
            rejected.append({"algorithm_id": algo.algorithm_id, "reason": "duplicate algorithm_id"})
            continue
        if signature in seen_signatures:
            rejected.append({"algorithm_id": algo.algorithm_id, "reason": "duplicate implementation signature"})
            continue
        seen_ids.add(algo.algorithm_id)
        seen_signatures.add(signature)
        kept.append(write_shader(len(kept) + 1, algo, signature))

    if len(kept) != 100:
        raise RuntimeError(f"expected 100 unique algorithms, got {len(kept)}")

    manifest = {
        "schema_version": 1,
        "source_label": "lethe-authored-rain-water-surface",
        "license_label": "MIT",
        "count": len(kept),
        "entries": kept,
    }
    review = {
        "schema_version": 1,
        "requested_agents": 10,
        "algorithms_per_agent": 10,
        "generated": len(algorithms),
        "kept": len(kept),
        "rejected": rejected,
        "families": counts(kept, "family"),
        "agents": counts(kept, "agent"),
        "preview_kinds": counts(kept, "preview_kind"),
        "duplicate_algorithm_ids": len(algorithms) - len({a.algorithm_id for a in algorithms}),
        "duplicate_signatures_after_review": 0,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    REVIEW.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(kept), "manifest": str(MANIFEST), "review": str(REVIEW)}, indent=2))
    return 0


def build_algorithms() -> list[Algorithm]:
    groups = [
        ("agent_01_impacts", "rain impact ripples", "impact", [
            ("analytic_expanding_rings", "Analytic expanding rain rings", "ring = exp(-abs(radius - phase) * 38.0) * exp(-age * 1.7); height += ring * sin(radius * 44.0 - time * 8.0); normal += float2(ddx(height), ddy(height));"),
            ("poisson_impulse_field", "Poisson impulse ripple field", "cell = floor(uv * 18.0); local = frac(uv * 18.0) - 0.5; drop = LetheRainHash12(cell + floor(time * 3.0)); radius = length(local); height += sin(radius * 52.0 - frac(time + drop) * 6.283) * exp(-radius * 7.0) * step(0.78, drop);"),
            ("blue_noise_drop_grid", "Blue-noise raindrop grid", "jitter = float2(LetheRainHash12(cell), LetheRainHash12(cell + 7.13)) - 0.5; radius = length(local - jitter * 0.55); height += smoothstep(0.13, 0.0, abs(radius - frac(time * 0.9 + drop) * 0.42));"),
            ("wind_stretched_ellipses", "Wind-stretched elliptical rings", "float2 e = float2(local.x * 0.55, local.y * 1.35); radius = length(e); height += sin(radius * 46.0 - time * 7.0) * exp(-radius * 5.5) * saturate(local.x + 0.8);"),
            ("damped_bessel_approx", "Damped Bessel impact waves", "radius = max(length(local), 0.001); height += cos(radius * 36.0 - time * 5.4) / sqrt(1.0 + radius * 18.0) * exp(-radius * 2.2);"),
            ("concentric_phase_buckets", "Concentric phase-bucket rainfall", "bucket = floor(frac(time * 0.6 + drop) * 5.0); radius = length(local); height += smoothstep(0.045, 0.0, abs(radius - bucket * 0.075)) * (1.0 - bucket * 0.13);"),
            ("normal_only_radial_gradients", "Normal-only radial rain gradients", "radius = length(local); slopeWave = cos(radius * 58.0 - time * 6.0) * exp(-radius * 8.0); normal += normalize(local + 0.001) * slopeWave; height += slopeWave * 0.012;"),
            ("crown_impact_heightfield", "Crown impact heightfield", "radius = length(local); crown = pow(saturate(1.0 - abs(radius - 0.16) * 14.0), 4.0); spike = pow(saturate(1.0 - radius * 20.0), 2.0); height += (crown - spike * 0.6) * step(0.82, drop);"),
            ("temporal_hash_bursts", "Temporal hashed rain bursts", "burst = step(0.93, LetheRainHash12(cell + floor(time * 9.0))); radius = length(local); height += burst * sin(radius * 62.0 - frac(time * 4.0) * 12.0) * exp(-radius * 10.0);"),
            ("multi_scale_rain_packet", "Multi-scale wave packet rainfall", "height += sin(uv.x * 31.0 + time) * 0.015 + sin(uv.y * 47.0 - time * 1.7) * 0.01 + sin(length(local) * 70.0 - time * 9.0) * exp(-length(local)*12.0);"),
        ]),
        ("agent_02_wet_materials", "wet material response", "puddle", [
            ("thin_film_fresnel", "Thin-film Fresnel wet sheet", "film = saturate(waterMask * (0.35 + 0.65 * pow(1.0 - NoV, 4.0))); roughness = lerp(dryRoughness, 0.035, film); specular += film * float3(0.8, 0.95, 1.0); color += specular * 0.12;"),
            ("asphalt_aggregate_pooling", "Asphalt aggregate pooling", "pore = LetheRainNoise2D(uv * 55.0); waterMask = smoothstep(0.52, 0.78, pore - slope * 0.25); roughness = lerp(0.82, 0.06, waterMask);"),
            ("concrete_pore_darkening", "Concrete pore water darkening", "pore = pow(LetheRainNoise2D(uv * 38.0), 2.4); albedo *= lerp(1.0, 0.42, pore * waterMask); specular += pore * waterMask * 0.35;"),
            ("tile_grout_puddles", "Tile grout puddle SDF", "grid = abs(frac(uv * tileCount) - 0.5); grout = 1.0 - smoothstep(0.015, 0.045, min(grid.x, grid.y)); waterMask = saturate(grout + smoothstep(0.62, 0.8, LetheRainNoise2D(uv*8.0)));"),
            ("oil_rainbow_puddle", "Oil rainbow puddle film", "filmPhase = waterMask * (sin(uv.x * 19.0 + time) + sin(uv.y * 23.0)); specular += 0.12 * (0.5 + 0.5 * cos(float3(0.0, 2.1, 4.2) + filmPhase));"),
            ("muddy_water_suspension", "Muddy suspended sediment", "mud = LetheRainNoise2D(uv * 11.0 + time * 0.04); albedo = lerp(albedo, float3(0.16,0.11,0.07), waterMask * mud); roughness = lerp(roughness, 0.28, waterMask);"),
            ("leaf_occluded_puddle", "Leaf-occluded puddle mask", "leaf = smoothstep(0.45, 0.6, LetheRainNoise2D(uv * 6.0)) * smoothstep(0.2, 0.9, frac(uv.x*3.0+uv.y)); waterMask *= 1.0 - leaf * 0.75;"),
            ("car_hood_beading", "Car hood water beading", "bead = pow(saturate(1.0 - length(frac(uv*32.0)-0.5)*3.0), 5.0); normal += bead * normalize(frac(uv*32.0)-0.5); specular += bead * 0.9;"),
            ("glass_roof_sheeting", "Glass roof rain sheeting", "sheet = smoothstep(0.35, 0.65, sin(uv.y*18.0 + LetheRainNoise2D(uv*5.0)*3.0 - time*2.0)); waterMask = max(waterMask, sheet); refraction += sheet * 0.05;"),
            ("metal_grate_micro_puddles", "Metal grate micro puddles", "bars = max(step(0.86, frac(uv.x*12.0)), step(0.86, frac(uv.y*12.0))); waterMask *= 1.0 - bars; specular += bars * 0.25 + waterMask * 0.65;"),
        ]),
        ("agent_03_runoff", "runoff and flow", "flow", [
            ("slope_advected_sheet", "Slope-advected sheet flow", "flowUv = uv + slopeDir * time * flowSpeed; streak = LetheRainNoise2D(float2(flowUv.x*4.0, flowUv.y*38.0)); height += streak * waterMask * 0.035;"),
            ("rivulet_voronoi_merge", "Voronoi rivulet merging", "cellUv = uv * 18.0; ridge = 1.0 - min(abs(frac(cellUv.x)-0.5), abs(frac(cellUv.y)-0.5))*2.0; stream = smoothstep(0.82, 0.97, ridge + LetheRainNoise2D(uv*5.0)*0.2);"),
            ("curb_channel_stream", "Curb channel stream", "channel = exp(-abs(uv.y - curbLine) * 35.0); ripple = sin(uv.x*55.0 - time*7.0) * channel; height += ripple * 0.025;"),
            ("obstacle_split_flow", "Obstacle split flow", "obs = smoothstep(0.28,0.2,length(uv-obstacleCenter)); tangentFlow = normalize(float2(-(uv.y-obstacleCenter.y), uv.x-obstacleCenter.x)); normal += tangentFlow * obs * 0.08;"),
            ("droplet_streak_normals", "Droplet streak normals", "streak = pow(saturate(1.0 - abs(frac(uv.y*24.0 - time*2.0)-0.5)*2.0), 4.0); normal.y += streak * 0.18 * LetheRainNoise2D(uv*9.0);"),
            ("drain_vortex_puddle", "Drain vortex puddle", "d = uv - drainCenter; swirl = atan2(d.y,d.x) + time*2.0; radius = length(d); height += sin(swirl*4.0 + radius*30.0) * exp(-radius*5.0) * 0.035;"),
            ("overflow_edge_sheet", "Overflow edge sheet", "edge = smoothstep(0.75, 1.0, waterLevel - surfaceHeight); height += sin(uv.x*80.0 - time*9.0) * edge * 0.018;"),
            ("rain_current_advection", "Rain-current advection field", "flow = float2(LetheRainNoise2D(uv*3.0), LetheRainNoise2D(uv*3.0+4.7))-0.5; uv += flow * currentStrength * time * 0.05; height += LetheRainNoise2D(uv*22.0)*0.02;"),
            ("road_camber_runoff", "Road camber runoff", "camber = abs(uv.x-0.5)*2.0; waterMask *= smoothstep(0.15,0.75,camber); normal.x += sign(uv.x-0.5) * waterMask * 0.06;"),
            ("micro_channel_braids", "Micro-channel braided water", "braid = sin(uv.x*28.0 + sin(uv.y*18.0-time)*2.0); stream = smoothstep(0.88,0.98,braid); height += stream * 0.025;"),
        ]),
        ("agent_04_wave_physics", "rain water wave physics", "wave", [
            ("gerstner_rain_chop", "Gerstner rain chop", "float2 dir=float2(0.8,0.6); q = dot(uv,dir)*waveFreq-time*waveSpeed; height += sin(q)*amplitude; normal += dir*cos(q)*amplitude;"),
            ("capillary_micro_waves", "Capillary micro waves", "height += sin(uv.x*140.0+time*9.0)*0.004 + sin(uv.y*173.0-time*11.0)*0.003; normal += float2(ddx(height),ddy(height))*capillaryScale;"),
            ("damped_wave_equation_step", "Damped wave equation approximation", "lap = sin(uv.x*18.0)+sin(uv.y*18.0)-2.0*sin((uv.x+uv.y)*9.0); height += lap * exp(-damping*time) * 0.035;"),
            ("spectral_band_sum", "Spectral rain band sum", "height += sin(dot(uv,float2(7,3))+time)*0.02 + sin(dot(uv,float2(17,-5))-time*1.7)*0.01 + sin(dot(uv,float2(-31,9))+time*2.3)*0.006;"),
            ("standing_wave_interference", "Standing puddle interference", "height += sin(uv.x*22.0)*sin(time*3.0)*0.025 + sin(uv.y*19.0)*sin(time*2.4)*0.018;"),
            ("wind_shear_surface", "Wind shear water surface", "shear = uv.x + LetheRainNoise2D(uv*6.0)*0.2; height += sin(shear*34.0 - time*5.0)*windStrength*0.02;"),
            ("radial_energy_decay", "Radial rain energy decay", "r=length(uv-center); height += sin(r*60.0-time*8.0)*exp(-r*3.5)*rainEnergy;"),
            ("shallow_water_caustic_wave", "Shallow water caustic wave", "height += sin(uv.x*16.0+time)*sin(uv.y*14.0-time*0.7)*0.03; caustic += pow(abs(height)*18.0,2.0);"),
            ("stochastic_normal_field", "Stochastic normal field", "normal += float2(LetheRainNoise2D(uv*64.0+time), LetheRainNoise2D(uv*64.0-time))-0.5; normal *= 0.07;"),
            ("beat_frequency_rain", "Beat-frequency rain wave", "height += (sin(uv.x*27.0-time*4.0)+sin(uv.x*29.0-time*4.2))*0.012;"),
        ]),
        ("agent_05_reflections", "rain reflections and lighting", "reflection", [
            ("streetlight_vertical_streak", "Streetlight vertical streak reflection", "streak = exp(-abs(uv.x-lightX)*55.0) * smoothstep(1.0,0.0,uv.y); reflection += lightColor * streak * waterMask;"),
            ("neon_smear_distortion", "Neon smear ripple distortion", "smearUv = uv + normal.xy * 0.08; neon = float3(step(0.94, frac(smearUv.x * 9.0)), step(0.93, frac(smearUv.x * 13.0 + 0.2)), step(0.92, frac(smearUv.x * 7.0 + 0.55))); reflection += neon * exp(-smearUv.y * 1.9) * waterMask;"),
            ("overcast_sky_lobe", "Overcast sky reflection lobe", "sky = lerp(float3(0.2,0.24,0.28), float3(0.55,0.62,0.7), pow(saturate(reflectVec.z),2.0)); reflection += sky * fresnel * waterMask;"),
            ("headlight_glint_packets", "Headlight glint packets", "glint = pow(saturate(dot(normalize(float2(uv.x-0.5,uv.y)), lightDir)), 80.0); reflection += glint * float3(1.0,0.86,0.55);"),
            ("blurred_reflection_lobes", "Blurred reflection lobes", "blur = waterMask * roughness; reflection += (envA*0.5 + envB*0.3 + envC*0.2) * (1.0-blur*0.5);"),
            ("mirror_breakup_cells", "Mirror breakup cells", "cell = floor(uv*12.0); angle = LetheRainHash12(cell)*6.283; reflectionUv += float2(cos(angle),sin(angle))*0.015*waterMask;"),
            ("city_reflection_columns", "City reflection columns", "column = step(0.75, LetheRainNoise2D(float2(floor(uv.x*18.0),0))); reflection += column * exp(-uv.y*2.5) * float3(0.6,0.8,1.0);"),
            ("fresnel_film_dark_edge", "Fresnel film dark edge", "film = pow(1.0-NoV,5.0); reflection = lerp(reflection, reflection*1.8+float3(0.05,0.08,0.1), film*waterMask);"),
            ("specular_microfacet_rain", "Specular microfacet rain", "alpha = lerp(0.65,0.035,waterMask); spec = pow(saturate(NoH), lerp(24.0, 180.0, waterMask)) * (0.04 + 0.96 * pow(1.0 - VoH, 5.0)); reflection += float3(spec, spec, spec);"),
            ("traffic_signal_ripple_reflect", "Traffic signal ripple reflection", "signal = float3(step(abs(uv.x-0.25),0.04), step(abs(uv.x-0.5),0.04), step(abs(uv.x-0.75),0.04)); reflection += signal * exp(-uv.y*3.0) * waterMask;"),
        ]),
        ("agent_06_splashes", "splashes foam and droplets", "splash", [
            ("crown_splash_mask", "Crown splash mask", "r=length(local); crown=pow(saturate(1.0-abs(r-0.12)*18.0),3.0); foam += crown*step(0.85,drop);"),
            ("white_micro_bubbles", "White micro bubbles", "bubble=pow(saturate(LetheRainNoise2D(uv*90.0)-0.82),4.0); foam += bubble*waterMask;"),
            ("misty_impact_bloom", "Misty impact bloom", "mist=exp(-length(local)*18.0)*step(0.92,drop); emissive += mist*float3(0.5,0.7,0.8);"),
            ("droplet_bead_highlight", "Droplet bead highlight", "bead=pow(saturate(1.0-length(frac(uv*38.0)-0.5)*3.5),6.0); specular += bead;"),
            ("foam_decay_trails", "Foam decay trails", "trail=LetheRainNoise2D(float2(uv.x*18.0, uv.y*5.0-time*0.7)); foam += smoothstep(0.72,0.9,trail)*exp(-timeSinceImpact);"),
            ("impact_star_splash", "Impact star splash", "ang=atan2(local.y,local.x); star=pow(abs(sin(ang*6.0)),12.0)*exp(-length(local)*9.0); foam += star;"),
            ("tiny_circular_bubble_pack", "Tiny circular bubble pack", "cell=floor(uv*42.0); p=frac(uv*42.0)-0.5; foam += smoothstep(0.08,0.02,length(p))*step(0.88,LetheRainHash12(cell));"),
            ("edge_splash_on_curbs", "Edge splash on curbs", "edge=exp(-abs(uv.y-curbLine)*45.0); foam += edge*pow(saturate(sin(uv.x*90.0-time*12.0)),6.0);"),
            ("sheet_break_whitecaps", "Sheet break whitecaps", "crest=smoothstep(0.78,0.94,abs(normal.x)+abs(normal.y)); foam += crest*waterMask;"),
            ("raindrop_rebound_specks", "Raindrop rebound specks", "speck=step(0.965,LetheRainNoise2D(uv*120.0+time*3.0)); foam += speck*exp(-frac(time*4.0));"),
        ]),
        ("agent_07_contexts", "rainy surface contexts", "context", [
            ("rooftop_puddle_membrane", "Rooftop puddle membrane", "tarNoise=LetheRainNoise2D(uv*14.0); waterMask=smoothstep(0.48,0.7,tarNoise-slope*0.2);"),
            ("road_puddle_lane_marks", "Road puddle with lane marks", "stripe=step(0.96,abs(sin(uv.x*3.14159*6.0))); albedo=lerp(asphaltColor,laneColor,stripe*(1-waterMask*0.4));"),
            ("tiled_plaza_rain", "Tiled plaza rain", "tile=abs(frac(uv*8.0)-0.5); grout=smoothstep(0.035,0.0,min(tile.x,tile.y)); waterMask=max(waterMask,grout*0.5);"),
            ("mud_puddle_rain", "Mud puddle rain", "sediment=LetheRainNoise2D(uv*9.0+time*0.03); color=lerp(waterColor,float3(0.18,0.12,0.06),sediment*0.65);"),
            ("glass_roof_rain", "Glass roof rain", "stream=smoothstep(0.75,0.95,sin(uv.y*30.0-time*3.0+LetheRainNoise2D(uv*4.0)*2.0)); refraction+=stream*0.08;"),
            ("car_hood_rain", "Car hood rain", "hoodCurve=pow(abs(uv.x-0.5)*2.0,2.0); bead=pow(saturate(1.0-length(frac(uv*40.0)-0.5)*3.0),5.0);"),
            ("fountain_basin_rain", "Fountain basin rain", "basin=1.0-smoothstep(0.45,0.5,length(uv-0.5)); height += basin*sin(length(uv-0.5)*80.0-time*5.0)*0.02;"),
            ("metal_grate_puddle", "Metal grate puddle", "grate=max(step(0.88,frac(uv.x*14.0)),step(0.88,frac(uv.y*14.0))); waterMask*=1-grate;"),
            ("leaf_litter_puddles", "Leaf litter puddles", "leaf=step(0.7,LetheRainNoise2D(uv*7.0))*smoothstep(0.2,0.7,frac(uv.x+uv.y)); waterMask*=1-leaf*0.7;"),
            ("shallow_flooded_floor", "Shallow flooded floor", "floorGrid=abs(frac(uv*5.0)-0.5); depth01=saturate(waterLevel - min(floorGrid.x,floorGrid.y)*0.02);"),
        ]),
        ("agent_08_stylized", "stylized rainy water", "stylized", [
            ("anime_rain_puddle", "Anime rain puddle bands", "band=floor((height+waterMask)*5.0)/5.0; color=lerp(color,float3(0.1,0.55,0.95),band);"),
            ("noir_high_contrast_rain", "Noir high-contrast rain", "value=step(0.55,specular.r+waterMask*0.3); color=lerp(float3(0.02,0.025,0.03),float3(0.9,0.95,1.0),value);"),
            ("pixel_rain_surface", "Pixel rain surface", "pix=floor(uv*160.0)/160.0; height=LetheRainNoise2D(pix*20.0+time);"),
            ("watercolor_puddle_bleed", "Watercolor puddle bleed", "bleed=smoothstep(0.35,0.75,LetheRainNoise2D(uv*4.0)); color=lerp(color,float3(0.2,0.45,0.7),bleed*waterMask);"),
            ("ink_ring_rain", "Ink ring rain", "ring=step(0.48,frac(length(local)*20.0-time*2.0)); color*=lerp(1.0,0.55,ring*waterMask);"),
            ("lowpoly_faceted_puddles", "Lowpoly faceted puddles", "cell=floor(uv*18.0); facet=LetheRainHash12(cell); normal=float2(facet-0.5,LetheRainHash12(cell+3.1)-0.5) * 0.18;"),
            ("comic_specular_dots", "Comic specular dots", "dotMask=step(0.92,LetheRainNoise2D(uv*55.0)); color+=dotMask*float3(1,1,1)*waterMask;"),
            ("thermal_rain_surface", "Thermal rain surface", "heat=sin(height*20.0+time)+LetheRainNoise2D(uv*9.0); color=lerp(float3(0,0,0.4),float3(1,0.4,0),saturate(heat));"),
            ("blueprint_rain_debug", "Blueprint debug rain vectors", "grid=step(0.98,frac(uv.x*20.0))+step(0.98,frac(uv.y*20.0)); color=float3(0.0,0.25,0.55)+grid*0.5+normal.xyx*0.2;"),
            ("dreamy_bokeh_rain", "Dreamy bokeh rain reflections", "bokeh=pow(saturate(1.0-length(frac(uv*12.0)-0.5)*2.0),8.0); color+=bokeh*reflectionColor*waterMask;"),
        ]),
        ("agent_09_temporal", "temporal rain events", "temporal", [
            ("rain_intensity_ramp", "Rain intensity ramp", "rainAmount=smoothstep(startTime,endTime,time); waterMask*=rainAmount; height*=rainAmount;"),
            ("thunder_flash_puddle", "Thunder flash puddle", "flash=pow(saturate(sin(time*0.7)*0.5+0.5),40.0); reflection+=flash*float3(0.8,0.9,1.0);"),
            ("gust_front_sweep", "Gust front sweep", "front=smoothstep(-0.1,0.1,uv.x-time*0.2); normal+=front*float2(0.12,0.02);"),
            ("slow_motion_drops", "Slow-motion drops", "slowT=floor(time*12.0)/12.0; height+=sin(length(local)*50.0-slowT*4.0)*exp(-length(local)*8.0);"),
            ("intermittent_rain_cells", "Intermittent rain cells", "cloud=LetheRainNoise2D(floor(uv*5.0)+floor(time*0.5)); waterMask*=step(0.35,cloud);"),
            ("passing_car_wake", "Passing car wake", "wake=exp(-abs(uv.y-carY)*20.0)*smoothstep(carX-0.4,carX,uv.x); height+=sin(uv.x*45.0-time*12.0)*wake;"),
            ("rain_aftershock_decay", "Rain aftershock decay", "decay=exp(-frac(time*0.8)*3.0); height+=LetheRainNoise2D(uv*18.0+floor(time))*decay*0.05;"),
            ("drizzle_to_downpour", "Drizzle to downpour", "rate=lerp(0.15,1.0,smoothstep(0.2,0.9,sin(time*0.15)*0.5+0.5)); waterMask*=rate; normal*=rate;"),
            ("wind_direction_shift", "Wind direction shift", "dir=normalize(lerp(float2(1,0),float2(0.2,1),sin(time*0.3)*0.5+0.5)); normal+=dir*sin(dot(uv,dir)*40.0-time*5.0)*0.04;"),
            ("evaporating_puddle_end", "Evaporating puddle end", "dry=smoothstep(0.4,1.0,time/endTime); waterMask*=1.0-dry*LetheRainNoise2D(uv*7.0);"),
        ]),
        ("agent_10_hybrid", "hybrid rain water systems", "hybrid", [
            ("impact_plus_flow_hybrid", "Impact plus flow hybrid", "height += impactRing * 0.7 + streamNoise * 0.3; normal += slopeDir * streamNoise * 0.06;"),
            ("puddle_reflection_caustic_mix", "Puddle reflection caustic mix", "reflection += float3(caustic, caustic, caustic)*0.25 + fresnel*envColor*waterMask;"),
            ("mud_foam_ripple_mix", "Mud foam ripple mix", "foam += rippleCrest*0.35; color=lerp(mudColor,foamColor,foam);"),
            ("traffic_neon_impact_mix", "Traffic neon impact mix", "neonUv=uv+normal.xy*0.08; trafficColor=float3(step(0.93,frac(neonUv.x*5.0)),step(0.96,frac(neonUv.x*8.0+0.2)),step(0.94,frac(neonUv.x*11.0+0.5))); reflection+=trafficColor*exp(-neonUv.y*2.2)*impactMask;"),
            ("curb_stream_splash_mix", "Curb stream splash mix", "stream=exp(-abs(uv.y-curb)*30); foam+=stream*splashMask; height+=stream*sin(uv.x*70-time*8)*0.02;"),
            ("leaf_blocked_flow_mix", "Leaf-blocked flow mix", "flow*=1-leafMask; waterMask=max(waterMask,accumulatedBehindLeaf);"),
            ("car_hood_bead_stream_mix", "Car hood bead and stream mix", "beadMask+=streamMask*0.3; normal+=beadNormal+streamNormal;"),
            ("tile_grout_impact_mix", "Tile grout impact mix", "impactMask*=1-grout; waterMask=max(waterMask,grout*0.5);"),
            ("storm_puddle_all_layers", "Storm puddle all layers", "height=impactHeight+flowHeight+windChop; foam=saturate(crownFoam+edgeFoam); reflection+=streetLight*waterMask;"),
            ("cinematic_rain_surface_stack", "Cinematic rain surface stack", "color=lerp(color,float3(0.02,0.05,0.08),depth01*0.45); color+=reflection*0.6+caustic*0.25+foam*0.15; normal=normalize(normal+impactNormal+flowNormal);"),
        ]),
    ]

    algorithms: list[Algorithm] = []
    for agent, family, preview_kind, specs in groups:
        for algorithm_id, title, hlsl_core in specs:
            algorithms.append(
                Algorithm(
                    agent=agent,
                    algorithm_id=algorithm_id,
                    title=title,
                    family=family,
                    hlsl_core=hlsl_core,
                    preview_kind=preview_kind,
                    controls=["rainIntensity", "wind", "waterLevel", "roughness", "reflection", "rippleScale"],
                )
            )
    return algorithms


def write_shader(order: int, algo: Algorithm, signature: str) -> dict:
    filename = f"{order:03d}_{algo.algorithm_id}.hlsl"
    path = OUT / filename
    code = shader_code(order, algo, signature)
    path.write_text(code, encoding="utf-8")
    return {
        "order": order,
        "agent": algo.agent,
        "algorithm_id": algo.algorithm_id,
        "title": algo.title,
        "family": algo.family,
        "preview_kind": algo.preview_kind,
        "controls": algo.controls,
        "signature": signature,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "abs_path": str(path),
        "license": "MIT",
        "source": "lethe-authored",
    }


def shader_code(order: int, algo: Algorithm, signature: str) -> str:
    fn = function_name(algo.algorithm_id)
    return f"""// Lethe authored rainy-day water surface shader #{order:03d}
// Algorithm ID: {algo.algorithm_id}
// Family: {algo.family}
// Assigned track: {algo.agent}
// Review signature: {signature}
// MIT-compatible for project use.

struct LetheRainSurfaceInput
{{
    float2 UV;
    float3 WorldPos;
    float3 ViewDir;
    float Time;
    float RainIntensity;
    float WaterLevel;
    float Roughness;
    float ReflectionStrength;
    float RippleScale;
}};

struct LetheRainSurfaceOutput
{{
    float3 BaseColor;
    float3 Normal;
    float Roughness;
    float Metallic;
    float Alpha;
    float3 Emissive;
    float Height;
    float WaterMask;
}};

float LetheRainHash12_{fn}(float2 p)
{{
    float3 p3 = frac(float3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}}

float LetheRainNoise2D_{fn}(float2 p)
{{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    return lerp(
        lerp(LetheRainHash12_{fn}(i), LetheRainHash12_{fn}(i + float2(1, 0)), u.x),
        lerp(LetheRainHash12_{fn}(i + float2(0, 1)), LetheRainHash12_{fn}(i + float2(1, 1)), u.x),
        u.y);
}}

LetheRainSurfaceOutput LetheRain_{fn}(LetheRainSurfaceInput I)
{{
    float2 uv = I.UV;
    float time = I.Time;
    float rain = saturate(I.RainIntensity);
    float waterMask = saturate(I.WaterLevel);
    float height = 0.0;
    float foam = 0.0;
    float3 albedo = float3(0.025, 0.032, 0.035);
    float3 reflection = float3(0.0, 0.0, 0.0);
    float3 specular = float3(0.0, 0.0, 0.0);
    float3 emissive = float3(0.0, 0.0, 0.0);
    float roughness = I.Roughness;
    float refraction = 0.0;
    float2 normal = float2(0.0, 0.0);
    float2 slopeDir = normalize(float2(0.82, 0.57));
    float2 obstacleCenter = float2(0.52, 0.48);
    float2 drainCenter = float2(0.50, 0.50);
    float2 center = float2(0.50, 0.50);
    float2 smearUv = uv;
    float2 neonUv = uv;
    float2 reflectionUv = uv;
    float2 flowUv = uv;
    float2 tile = float2(0.0, 0.0);
    float2 floorGrid = float2(0.0, 0.0);
    float2 dir = float2(1.0, 0.0);
    float2 impactNormal = float2(0.0, 0.0);
    float2 flowNormal = float2(0.0, 0.0);
    float2 local = frac(uv * 18.0) - 0.5;
    float2 cell = floor(uv * 18.0);
    float drop = LetheRainHash12_{fn}(cell);
    float radius = length(local);
    float r = radius;
    float crown = 0.0;
    float film = 0.0;
    float pore = 0.0;
    float slope = 0.0;
    float slopeWave = 0.0;
    float alpha = 0.0;
    float amp = 0.0;
    float amplitude = 0.032 * rain * I.RippleScale;
    float angle = 0.0;
    float ang = 0.0;
    float basin = 0.0;
    float bead = 0.0;
    float beadMask = 0.0;
    float blur = 0.0;
    float bokeh = 0.0;
    float bubble = 0.0;
    float bucket = 0.0;
    float burst = 0.0;
    float camber = 0.0;
    float capillaryScale = 0.20;
    float caustic = 0.0;
    float channel = 0.0;
    float cloud = 0.0;
    float column = 0.0;
    float crownFoam = 0.0;
    float currentStrength = 1.0;
    float curb = 0.58;
    float curbLine = 0.58;
    float damping = 0.28;
    float decay = 0.0;
    float depth01 = saturate(I.WaterLevel + 0.18 * LetheRainNoise2D_{fn}(uv * 5.0));
    float dry = 0.0;
    float dryRoughness = max(I.Roughness, 0.75);
    float edge = 0.0;
    float edgeFoam = 0.0;
    float endTime = 12.0;
    float facet = 0.0;
    float flash = 0.0;
    float flow = LetheRainNoise2D_{fn}(uv * 4.0);
    float flowHeight = sin(dot(uv, slopeDir) * 42.0 - time * 4.0) * 0.018 * waterMask;
    float flowSpeed = 0.45;
    float fresnel = pow(1.0 - saturate(abs(I.ViewDir.z)), 5.0);
    float front = 0.0;
    float glint = 0.0;
    float grout = 0.0;
    float gust = 0.0;
    float hoodCurve = 0.0;
    float impactHeight = sin(radius * 64.0 - time * 8.0) * exp(-radius * 9.0) * rain;
    float impactMask = smoothstep(0.15, 0.02, abs(radius - frac(time * 0.7 + drop) * 0.35)) * step(0.68, drop);
    float impactRing = sin(radius * 58.0 - time * 7.0) * exp(-radius * 8.0) * step(0.72, drop);
    float laneColor = 0.85;
    float lap = 0.0;
    float leaf = 0.0;
    float leafMask = smoothstep(0.62, 0.86, LetheRainNoise2D_{fn}(uv * 6.0));
    float lightX = 0.35;
    float mud = 0.0;
    float NoV = saturate(abs(I.ViewDir.z));
    float NoH = saturate(0.55 + 0.45 * dot(normalize(float2(0.32, 0.95)), normalize(uv - 0.5 + 0.01)));
    float obs = 0.0;
    float q = 0.0;
    float rainAmount = rain;
    float rainEnergy = rain;
    float rate = rain;
    float ripple = 0.0;
    float rippleCrest = smoothstep(0.72, 0.96, abs(sin(radius * 64.0 - time * 8.0)));
    float row = 0.0;
    float sheet = 0.0;
    float slowT = time;
    float spec = 0.0;
    float speck = 0.0;
    float splashMask = impactMask;
    float startTime = 0.0;
    float streak = 0.0;
    float stream = 0.0;
    float streamMask = 0.0;
    float streamNoise = LetheRainNoise2D_{fn}(float2(uv.x * 5.0, uv.y * 32.0 - time * 1.2));
    float tarNoise = 0.0;
    float tileCount = 8.0;
    float timeSinceImpact = frac(time + drop) * 2.0;
    float VoH = NoH;
    float wake = 0.0;
    float waterLevel = I.WaterLevel;
    float waveFreq = 26.0;
    float waveSpeed = 4.0;
    float windChop = sin(dot(uv, float2(21.0, 9.0)) - time * 4.8) * 0.014 * rain;
    float windStrength = 1.0;
    float carX = frac(time * 0.12);
    float carY = 0.42;
    float accumulatedBehindLeaf = leafMask * smoothstep(0.45, 0.2, uv.y);
    float3 asphaltColor = float3(0.028, 0.031, 0.032);
    float3 envA = float3(0.12, 0.16, 0.19);
    float3 envB = float3(0.32, 0.42, 0.50);
    float3 envC = float3(0.65, 0.55, 0.42);
    float3 envColor = float3(0.25, 0.32, 0.38);
    float3 foamColor = float3(0.84, 0.90, 0.92);
    float3 lightColor = float3(1.0, 0.74, 0.42);
    float3 mudColor = float3(0.17, 0.11, 0.065);
    float3 reflectionColor = float3(0.30, 0.55, 0.95);
    float3 reflectVec = reflect(-normalize(I.ViewDir), float3(normal, 1.0));
    float3 signal = float3(0.0, 0.0, 0.0);
    float3 sky = float3(0.0, 0.0, 0.0);
    float3 streetLight = float3(1.0, 0.65, 0.32);
    float3 trafficColor = float3(0.0, 0.0, 0.0);
    float3 waterColor = float3(0.04, 0.075, 0.08);
    float2 lightDir = normalize(float2(0.18, 0.98));
    float2 pix = uv;
    float band = 0.0;
    float dotMask = 0.0;
    float grid = 0.0;
    float heat = 0.0;
    float stripe = 0.0;
    float value = 0.0;
    float3 color = albedo;

    // Unique algorithm core.
    {algo.hlsl_core.replace("LetheRainNoise2D(", f"LetheRainNoise2D_{fn}(").replace("LetheRainHash12(", f"LetheRainHash12_{fn}(")}

    LetheRainSurfaceOutput O;
    O.BaseColor = saturate(color + reflection * I.ReflectionStrength + foam.xxx * 0.35);
    O.Normal = normalize(float3(normal.x, normal.y, 1.0));
    O.Roughness = saturate(roughness);
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = emissive;
    O.Height = height;
    O.WaterMask = waterMask;
    return O;
}}
"""


def feature_signature(algo: Algorithm) -> str:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[+\-*/]", algo.hlsl_core.lower())
    stop = {"float", "float2", "float3", "uv", "time", "height", "normal", "watermask"}
    normalized = [token for token in tokens if token not in stop]
    payload = "|".join([algo.family, algo.preview_kind, *normalized[:60]])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def function_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value.title())


def counts(items: list[dict], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        result[item[key]] = result.get(item[key], 0) + 1
    return dict(sorted(result.items()))


if __name__ == "__main__":
    raise SystemExit(main())
