"""Procedurally place 1000 actors from the 50-asset library, one UE call.

Token-cheap: the 1000-actor list is generated in Python and written to a
temp JSON file; the UE script (fixed, small) reads that file, clears the
scene, spawns, and attaches. Nothing per-actor is printed to the chat.

Hierarchy: settlements (fire pit / fort anchors with market tables +
furniture), groves (a tree anchors shrubs/ferns/logs), rock piles
(a boulder anchors stones), then scattered ground cover hung under
random anchors — every actor lands under some parent or is a top anchor.

Run with ws_server STOPPED. Restart it after to view the tree.

    python scripts/build_town_1000.py
"""
from __future__ import annotations

import json
import math
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from lethe.server import _run_in_ue  # noqa: E402

random.seed(7)
TARGET = 1000
HALF = 16000  # map half-extent in cm (320 m square)

BIG_TREE = ["pine_tree_01", "fir_tree_01", "island_tree_01", "tree_small_02"]
GROUND_VEG = ["fern_02", "shrub_01", "shrub_02", "moss_01", "grass_medium_01",
              "dry_branches_medium_01", "tree_stump_01", "tree_stump_02",
              "dead_tree_trunk", "dead_tree_trunk_02"]
ROCK_SMALL = ["rock_07", "rock_09", "stone_01"]
STRUCT = ["stone_fire_pit", "modular_fort_01", "large_castle_door", "large_iron_gate"]
CONTAINER = ["wooden_barrels_01", "wine_barrel_01", "wooden_crate_01",
             "wooden_crate_02", "wooden_bucket_01", "wooden_bucket_02",
             "treasure_chest", "wicker_basket_01", "wicker_basket_02", "cannon_01"]
LIGHTING = ["wooden_lantern_01", "Lantern_01", "lantern_chandelier_01"]
FURNITURE = ["painted_wooden_bench", "WoodenChair_01", "round_wooden_table_01",
             "folding_wooden_stool", "wooden_stool_01", "painted_wooden_chair_02"]
GOODS = ["ceramic_vase_01", "ceramic_vase_02", "jug_01", "food_apple_01"]
MISC = ["kite_shield", "wooden_axe", "spinning_wheel_01", "gate_latch_01"]

# tiny meshes scaled up so they read at this density
SCALE_UP = {"rock_09": 4.0, "stone_01": 4.0, "moss_01": 6.0,
            "grass_medium_01": 3.0, "food_apple_01": 2.0, "gate_latch_01": 3.0}

actors = []          # (label, slug, x, y, z, yaw, scale, parent_label)
anchors = []         # labels eligible to parent scattered fill

def add(slug, x, y, z, yaw, parent, scale=None):
    if scale is None:
        scale = SCALE_UP.get(slug, 1.0)
    label = f"{slug}_{len(actors)}"
    actors.append((label, slug, round(x), round(y), round(z),
                   round(yaw), scale, parent))
    return label

def ring(cx, cy, rmin, rmax):
    a = random.uniform(0, math.tau)
    r = random.uniform(rmin, rmax)
    return cx + math.cos(a) * r, cy + math.sin(a) * r

# 1) Settlements -----------------------------------------------------------
for _ in range(12):
    cx, cy = random.uniform(-HALF*0.55, HALF*0.55), random.uniform(-HALF*0.55, HALF*0.55)
    anc = add(random.choice(STRUCT), cx, cy, 0, random.uniform(0, 360), None)
    anchors.append(anc)
    # market table (3-level: anchor -> table -> goods)
    if random.random() < 0.8:
        tx, ty = ring(cx, cy, 300, 700)
        tbl = add("WoodenTable_01", tx, ty, 0, random.uniform(0, 360), anc)
        for _ in range(random.randint(2, 4)):
            add(random.choice(GOODS), tx+random.uniform(-60, 60),
                ty+random.uniform(-30, 30), 55, 0, tbl)
    # surrounding furniture / containers / lighting / misc
    for _ in range(random.randint(8, 15)):
        s = random.choice(FURNITURE + CONTAINER + LIGHTING + MISC)
        x, y = ring(cx, cy, 200, 900)
        add(s, x, y, 0, random.uniform(0, 360), anc)

