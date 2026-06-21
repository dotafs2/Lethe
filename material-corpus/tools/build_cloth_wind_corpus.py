"""Generate a large Lethe-authored cloth wind shader corpus.

The output is intentionally many small, searchable shader references rather
than one huge file. Each generated file has a distinct use case, function name,
parameter profile, and tags so the corpus search layer can retrieve useful
material-building context.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "cloth_wind_generated"
HLSL_ROOT = OUT_ROOT / "hlsl"
GLSL_ROOT = OUT_ROOT / "glsl"
METADATA_PATH = OUT_ROOT / "generated_metadata.json"


@dataclass(frozen=True)
class UseCase:
    slug: str
    title: str
    pin_axis: str
    motion: str
    detail: str
    normal: bool


USE_CASES = [
    UseCase("flag_hoist", "pinned hoist flag", "uv.x", "free edge flutter", "loose edge snap", False),
    UseCase("banner_top", "top-hung banner", "1.0 - uv.y", "vertical cloth sag", "bottom ripple", False),
    UseCase("curtain_top", "top-pinned curtain", "1.0 - uv.y", "sideways fold travel", "lower cloth lag", False),
    UseCase("cape_shoulders", "shoulder-pinned cape", "uv.y", "trailing wind drag", "bottom delayed gust", False),
    UseCase("scarf_center", "neck-pinned scarf", "abs(uv.x - 0.5) * 2.0", "long ribbon wave", "tip whip", False),
    UseCase("sleeve_cuff", "sleeve cuff flutter", "uv.y", "short fabric shake", "small hem vibration", False),
    UseCase("skirt_hem", "skirt hem wind", "1.0 - uv.y", "radial hem lift", "alternating pleats", False),
    UseCase("tablecloth_edge", "tablecloth loose edge", "max(uv.x, uv.y)", "edge lift", "corner ripple", False),
    UseCase("tent_fabric", "tent fabric gust", "uv.y", "broad gust pressure", "seam flutter", False),
    UseCase("sailcloth", "sail cloth pressure", "uv.x", "wind-filled bulge", "luff vibration", False),
    UseCase("micro_wrinkle", "animated fabric micro wrinkles", "uv.x", "normal perturbation", "woven shimmer", True),
    UseCase("world_gust", "world-space shared gust", "uv.y", "coherent gust field", "multi-actor phase", False),
]

STYLE_PROFILES = [
    ("calm", 0.18, 7.0, 0.35, 0.75),
    ("breezy", 0.32, 11.0, 0.55, 1.0),
    ("gusty", 0.55, 17.0, 0.85, 1.2),
    ("storm", 0.85, 25.0, 1.1, 1.45),
    ("toon", 0.45, 13.0, 0.7, 0.95),
    ("silk", 0.24, 19.0, 0.42, 0.65),
]

SCALE_PROFILES = [
    ("small", 0.65, 0.85),
    ("medium", 1.0, 1.0),
    ("large", 1.45, 1.2),
    ("hero", 1.85, 1.45),
]


def main() -> int:
    HLSL_ROOT.mkdir(parents=True, exist_ok=True)
    GLSL_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "source_label": "lethe-authored-cloth-wind-generated",
        "license_label": "MIT",
        "generator": str(Path(__file__).relative_to(ROOT)),
        "items": [],
    }

    for use_case in USE_CASES:
        for style_name, amp, freq, gust, speed in STYLE_PROFILES:
            for scale_name, scale_amp, scale_freq in SCALE_PROFILES:
                variant = f"{use_case.slug}_{style_name}_{scale_name}"
                function = _function_name(variant)
                tags = [use_case.slug, style_name, scale_name, "cloth", "wind", "fabric"]
                if use_case.normal:
                    hlsl = _hlsl_normal_variant(use_case, function, amp * scale_amp, freq * scale_freq, gust, speed, tags)
                    glsl = _glsl_normal_variant(use_case, function, amp * scale_amp, freq * scale_freq, gust, speed, tags)
                else:
                    hlsl = _hlsl_offset_variant(use_case, function, amp * scale_amp, freq * scale_freq, gust, speed, tags)
                    glsl = _glsl_offset_variant(use_case, function, amp * scale_amp, freq * scale_freq, gust, speed, tags)

                hlsl_path = HLSL_ROOT / use_case.slug / f"{variant}.hlsl"
                glsl_path = GLSL_ROOT / use_case.slug / f"{variant}.glsl"
                hlsl_path.parent.mkdir(parents=True, exist_ok=True)
                glsl_path.parent.mkdir(parents=True, exist_ok=True)
                hlsl_path.write_text(hlsl, encoding="utf-8")
                glsl_path.write_text(glsl, encoding="utf-8")
                metadata["items"].append(_metadata_item(hlsl_path, variant, use_case, style_name, scale_name, tags))
                metadata["items"].append(_metadata_item(glsl_path, variant, use_case, style_name, scale_name, tags))

    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(metadata["items"]), "metadata": str(METADATA_PATH)}, indent=2))
    return 0


def _hlsl_offset_variant(
    use_case: UseCase,
    function: str,
    amplitude: float,
    frequency: float,
    gust: float,
    speed: float,
    tags: list[str],
) -> str:
    return f"""// Lethe generated cloth wind reference, MIT-compatible for project use.
