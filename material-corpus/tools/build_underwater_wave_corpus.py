"""Generate and review 100 underwater wave HLSL shader references."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "underwater_wave_hlsl"
MANIFEST_PATH = OUT_ROOT / "underwater_wave_manifest.json"
REVIEW_PATH = OUT_ROOT / "dedupe_review.json"


@dataclass(frozen=True)
class WaveProfile:
    family: str
    caustic: str
    depth: str
    distortion: str
    color: str
    motion: str
    scale: str


FAMILIES = [
    "surface_swell",
    "subsurface_ripple",
    "caustic_lattice",
    "deep_current",
    "diver_wake",
    "reef_shimmer",
    "pool_floor_wave",
    "cave_blue_drift",
    "kelp_shadow_wave",
    "bubble_lens_wave",
]
CAUSTICS = ["none", "soft_cross", "sharp_net", "ring_focus", "broken_tiles", "sunbeam_strands"]
DEPTHS = ["shallow", "midwater", "deep", "abyss_fade"]
DISTORTIONS = ["sine_scroll", "fbm_warp", "dual_normal", "vortex_shear", "screen_refraction"]
COLORS = ["cyan", "tropical", "deep_blue", "green_lagoon", "moonlit", "murky_teal"]
MOTIONS = ["calm", "drifting", "tidal", "surging", "storm_underwater"]
SCALES = ["macro", "medium", "fine"]

TARGET_COUNT = 100


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    generated = _candidate_profiles()
    kept: list[dict] = []
    rejected: list[dict] = []
    seen = set()

    for idx, profile in enumerate(generated, start=1):
        fp = _fingerprint(profile)
        near = _near_fingerprint(profile)
        if fp in seen or near in seen:
            rejected.append(
                {
                    "candidate": _slug(profile),
                    "fingerprint": fp,
                    "near_fingerprint": near,
                    "reason": "similar wave family / caustic / depth / distortion profile already kept",
                }
            )
            continue
        seen.add(fp)
        seen.add(near)
        kept.append(_write_shader(len(kept) + 1, profile))
        if len(kept) >= TARGET_COUNT:
            break

    manifest = {
        "schema_version": 1,
        "source_label": "lethe-authored-underwater-wave",
        "license_label": "MIT",
        "count": len(kept),
        "entries": kept,
    }
    review = {
        "schema_version": 1,
        "generated_candidates": len(generated),
        "target_count": TARGET_COUNT,
        "kept": len(kept),
        "rejected_similar": len(rejected),
        "rejected": rejected,
        "kept_families": _counts(kept, "family"),
        "kept_caustics": _counts(kept, "caustic"),
        "kept_depths": _counts(kept, "depth"),
        "kept_distortions": _counts(kept, "distortion"),
        "kept_colors": _counts(kept, "color"),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    REVIEW_PATH.write_text(json.dumps(review, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(kept), "manifest": str(MANIFEST_PATH), "review": str(REVIEW_PATH)}, indent=2))
    return 0


def _candidate_profiles() -> list[WaveProfile]:
    profiles = []
    for family in FAMILIES:
        for caustic in CAUSTICS:
            for depth in DEPTHS:
                for distortion in DISTORTIONS:
                    for color in COLORS:
                        motion = MOTIONS[(len(profiles) + len(family)) % len(MOTIONS)]
                        scale = SCALES[(len(profiles) + len(caustic)) % len(SCALES)]
                        profiles.append(WaveProfile(family, caustic, depth, distortion, color, motion, scale))
    profiles.sort(key=lambda p: hashlib.sha1(_slug(p).encode()).hexdigest())
    return profiles


def _fingerprint(profile: WaveProfile) -> str:
    return "|".join([profile.family, profile.caustic, profile.depth, profile.distortion, profile.color])


def _near_fingerprint(profile: WaveProfile) -> str:
    family_group = {
        "surface_swell": "surface",
        "subsurface_ripple": "surface",
        "pool_floor_wave": "floor",
        "reef_shimmer": "floor",
        "deep_current": "deep",
        "cave_blue_drift": "deep",
        "diver_wake": "wake",
        "bubble_lens_wave": "wake",
        "kelp_shadow_wave": "shadow",
        "caustic_lattice": "caustic",
    }[profile.family]
    caustic_group = "caustic_off" if profile.caustic == "none" else ("caustic_soft" if profile.caustic in {"soft_cross", "sunbeam_strands"} else "caustic_hard")
    depth_group = "near" if profile.depth in {"shallow", "midwater"} else "far"
    distortion_group = "smooth" if profile.distortion in {"sine_scroll", "dual_normal"} else "warped"
    color_group = "clear" if profile.color in {"cyan", "tropical", "moonlit"} else "dense"
    return "|".join([family_group, caustic_group, depth_group, distortion_group, color_group])


def _write_shader(order: int, profile: WaveProfile) -> dict:
    slug = _slug(profile)
    path = OUT_ROOT / f"{order:03d}_{slug}.hlsl"
    code = _shader_code(order, profile)
    path.write_text(code, encoding="utf-8")
    return {
        "order": order,
        "title": _title(profile),
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "abs_path": str(path),
        "family": profile.family,
        "caustic": profile.caustic,
        "depth": profile.depth,
        "distortion": profile.distortion,
        "color": profile.color,
        "motion": profile.motion,
        "scale": profile.scale,
        "license": "MIT",
        "source": "lethe-authored",
        "fingerprint": _fingerprint(profile),
        "near_fingerprint": _near_fingerprint(profile),
    }


def _shader_code(order: int, profile: WaveProfile) -> str:
    fn = _function_name(profile)
    params = _params(profile)
    base_color = _color(profile.color)
    caustic_expr = _caustic_expr(profile.caustic, fn)
    depth_expr = _depth_expr(profile.depth)
    distortion_expr = _distortion_expr(profile.distortion)
    return f"""// Lethe authored underwater wave reference #{order:03d}, MIT-compatible for project use.
