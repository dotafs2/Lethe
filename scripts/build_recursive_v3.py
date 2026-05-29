"""Layer 0+2 of the plan.md algorithm — pure geometry, no LLM/VLM yet.

  Layer 0: lay a ground plane (the root all objects sit on).
  Layer 2: per hand-written region ("flower pot"), CRAWLER recursive growth:
             grow(anchor) → breadth-fill props around it → recurse into
             tables (decor on top) and trees (ground cover beneath).
           Placement uses: incremental rejection sampling, spatial-hash
           collision on footprint circles, and ground-snap via bounds_min.z.

All geometry is computed in Python (fast, free); UE just spawns the result
in ONE call. Run with ws_server stopped.

    python scripts/build_recursive_v3.py [target_count]
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from lethe.server import _run_in_ue  # noqa: E402

random.seed(42)
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 500

# ---------------------------------------------------------------------------
# Asset library: bounds → footprint radius + ground-snap z, grouped by role
# ---------------------------------------------------------------------------
LIB = {r["slug"]: r for r in json.loads(
    (ROOT / "scripts" / "_asset_library.json").read_text(encoding="utf-8")) if r.get("ok")}

ROLE = {
    # anchors — region cores, can grow a ring of props, are "major"
    "stone_fire_pit": "anchor", "modular_fort_01": "anchor",
    "large_castle_door": "anchor", "large_iron_gate": "anchor",
    "spinning_wheel_01": "anchor",
    # trees — can grow ground cover beneath
    "pine_tree_01": "tree", "fir_tree_01": "tree", "island_tree_01": "tree",
    "tree_small_02": "tree", "dead_tree_trunk": "tree", "dead_tree_trunk_02": "tree",
    # props — ring around anchors
    "wooden_barrels_01": "prop", "wine_barrel_01": "prop", "wooden_crate_01": "prop",
    "wooden_crate_02": "prop", "wooden_bucket_01": "prop", "wooden_bucket_02": "prop",
    "treasure_chest": "prop", "cannon_01": "prop", "painted_wooden_bench": "prop",
    "WoodenChair_01": "prop", "painted_wooden_chair_02": "prop",
    "folding_wooden_stool": "prop", "wooden_stool_01": "prop",
    # tables — surfaces that host decor on top (depth recursion)
    "WoodenTable_01": "table", "round_wooden_table_01": "table",
    # decor — leaves, on tables or beside props
    "ceramic_vase_01": "decor", "ceramic_vase_02": "decor", "jug_01": "decor",
    "food_apple_01": "decor", "wicker_basket_01": "decor", "wicker_basket_02": "decor",
    "kite_shield": "decor", "wooden_axe": "decor", "wooden_lantern_01": "decor",
    "Lantern_01": "decor", "lantern_chandelier_01": "decor",
    # ground cover — leaves, scattered low to the ground
    "shrub_01": "ground", "shrub_02": "ground", "fern_02": "ground", "moss_01": "ground",
    "grass_medium_01": "ground", "rock_07": "ground", "rock_09": "ground",
    "stone_01": "ground", "boulder_01": "ground", "tree_stump_01": "ground",
    "tree_stump_02": "ground", "dry_branches_medium_01": "ground",
}
BY_ROLE: dict[str, list[str]] = {}
for s, r in ROLE.items():
    if s in LIB:
        BY_ROLE.setdefault(r, []).append(s)

FOOTPRINT_FACTOR = {"anchor": 0.55, "tree": 0.22, "prop": 0.5,
                    "table": 0.5, "decor": 0.45, "ground": 0.38}
# small cm-scale items get scaled up so they read on a 100m+ map
SCALE_OVERRIDE = {"rock_09": 3.0, "stone_01": 3.0, "moss_01": 3.5,
                  "grass_medium_01": 1.8, "rock_07": 1.8, "food_apple_01": 1.5}


def scale_of(slug: str) -> float:
    return SCALE_OVERRIDE.get(slug, 1.0)


def dims(slug: str):
    b = LIB[slug]
    mn, mx = b["bounds_min"], b["bounds_max"]
    return (mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2], mn[2])


def footprint_r(slug: str, sc: float) -> float:
    dx, dy, _, _ = dims(slug)
    return 0.5 * math.hypot(dx, dy) * FOOTPRINT_FACTOR[ROLE[slug]] * sc


def ground_z(slug: str, sc: float) -> float:
    return -dims(slug)[3] * sc           # lift so the model's base sits on z=0


def top_z(slug: str, sc: float) -> float:
    _, _, dz, _ = dims(slug)
    return dz * sc                        # surface height (for decor on tables)


# ---------------------------------------------------------------------------
# Spatial hash (footprint-circle collision, O(1) amortized)
# ---------------------------------------------------------------------------
class Grid:
    def __init__(self, cell=450):
        self.cell = cell
        self.d: dict[tuple[int, int], list] = {}

    def _k(self, x, y):
        return (int(x // self.cell), int(y // self.cell))

    def free(self, x, y, r) -> bool:
        kx, ky = self._k(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (ox, oy, orr) in self.d.get((kx+dx, ky+dy), ()):  # noqa
                    if (x-ox)**2 + (y-oy)**2 < (r+orr)**2:
                        return False
        return True

    def insert(self, x, y, r):
        self.d.setdefault(self._k(x, y), []).append((x, y, r))


# ---------------------------------------------------------------------------
# Placement accumulator
# ---------------------------------------------------------------------------
placements: list[dict] = []
grid = Grid()


def place(slug, x, y, parent, yaw=None, z=None, collide=True) -> int | None:
    sc = scale_of(slug)
    r = footprint_r(slug, sc)
    if collide and not grid.free(x, y, r):
        return None
    if collide:
        grid.insert(x, y, r)
    idx = len(placements)
    placements.append(dict(
        slug=slug, x=round(x, 1), y=round(y, 1),
        z=round(z if z is not None else ground_z(slug, sc), 1),
        yaw=round(yaw if yaw is not None else random.uniform(0, 360), 1),
        scale=sc, parent=parent,
    ))
    return idx


def stop() -> bool:
    return len(placements) >= TARGET


# ---------------------------------------------------------------------------
# Recursive growth
# ---------------------------------------------------------------------------
def grow_table(parent_idx, x, y, table_slug):
    """Depth recursion: a few decor items on the table top."""
    th = top_z(table_slug, scale_of(table_slug))
    for _ in range(random.randint(2, 4)):
        if stop():
            return
        slug = random.choice(BY_ROLE["decor"])
        place(slug, x + random.uniform(-35, 35), y + random.uniform(-35, 35),
              parent_idx, z=th, collide=False)


def grow_town(reg):
    cx, cy, R = reg["cx"], reg["cy"], reg["radius"]
    core = random.choice(reg["anchors"])
    ci = place(core, cx, cy, None)
    if ci is None:
        return
    prop_pool = BY_ROLE["prop"] + BY_ROLE["table"] * 2
    for _ in range(reg["props_n"]):
        if stop():
            return
        for _ in range(6):                       # K rejection samples
            ang = random.uniform(0, 2*math.pi)
            rad = random.uniform(260, R)
            x, y = cx + math.cos(ang)*rad, cy + math.sin(ang)*rad
            slug = random.choice(prop_pool)
            yaw = math.degrees(math.atan2(cy - y, cx - x))   # face the core
            pi = place(slug, x, y, ci, yaw=yaw)
            if pi is not None:
                if ROLE[slug] == "table":
                    grow_table(pi, x, y, slug)
                break


def grow_forest(reg):
    cx, cy, R = reg["cx"], reg["cy"], reg["radius"]
    for _ in range(reg["trees_n"]):
        if stop():
            return
        for _ in range(6):
            ang = random.uniform(0, 2*math.pi)
            rad = random.uniform(0, R) ** 0.9 * (R ** 0.1)   # mild outward spread
            x, y = cx + math.cos(ang)*rad, cy + math.sin(ang)*rad
            tslug = random.choice(BY_ROLE["tree"])
            ti = place(tslug, x, y, None)
            if ti is not None:
                for _ in range(random.randint(1, 3)):       # ground cover beneath
                    if stop():
                        return
                    gslug = random.choice(BY_ROLE["ground"])
                    place(gslug, x + random.uniform(-350, 350),
                          y + random.uniform(-350, 350), ti)
                break


def grow_scatter(reg):
    cx, cy, R = reg["cx"], reg["cy"], reg["radius"]
    for _ in range(reg["n"]):
        if stop():
            return
        for _ in range(4):
            ang = random.uniform(0, 2*math.pi)
            rad = random.uniform(0, R)
            x, y = cx + math.cos(ang)*rad, cy + math.sin(ang)*rad
            slug = random.choice(BY_ROLE["ground"])
            if place(slug, x, y, None) is not None:
                break


# Hand-written region plan (Layer 1 stub): a central town + districts + forests
REGIONS = [
    dict(kind="town",   cx=0,     cy=0,     radius=2200, anchors=["stone_fire_pit"],     props_n=48),
    dict(kind="town",   cx=4800,  cy=2800,  radius=1600, anchors=["modular_fort_01"],    props_n=30),
    dict(kind="town",   cx=4200,  cy=-3200, radius=1500, anchors=["large_castle_door", "spinning_wheel_01"], props_n=28),
    dict(kind="forest", cx=-5800, cy=1200,  radius=4200, trees_n=38),
    dict(kind="forest", cx=-1200, cy=-6800, radius=3600, trees_n=30),
    dict(kind="forest", cx=6500,  cy=4800,  radius=2600, trees_n=18),
    dict(kind="scatter", cx=0,    cy=0,     radius=9500, n=150),
]


def main():
    for reg in REGIONS:
        if stop():
            break
        {"town": grow_town, "forest": grow_forest, "scatter": grow_scatter}[reg["kind"]](reg)

    n_attached = sum(1 for p in placements if p["parent"] is not None)
    print(f"computed {len(placements)} placements ({n_attached} attached) — sending to UE...")

    payload = json.dumps(placements)
    script = UE_TEMPLATE.replace("%PLACEMENTS%", payload)
    out = _run_in_ue(script)
    for line in out.splitlines():
        i = line.find("LETHE_JSON::")
        if i >= 0:
            print(json.loads(line[i+len("LETHE_JSON::"):]))
            return
    print("unexpected UE output:\n", out[:800])


UE_TEMPLATE = r'''
import unreal, json

P = json.loads(r"""%PLACEMENTS%""")
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
reg = unreal.AssetRegistryHelpers.get_asset_registry()

# clear existing static-mesh actors
deleted = 0
for a in list(eas.get_all_level_actors()):
    if isinstance(a, unreal.StaticMeshActor):
        eas.destroy_actor(a); deleted += 1

# Layer 0: ground plane
ground = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
ga = eas.spawn_actor_from_object(ground, unreal.Vector(0, 0, 0))
ga.set_actor_scale3d(unreal.Vector(280, 280, 1))   # ~280 m
ga.set_actor_label("Ground")

mesh_cache = {}
def find_mesh(slug):
    if slug in mesh_cache:
        return mesh_cache[slug]
    m = None
    for ad in reg.get_assets_by_path("/Game/Lethe/Models/" + slug, recursive=True):
        o = ad.get_asset()
        if isinstance(o, unreal.StaticMesh):
            m = o; break
    mesh_cache[slug] = m
    return m

actors = []
spawned, missing = 0, set()
for p in P:
    m = find_mesh(p["slug"])
    if m is None:
        missing.add(p["slug"]); actors.append(None); continue
    loc = unreal.Vector(p["x"], p["y"], p["z"])
    rot = unreal.Rotator(0.0, 0.0, p["yaw"])
    a = eas.spawn_actor_from_object(m, loc, rot)
    a.set_actor_scale3d(unreal.Vector(p["scale"], p["scale"], p["scale"]))
    a.set_actor_label(p["slug"] + "_" + str(len(actors)))
    a.tags = [unreal.Name("lethe_v3")]
    actors.append(a); spawned += 1

attached = 0
for p, a in zip(P, actors):
    if a is None or p["parent"] is None:
        continue
    par = actors[p["parent"]]
    if par is not None:
        a.attach_to_actor(par, "", unreal.AttachmentRule.KEEP_WORLD,
            unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        attached += 1

print("LETHE_JSON::" + json.dumps({
    "deleted": deleted, "spawned": spawned,
    "attached": attached, "missing": sorted(missing),
}))
'''


if __name__ == "__main__":
    main()