// Use case: {use_case.title}. Motion: {use_case.motion}. Detail: {use_case.detail}.
// Tags: {", ".join(tags)}

float LetheGenHash12_{function}(float2 p)
{{
    float3 p3 = frac(float3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}}

float LetheGenNoise2D_{function}(float2 p)
{{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    float a = LetheGenHash12_{function}(i + float2(0.0, 0.0));
    float b = LetheGenHash12_{function}(i + float2(1.0, 0.0));
    float c = LetheGenHash12_{function}(i + float2(0.0, 1.0));
    float d = LetheGenHash12_{function}(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
}}

float3 Lethe_{function}_Offset(float2 uv, float3 worldPos, float3 normalWS, float3 tangentWS, float time)
{{
    float pinValue = saturate({use_case.pin_axis});
    float freeMask = smoothstep(0.06, 0.35, pinValue);
    float carrier = sin(uv.x * {frequency:.4f} + uv.y * {frequency * 0.31:.4f} - time * {speed:.4f});
    float cross = sin((uv.x - uv.y) * {frequency * 1.73:.4f} + time * {speed * 1.57:.4f});
    float gust = LetheGenNoise2D_{function}(worldPos.xy * {0.011 * frequency:.5f} + float2(time * {0.09 * speed:.5f}, time * 0.037));
    float detail = sin(uv.x * {frequency * 3.2:.4f} - time * {speed * 2.4:.4f}) * smoothstep(0.55, 1.0, pinValue);
    float pressure = carrier * 0.62 + cross * 0.23 + detail * 0.13 + (gust - 0.5) * {gust:.4f};
    float3 windDir = normalize(float3(0.74, 0.38, 0.0));
    return (normalWS * pressure + windDir * gust * 0.18 + tangentWS * cross * 0.08) * freeMask * {amplitude:.4f};
}}
"""


def _hlsl_normal_variant(
    use_case: UseCase,
    function: str,
    amplitude: float,
    frequency: float,
    gust: float,
    speed: float,
    tags: list[str],
) -> str:
    return f"""// Lethe generated cloth wind normal reference, MIT-compatible for project use.
// Use case: {use_case.title}. Motion: {use_case.motion}. Detail: {use_case.detail}.
// Tags: {", ".join(tags)}

float3 Lethe_{function}_Normal(float2 uv, float3 normalWS, float3 tangentWS, float3 bitangentWS, float time)
{{
    float weaveA = sin(uv.x * {frequency * 9.0:.4f} + uv.y * {frequency * 1.7:.4f} + time * {speed * 2.1:.4f});
    float weaveB = sin(uv.y * {frequency * 8.2:.4f} - uv.x * {frequency * 2.3:.4f} - time * {speed * 1.8:.4f});
    float pulse = sin((uv.x + uv.y) * {frequency * 3.7:.4f} + time * {speed:.4f}) * {gust:.4f};
    float2 slope = float2(weaveA + pulse * 0.35, weaveB - pulse * 0.25) * {amplitude * 0.12:.4f};
    return normalize(normalWS + tangentWS * slope.x + bitangentWS * slope.y);
}}
"""


def _glsl_offset_variant(
    use_case: UseCase,
    function: str,
    amplitude: float,
    frequency: float,
    gust: float,
    speed: float,
    tags: list[str],
) -> str:
    glsl_function = function.lower()
    pin_expr = use_case.pin_axis.replace("float2", "vec2").replace("uv.", "uv.")
    return f"""// Lethe generated cloth wind reference, MIT-compatible for project use.
// Use case: {use_case.title}. Motion: {use_case.motion}. Detail: {use_case.detail}.
// Tags: {", ".join(tags)}

float lethe_gen_hash12_{glsl_function}(vec2 p) {{
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}}

float lethe_gen_noise2d_{glsl_function}(vec2 p) {{
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = lethe_gen_hash12_{glsl_function}(i + vec2(0.0, 0.0));
    float b = lethe_gen_hash12_{glsl_function}(i + vec2(1.0, 0.0));
    float c = lethe_gen_hash12_{glsl_function}(i + vec2(0.0, 1.0));
    float d = lethe_gen_hash12_{glsl_function}(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}}

vec3 lethe_{glsl_function}_offset(vec2 uv, vec3 worldPos, vec3 normal, vec3 tangent, float time) {{
    float pinValue = clamp({pin_expr}, 0.0, 1.0);
    float freeMask = smoothstep(0.06, 0.35, pinValue);
    float carrier = sin(uv.x * {frequency:.4f} + uv.y * {frequency * 0.31:.4f} - time * {speed:.4f});
    float crossWave = sin((uv.x - uv.y) * {frequency * 1.73:.4f} + time * {speed * 1.57:.4f});
    float gust = lethe_gen_noise2d_{glsl_function}(worldPos.xy * {0.011 * frequency:.5f} + vec2(time * {0.09 * speed:.5f}, time * 0.037));
    float detail = sin(uv.x * {frequency * 3.2:.4f} - time * {speed * 2.4:.4f}) * smoothstep(0.55, 1.0, pinValue);
    float pressure = carrier * 0.62 + crossWave * 0.23 + detail * 0.13 + (gust - 0.5) * {gust:.4f};
    vec3 windDir = normalize(vec3(0.74, 0.38, 0.0));
    return (normal * pressure + windDir * gust * 0.18 + tangent * crossWave * 0.08) * freeMask * {amplitude:.4f};
}}
"""


def _glsl_normal_variant(
    use_case: UseCase,
    function: str,
    amplitude: float,
    frequency: float,
    gust: float,
    speed: float,
    tags: list[str],
) -> str:
    glsl_function = function.lower()
    return f"""// Lethe generated cloth wind normal reference, MIT-compatible for project use.
// Use case: {use_case.title}. Motion: {use_case.motion}. Detail: {use_case.detail}.
// Tags: {", ".join(tags)}

vec3 lethe_{glsl_function}_normal(vec2 uv, vec3 normal, vec3 tangent, vec3 bitangent, float time) {{
    float weaveA = sin(uv.x * {frequency * 9.0:.4f} + uv.y * {frequency * 1.7:.4f} + time * {speed * 2.1:.4f});
    float weaveB = sin(uv.y * {frequency * 8.2:.4f} - uv.x * {frequency * 2.3:.4f} - time * {speed * 1.8:.4f});
    float pulse = sin((uv.x + uv.y) * {frequency * 3.7:.4f} + time * {speed:.4f}) * {gust:.4f};
    vec2 slope = vec2(weaveA + pulse * 0.35, weaveB - pulse * 0.25) * {amplitude * 0.12:.4f};
    return normalize(normal + tangent * slope.x + bitangent * slope.y);
}}
"""


def _metadata_item(path: Path, variant: str, use_case: UseCase, style_name: str, scale_name: str, tags: list[str]) -> dict[str, str | list[str]]:
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "variant": variant,
        "use_case": use_case.slug,
        "title": use_case.title,
        "style": style_name,
        "scale": scale_name,
        "language": path.suffix.lstrip("."),
        "license": "MIT",
        "source": "lethe-authored-generated",
        "tags": tags,
    }


def _function_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).title().replace("_", "")


if __name__ == "__main__":
    raise SystemExit(main())