// Family: {profile.family}. Caustics: {profile.caustic}. Depth: {profile.depth}.
// Distortion: {profile.distortion}. Motion: {profile.motion}. Scale: {profile.scale}.

float LetheUWHash12_{fn}(float2 p)
{{
    float3 p3 = frac(float3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}}

float LetheUWNoise2D_{fn}(float2 p)
{{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    float a = LetheUWHash12_{fn}(i);
    float b = LetheUWHash12_{fn}(i + float2(1.0, 0.0));
    float c = LetheUWHash12_{fn}(i + float2(0.0, 1.0));
    float d = LetheUWHash12_{fn}(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
}}

float2 LetheUWDisplace_{fn}(float2 uv, float time, float strength)
{{
    float2 flow = float2({params['flow_x']:.4f}, {params['flow_y']:.4f}) * time;
    float n = LetheUWNoise2D_{fn}(uv * {params['noise_scale']:.4f} + flow);
    float waveA = sin(uv.x * {params['freq_a']:.4f} + uv.y * {params['skew']:.4f} - time * {params['speed_a']:.4f});
    float waveB = sin((uv.x - uv.y) * {params['freq_b']:.4f} + time * {params['speed_b']:.4f});
    {distortion_expr}
}}

float3 LetheUWColor_{fn}(float2 uv, float depth01, float time, float customStrength)
{{
    float2 duv = LetheUWDisplace_{fn}(uv, time, customStrength);
    float wave = sin(duv.x * {params['color_freq']:.4f} + time * {params['color_speed']:.4f});
    {caustic_expr}
    {depth_expr}
    float3 shallowColor = float3({base_color[0]:.4f}, {base_color[1]:.4f}, {base_color[2]:.4f});
    float3 deepColor = shallowColor * float3(0.15, 0.28, 0.52);
    float3 color = lerp(shallowColor, deepColor, depthFade);
    color += caustic * float3(0.95, 1.0, 0.82) * {params['caustic_strength']:.4f};
    color += wave * {params['wave_light']:.4f};
    return saturate(color);
}}

float LetheUWHeight_{fn}(float2 uv, float time, float amplitude)
{{
    float2 duv = LetheUWDisplace_{fn}(uv, time, 1.0);
    float h = sin(duv.x * {params['height_freq']:.4f} - time * {params['height_speed']:.4f});
    h += (LetheUWNoise2D_{fn}(duv * {params['height_noise']:.4f}) - 0.5) * 0.65;
    return h * amplitude * {params['height_amp']:.4f};
}}
"""


def _params(profile: WaveProfile) -> dict[str, float]:
    family_i = FAMILIES.index(profile.family) + 1
    caustic_i = CAUSTICS.index(profile.caustic) + 1
    depth_i = DEPTHS.index(profile.depth) + 1
    distortion_i = DISTORTIONS.index(profile.distortion) + 1
    motion_i = MOTIONS.index(profile.motion) + 1
    scale_mul = {"macro": 0.65, "medium": 1.0, "fine": 1.55}[profile.scale]
    speed_mul = {"calm": 0.55, "drifting": 0.78, "tidal": 1.0, "surging": 1.25, "storm_underwater": 1.55}[profile.motion]
    return {
        "flow_x": (0.03 * family_i + 0.011 * caustic_i) * speed_mul,
        "flow_y": (0.017 * depth_i - 0.006 * distortion_i) * speed_mul,
        "noise_scale": (2.0 + 0.37 * family_i) * scale_mul,
        "freq_a": (5.0 + family_i * 1.7) * scale_mul,
        "freq_b": (8.5 + caustic_i * 2.1) * scale_mul,
        "skew": 2.0 + distortion_i * 0.7,
        "speed_a": (0.8 + motion_i * 0.28) * speed_mul,
        "speed_b": (1.1 + family_i * 0.11) * speed_mul,
        "color_freq": (7.0 + caustic_i * 2.8) * scale_mul,
        "color_speed": (0.6 + motion_i * 0.2) * speed_mul,
        "caustic_strength": 0.0 if profile.caustic == "none" else min(0.85, 0.22 + caustic_i * 0.09),
        "wave_light": 0.025 + family_i * 0.004,
        "height_freq": (4.0 + distortion_i * 2.2) * scale_mul,
        "height_speed": (0.9 + motion_i * 0.18) * speed_mul,
        "height_noise": (2.5 + depth_i * 0.8) * scale_mul,
        "height_amp": 0.6 + 0.05 * family_i,
    }


def _caustic_expr(caustic: str, fn: str) -> str:
    if caustic == "none":
        return "float caustic = 0.0;"
    if caustic == "soft_cross":
        return "float caustic = pow(saturate(sin(duv.x * 17.0) * sin(duv.y * 19.0)), 2.0);"
    if caustic == "sharp_net":
        return "float caustic = pow(abs(sin(duv.x * 31.0) + sin(duv.y * 29.0)) * 0.5, 7.0);"
    if caustic == "ring_focus":
        return "float caustic = pow(saturate(1.0 - abs(frac(length(duv - 0.5) * 8.0 - time * 0.4) - 0.5) * 3.0), 3.0);"
    if caustic == "broken_tiles":
        return f"float caustic = pow(LetheUWNoise2D_{fn}(floor(duv * 18.0) + time * 0.2), 5.0);"
    return "float caustic = pow(saturate(sin(duv.x * 13.0 + time) + sin(duv.y * 27.0 - time * 0.7)), 3.0);"


def _depth_expr(depth: str) -> str:
    if depth == "shallow":
        return "float depthFade = saturate(depth01 * 0.55);"
    if depth == "midwater":
        return "float depthFade = smoothstep(0.08, 0.92, depth01);"
    if depth == "deep":
        return "float depthFade = pow(saturate(depth01), 1.65);"
    return "float depthFade = smoothstep(0.18, 0.75, depth01) * 0.85 + depth01 * 0.25;"


def _distortion_expr(distortion: str) -> str:
    if distortion == "sine_scroll":
        return "return uv + float2(waveA, waveB) * strength * 0.018;"
    if distortion == "fbm_warp":
        return "return uv + float2(waveA + n - 0.5, waveB - n + 0.5) * strength * 0.024;"
    if distortion == "dual_normal":
        return "return uv + normalize(float2(waveA, waveB) + 0.001) * strength * (0.014 + n * 0.012);"
    if distortion == "vortex_shear":
        return "float2 center = uv - 0.5; return uv + float2(-center.y, center.x) * (waveA + n) * strength * 0.022;"
    return "return uv + float2(waveA * 0.7 + n * 0.4, waveB * 0.7 - n * 0.4) * strength * 0.03;"


def _color(name: str) -> tuple[float, float, float]:
    return {
        "cyan": (0.02, 0.62, 0.92),
        "tropical": (0.0, 0.82, 0.72),
        "deep_blue": (0.03, 0.22, 0.70),
        "green_lagoon": (0.05, 0.58, 0.42),
        "moonlit": (0.22, 0.42, 0.88),
        "murky_teal": (0.08, 0.34, 0.32),
    }[name]


def _title(profile: WaveProfile) -> str:
    return " ".join([profile.family, profile.caustic, profile.depth, profile.distortion, profile.color, profile.motion, profile.scale]).replace("_", " ").title()


def _slug(profile: WaveProfile) -> str:
    return "_".join([profile.family, profile.caustic, profile.depth, profile.distortion, profile.color, profile.motion, profile.scale])


def _function_name(profile: WaveProfile) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", _title(profile))


def _counts(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item[key]] = counts.get(item[key], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
