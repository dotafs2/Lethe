# Lethe Weight Tree — Auto-Layout Tool 设计计划

> 状态：设计阶段
> 上次更新：2026-05-26
> 配套 demo：`weight-tree-demo.html`（浏览器打开可交互查看核心放置思路）

---

## 一、目标

为 Lethe 自动地编工具设计一套**自动化世界生成**的数据结构和算法。每个物体在被放置时，根据已经摆好的少量参考物体计算自己的位置和朝向，AI 驱动决策，UE 兜底验证。

**核心限制**：
- 线性增量放置：物体一个一个加入
- 一旦放置永不再动（避免松弛求解 / 循环依赖）
- 已知 asset 库规模量级：**几百个物体**（这决定后续策略）

---

## 二、核心数据结构：Attachment Tree + Soft Refs

经过多轮讨论后收敛的结构：**每个物体严格挂在一个 Surface 上（attachment 硬边），跨边引用作为软引用（影响放置参数但不构成拓扑）**。

```
─── 硬边：每个物体唯一的 attachment 父 ─────
[Floor]                                    (root, world anchor)
  ├── [Desk]                               attaches_to: horizontal_up
  │     ├── [Lamp]                         attaches_to: horizontal_up (desk_top)
  │     └── [Water]                        attaches_to: horizontal_up
  ├── [Chair]                              attaches_to: horizontal_up
  └── [Sofa]
         └── [Pillow]

─── 软边：影响放置参数，不影响拓扑 ─────
[Chair]  ┄┄► [Desk]   (yaw: 朝向桌子)
[Water]  ┄┄► [Chair]  (u,v: 偏向使用者侧)
```

### 2.1 Surface 抽象（统一所有附着关系）

```python
class Surface:
    id: str                      # e.g. "desk_03.top"
    tag: str                     # e.g. "horizontal_up" | "vertical_wall" | "horizontal_down"
    local_plane: Plane           # origin + u_axis + v_axis + u_extent + v_extent
    accepts: list[str]           # 白名单：["decor", "light", "drink"]
    occupied: list[Rect]         # 已被占用的 2D 区域（避免下次采样挤同一处）
```

**重要：floor / wall / desk_top 都是 Surface，没有特殊类型**。
- Floor 提供 1 个 `horizontal_up`，accepts: `[furniture, plant]`
- Wall 提供 1 个 `vertical_wall`，accepts: `[window, painting]`
- Desk 提供 1 个 `horizontal_up`（桌面），accepts: `[decor, light]`
- Chair 自身不提供 surface（不能再叠东西）

### 2.2 SoftRef 结构

```python
class SoftRef:
    target_id: str
    channel: Literal["position", "facing", "presence"]
    weight: float = 1.0
```

软引用作用域只剩**步骤②的 (u,v) 偏移和 yaw 决策**，不再影响 attachment 拓扑。

---

## 三、Placement Metadata Schema（核心契约）

每个 asset 配一份 metadata，定义它怎么被放置。这是 LLM、放置算法、人工编辑三方共享的接口。

```python
from pydantic import BaseModel
from typing import Literal

class SurfaceDef(BaseModel):
    id: str
    tag: str
    local_plane: dict   # origin + u/v axes + extents
    accepts: list[str]

class PlacementMetadata(BaseModel):
    # ─── 朝向 ───
    align_up: Literal["world_up", "world_down", "surface_normal", "none"] = "world_up"
    up_priority: Literal["world", "surface"] = "world"

    # ─── 附着 ───
    attaches_to: list[str]               # 接受的 surface tag 列表
    attach_pivot: Literal["bottom_center", "top_center", "back_center", "custom"] = "bottom_center"
    attach_offset_m: float = 0.0         # 沿 align_up 偏移；气球 > 0、吊灯 < 0

    # ─── 我提供的表面 ───
    surfaces: list[SurfaceDef] = []

    # ─── Yaw 决策策略 ───
    yaw_strategy: Literal[
        "face_nearest_seat",     # 桌子朝椅子
        "face_nearest_anchor",   # 椅子朝桌子
        "back_to_wall",          # 沙发背靠墙
        "match_surface_u",
        "random",
        "fixed",
    ] = "random"

    # ─── Placement bounds（碰撞用，比 visual mesh 略大）───
    placement_bounds_padding_m: float = 0.05
    use_space_extend: dict[str, float] = {}   # e.g. {"front": 0.7} 椅子前面腿部空间

    # ─── LLM 输出可信度 + 人工 review 状态 ───
    llm_confidence: float = 1.0
    llm_reasoning: str = ""
    human_reviewed: bool = False           # True 则不被 LLM 覆盖
```

### 关键设计点
- **`human_reviewed: True` 永远不被 LLM 覆盖**——保护人工修过的条目
- **`llm_confidence < 0.7` 自动进 review 队列**——让 LLM 自己承认不确定的
- **所有字段有 default**——schema 演进时旧 metadata 不破

---

## 四、放置算法

### 4.1 主流程

