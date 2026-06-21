"""Offline demo artifacts for material synthesis packs.

This module deliberately produces synthetic previews. It is for UI/customer
flow demos when Unreal Editor is not available, not for real material
acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .analyzer import analyze_validation_report


def build_offline_demo_report(pack_dir: str | Path) -> dict[str, Any]:
    """Create synthetic previews + report + customer summaries for a pack."""

    root = Path(pack_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    preview_dir = root / "previews"
    preview_dir.mkdir(exist_ok=True)

    results = []
    for candidate in manifest.get("candidates", []):
        preview_path = preview_dir / f"{int(candidate['order']):03d}_{candidate['id']}_synthetic.png"
        _write_synthetic_preview(candidate, preview_path)
        results.append(
            {
                "candidate_id": candidate["id"],
                "order": candidate["order"],
                "name": candidate["name"],
                "generation": candidate.get("generation", {}),
                "script": candidate.get("files", {}).get("ue_script"),
                "create_ok": True,
                "payload": {
                    "ok": True,
                    "asset": f"/Game/Lethe/GeneratedMaterials/{candidate['name']}",
                    "synthetic_preview": True,
                },
                "stdout": "offline synthetic demo; Unreal Editor was not run",
                "error": None,
                "traceback": None,
                "compile": {
                    "attempted": False,
                    "ok": None,
                    "error": "offline synthetic demo; Unreal compile was not run",
                },
                "preview": {
                    "attempted": True,
                    "ok": True,
                    "path": str(preview_path.resolve()),
                    "error": None,
                    "synthetic": True,
                },
            }
        )

    report = {
        "pack_dir": str(root.resolve()),
        "synthetic_demo": True,
        "count": len(results),
        "created": len(results),
        "previewed": len(results),
        "preview_dir": str(preview_dir.resolve()),
        "results": results,
        "notes": [
            "Synthetic offline demo only; Unreal Editor was not run.",
            "Use material_synth_replay_pack_in_ue for real material creation, compile, and screenshots.",
        ],
    }
    (root / "ue_validation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = analyze_validation_report(root)
    return {
        "report": report,
        "summary": summary,
        "pack_dir": str(root.resolve()),
        "gallery": str((root / "customer_gallery.html").resolve()),
    }


def _write_synthetic_preview(candidate: dict[str, Any], path: Path) -> None:
    generation = candidate.get("generation", {})
    parameters = candidate.get("parameters", {})
    seed_text = f"{candidate.get('id')}:{generation.get('strategy')}:{candidate.get('order')}"
    color_a = _color_from_text(seed_text + ":a")
    color_b = _color_from_text(seed_text + ":b")
    color_c = _color_from_text(seed_text + ":c")
    width, height = 512, 380
    image = Image.new("RGB", (width, height), color_a)
    draw = ImageDraw.Draw(image)

    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(color_a[0] * (1 - t) + color_b[0] * t)
        g = int(color_a[1] * (1 - t) + color_b[1] * t)
        b = int(color_a[2] * (1 - t) + color_b[2] * t)
        draw.line((0, y, width, y), fill=(r, g, b))

    stripe_count = 7 + int(candidate.get("order", 1)) % 5
    for i in range(stripe_count):
        y = int((i + 0.6) * height / (stripe_count + 1))
        offset = (i * 37 + len(seed_text) * 11) % width
        points = []
        for x in range(-40, width + 80, 28):
            yy = y + int(18 * _wave((x + offset) / 45.0, i))
            points.append((x, yy))
        draw.line(points, fill=color_c, width=5)

    foam = parameters.get("foam_cut", 0.65)
    radius = int(28 + float(foam) * 42) if isinstance(foam, (float, int)) else 48
    for i in range(18):
        x = (i * 97 + len(seed_text) * 13) % width
        y = int(height * 0.18 + ((i * 53) % int(height * 0.65)))
        draw.ellipse((x - radius, y - radius // 3, x + radius, y + radius // 3), outline=(245, 250, 235), width=2)

    label = f"{generation.get('agent_id', 'agent')} / {generation.get('strategy', 'strategy')}"
    draw.rectangle((0, height - 42, width, height), fill=(10, 14, 20))
    draw.text((14, height - 30), label[:72], fill=(230, 235, 240))
    image.save(path)


def _color_from_text(text: str) -> tuple[int, int, int]:
    value = sum((idx + 1) * ord(ch) for idx, ch in enumerate(text))
    return (
        24 + value % 160,
        70 + (value // 7) % 150,
        96 + (value // 17) % 140,
    )


def _wave(x: float, phase: int) -> float:
    # Tiny deterministic wave approximation without pulling in numpy.
    wrapped = (x + phase * 0.73) % 6.28318
    return (
        1.27323954 * wrapped - 0.405284735 * wrapped * abs(wrapped)
        if wrapped <= 3.14159
        else -1.27323954 * (wrapped - 3.14159) + 0.405284735 * (wrapped - 3.14159) * abs(wrapped - 3.14159)
    )
