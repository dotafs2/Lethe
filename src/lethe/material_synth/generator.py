"""Deterministic seed generator for HLSL material candidates.

This is not the final AI layer. It is the local, testable substrate that future
LLM/agent generation will target: a fixed interface, bounded HLSL body, and
metadata that can be validated before UE sees anything.
"""
from __future__ import annotations

from .schema import MaterialCandidate, MaterialRequest, slugify, stable_id


_OCEAN_VARIANTS = [
    {
        "suffix": "cel_foam_ribbons",
        "deep": [0.015, 0.210, 0.420],
        "shallow": [0.035, 0.650, 0.780],
        "foam": [0.960, 0.980, 0.900],
        "speed": 0.36,
        "scale": 3.0,
        "banding": 5.0,
        "foam_cut": 0.66,
    },
    {
        "suffix": "turquoise_lagoon",
        "deep": [0.000, 0.180, 0.360],
        "shallow": [0.060, 0.780, 0.700],
        "foam": [1.000, 0.960, 0.850],
        "speed": 0.28,
        "scale": 2.4,
        "banding": 4.0,
        "foam_cut": 0.61,
    },
    {
        "suffix": "graphic_blue",
        "deep": [0.025, 0.080, 0.360],
        "shallow": [0.050, 0.420, 0.950],
        "foam": [0.900, 0.980, 1.000],
        "speed": 0.42,
        "scale": 3.8,
        "banding": 6.0,
        "foam_cut": 0.70,
    },
    {
        "suffix": "sunlit_foam_cells",
        "deep": [0.010, 0.260, 0.340],
        "shallow": [0.140, 0.830, 0.760],
        "foam": [1.000, 0.930, 0.710],
        "speed": 0.32,
        "scale": 4.6,
        "banding": 5.0,
        "foam_cut": 0.58,
    },
]

_AGENT_STRATEGIES = [
    ("agent_01", "graphic_foam_shapes", "anime_ocean"),
    ("agent_02", "turquoise_readability", "anime_ocean"),
    ("agent_03", "fast_scroll_motion", "motion"),
    ("agent_04", "soft_lagoon_color", "color"),
    ("agent_05", "high_contrast_linework", "linework"),
    ("agent_06", "sunlit_foam_cells", "foam"),
    ("agent_07", "deep_blue_cel_bands", "bands"),
    ("agent_08", "rim_light_readability", "fresnel"),
    ("agent_09", "low_cost_procedural", "performance"),
    ("agent_10", "wildcard_variation", "exploration"),
]


def generate_candidates(request: MaterialRequest | str, count: int | None = None) -> list[MaterialCandidate]:
    """Generate local candidate materials for a request.

    For now this is intentionally deterministic and biased toward water/anime
    ocean prompts because that is the first customer-facing target discussed in
    the product direction. Generic prompts still get procedural surface variants.
    """

    if isinstance(request, str):
        request = MaterialRequest(prompt=request, count=count or 12)
    elif count is not None:
        request = MaterialRequest(
            prompt=request.prompt,
            count=count,
            seed=request.seed,
            target=request.target,
        )

    prompt_lower = request.prompt.lower()
    if any(token in prompt_lower for token in ("ocean", "sea", "water", "wave", "foam", "海", "水", "浪")):
        return _generate_ocean(request)
    return _generate_generic(request)


