"""HLSL wrappers used by Lethe's material synthesizer."""
from __future__ import annotations

from .schema import MaterialCandidate

STRUCTS_AND_HELPERS = r"""
struct LetheMaterialInput
{
    float2 UV;
    float3 WorldPos;
    float3 Normal;
    float3 CameraVector;
    float Time;
};

struct LetheMaterialOutput
{
    float3 BaseColor;
    float Roughness;
    float Metallic;
    float Alpha;
    float3 Emissive;
};

float lethe_hash21(float2 p)
{
    p = frac(p * float2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return frac(p.x * p.y);
}

float lethe_noise21(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    float a = lethe_hash21(i);
    float b = lethe_hash21(i + float2(1.0, 0.0));
    float c = lethe_hash21(i + float2(0.0, 1.0));
    float d = lethe_hash21(i + float2(1.0, 1.0));
    float2 u = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
}

float lethe_fbm(float2 p)
{
    float value = 0.0;
    float amp = 0.5;
    [unroll]
    for (int i = 0; i < 4; ++i)
    {
        value += amp * lethe_noise21(p);
        p = p * 2.03 + float2(17.1, 9.2);
        amp *= 0.5;
    }
    return value;
}
""".strip()


def wrap_hlsl_body(hlsl_body: str, function_name: str = "LetheMain") -> str:
    """Wrap a candidate body into a complete HLSL helper function."""

    body = hlsl_body.strip()
    return (
        f"{STRUCTS_AND_HELPERS}\n\n"
        f"LetheMaterialOutput {function_name}(LetheMaterialInput I)\n"
        "{\n"
        f"{body}\n"
        "}\n"
    )


def build_channel_custom_code(candidate: MaterialCandidate, channel: str) -> str:
    """Build UE Custom node code returning a single material channel.

    UE material Custom nodes are easiest to wire when each node returns one
    value. UE inserts Custom node code inside an engine-generated function, so
    this must be inline HLSL: no nested struct or function definitions.
    """

    channel_map = {
        "BaseColor": "O_BaseColor",
        "Emissive": "O_Emissive",
        "Roughness": "O_Roughness",
        "Metallic": "O_Metallic",
        "Alpha": "O_Alpha",
    }
    if channel not in channel_map:
        raise ValueError(f"unknown channel: {channel}")

    code = candidate.hlsl_body.strip()
    code = code.replace(
        "LetheMaterialOutput O;",
        "\n".join(
            [
                "float3 O_BaseColor = float3(0.0, 0.0, 0.0);",
                "float O_Roughness = 0.5;",
                "float O_Metallic = 0.0;",
                "float O_Alpha = 1.0;",
                "float3 O_Emissive = float3(0.0, 0.0, 0.0);",
            ]
        ),
    )
    replacements = {
        "O.BaseColor": "O_BaseColor",
        "O.Roughness": "O_Roughness",
        "O.Metallic": "O_Metallic",
        "O.Alpha": "O_Alpha",
        "O.Emissive": "O_Emissive",
        "I.UV": "UV",
        "I.WorldPos": "WorldPos",
        "I.Normal": "Normal",
        "I.CameraVector": "CameraVector",
        "I.Time": "Time",
    }
    for before, after in replacements.items():
        code = code.replace(before, after)
    code = code.replace("return O;", f"return {channel_map[channel]};")
    return code + "\n"
