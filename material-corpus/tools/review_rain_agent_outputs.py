"""Review delegated agent outputs for rainy-day water surface shaders."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "rain_water_agents"
OUT_DIR = ROOT / "rain_water_surface_hlsl"
REPORT = OUT_DIR / "agent_review_report.json"

EXPECTED = {
    "agent_01_impact_ripples.json": ["impact", "ripple", "drop", "rain"],
    "agent_02_puddle_materials.json": ["puddle", "water", "wet", "film"],
    "agent_03_flow_gutters.json": ["flow", "stream", "runoff", "water"],
    "agent_04_wave_physics.json": ["wave", "normal", "height", "surface"],
    "agent_05_reflection_lighting.json": ["reflection", "specular", "light", "puddle"],
    "agent_06_foam_splashes.json": ["foam", "splash", "droplet", "rain"],
    "agent_07_material_contexts.json": ["puddle", "rain", "surface", "water"],
    "agent_08_stylized.json": ["rain", "puddle", "water", "stylized"],
    "agent_09_temporal.json": ["time", "rain", "event", "water", "gust", "front", "ramp", "flash"],
    "agent_10_hybrid.json": ["rain", "water", "flow", "impact"],
}

REQUIRED_FIELDS = ["title", "algorithm_family", "uniqueness_notes", "hlsl", "preview_model", "parameters"]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    global_signatures: dict[str, str] = {}
    global_families: dict[str, str] = {}
    files = []
    total_items = 0
    duplicate_signatures = []
    duplicate_families = []
    missing_files = []

    for filename, keywords in EXPECTED.items():
        path = AGENT_DIR / filename
        if not path.exists():
            missing_files.append(filename)
            files.append({"file": filename, "status": "missing"})
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            files.append({"file": filename, "status": "invalid_json", "error": str(exc)})
            continue

        file_report = review_items(filename, data, keywords)
        files.append(file_report)
        total_items += file_report["count"]

        for item in data if isinstance(data, list) else []:
            family = str(item.get("algorithm_family", "")).strip().lower()
            sig = code_signature(str(item.get("hlsl", "")))
            if family:
                if family in global_families:
                    duplicate_families.append({"family": family, "first": global_families[family], "second": filename})
                else:
                    global_families[family] = filename
            if sig:
                if sig in global_signatures:
                    duplicate_signatures.append({"signature": sig, "first": global_signatures[sig], "second": filename})
                else:
                    global_signatures[sig] = filename

    report = {
        "schema_version": 1,
        "expected_files": len(EXPECTED),
        "present_files": len([f for f in files if f.get("status") != "missing"]),
        "missing_files": missing_files,
        "expected_items": 100,
        "total_items": total_items,
        "global_unique_families": len(global_families),
        "global_unique_code_signatures": len(global_signatures),
        "duplicate_families": duplicate_families,
        "duplicate_signatures": duplicate_signatures,
        "files": files,
        "strict_pass": (
            not missing_files
            and total_items == 100
            and not duplicate_families
            and not duplicate_signatures
            and all(f.get("strict_pass") for f in files)
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "strict_pass": report["strict_pass"],
        "present_files": report["present_files"],
        "total_items": total_items,
        "report": str(REPORT),
    }, indent=2))
    return 0 if report["strict_pass"] else 2


def review_items(filename: str, data: object, keywords: list[str]) -> dict:
    if not isinstance(data, list):
        return {"file": filename, "status": "not_array", "strict_pass": False, "count": 0}

    families = []
    signatures = []
    item_issues = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            item_issues.append({"index": index, "issue": "item_not_object"})
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in item or item[field] in ("", None)]
        if missing:
            item_issues.append({"index": index, "issue": "missing_fields", "fields": missing})
        text = " ".join(str(item.get(field, "")) for field in ("title", "algorithm_family", "uniqueness_notes", "hlsl", "preview_model")).lower()
        if not any(keyword in text for keyword in keywords):
            item_issues.append({"index": index, "issue": "possibly_off_target", "keywords": keywords})
        hlsl = str(item.get("hlsl", ""))
        if len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", hlsl)) < 24:
            item_issues.append({"index": index, "issue": "hlsl_too_thin"})
        family = str(item.get("algorithm_family", "")).strip().lower()
        if family:
            families.append(family)
        sig = code_signature(hlsl)
        if sig:
            signatures.append(sig)

    duplicate_families = sorted({family for family in families if families.count(family) > 1})
    duplicate_signatures = sorted({sig for sig in signatures if signatures.count(sig) > 1})
    return {
        "file": filename,
        "status": "reviewed",
        "count": len(data),
        "unique_families": len(set(families)),
        "unique_code_signatures": len(set(signatures)),
        "duplicate_families": duplicate_families,
        "duplicate_code_signatures": duplicate_signatures,
        "item_issues": item_issues,
        "strict_pass": len(data) == 10 and not duplicate_families and not duplicate_signatures and not item_issues,
    }


def code_signature(hlsl: str) -> str:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[+\-*/]", hlsl.lower())
    stop = {
        "float", "float2", "float3", "float4", "uv", "time", "hlsl", "return",
        "height", "normal", "color", "water", "rain", "saturate", "lerp",
    }
    useful = [token for token in tokens if token not in stop]
    if len(useful) < 8:
        return ""
    payload = "|".join(useful[:80])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(main())