def _generate_ocean(request: MaterialRequest) -> list[MaterialCandidate]:
    candidates: list[MaterialCandidate] = []
    base_slug = slugify(request.prompt, fallback="anime_ocean")[:36]
    for idx in range(request.count):
        variant = _OCEAN_VARIANTS[(idx + request.seed) % len(_OCEAN_VARIANTS)]
        detail_phase = (idx // len(_OCEAN_VARIANTS)) + 1
        agent_id, strategy, strategy_family = _agent_strategy(idx, request.seed)
        name = f"{base_slug}_{variant['suffix']}_{detail_phase:02d}"
        body = _ocean_body(variant, detail_phase)
        candidates.append(
            MaterialCandidate(
                id=stable_id(request.prompt, idx, variant["suffix"], request.seed),
                name=name,
                prompt=request.prompt,
                description=(
                    "Stylized HLSL ocean with cel-shaded color bands, moving "
                    "foam masks, and a mild fresnel rim."
                ),
                hlsl_body=body,
                tags=["hlsl", "unreal", "custom-node", "water", "anime", "procedural"],
                parameters={
                    "speed": variant["speed"],
                    "scale": variant["scale"],
                    "banding": variant["banding"],
                    "foam_cut": variant["foam_cut"],
                    "detail_phase": detail_phase,
                },
                generation={
                    "generator": "lethe.local_seed.v1",
                    "agent_id": agent_id,
                    "strategy": strategy,
                    "strategy_family": strategy_family,
                    "variant_index": idx,
                    "batch_size": request.count,
                    "seed": request.seed,
                    "provenance": "local_template_no_external_sources",
                },
                risk_notes=[
                    "Generated locally from Lethe templates; no external source material was copied.",
                    "Static validation only until a UE project is supplied for real shader compilation.",
                ],
            )
        )
    return candidates


def _agent_strategy(idx: int, seed: int) -> tuple[str, str, str]:
    return _AGENT_STRATEGIES[(idx + seed) % len(_AGENT_STRATEGIES)]


def _vec3(values: list[float]) -> str:
    return f"float3({values[0]:.3f}, {values[1]:.3f}, {values[2]:.3f})"


def _ocean_body(variant: dict[str, object], detail_phase: int) -> str:
    speed = float(variant["speed"]) * (1.0 + 0.05 * (detail_phase - 1))
    scale = float(variant["scale"])
    banding = float(variant["banding"])
    foam_cut = float(variant["foam_cut"]) - 0.010 * (detail_phase - 1)
    ripple = 7.0 + detail_phase * 1.7
    deep = _vec3(variant["deep"])  # type: ignore[arg-type]
    shallow = _vec3(variant["shallow"])  # type: ignore[arg-type]
    foam = _vec3(variant["foam"])  # type: ignore[arg-type]

    return f"""
    LetheMaterialOutput O;
    float2 uv = I.UV * {scale:.3f};
    float t = I.Time * {speed:.3f};
    float2 flow = uv;
    flow.x += sin(uv.y * 1.10 + t * 1.20) * 0.12 + sin(uv.y * 2.70 - t * 0.7) * 0.035;
    flow.y += cos(uv.x * 0.95 - t * 1.10) * 0.10 + sin(uv.x * 2.10 + t * 0.35) * 0.030;

    float broad_a = sin(flow.x * 2.05 + flow.y * 0.62 + t * 0.45);
    float broad_b = sin(flow.y * 1.72 - flow.x * 0.68 - t * 0.38);
    float broad_c = sin((flow.x + flow.y) * 1.18 + sin(flow.x * 1.65) * 0.48);

    float cell_a = sin(flow.x * {ripple * 0.44:.3f} + sin(flow.y * 1.55 + t) * 1.10);
    float cell_b = sin(flow.y * {ripple * 0.36:.3f} + cos(flow.x * 1.35 - t * 0.55) * 0.95);
    float cell_c = sin((flow.x - flow.y * 0.55) * {ripple * 0.30:.3f} + sin(flow.y * 1.70) * 0.75);
    float cell_field = abs(cell_a * cell_b) + abs(cell_b * cell_c) * 0.55;
    float cell_line = 1.0 - smoothstep(0.055, 0.155, cell_field);

    float crest_a = abs(sin(flow.x * 1.95 + flow.y * 0.22 + t * 0.75));
    float crest_b = abs(sin(flow.x * 0.82 - flow.y * 1.62 - t * 0.62));
    float long_crest = (1.0 - smoothstep(0.028, 0.078, min(crest_a, crest_b)));
    float broken_mask = smoothstep(-0.15, 0.55, sin(flow.y * 2.65 + sin(flow.x * 1.1) + t));
    long_crest *= broken_mask;

    float fleck = smoothstep(0.965, 0.995, sin(flow.x * 7.7 - t * 1.1) * 0.5 + sin(flow.y * 8.9 + t * 1.3) * 0.5 + 0.5);
    float foam_mask = saturate(cell_line * 0.82 + long_crest * 0.34 + fleck * 0.16);
    foam_mask *= smoothstep({foam_cut - 0.380:.3f}, {foam_cut + 0.120:.3f}, foam_mask);
    float thin_foam = saturate(cell_line * 1.35 + long_crest * 0.75);
    float water_variation = saturate(0.50 + broad_a * 0.20 + broad_b * 0.16 + broad_c * 0.12);
    float band = floor(water_variation * {banding:.3f}) / max({banding - 1.0:.3f}, 1.0);
    float facing = saturate(dot(normalize(I.Normal), normalize(-I.CameraVector)));
    float fresnel = pow(1.0 - facing, 2.4);
    float3 water = lerp({deep}, {shallow}, saturate(band * 0.85 + 0.08));
    float3 ink = lerp({deep}, float3(0.050, 0.120, 0.180), 0.35);
    float3 line_tint = lerp(ink, {foam}, thin_foam);
    float3 rim = lerp(water, {shallow}, saturate(fresnel * 0.25));
    O.BaseColor = lerp(rim, line_tint, saturate(foam_mask * 0.92));
    O.Roughness = lerp(0.22, 0.58, foam_mask);
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = {foam} * saturate(thin_foam + fleck) * 0.040 + {shallow} * fresnel * 0.020;
    return O;
""".rstrip()


def _generate_generic(request: MaterialRequest) -> list[MaterialCandidate]:
    candidates: list[MaterialCandidate] = []
    base_slug = slugify(request.prompt)[:36]
    palettes = [
        ([0.18, 0.17, 0.15], [0.75, 0.55, 0.30]),
        ([0.05, 0.08, 0.11], [0.55, 0.95, 0.88]),
        ([0.20, 0.08, 0.13], [0.90, 0.32, 0.54]),
        ([0.10, 0.13, 0.08], [0.48, 0.72, 0.28]),
    ]
    for idx in range(request.count):
        dark, light = palettes[(idx + request.seed) % len(palettes)]
        agent_id, strategy, strategy_family = _agent_strategy(idx, request.seed)
        scale = 2.5 + (idx % 5) * 0.55
        body = f"""
    LetheMaterialOutput O;
    float2 uv = I.UV * {scale:.3f};
    float2 noise_uv = uv + I.Time * 0.05;
    float n0 = frac(sin(dot(floor(noise_uv * 9.0), float2(12.9898, 78.233))) * 43758.5453);
    float n1 = frac(sin(dot(floor(noise_uv * 19.0 + n0), float2(39.3468, 11.135))) * 24634.6345);
    float n = saturate(n0 * 0.6 + n1 * 0.4);
    float bands = floor(saturate(n) * 5.0) / 4.0;
    float facing = saturate(dot(normalize(I.Normal), normalize(-I.CameraVector)));
    float fresnel = pow(1.0 - facing, 3.0);
    O.BaseColor = lerp({_vec3(dark)}, {_vec3(light)}, bands);
    O.Roughness = lerp(0.35, 0.82, n);
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = {_vec3(light)} * fresnel * 0.05;
    return O;
""".rstrip()
        candidates.append(
            MaterialCandidate(
                id=stable_id(request.prompt, idx, request.seed),
                name=f"{base_slug}_procedural_{idx + 1:02d}",
                prompt=request.prompt,
                description="Generic procedural HLSL material using bounded noise and cel bands.",
                hlsl_body=body,
                tags=["hlsl", "unreal", "custom-node", "procedural"],
                parameters={"scale": scale},
                generation={
                    "generator": "lethe.local_seed.v1",
                    "agent_id": agent_id,
                    "strategy": strategy,
                    "strategy_family": strategy_family,
                    "variant_index": idx,
                    "batch_size": request.count,
                    "seed": request.seed,
                    "provenance": "local_template_no_external_sources",
                },
                risk_notes=[
                    "Generated locally from Lethe templates; no external source material was copied.",
                    "Static validation only until a UE project is supplied for real shader compilation.",
                ],
            )
        )
    return candidates
