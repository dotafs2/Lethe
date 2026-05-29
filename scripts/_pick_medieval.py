"""Score the 436 PolyHaven models for medieval-town / map relevance.

Reads _models_dump.json, prints ranked candidates grouped by role.
Pure local — no UE, no network.
"""
import json
import re
from pathlib import Path
from collections import defaultdict

rows = json.loads((Path(__file__).resolve().parent / "_models_dump.json").read_text(encoding="utf-8"))

# Role buckets with their matching keywords (checked against slug+name+tags+cats)
ROLES = {
    "terrain_nature": [
        "rock", "stone", "boulder", "cliff", "pebble", "tree", "log", "stump",
        "branch", "trunk", "bark", "bush", "shrub", "fern", "grass", "moss",
        "ivy", "reed", "mushroom", "plant", "flower", "leaf", "leaves", "root",
        "dead tree", "pine", "fir", "oak", "willow", "lavender", "cactus",
    ],
    "structure": [
        "ruin", "wall", "arch", "pillar", "column", "statue", "bridge", "gate",
        "fence", "post", "palisade", "stair", "building", "house", "hut",
        "tower", "well", "fountain", "trough", "brick", "cobble",
    ],
    "container_prop": [
        "barrel", "crate", "box", "basket", "sack", "pottery", "vase", "jug",
        "amphora", "clay", "ceramic", "urn", "pot ", "cart", "wagon", "wheel",
        "bucket", "bottle", "tankard", "mug", "cup", "plate", "bowl", "dish",
        "chest", "ladder", "rope", "chain", "anvil", "hammer", "axe", "sack",
        "hay", "straw", "grain", "lantern", "torch", "candle", "brazier",
        "jar", "flask", "keg", "cask", "pitcher", "cauldron",
    ],
    "furniture_wood": [
        "table", "chair", "bench", "stool", "cabinet", "shelf", "wood",
        "wooden", "plank", "timber", "stand", "rack", "drawer",
    ],
    "food": [
        "bread", "fruit", "apple", "vegetable", "cheese", "meat", "fish",
        "egg", "loaf", "pumpkin", "corn",
    ],
}

# Hard excludes — clearly modern / electronic / industrial
BLOCK = [
    "electronic", "computer", "laptop", "phone", "tv", "monitor", "screen",
    "plastic", "neon", "appliance", "fridge", "microwave", "washer", "dryer",
    "office", "printer", "camera", "speaker", "headphone", "console", "gaming",
    "extinguisher", "valve", "gauge", "meter", "circuit", "battery", "cable",
    "socket", "switch", "led", "lcd", "usb", "router", "modem", "fan ",
    "car", "tire", "traffic", "gasoline", "fuel", "engine", "motor", "machine",
    "forklift", "pallet jack", "dumpster", "trash", "recycl", "soda", "can ",
    "cardboard", "scaffold", "concrete", "rebar", "pipe", "duct", "vent",
    "helmet", "hardhat", "cone", "barrier", "sign", "shipping container",
]

def text_of(r):
    return " ".join([
        r["slug"].replace("_", " ").lower(),
        r["name"].lower(),
        " ".join(c.lower() for c in r.get("categories", [])),
        " ".join(t.lower() for t in r.get("tags", [])),
    ])

graded = defaultdict(list)
seen = set()
for r in rows:
    t = text_of(r)
    if any(b in t for b in BLOCK):
        continue
    for role, kws in ROLES.items():
        score = sum(1 for kw in kws if kw in t)
        if score > 0 and r["slug"] not in seen:
            graded[role].append((score, r["slug"], r["name"], r.get("categories", [])))
            seen.add(r["slug"])
            break  # first matching role wins (priority order)

print("=" * 70)
for role in ROLES:
    items = sorted(graded[role], key=lambda x: -x[0])
    print(f"\n### {role}  ({len(items)})")
    for score, slug, name, cats in items:
        print(f"  [{score}] {slug:<28s} {name:<24s} {cats}")

total = sum(len(v) for v in graded.values())
print(f"\n{'='*70}\nTOTAL CANDIDATES: {total}")
