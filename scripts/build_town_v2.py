"""Build a medieval town from the imported asset library (one UE round-trip).

Improvements over build_medieval_town.py:
  * Spawns from already-imported meshes in /Game/Lethe/Models/<slug>/ —
    no re-download.
  * Clears + spawns + attaches in a SINGLE UE Remote Execution call
    (fast, no concurrency hazard).
  * 3-4 level hierarchy that demonstrates the "objects hang under objects"
    tree paradigm from plan.md.

Tree shape (parents reference child labels):

    World
    ├── TownCenter (stone_fire_pit, the square anchor)
    │     ├── Bench_E / Bench_W / Stool_S / Stump_N
    │     ├── Chandelier (hangs above the fire)
    │     ├── MarketTable
    │     │     ├── Vase1 / Vase2 / Jug / Apple   (goods ON the table)
    │     │     └── Basket                         (on the ground beside it)
    │     └── Barrels
    │           ├── BucketTop (on top of barrels)
    │           └── Crate_S / Bucket_S
    ├── Gatehouse (large_castle_door)
    │     ├── IronGate / Latch / LanternL / LanternR
    ├── Fort (modular_fort_01)
    │     ├── Cannon / Shield / Chest / CrateF / LanternF
    ├── Workshop (spinning_wheel_01)
    │     ├── WorkChair / Axe / Stool_W / Bucket_W
    ├── Pine_1 / Fir_1 / Pine_2 (each with shrubs/ferns/logs under it)
    ├── IslandTree (→ TreeSmall)
    └── Boulder_1 / Boulder_2 (each with rocks/stones under it)

Run with ws_server STOPPED. Restart it afterwards to see the tree.

    python scripts/build_town_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from lethe.server import _run_in_ue  # noqa: E402

# Coordinates in cm (UE units). X=east, Y=north, Z=up. Fire pit at origin.
# Each entry: (label, slug, x, y, z, yaw, scale, parent_label_or_None)
RECIPE = [
    # ─── Town center (square) ───
    ("TownCenter",   "stone_fire_pit",         0,     0,    0,    0, 1.0, None),
    ("Bench_E",      "painted_wooden_bench",   250,   0,    0,  -90, 1.0, "TownCenter"),
    ("Bench_W",      "painted_wooden_bench",  -250,   0,    0,   90, 1.0, "TownCenter"),
    ("Stool_S",      "folding_wooden_stool",    0,  -230,   0,    0, 1.0, "TownCenter"),
    ("Stump_N",      "tree_stump_02",           0,   250,   0,    0, 1.0, "TownCenter"),
    ("Chandelier",   "lantern_chandelier_01",   0,     0,  300,   0, 1.0, "TownCenter"),

    # ─── Market stall (3-level: TownCenter → MarketTable → goods) ───
    ("MarketTable",  "WoodenTable_01",         700,  380,   0,    0, 1.0, "TownCenter"),
    ("Vase1",        "ceramic_vase_01",        640,  380,  55,    0, 1.0, "MarketTable"),
    ("Vase2",        "ceramic_vase_02",        760,  380,  55,    0, 1.0, "MarketTable"),
    ("Jug",          "jug_01",                 700,  410,  55,   30, 1.0, "MarketTable"),
    ("Apple",        "food_apple_01",          700,  350,  55,    0, 1.0, "MarketTable"),
    ("Basket",       "wicker_basket_01",       600,  280,   0,    0, 1.0, "MarketTable"),

    # ─── Storage cluster (TownCenter → Barrels → ...) ───
    ("Barrels",      "wooden_barrels_01",      700, -380,   0,    0, 1.0, "TownCenter"),
    ("BucketTop",    "wooden_bucket_01",       700, -380,  92,    0, 1.0, "Barrels"),
    ("Crate_S",      "wooden_crate_02",        830, -380,   0,   20, 1.0, "Barrels"),
    ("Bucket_S",     "wooden_bucket_02",       600, -450,   0,    0, 1.0, "Barrels"),

    # ─── Gatehouse (south entrance) ───
    ("Gatehouse",    "large_castle_door",        0, -1700,  0,    0, 1.0, None),
    ("IronGate",     "large_iron_gate",          0, -1740,  0,    0, 1.0, "Gatehouse"),
    ("Latch",        "gate_latch_01",           80, -1695, 150,   0, 1.0, "Gatehouse"),
    ("LanternL",     "wooden_lantern_01",     -130, -1700, 220,   0, 1.0, "Gatehouse"),
    ("LanternR",     "wooden_lantern_01",      130, -1700, 220,   0, 1.0, "Gatehouse"),

    # ─── Fort (northeast) ───
    ("Fort",         "modular_fort_01",       1900,  1500,  0,  200, 1.0, None),
    ("Cannon",       "cannon_01",             1500,  1150,  0,  225, 1.0, "Fort"),
    ("Shield",       "kite_shield",           1650,  1800, 90,    0, 1.0, "Fort"),
    ("Chest",        "treasure_chest",        2050,  1750,  0,  160, 1.0, "Fort"),
    ("CrateF",       "wooden_crate_01",       2100,  1250,  0,    0, 1.0, "Fort"),
    ("LanternF",     "Lantern_01",            1600,  1450, 100,   0, 1.0, "Fort"),

    # ─── Workshop (southeast) ───
    ("Workshop",     "spinning_wheel_01",     1700, -1200,  0,    0, 1.0, None),
    ("WorkChair",    "painted_wooden_chair_02",1850, -1200, 0,  -90, 1.0, "Workshop"),
    ("Axe",          "wooden_axe",            1550, -1050,  0,   45, 1.0, "Workshop"),
    ("Stool_W",      "wooden_stool_01",       1800, -1380,  0,    0, 1.0, "Workshop"),
    ("Bucket_W",     "wooden_bucket_02",      1550, -1380,  0,    0, 1.0, "Workshop"),

    # ─── Forest, west (each tree is a small subtree) ───
    ("Pine_1",       "pine_tree_01",         -2000,  1400,  0,   15, 1.0, None),
    ("Shrub_a",      "shrub_01",             -1750,  1400,  0,    0, 1.0, "Pine_1"),
    ("Fern_a",       "fern_02",              -2150,  1550,  0,    0, 1.0, "Pine_1"),
    ("Moss_a",       "moss_01",              -1880,  1250,  0,    0, 1.0, "Pine_1"),
    ("Fir_1",        "fir_tree_01",          -2200,    50,  0,   70, 1.0, None),
    ("Shrub_b",      "shrub_02",             -1950,   120,  0,    0, 1.0, "Fir_1"),
    ("DeadLog",      "dead_tree_trunk",      -2000,  -250,  0,   30, 1.0, "Fir_1"),
    ("Pine_2",       "pine_tree_01",         -1900, -1400,  0,  200, 1.0, None),
    ("DryBranch",    "dry_branches_medium_01",-1700, -1350,  0,   60, 1.0, "Pine_2"),
    ("Fern_b",       "fern_02",              -2050, -1500,  0,    0, 1.0, "Pine_2"),

    # ─── East edge trees ───
    ("IslandTree",   "island_tree_01",        2300,  -200,  0,    0, 1.0, None),
    ("TreeSmall",    "tree_small_02",         2050,   150,  0,  120, 1.0, "IslandTree"),

    # ─── Scattered rocks (each boulder anchors smaller stones) ───
    ("Boulder_1",    "boulder_01",             900,  1650,  0,   20, 1.0, None),
    ("Rock_a",       "rock_07",               1060,  1650,  0,    0, 3.0, "Boulder_1"),
    ("Stone_a",      "stone_01",               820,  1750,  0,    0, 4.0, "Boulder_1"),
    ("Boulder_2",    "boulder_01",            -900,  -850,  0,  110, 1.0, None),
    ("DeadLog2",     "dead_tree_trunk_02",   -1120,  -800,  0,   60, 1.0, "Boulder_2"),
]


BUILD_SCRIPT = r'''
import unreal, json

RECIPE = json.loads(r"""%RECIPE_JSON%""")

sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()

# 1) Clear all StaticMeshActors
deleted = 0
for a in list(sub.get_all_level_actors()):
    if isinstance(a, unreal.StaticMeshActor):
        sub.destroy_actor(a); deleted += 1

# Cache: slug -> StaticMesh
mesh_cache = {}
def find_mesh(slug):
    if slug in mesh_cache:
        return mesh_cache[slug]
    dest = "/Game/Lethe/Models/" + slug
    found = None
    for ad in reg.get_assets_by_path(dest, recursive=True):
        obj = ad.get_asset()
        if isinstance(obj, unreal.StaticMesh):
            found = obj; break
    mesh_cache[slug] = found
    return found

# 2) Spawn everything
label_to_actor = {}
spawned, missing = 0, []
for label, slug, x, y, z, yaw, scale, parent in RECIPE:
    mesh = find_mesh(slug)
    if mesh is None:
        missing.append(slug); continue
    loc = unreal.Vector(float(x), float(y), float(z))
    rot = unreal.Rotator(0.0, 0.0, float(yaw))
    actor = sub.spawn_actor_from_object(mesh, loc, rot)
    actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    actor.set_actor_label(label)
    actor.tags = [unreal.Name("lethe_town")]
    label_to_actor[label] = actor
    spawned += 1

# 3) Attach hierarchy (KEEP_WORLD so visual positions stay put)
attached = 0
for label, slug, x, y, z, yaw, scale, parent in RECIPE:
    if not parent:
        continue
    child = label_to_actor.get(label)
    par = label_to_actor.get(parent)
    if child and par:
        child.attach_to_actor(par, "",
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD, False)
        attached += 1

print("LETHE_JSON::" + json.dumps({
    "deleted": deleted, "spawned": spawned,
    "attached": attached, "missing": missing,
}))
'''


def main():
    recipe_json = json.dumps(RECIPE)
    script = BUILD_SCRIPT.replace("%RECIPE_JSON%", recipe_json)
    print(f"Building town: {len(RECIPE)} actors in one UE call...")
    out = _run_in_ue(script)
    payload = None
    for line in out.splitlines():
        idx = line.find("LETHE_JSON::")
        if idx >= 0:
            payload = json.loads(line[idx + len("LETHE_JSON::"):])
            break
    if payload is None:
        print("Unexpected UE output:\n", out[:1000])
        return
    print(f"  deleted:  {payload['deleted']}")
    print(f"  spawned:  {payload['spawned']}")
    print(f"  attached: {payload['attached']}")
    if payload["missing"]:
        print(f"  MISSING meshes: {payload['missing']}")
    print("Done. Restart ws_server to view the tree.")


if __name__ == "__main__":
    main()
