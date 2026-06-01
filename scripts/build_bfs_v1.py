"""BFS layer-by-layer scene builder — plan.md v4 algorithm.

Level 1: Big frame   — landmarks (gate, fort, fire pit) + region anchors
Level 2: Mid         — building clusters, tree groves
Level 3: Fine        — furniture, barrels, crates, props
Level 4: Detail      — tabletop items, ground cover, grass/rocks

All geometry computed in Python (spatial hash, footprint collision, ground-snap).
One UE call clears + spawns + attaches.

Run with ws_server stopped:
    python scripts/build_bfs_v1.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from lethe.server import _run_in_ue  # noqa: E402

random.seed(7)

# ── Asset library ──────────────────────────────────────────────────────────
LIB = {r["slug"]: r for r in json.loads(
    (ROOT / "scripts" / "_asset_library.json").read_text(encoding="utf-8")
) if r.get("ok")}


def dims(slug: str):
    b = LIB[slug]
    mn, mx = b["bounds_min"], b["bounds_max"]
    return mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2], mn[2]   # dx,dy,dz,base_z


SCALE_FIX = {
    "rock_07": 2.5, "rock_09": 3.5, "stone_01": 3.0,
    "moss_01": 2.5, "grass_medium_01": 2.0,
    "food_apple_01": 1.8, "Lantern_01": 1.5, "wooden_lantern_01": 1.2,
}


def sc(slug): return SCALE_FIX.get(slug, 1.0)


def fp_r(slug, footprint_ratio=0.45):
    dx, dy, _, _ = dims(slug)
    return 0.5 * math.hypot(dx, dy) * footprint_ratio * sc(slug)


def ground_z(slug):   # lift so model base sits on z=0
    return -dims(slug)[3] * sc(slug)


def tabletop_z(slug, table_slug):   # place on table surface
    _, _, table_h, table_base = dims(table_slug)
    table_top = (table_h - table_base) * sc(table_slug)
    item_base = -dims(slug)[3] * sc(slug)
    return table_top + item_base


# ── Spatial hash ───────────────────────────────────────────────────────────
class Grid:
    def __init__(self, cell=500):
        self.cell = cell
        self.d: dict = {}

    def _k(self, x, y): return int(x//self.cell), int(y//self.cell)

    def free(self, x, y, r) -> bool:
        kx, ky = self._k(x, y)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for ox, oy, orr in self.d.get((kx+dx, ky+dy), ()):
                    if (x-ox)**2+(y-oy)**2 < (r+orr)**2:
                        return False
        return True

    def insert(self, x, y, r):
        self.d.setdefault(self._k(x,y), []).append((x,y,r))


# ── Tree node ──────────────────────────────────────────────────────────────
@dataclass
class Node:
    id: int
    slug: str
    x: float
    y: float
    z: float
    yaw: float
    scale: float
    parent_id: Optional[int]
    level: int
    children: list = field(default_factory=list)


nodes: list[Node] = []
grid = Grid()
_next_id = 0


def add(slug, x, y, z, yaw, parent: Optional[Node], level,
        collide=True, fp_ratio=0.45) -> Optional[Node]:
    global _next_id
    r = fp_r(slug, fp_ratio)
    if collide and not grid.free(x, y, r):
        return None
    if collide:
        grid.insert(x, y, r)
    n = Node(_next_id, slug, round(x,1), round(y,1), round(z,2),
             round(yaw,1), sc(slug), parent.id if parent else None, level)
    _next_id += 1
    nodes.append(n)
    if parent:
        parent.children.append(n)
    return n


def try_place(slug, cx, cy, min_r, max_r, parent, level,
              yaw_toward=None, attempts=8, fp_ratio=0.45):
    for _ in range(attempts):
        ang = random.uniform(0, 2*math.pi)
        r   = random.uniform(min_r, max_r)
        x, y = cx + math.cos(ang)*r, cy + math.sin(ang)*r
        yaw = math.degrees(math.atan2(cy-y, cx-x)) if yaw_toward else random.uniform(0,360)
        n = add(slug, x, y, ground_z(slug), yaw, parent, level, fp_ratio=fp_ratio)
        if n: return n
    return None


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 1 — Big frame: landmarks (few, large, whole map)
# ═══════════════════════════════════════════════════════════════════════════
print("▶ Level 1 — Big framework")

# Town square anchor (fire pit)
L1_TOWN = add("stone_fire_pit", 0, 0, ground_z("stone_fire_pit"), 0, None, 1)
# Fort NE
L1_FORT = add("modular_fort_01", 5200, 4000, ground_z("modular_fort_01"), 200, None, 1)
# Gate S (town entrance)
L1_GATE = add("large_castle_door", 0, -4500, ground_z("large_castle_door"), 0, None, 1)
# Workshop SE
L1_WORK = add("spinning_wheel_01", 4500, -3500, ground_z("spinning_wheel_01"), 45, None, 1)
# Secondary iron gate near fort
add("large_iron_gate", 4800, 3200, ground_z("large_iron_gate"), 200, L1_FORT, 1)

L1_ANCHORS = [n for n in [L1_TOWN, L1_FORT, L1_GATE, L1_WORK] if n]
print(f"  placed {len([n for n in nodes if n.level==1])} L1 nodes")


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 2 — Mid structures: tables + tree groves + secondary props
# ═══════════════════════════════════════════════════════════════════════════
print("▶ Level 2 — Mid structures")

TREES   = ["pine_tree_01","fir_tree_01","island_tree_01","tree_small_02",
           "dead_tree_trunk","dead_tree_trunk_02"]
TABLES  = ["WoodenTable_01","round_wooden_table_01"]
BARRELS = ["wooden_barrels_01","wine_barrel_01"]
CRATES  = ["wooden_crate_01","wooden_crate_02"]
SEATING = ["painted_wooden_bench","WoodenChair_01","painted_wooden_chair_02",
           "folding_wooden_stool","wooden_stool_01"]

# Market tables around town square
l2_tables = []
for _ in range(6):
    t = try_place(random.choice(TABLES), 0, 0, 400, 1400, L1_TOWN, 2,
                  yaw_toward=True, fp_ratio=0.5)
    if t: l2_tables.append(t)

# Seating ring around fire
for _ in range(8):
    try_place(random.choice(SEATING), 0, 0, 250, 600, L1_TOWN, 2,
              yaw_toward=True, fp_ratio=0.5)

# Fort props (barrels + crates forming a cluster)
for _ in range(6):
    slug = random.choice(BARRELS+CRATES)
    try_place(slug, L1_FORT.x, L1_FORT.y, 600, 2000, L1_FORT, 2,
              yaw_toward=False, fp_ratio=0.5)

# Workshop props
for _ in range(4):
    try_place(random.choice(BARRELS+CRATES+SEATING),
              L1_WORK.x, L1_WORK.y, 250, 900, L1_WORK, 2,
              yaw_toward=True, fp_ratio=0.5)

# Cannon by gate
try_place("cannon_01", L1_GATE.x, L1_GATE.y, 300, 600, L1_GATE, 2,
          yaw_toward=False)

# Tree groves — 4 clusters in compass directions
grove_centers = [(-6500,1500),(-1500,-7000),(7500,2000),(-5000,-5000)]
l2_trees: list[Node] = []
for gx, gy in grove_centers:
    for _ in range(10):
        t = try_place(random.choice(TREES), gx, gy, 0, 3500, None, 2,
                      yaw_toward=False, fp_ratio=0.2)
        if t: l2_trees.append(t)

# Scattered individual trees around town
for _ in range(16):
    t = try_place(random.choice(TREES), 0, 0, 2500, 9000, None, 2,
                  yaw_toward=False, fp_ratio=0.2)
    if t: l2_trees.append(t)

print(f"  placed {len([n for n in nodes if n.level==2])} L2 nodes")


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 3 — Fine structures: more props filling the gaps
# ═══════════════════════════════════════════════════════════════════════════
print("▶ Level 3 — Fine props")

FINE = (["wooden_bucket_01","wooden_bucket_02"]*3 +
        ["treasure_chest","wicker_basket_01","wicker_basket_02"]*2 +
        ["kite_shield","wooden_axe"] +
        ["painted_wooden_bench","wooden_stool_01"])

# Fill around each L1 anchor with fine props
for anch in L1_ANCHORS:
    for _ in range(12):
        try_place(random.choice(FINE), anch.x, anch.y, 600, 2500, anch, 3,
                  yaw_toward=True, fp_ratio=0.5)

# Props scattered on the path between gate and town
for t in range(14):
    frac = (t+1)/15
    px = L1_GATE.x + frac*(L1_TOWN.x - L1_GATE.x) + random.uniform(-400,400)
    py = L1_GATE.y + frac*(L1_TOWN.y - L1_GATE.y) + random.uniform(-400,400)
    slug = random.choice(FINE)
    try_place(slug, px, py, 0, 300, None, 3, yaw_toward=False)

print(f"  placed {len([n for n in nodes if n.level==3])} L3 nodes")


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 4 — Detail: tabletop items + lanterns + ground cover filling ALL gaps
# ═══════════════════════════════════════════════════════════════════════════
print("▶ Level 4 — Detail")

TABLETOP = ["ceramic_vase_01","ceramic_vase_02","jug_01",
            "food_apple_01","wicker_basket_02","wooden_lantern_01","Lantern_01"]
GROUNDCOVER = ["shrub_01","shrub_02","fern_02","moss_01","grass_medium_01",
               "rock_07","rock_09","stone_01","boulder_01",
               "tree_stump_01","tree_stump_02","dry_branches_medium_01"]
LANTERNS = ["wooden_lantern_01","Lantern_01"]

# Tabletop items on every L2 table
for tbl in l2_tables:
    tbl_slug = tbl.slug
    dx, dy, _, _ = dims(tbl_slug)
    tw = dx * sc(tbl_slug)
    td = dy * sc(tbl_slug)
    spots = [(-0.3,0),(0.3,0),(0,0.25),(0,-0.25),(0,0)]
    random.shuffle(spots)
    for i in range(random.randint(2,4)):
        fx, fy = spots[i]
        ox, oy = fx*tw*0.8, fy*td*0.8
        slug = random.choice(TABLETOP)
        z = tabletop_z(slug, tbl_slug)
        add(slug, tbl.x+ox, tbl.y+oy, z, random.uniform(0,360), tbl, 4,
            collide=False)

# Lanterns beside gate + fort
for anch in [L1_GATE, L1_FORT]:
    for side in [1,-1]:
        try_place(random.choice(LANTERNS), anch.x+side*180, anch.y,
                  0, 50, anch, 4, yaw_toward=False, attempts=4)

# Ground cover beneath every tree
for tree in l2_trees:
    for _ in range(random.randint(2, 5)):
        slug = random.choice(GROUNDCOVER)
        try_place(slug, tree.x, tree.y, 200, 900, tree, 4,
                  yaw_toward=False, fp_ratio=0.3, attempts=6)

# Dense ground scatter to fill the whole area
for _ in range(350):
    ang  = random.uniform(0, 2*math.pi)
    dist = random.uniform(500, 11000) ** 0.8 * (11000**0.2)
    x = math.cos(ang)*dist
    y = math.sin(ang)*dist
    slug = random.choice(GROUNDCOVER)
    try_place(slug, x, y, 0, 200, None, 4,
              yaw_toward=False, fp_ratio=0.3, attempts=3)

print(f"  placed {len([n for n in nodes if n.level==4])} L4 nodes")
print(f"  TOTAL  {len(nodes)} nodes")


# ═══════════════════════════════════════════════════════════════════════════
# Compile + send to UE (one call)
# ═══════════════════════════════════════════════════════════════════════════
payload = [
    dict(slug=n.slug, x=n.x, y=n.y, z=n.z, yaw=n.yaw,
         scale=n.scale, parent_id=n.parent_id, label=f"L{n.level}_{n.slug}_{n.id}")
    for n in nodes
]

UE_SCRIPT = r'''
import unreal, json

P = json.loads(r"""%P%""")

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()

# 0 — clear
deleted = 0
for a in list(eas.get_all_level_actors()):
    if isinstance(a, unreal.StaticMeshActor):
        eas.destroy_actor(a); deleted += 1

# Layer 0 — ground plane
gnd = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
ga  = eas.spawn_actor_from_object(gnd, unreal.Vector(0,0,0))
ga.set_actor_scale3d(unreal.Vector(300,300,1))
ga.set_actor_label("Ground")

# cache slugs -> mesh
cache = {}
def mesh(slug):
    if slug in cache: return cache[slug]
    m = None
    for ad in reg.get_assets_by_path("/Game/Lethe/Models/"+slug, recursive=True):
        o = ad.get_asset()
        if isinstance(o, unreal.StaticMesh):
            m = o; break
    cache[slug] = m
    return m

actors = []
spawned = 0; missing = set()
for p in P:
    m = mesh(p["slug"])
    if m is None:
        missing.add(p["slug"]); actors.append(None); continue
    a = eas.spawn_actor_from_object(m,
        unreal.Vector(p["x"], p["y"], p["z"]),
        unreal.Rotator(0.0, 0.0, p["yaw"]))
    a.set_actor_scale3d(unreal.Vector(p["scale"], p["scale"], p["scale"]))
    a.set_actor_label(p["label"])
    a.tags = [unreal.Name("lethe_bfs")]
    actors.append(a); spawned += 1

# attach hierarchy
attached = 0
for p, a in zip(P, actors):
    if a is None or p["parent_id"] is None: continue
    par = actors[p["parent_id"]]
    if par:
        a.attach_to_actor(par, "",
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD, False)
        attached += 1

print("LETHE_JSON::" + json.dumps({
    "deleted": deleted, "spawned": spawned,
    "attached": attached, "missing": sorted(missing)
}))
'''.replace("%P%", json.dumps(payload))

print("\nSending to UE...")
out = _run_in_ue(UE_SCRIPT)
for line in out.splitlines():
    i = line.find("LETHE_JSON::")
    if i >= 0:
        r = json.loads(line[i+len("LETHE_JSON::"):])
        print(f"  deleted={r['deleted']} spawned={r['spawned']} "
              f"attached={r['attached']} missing={r['missing']}")
        break
else:
    print("Unexpected UE output:\n", out[:800])
