"""在运行中的 UE 里遍历所有 StaticMesh,按包围盒尺寸刷 L0/1/2/3,写成 JSON。

走保留的通信协议(remote_execution,纯标准库,不碰 PIL/mcp)。
.uasset 是 UE 二进制,只能在编辑器里读,所以分类在 UE 内完成(按尺寸,不调 VLM)。

    python tools/tag_levels_ue.py [-o ue_model_levels.json]

前置:UE 编辑器开着该项目,PythonScriptPlugin + Remote Execution 已启用。
输出 {资产全路径: 层级},不改动任何 .uasset。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lethe import remote_execution as remote  # noqa: E402

# 在 UE 里跑的代码:列 StaticMesh -> 包围盒 -> 按最长边(米)分层
#  -> 写 metadata tag `Lethe.L` 到资产(save)+ 加进 Lethe_L0..L3 集合(可见分组)
UE_CODE = r'''
import unreal, json

# 尺寸阈值(最长边,米):>=50 -> L0, >=10 -> L1, >=1.5 -> L2, 其余 L3
def level_of(max_m):
    if max_m >= 50: return 0
    if max_m >= 10: return 1
    if max_m >= 1.5: return 2
    return 3

ar = unreal.AssetRegistryHelpers.get_asset_registry()
assets = ar.get_assets_by_path("/Game", recursive=True)

eal = unreal.EditorAssetLibrary
cs = unreal.get_editor_subsystem(unreal.CollectionManagerSubsystem)
container = cs.get_base_game_collection_container()
colls = {lv: cs.create_or_empty_collection(
            container, "Lethe_L%d" % lv, unreal.CollectionShareType.LOCAL)
         for lv in (0, 1, 2, 3)}

levels = {}
by_level = {0: [], 1: [], 2: [], 3: []}
n = 0
for a in assets:
    try:
        if str(a.asset_class_path.asset_name) != "StaticMesh":
            continue
    except Exception:
        continue
    obj = a.get_asset()
    if obj is None:
        continue
    try:
        ext = obj.get_bounds().box_extent          # 半尺寸 cm
    except Exception:
        continue
    lv = level_of(2.0 * max(ext.x, ext.y, ext.z) / 100.0)
    pkg = str(a.package_name)
    eal.set_metadata_tag(obj, "Lethe.L", str(lv))  # 刷在资产上
    eal.save_asset(pkg, only_if_is_dirty=True)
    by_level[lv].append(unreal.SoftObjectPath("%s.%s" % (pkg, str(a.asset_name))))
    levels[pkg] = lv
    n += 1

added = {}
for lv, paths in by_level.items():
    if paths and colls.get(lv) is not None:
        cs.add_assets_to_collection(colls[lv], paths)  # 加进可见集合
    added[lv] = len(paths)

print("LETHE_JSON::" + json.dumps({"count": n, "levels": levels, "added": added}))
'''


def main() -> None:
    ap = argparse.ArgumentParser(description="UE 内批量刷模型层级")
    ap.add_argument("-o", "--out", default="ue_model_levels.json")
    args = ap.parse_args()

    rx = remote.RemoteExecution(remote.RemoteExecutionConfig())
    rx.start()
    try:
        deadline = time.time() + 6
        while not rx.remote_nodes and time.time() < deadline:
            time.sleep(0.1)
        if not rx.remote_nodes:
            print("没发现 UE 节点。请确认编辑器开着、PythonScriptPlugin + Remote Execution 已启用。")
            sys.exit(1)
        rx.open_command_connection(rx.remote_nodes[0]["node_id"])
        res = rx.run_command(UE_CODE, exec_mode=remote.MODE_EXEC_FILE)
    finally:
        rx.stop()

    text = "\n".join(
        (it.get("output", "") if isinstance(it, dict) else str(it))
        for it in (res.get("output") or [])
    )
    payload = None
    for line in text.splitlines():
        i = line.find("LETHE_JSON::")
        if i >= 0:
            payload = json.loads(line[i + len("LETHE_JSON::"):])
            break
    if payload is None:
        print("没拿到 UE 返回的 JSON,原始输出:\n" + text[:1000])
        sys.exit(1)

    Path(args.out).write_text(
        json.dumps(payload["levels"], indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {}
    for lv in payload["levels"].values():
        counts[lv] = counts.get(lv, 0) + 1
    print(f"共 {payload['count']} 个 StaticMesh -> {args.out}")
    print("各层数量:", {f"L{k}": counts.get(k, 0) for k in (0, 1, 2, 3)})


if __name__ == "__main__":
    main()
