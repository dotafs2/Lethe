"""Batch-download 50 medieval/map PolyHaven models into the UE project.

For each slug: fetch the file manifest, pick the LOWEST glTF texture
resolution, download glTF + sidecar textures into the project's
Saved/Lethe/Downloads cache, then IMPORT into /Game/Lethe/Models/<slug>/
WITHOUT spawning an actor (keeps the level clean — this just builds the
asset library).

Writes scripts/_asset_library.json recording each model's slug, name,
role, imported StaticMesh path, and bounds, so later placement code can
query the library offline.

Run with ws_server STOPPED (avoids concurrent UE Remote Execution calls).

    python scripts/download_assets.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lethe.server import (
    _http_get_json,
    _http_download,
    _ue_saved_dir,
    _run_in_ue,
    _POLYHAVEN_API,
)

# ---------------------------------------------------------------------------
# The 50 picks — grouped by role in a medieval town map
# ---------------------------------------------------------------------------
PICKS: list[tuple[str, str]] = [
    # --- terrain / nature (18) ---
    ("tree_stump_01", "terrain_nature"),
    ("tree_stump_02", "terrain_nature"),
    ("dead_tree_trunk", "terrain_nature"),
    ("dead_tree_trunk_02", "terrain_nature"),
    ("fir_tree_01", "terrain_nature"),
    ("pine_tree_01", "terrain_nature"),
    ("tree_small_02", "terrain_nature"),
    ("island_tree_01", "terrain_nature"),
    ("fern_02", "terrain_nature"),
    ("shrub_01", "terrain_nature"),
    ("shrub_02", "terrain_nature"),
    ("boulder_01", "terrain_nature"),
    ("rock_07", "terrain_nature"),
    ("rock_09", "terrain_nature"),
    ("stone_01", "terrain_nature"),
    ("moss_01", "terrain_nature"),
    ("grass_medium_01", "terrain_nature"),
    ("dry_branches_medium_01", "terrain_nature"),
    # --- structure (5) ---
    ("large_castle_door", "structure"),
    ("large_iron_gate", "structure"),
    ("stone_fire_pit", "structure"),
    ("modular_fort_01", "structure"),
    ("gate_latch_01", "structure"),
    # --- container / prop (13) ---
    ("wooden_barrels_01", "container_prop"),
    ("wine_barrel_01", "container_prop"),
    ("wooden_crate_01", "container_prop"),
    ("wooden_crate_02", "container_prop"),
    ("wooden_bucket_01", "container_prop"),
    ("wooden_bucket_02", "container_prop"),
    ("treasure_chest", "container_prop"),
    ("ceramic_vase_01", "container_prop"),
    ("ceramic_vase_02", "container_prop"),
    ("jug_01", "container_prop"),
    ("wicker_basket_01", "container_prop"),
    ("wicker_basket_02", "container_prop"),
    ("cannon_01", "container_prop"),
    # --- lighting (3) ---
    ("wooden_lantern_01", "lighting"),
    ("Lantern_01", "lighting"),
    ("lantern_chandelier_01", "lighting"),
    # --- wooden furniture (7) ---
    ("painted_wooden_bench", "furniture"),
    ("WoodenChair_01", "furniture"),
    ("WoodenTable_01", "furniture"),
    ("round_wooden_table_01", "furniture"),
    ("folding_wooden_stool", "furniture"),
    ("wooden_stool_01", "furniture"),
    ("painted_wooden_chair_02", "furniture"),
    # --- market / misc (4) ---
    ("kite_shield", "misc"),
    ("wooden_axe", "misc"),
    ("spinning_wheel_01", "misc"),
    ("food_apple_01", "misc"),
]

# Import-only UE script — imports the glTF as a StaticMesh, does NOT spawn.
IMPORT_ONLY_TMPL = r'''
import unreal, json
_GLTF_PATH = r"{gltf_path}".replace("\\", "/")
_SLUG = "{slug}"
_DEST = "/Game/Lethe/Models/" + _SLUG

_task = unreal.AssetImportTask()
_task.filename = _GLTF_PATH
_task.destination_path = _DEST
_task.replace_existing = True
_task.automated = True
_task.save = True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([_task])

_mesh = None
_reg = unreal.AssetRegistryHelpers.get_asset_registry()
for _ad in _reg.get_assets_by_path(_DEST, recursive=True):
    _a = _ad.get_asset()
    if isinstance(_a, unreal.StaticMesh):
        _mesh = _a
        break

if _mesh is None:
    print("LETHE_JSON::" + json.dumps({{"error": "no StaticMesh under " + _DEST}}))
else:
    _b = _mesh.get_bounding_box()
    _min, _max = _b.min, _b.max
    print("LETHE_JSON::" + json.dumps({{
        "ok": True,
        "mesh": _mesh.get_path_name(),
        "bounds_min": [_min.x, _min.y, _min.z],
        "bounds_max": [_max.x, _max.y, _max.z],
    }}))
'''


def pick_lowest_res(gltf_section: dict) -> str | None:
    """Choose the smallest texture resolution key like '1k','2k','4k'."""
    if not gltf_section:
        return None

    def res_value(k: str) -> float:
        # '1k' -> 1, '2k' -> 2, '4k' -> 4, '8k' -> 8; non-standard -> inf
        kl = k.lower().strip()
        if kl.endswith("k") and kl[:-1].replace(".", "").isdigit():
            return float(kl[:-1])
        return float("inf")

    return sorted(gltf_section.keys(), key=res_value)[0]


def download_and_import(slug: str, role: str) -> dict:
    rec = {"slug": slug, "role": role, "ok": False}
    try:
        files = _http_get_json(f"{_POLYHAVEN_API}/files/{slug}")
    except Exception as e:
        rec["error"] = f"manifest fetch failed: {e}"
        return rec

    gltf_section = files.get("gltf") or {}
    res = pick_lowest_res(gltf_section)
    if not res:
        rec["error"] = f"no glTF formats (have {sorted(files.keys())})"
        return rec
    rec["resolution"] = res

    gltf_info = (gltf_section[res].get("gltf") or {})
    gltf_url = gltf_info.get("url")
    if not gltf_url:
        rec["error"] = "no glTF url"
        return rec

    cache_root = os.path.join(_ue_saved_dir(), "Lethe", "Downloads", "Models", slug)
    os.makedirs(cache_root, exist_ok=True)
    gltf_name = os.path.basename(gltf_url.split("?")[0])
    gltf_local = os.path.join(cache_root, gltf_name)

    try:
        if not os.path.exists(gltf_local):
            _http_download(gltf_url, gltf_local)
        # sidecar files (textures, .bin)
        for rel_path, info in (gltf_info.get("include") or {}).items():
            url = info.get("url")
            if not url:
                continue
            dest = os.path.join(cache_root, rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if not os.path.exists(dest):
                _http_download(url, dest)
    except Exception as e:
        rec["error"] = f"download failed: {e}"
        return rec

    # import into UE
    script = IMPORT_ONLY_TMPL.format(gltf_path=gltf_local.replace("\\", "\\\\"), slug=slug)
    stdout = _run_in_ue(script)
    payload = None
    for line in stdout.splitlines():
        idx = line.find("LETHE_JSON::")
        if idx >= 0:
            try:
                payload = json.loads(line[idx + len("LETHE_JSON::"):])
            except Exception:
                pass
            break
    if not payload or "error" in (payload or {}):
        rec["error"] = f"import failed: {payload.get('error') if payload else stdout[:200]}"
        return rec

    rec.update({
        "ok": True,
        "name": slug.replace("_", " ").title(),
        "mesh": payload["mesh"],
        "bounds_min": payload["bounds_min"],
        "bounds_max": payload["bounds_max"],
    })
    return rec


def main():
    print(f"Downloading {len(PICKS)} models (lowest resolution, import-only)\n")
    results = []
    t0 = time.time()
    for i, (slug, role) in enumerate(PICKS, 1):
        print(f"[{i:2d}/{len(PICKS)}] {slug:<28s} ({role}) ... ", end="", flush=True)
        rec = download_and_import(slug, role)
        if rec["ok"]:
            print(f"OK  res={rec.get('resolution')}")
        else:
            print(f"FAIL  {rec.get('error', '')[:80]}")
        results.append(rec)

    out = Path(__file__).resolve().parent / "_asset_library.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"done in {time.time()-t0:.0f}s — {ok}/{len(PICKS)} imported")
    print(f"library manifest: {out}")
    fails = [r["slug"] for r in results if not r["ok"]]
    if fails:
        print(f"failed: {', '.join(fails)}")


if __name__ == "__main__":
    main()
