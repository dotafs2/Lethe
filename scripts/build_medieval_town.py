"""Build a small medieval village clearing in the open UE editor session.

Layout (matches the tree paradigm in plan.md):

    World
    ├── FirePit                    ← town anchor (stone_fire_pit)
    │     ├── Bench_E / Bench_W    (painted_wooden_bench, sit around the fire)
    │     ├── Stump_N / Stump_S    (tree_stump_*, extra seats)
    │     └── Barrel_NE / Barrel_NW (barrel_03, trade/storage near the fire)
    ├── Lamp_NE / Lamp_SW          (street_lamp_01, ambient lighting at edges)
    ├── Pine_NE / Fir_NW / ...     (pine_tree_01 / fir_tree_01, outskirts)
    └── Rock_E / Rock_W / Rock_N   (rock_07 / rock_09, scattered)

Run with the UE editor open AND ws_server stopped (avoid concurrent UE calls).
After this finishes, restart ws_server and the 3D tree viz will show the
hierarchy via the AttachToActor relationships.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lethe.server import _run_in_ue, polyhaven_spawn_model  # noqa: E402


# -------------------------------------------------------------------- helpers

def ue(code: str) -> str:
    out = _run_in_ue(code)
    print(out)
    return out


def clear_scene() -> None:
    print("\n=== Clearing scene ===")
    ue(
        "import unreal\n"
        "sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "n = 0\n"
        "for a in list(sub.get_all_level_actors()):\n"
        "    if isinstance(a, unreal.StaticMeshActor):\n"
        "        sub.destroy_actor(a); n += 1\n"
        "print(f'deleted {n}')\n"
    )


def spawn(slug: str, x: float, y: float, z: float, yaw: float = 0.0,
          scale: float = 1.0, label: str = "", tag: str = "lethe_town") -> str | None:
    """Spawn a PolyHaven asset; return the UE actor name or None on failure."""
    print(f"\n→ spawn {slug:<28s} @ ({x:>6.0f},{y:>6.0f},{z:>4.0f}) yaw={yaw:>4.0f} scale={scale}")
    raw = polyhaven_spawn_model(slug=slug, x=x, y=y, z=z, yaw=yaw,
                                scale=scale, resolution="2k", tag=tag)
    try:
        data = json.loads(raw)
    except Exception:
        print("  ! parse failed:", raw[:300])
        return None
    if not data.get("ok"):
        print("  ! spawn failed:", data.get("error", raw[:200]))
        return None

    actor_name = data["actor"]
    print(f"  ✓ actor: {actor_name}")
    if label:
        ue(
            "import unreal\n"
            "sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
            f"a = next((x for x in sub.get_all_level_actors() if x.get_name() == {actor_name!r}), None)\n"
            f"a.set_actor_label({label!r}) if a else None\n"
        )
    return actor_name


def attach(child_name: str, parent_name: str) -> None:
    ue(
        "import unreal\n"
        "sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "acts = sub.get_all_level_actors()\n"
        f"child = next((a for a in acts if a.get_name() == {child_name!r}), None)\n"
        f"parent = next((a for a in acts if a.get_name() == {parent_name!r}), None)\n"
        "if child and parent:\n"
        "    child.attach_to_actor(parent, '', unreal.AttachmentRule.KEEP_WORLD,\n"
        "                          unreal.AttachmentRule.KEEP_WORLD,\n"
        "                          unreal.AttachmentRule.KEEP_WORLD, False)\n"
        "    print('attached', child.get_name(), '->', parent.get_name())\n"
        "else:\n"
        f"    print('attach miss: child={{}} parent={{}}'.format(child is not None, parent is not None))\n"
    )


# -------------------------------------------------------------------- recipe
#
#   Coordinates are in centimeters (UE default).
#   1 m = 100 units. The fire pit sits at the origin; everything else radiates.
#
RECIPE: list[dict] = [
    # ─── anchor ───
    dict(slug="stone_fire_pit", x=0, y=0, z=0, yaw=0, scale=1.0,
         label="FirePit", parent=None),

    # ─── inner ring around the fire (radius ~300 cm) ───
    dict(slug="painted_wooden_bench", x=300, y=0, z=0, yaw=90, scale=1.0,
         label="Bench_E", parent="FirePit"),
    dict(slug="painted_wooden_bench", x=-300, y=0, z=0, yaw=-90, scale=1.0,
         label="Bench_W", parent="FirePit"),
    dict(slug="tree_stump_01", x=0, y=300, z=0, yaw=0, scale=1.0,
         label="Stump_N", parent="FirePit"),
    dict(slug="tree_stump_02", x=0, y=-300, z=0, yaw=180, scale=1.0,
         label="Stump_S", parent="FirePit"),
    dict(slug="barrel_03", x=220, y=220, z=0, yaw=45, scale=1.0,
         label="Barrel_NE", parent="FirePit"),
    dict(slug="barrel_03", x=-220, y=220, z=0, yaw=-45, scale=1.0,
         label="Barrel_NW", parent="FirePit"),

    # ─── lamps at edges (radius ~800 cm) ───
    dict(slug="street_lamp_01", x=800, y=500, z=0, yaw=-135, scale=1.0,
         label="Lamp_NE", parent=None),
    dict(slug="street_lamp_01", x=-800, y=-500, z=0, yaw=45, scale=1.0,
         label="Lamp_SW", parent=None),

    # ─── outskirts: trees (radius ~1500 cm) ───
    dict(slug="pine_tree_01", x=1500, y=1000, z=0, yaw=15, scale=1.0,
         label="Pine_NE", parent=None),
    dict(slug="fir_tree_01", x=-1500, y=1000, z=0, yaw=70, scale=1.0,
         label="Fir_NW", parent=None),
    dict(slug="pine_tree_01", x=1500, y=-1000, z=0, yaw=200, scale=1.0,
         label="Pine_SE", parent=None),
    dict(slug="fir_tree_01", x=-1500, y=-1000, z=0, yaw=-110, scale=1.0,
         label="Fir_SW", parent=None),

    # ─── scattered rocks ───
    dict(slug="rock_07", x=900, y=0, z=0, yaw=20, scale=1.0,
         label="Rock_E", parent=None),
    dict(slug="rock_09", x=-900, y=0, z=0, yaw=110, scale=1.0,
         label="Rock_W", parent=None),
    dict(slug="rock_07", x=0, y=1100, z=0, yaw=70, scale=1.0,
         label="Rock_N", parent=None),
]


# -------------------------------------------------------------------- main

def main() -> None:
    clear_scene()

    label_to_actor: dict[str, str] = {}

    # Pass 1: spawn everything
    print("\n=== Spawning recipe ===")
    for entry in RECIPE:
        actor = spawn(
            slug=entry["slug"], x=entry["x"], y=entry["y"], z=entry["z"],
            yaw=entry["yaw"], scale=entry["scale"], label=entry["label"],
        )
        if actor:
            label_to_actor[entry["label"]] = actor

    # Pass 2: attach children to parents
    print("\n=== Attaching hierarchy ===")
    for entry in RECIPE:
        if not entry["parent"]:
            continue
        child = label_to_actor.get(entry["label"])
        parent = label_to_actor.get(entry["parent"])
        if not (child and parent):
            print(f"  skip {entry['label']} (missing actor)")
            continue
        print(f"  {entry['label']} → {entry['parent']}")
        attach(child, parent)

    print("\n=== Done ===")
    print(f"Spawned {len(label_to_actor)} actors, "
          f"{sum(1 for e in RECIPE if e['parent'])} attached")


if __name__ == "__main__":
    main()