```python
def place_object(type: str, intent: dict) -> Placement | None:
    metadata = load_metadata(type)

    for attempt in range(MAX_ATTEMPTS):  # 默认 5
        # ① 选 Surface（语义层）
        surface = choose_surface(metadata.attaches_to, intent, world)

        # ② 选 (u, v)（几何层）
        uv = choose_uv(surface, intent.soft_refs, metadata)

        # ③ 计算 transform（朝向）
        xform = compute_transform(
            surface, uv,
            align_up=metadata.align_up,
            up_priority=metadata.up_priority,
            attach_offset=metadata.attach_offset_m,
            yaw=resolve_yaw(metadata.yaw_strategy, intent.soft_refs),
        )

        # ④ 临时 commit + 验证流水线
        actor = spawn_and_attach(type, xform, parent=surface.owner)

        if not overlap_check(actor):           # UE ComponentOverlapMulti
            actor.destroy(); continue

        if not photo_verify(actor, intent):    # VLM 拍照验证
            actor.destroy(); continue

        # ⑤ 更新 surface occupancy + 返回
        surface.occupied.append(actor.uv_rect)
        return Placement(actor, surface, uv, xform)

    return None  # 失败，调用方决定降级策略
```

### 4.2 验证流水线（顺序很重要：越便宜越早）

| 步骤 | 成本 | 作用 |
|---|---|---|
| ① UE overlap check (`ComponentOverlapMulti`) | μs 级，免费 | 几何穿插 |
| ② VLM 拍照验证 | 秒级，几分钱 | 语义错误（朝向、位置不合理） |

**90% 失败应该被 ① 挡住**。VLM 只处理"形状没撞但看起来不对"的情况。

### 4.3 拍照验证的工程细节
- **相机角度**：从新物体位置出发，沿 `-align_up` 后退 1.5m + 抬高 30°
- **分辨率**：512×512 或 768×768 即可，全分辨率浪费
- **缓存**：`(type, surface_id, uv_quantized_0.1m)` 为 key 哈希
- **VLM 输出必须含原因**："台灯朝墙壁" 这种反馈能指导下次重试调整 yaw
- **重试预算**：N=5，超过则降级（换 surface / 去软引用 / 放弃）
- **可能的优化**：一次 attach 10 个物体后只拍 1 张总图给 VLM 看（代价：失败时不知道哪个错）

---

## 五、UE 碰撞与重力策略

### 5.1 用 UE 自定义 Collision Channel 表达 overlap 规则

不要给每个物体手写"不能跟谁重叠"的列表。**用 channel + response matrix**：

```
Custom channels:
  PlacementSolid    ← 桌、椅、柜子、植物
  PlacementSurface  ← 桌面、墙面、地板
  PlacementDecor    ← 水杯、笔、书
  PlacementAttach   ← 窗、画、插座

关键 response（其余 Overlap）：
  Solid   vs Solid   = Block
  Solid   vs Decor   = Block
  Decor   vs Decor   = Overlap
  Attach  vs Attach  = Block
```

### 5.2 Placement Bounds ≠ Visual Mesh
每个 asset 单独配 `UBoxComponent("PlacementBounds")`，渲染时隐藏，placement 查询专用：
- 复杂 mesh 用简化 bounds 查询更快
- 包含**功能空间**而非纯几何（椅子前面 0.7m 留腿部空间）

### 5.3 "重力"的真实含义：朝向约束，不是物理

讨论中明确：你说的"重力"不是 physics simulation，而是 `align_up` 向量：
- 普通物体：`align_up = world_up`
- 吊灯：`align_up = world_down`（顶朝下 hang）
- 磁铁贴纸：`align_up = surface_normal`（跟着斜面走）
- 气球：`align_up = world_up` + `attach_offset_m = 2.5`（绳长偏移）

**up_priority** 决定 align_up 跟 surface_normal 冲突时谁赢（如斜屋顶上的画）：
- 默认 `world`（大部分室内物体）
- `surface`（贴附装饰：磁铁、贴纸）

---

## 六、LLM 集成策略（已敲定）

### 6.1 决策栈：越便宜越早，LLM 是最后一道

```
① Asset metadata 查表  ──► 99% 命中，O(1)，免费
② 类型启发式规则        ──► 元数据缺失时按 tag 兜底，O(1)
③ MCP 工具调用 LLM      ──► 长尾、明确歧义场景
④ 人工介入              ──► LLM 也犹豫时
```

### 6.2 选定方案：离线扫库一次，运行时不调 LLM

几百个 asset → 离线扫描成本极低：
- 500 物体 × ~500 in + 200 out tokens × Claude Sonnet = **总成本 ~$1.50**
- 一次跑完缓存，**永久免费**

```
asset_library/
  ├─ chair_dining_01/
  │   ├─ mesh.fbx
  │   ├─ preview.png        ← 渲染预览图，VLM 输入
  │   └─ placement.yaml     ← LLM 生成的 metadata（人可编辑）
  └─ ...
```

### 6.3 扫描脚本逻辑

