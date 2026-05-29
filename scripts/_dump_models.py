"""Dump the full PolyHaven model library to JSON so we can pick map assets.

Pure HTTP — does not touch UE.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lethe.server import _polyhaven_assets

assets = _polyhaven_assets("models")
rows = []
for slug, meta in assets.items():
    rows.append({
        "slug": slug,
        "name": meta.get("name") or slug,
        "categories": meta.get("categories", []),
        "tags": meta.get("tags", []),
    })

out = Path(__file__).resolve().parent / "_models_dump.json"
out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"total models: {len(rows)}")
print(f"written: {out}")

# also print a compact category histogram
from collections import Counter
cat_counter = Counter()
for r in rows:
    for c in r["categories"]:
        cat_counter[c] += 1
print("\ntop categories:")
for c, n in cat_counter.most_common(40):
    print(f"  {n:3d}  {c}")
