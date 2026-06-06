"""批量给文件夹里的所有模型刷 LOD 层级(L0/L1/L2…)。

做法:载入每个模型 → 量实测 bbox → 画三视图(俯/前/侧正交轮廓)→
连同「各层级标准尺寸」参考表一起喂给 VLM,让它对照判断,返回一个层级整数。

输出只有 {模型名: 层级},别的不写。

    python tools/tag_levels.py <models_dir> [-o model_levels.json]
                               [--dry-run] [--debug-views <dir>]

依赖:pip install trimesh numpy pillow anthropic   (需 ANTHROPIC_API_KEY)
载入支持 .glb/.gltf/.obj/.ply/.stl(.fbx/.uasset 拿不到几何,会跳过)。
尺寸单位假定为【米】(glTF 规范即米);别的单位请自行换算 LEVEL_REFERENCE。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw
import anthropic

MESH_EXTS = {".glb", ".gltf", ".obj", ".ply", ".stl"}

# ── 各层级标准尺寸:给 VLM 对照用,随便改 ─────────────────────────────────
LEVEL_REFERENCE = """\
层级(固定 4 级,按最长边的大致尺寸,米):
  L0 宏观区  ~500 m   整片地貌:小镇 / 农田 / 森林
  L1 功能区  ~50 m    村里的子区:市集 / 住宅 / 铁匠铺
  L2 物体    ~5 m     房子 / 树 / 井 / 摊位 / 栅栏
  L3 小件    ~0.5 m   家具 / 工具 / 盆栽 / 摆件"""

RUBRIC = (
    "看三视图和实测尺寸,对照下面参考给它一个层级。只回答 0/1/2/3 中的一个数字。\n\n"
    + LEVEL_REFERENCE
)

VIEWS = [("TOP 俯视", 0, 1), ("FRONT 前视", 0, 2), ("SIDE 侧视", 1, 2)]


def load_mesh(path: Path) -> trimesh.Trimesh:
    m = trimesh.load(path, force="mesh")
    if not isinstance(m, trimesh.Trimesh) or len(m.vertices) == 0:
        raise ValueError("空网格或无法解析")
    return m


def render_three_views(mesh: trimesh.Trimesh, px: int = 300) -> Image.Image:
    """把三个正交投影的填充轮廓横向拼成一张图。"""
    V, F = mesh.vertices, mesh.faces
    combo = Image.new("RGB", (px * 3, px), "white")
    for vi, (label, a, b) in enumerate(VIEWS):
        pts = V[:, [a, b]]
        mn, mx = pts.min(0), pts.max(0)
        span = float((mx - mn).max()) or 1.0
        sc = (px - 20) / span
        xy = (pts - mn) * sc + 10
        img = Image.new("RGB", (px, px), "white")
        d = ImageDraw.Draw(img)
        for tri in F:
            poly = [(float(xy[i, 0]), float(px - xy[i, 1])) for i in tri]  # 翻 y,让上为上
            d.polygon(poly, fill=(70, 70, 70))
        d.text((6, 6), label, fill=(200, 0, 0))
        combo.paste(img, (vi * px, 0))
    return combo


def img_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


_client = anthropic.Anthropic()


def classify(views_b64: str, size: np.ndarray, name: str) -> int:
    msg = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8,
        system=RUBRIC,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": views_b64}},
            {"type": "text", "text": (
                f"文件名:{name}\n"
                f"实测尺寸(米) 长x宽x高: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f}\n"
                f"层级:")},
        ]}],
    )
    txt = msg.content[0].text.strip()
    for ch in txt:
        if ch.isdigit():
            return int(ch)
    raise ValueError(f"没从 {txt!r} 解析出层级({name})")


def main() -> None:
    ap = argparse.ArgumentParser(description="批量刷模型层级(三视图+尺寸)")
    ap.add_argument("models_dir", help="放模型的文件夹")
    ap.add_argument("-o", "--out", default="model_levels.json")
    ap.add_argument("--dry-run", action="store_true", help="只载入量尺寸+渲图,不调 VLM")
    ap.add_argument("--debug-views", metavar="DIR", help="把三视图存到这个目录便于检查")
    args = ap.parse_args()

    root = Path(args.models_dir)
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in MESH_EXTS)
    if not files:
        print(f"{root} 下没有可解析模型({'/'.join(sorted(MESH_EXTS))})")
        return

    dbg = Path(args.debug_views) if args.debug_views else None
    if dbg:
        dbg.mkdir(parents=True, exist_ok=True)

    levels: dict[str, int] = {}
    for i, p in enumerate(files, 1):
        name = p.stem
        try:
            mesh = load_mesh(p)
        except Exception as e:
            print(f"[{i}/{len(files)}] {name} -> 跳过({e})")
            continue
        size = mesh.extents  # [x,y,z]
        views = render_three_views(mesh)
        if dbg:
            views.save(dbg / f"{name}.png")
        if args.dry_run:
            print(f"[{i}/{len(files)}] {name}  尺寸 {size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f} m")
            continue
        lv = classify(img_b64(views), size, name)
        levels[name] = lv
        print(f"[{i}/{len(files)}] {name}  {size[0]:.1f}x{size[1]:.1f}x{size[2]:.1f}m -> L{lv}")

    if not args.dry_run:
        Path(args.out).write_text(
            json.dumps(levels, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"已写 {len(levels)} 条 -> {args.out}")


if __name__ == "__main__":
    main()