```python
for asset_dir in asset_library:
    yaml_path = asset_dir / "placement.yaml"

    # human_reviewed 永不覆盖
    if yaml_path.exists():
        meta = PlacementMetadata.parse_file(yaml_path)
        if meta.human_reviewed:
            continue

    # 调 LLM（preview.png + mesh info）
    result = llm.judge_placement(preview, asset_info)
    meta = PlacementMetadata.model_validate(result)
    yaml_path.write_text(meta.model_dump_yaml())

    if meta.llm_confidence < 0.7:
        review_queue.append(asset_dir)
```

### 6.4 运行时的 MCP 工具仅用于这些场景
- ✅ **语义 surface 选择**：多个候选 surface 时让 LLM 判断（水杯放主桌还是茶几）
- ✅ **yaw 朝向意图**：椅子朝桌子还是朝电视
- ✅ **拍照验证后的语义反馈**（已有的 Lethe 机制）
- ❌ `up_priority` / `attach_offset` / `(u,v)` — 这些走元数据 + 几何，不该 per-call 调 LLM

---

## 七、Demo（已完成）

文件：`weight-tree-demo.html`（单文件，浏览器打开）

**实现的概念**：
- 范围球（白色 wireframe）= 探测范围
- 绿线 = 被选为参考；红线 = 范围内但被拒绝
- 黄色实线 = primary parent；青色虚线 = soft ref
- 右侧 DAG 面板 + 决策 log

**已演示的放置规则**：Desk / Chair / Lamp / Water（含交叉边） / Window（拒绝被挡墙）/ Plant

**Demo 还缺什么**（如果要继续可加）：
- (a) Surface 抽象的可视化（彩色 patch 显示已占用区）
- (b) `align_up` 向量可视化
- (c) Attach 后 AABB overlap 检查，失败画红 X 并重试
- (d) "等待 VLM 验证" 占位（demo 里没法真做）

---

## 八、设计讨论中**否决**的方案（避免回头踩坑）

| 方案 | 否决原因 |
|---|---|
| 马尔科夫链类比 | 误导。每个新物体从全集 P_t 挑 K 个 = 完整状态依赖，不是马尔科夫无记忆性 |
| 让 AI 当 selector 默认 dispatcher | 成本爆炸：每物体多次 LLM 调用 = 几十秒延迟 + 几块钱 |
| Per-call MCP 调 LLM 决定 up_priority | 99% 情况答案显然，不值得 |
| 程序化挖洞（boolean）做窗户 | 复杂度高、编辑器性能差。改用 surface attachment 抽象 |
| 用 visual mesh 的 complex collision 做 placement 查询 | 性能差，且不包含功能空间（椅子前的腿部空间） |
| 给每个物体写"不能跟谁重叠"的列表 | 维护爆炸，用 UE channel + response matrix 代替 |

---

## 九、Open Questions（回家继续想）

### 9.1 强相关的设计
- [ ] **Probe center 来自哪？** Demo 里是随机，真实系统里 AI 该有意图（"我要在窗户对面放沙发"）。这是 LLM 真正该决策的地方。
- [ ] **Yaw 决策的优先级链怎么定？** 如果 metadata 说 `face_nearest_seat` 但场景里没椅子？fallback chain 怎么走。
- [ ] **Surface 的 occupied 区域 padding 默认值多少？** 太小挤，太大稀疏。可能需要按 surface 类型分（桌面紧密、地面宽松）。
- [ ] **多 chain 之间的全局协调**：每对邻居都合理，整体可能挤一角。需要全局后验吗？还是相信 VLM 拍照能抓到？

### 9.2 工程实现
- [ ] **UE side：metadata 怎么注入到 actor？** 自定义 DataAsset？挂在 Blueprint subclass 上？
- [ ] **MCP server 加新工具的清单**：
  - `judge_placement_params`（离线扫描用）
  - `choose_surface_semantic`（运行时多候选时用）
  - `verify_placement_photo`（拍照验证，可能已存在）
- [ ] **预览图怎么批量生成？** UE commandlet 还是 Python 渲染？放哪个角度？
- [ ] **Review CLI 工具**：扫完后过 low-confidence 队列的命令行 UI

### 9.3 范围内但不急
- [ ] **Attachment 删除的级联**：删 desk 后 lamp 也删吗？(应该是的，硬边语义)
- [ ] **场景重生成时怎么"重放"**：要不要把放置历史存成 sequence 便于回放/调试
- [ ] **多人协作场景下的 metadata 冲突**：placement.yaml 进 git 后多人编辑同一个怎么办

---

## 十、下一步路线图建议

按依赖顺序：

1. **把 `PlacementMetadata` 写成正式的 pydantic 模型** 放进 `src/lethe/placement/`
2. **写 `scan_assets.py`** —— 选一小批（10 个）asset 跑一遍，验证 LLM 输出质量
3. **写 `review_cli.py`** —— 让低置信度的人工过一遍
4. **改 demo 成 metadata-driven** —— 把硬编码的 desk/chair 规则换成读 yaml
5. **UE 侧 DataAsset 接入** —— 让 placement.yaml 能在 UE 里被 actor 消费
6. **接 placement 算法到现有 MCP server** —— 暴露 `place_object(type, intent)` 工具
7. **VLM 验证回路** —— 接入已有的拍照机制，关闭决策环

每步独立可测，前 4 步在 Python + 浏览器里就能搞，不需要 UE。