# 2) Groves ----------------------------------------------------------------
while len(actors) < int(TARGET * 0.55):
    cx, cy = random.uniform(-HALF, HALF), random.uniform(-HALF, HALF)
    anc = add(random.choice(BIG_TREE), cx, cy, 0, random.uniform(0, 360), None)
    anchors.append(anc)
    for _ in range(random.randint(3, 7)):
        s = random.choice(GROUND_VEG + ROCK_SMALL)
        x, y = ring(cx, cy, 150, 800)
        add(s, x, y, 0, random.uniform(0, 360), anc)

# 3) Rock piles ------------------------------------------------------------
while len(actors) < int(TARGET * 0.70):
    cx, cy = random.uniform(-HALF, HALF), random.uniform(-HALF, HALF)
    anc = add("boulder_01", cx, cy, 0, random.uniform(0, 360), None)
    anchors.append(anc)
    for _ in range(random.randint(3, 6)):
        s = random.choice(ROCK_SMALL + ["dead_tree_trunk", "moss_01"])
        x, y = ring(cx, cy, 80, 500)
        add(s, x, y, 0, random.uniform(0, 360), anc)

# 4) Scattered ground cover under random anchors, fill to exactly TARGET ---
while len(actors) < TARGET:
    parent = random.choice(anchors)
    # find parent coords
    px, py = next((a[2], a[3]) for a in actors if a[0] == parent)
    s = random.choice(GROUND_VEG + ROCK_SMALL)
    x, y = ring(px, py, 200, 1200)
    add(s, x, y, 0, random.uniform(0, 360), parent)

# ---- write to temp file, run one UE call --------------------------------
spawn_file = Path(tempfile.gettempdir()) / "lethe_spawn.json"
spawn_file.write_text(json.dumps(actors), encoding="utf-8")

n_top = sum(1 for a in actors if a[7] is None)
print(f"generated {len(actors)} actors ({n_top} top anchors, "
      f"{len(actors)-n_top} children) -> {spawn_file}")

UE = r'''
import unreal, json
data = json.load(open(r"%FILE%", encoding="utf-8"))
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()
deleted = 0
for a in list(sub.get_all_level_actors()):
    if isinstance(a, unreal.StaticMeshActor):
        sub.destroy_actor(a); deleted += 1
mc = {}
def mesh(slug):
    if slug in mc: return mc[slug]
    m = None
    for ad in reg.get_assets_by_path("/Game/Lethe/Models/"+slug, recursive=True):
        o = ad.get_asset()
        if isinstance(o, unreal.StaticMesh): m = o; break
    mc[slug] = m; return m
L = {}
sp = 0
for label, slug, x, y, z, yaw, scale, parent in data:
    m = mesh(slug)
    if m is None: continue
    act = sub.spawn_actor_from_object(m, unreal.Vector(x, y, z), unreal.Rotator(0, 0, yaw))
    act.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    act.set_actor_label(label)
    L[label] = act; sp += 1
at = 0
for label, slug, x, y, z, yaw, scale, parent in data:
    if parent and label in L and parent in L:
        L[label].attach_to_actor(L[parent], "", unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        at += 1
print("LETHE_JSON::" + json.dumps({"deleted": deleted, "spawned": sp, "attached": at}))
'''.replace("%FILE%", str(spawn_file).replace("\\", "/"))

print("running UE spawn (1000 actors)...")
out = _run_in_ue(UE)
for line in out.splitlines():
    i = line.find("LETHE_JSON::")
    if i >= 0:
        p = json.loads(line[i+len("LETHE_JSON::"):])
        print(f"  deleted={p['deleted']} spawned={p['spawned']} attached={p['attached']}")
        break
else:
    print("unexpected UE output:", out[:500])
print("done — restart ws_server to view.")
