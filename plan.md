# Lethe 自动地编工具 — 设计文档

> Status: v3（算法收敛到"区域容器 + 爬虫递归生长 + 节点级拍照验证"）
> 上次更新: 2026-05-29
> 配套 demo: `tree-3d-demo.html`（浏览器打开即可）

---

## 一、核心理念

1. **AI 完全自治** — runtime 不打断用户，用户只在场景生成完后审核
2. **树是核心** — 既是数据结构也是 UI，操作树 = 操作场景
3. **失败可跳过** — 单个物体放不下就不放（"可以不放"）
4. **视觉锚定** — 通过 Scene Brief（参考图 + 故事 + 关键词）保证主题一致

---

## 二、已敲定的设计

### 2.1 物体属性 = 离散标签集合

```python
asset.tags = {"human", "ground", "structure", "residential"}
region.accept_tags = {"natural", "ground", "agricultural"}

# 兼容性判定
def compatible(asset, region):
    overlap = asset.tags & region.accept_tags
    return len(overlap) >= region.min_match
```

**为什么不用别的：**

| 方案 | 否决原因 |
|---|---|
| Embedding 向量 | 黑箱，人工 review 抓瞎，YAML 改不动 |
| 命名属性轴（urbanization=0.7） | 设计复杂，扩展时需要重新设计轴 |

### 2.2 树结构

```
World (隐藏根)
├── Region_village_01
│   ├── House_01            (picked)
│   │   ├── Chair_01
│   │   └── Table_02
│   ├── House_01_alt_v2     (rejected, terminal)
│   ├── House_01_alt_v3     (rejected, terminal)
│   └── Well_01             (picked)
└── Region_wilderness_01
    └── ...
```

- 每节点严格 **一个父亲**（rooted tree，非 DAG）
- 子节点 **完全依赖父节点**：mute 父 → 子全隐藏，delete 父 → 子全消失
- 第一版用完全依赖，后续扩展软引用进 TODO

### 2.3 分支保留策略：Lazy 模型 A

```
所有"考虑过的分支"都保留在树里
但 rejected 分支默认不会继续生长（terminal）
用户点击 rejected 节点 → AI 才从那里开始往下生成
```

**存 diff 不存 snapshot**：

```python
TreeNode {
    id: "house_03"
    parent: "region_village_01"
    action: "place house at (3,5,2) yaw=90"
    seed: 12345
    picked: True
    judge_score: 0.87
    rejected_reason: null  # 或 "collision_failed" / "judge_too_low" / "theme_mismatch"
}

# 恢复任意节点状态 = 从 root 沿父链 replay 所有 action
# 存储：每节点 ~200 bytes，10000 节点也才 2MB
```

### 2.4 Scene Brief（视觉/语义锚点）

```yaml
scene_brief:
  references:                    # AI 生成的参考图，3-5 张
    - ref_01.png
    - ref_02.png
    - ref_03.png
  story: |                       # < 200 字背景叙述
    12世纪英格兰边境村庄，秋季雨后清晨。
    去年遭过盗匪袭击，部分建筑还没完全修复。
  refined_keywords:              # 强制结构化，不要散文
    mood: [solemn, rebuilding, rustic]
    palette: [muted_greens, wet_stone, wood_browns]
    avoid: [fantasy, bright_colors, modern]
    density: sparse
```

整个 generation 期间 **immutable**，喂给 Selector / Judge / Validator 三个组件。

### 2.5 放置算法：区域容器 + 爬虫递归生长 + 节点级验证 ⭐核心

这是整个工具的核心算法，三层结构：

```
Layer 0  — 地面/地形：所有物体落地的参照面，也是树的 root（不能砍）
Layer 1  — LLM 划区域（"花盆"，调用少）：
             regions[] = {type, polygon, density, allowed_tags, anchor_slug}
             先手写跑通，再接 LLM
Layer 2  — 每个区域内"爬虫式"递归生长（核心循环）：
```

```python
grow(node, region, depth):
    if depth >= MAX_DEPTH or region.saturated():
        return

    # ① 广度：在 node 周围铺一圈子物体
    children = []
    for slug in pick_children(node, region.allowed_tags):
        for attempt in range(K):                      # K≈6
            pos = sample_around(node)
            z   = -bounds_min[slug].z * scale          # 落地校正
            if no_overlap(pos, slug, grid):            # 只查已放置的邻居
                c = place_tentative(slug, pos, yaw_rule(node, pos))
                children.append(c); grid.insert(c)     # 空间哈希
                break
            # else: K 次全撞 → 跳过这个（"可以不放"）

    # ② 验证：仅当 node 是 major anchor（建筑/树丛/区域核心）
    if node.is_major:
        photo = capture(node + children)
        if not LLM_ok(photo, scene_brief):
            rollback(children)                         # 撤销暂定，重采/剪枝
            return
    commit(children)                                   # 验过 → 永久，从此不动

    # ③ 深度：递归每个能继续长的子节点
    for c in children:
        if c.can_grow:                                 # 建筑能长附属，草不能
            grow(c, region, depth + 1)
```

**"深度优先 + 每个节点广度优先"**：DFS 递归遍历，但每个节点 visit 时先广度填满自己周围一圈，再钻进每个子节点继续卷。整棵树这样"爬"出来。

**两阶段 commit（统一"永不动"与"验证重来"）**：
- 生长时子物体是 `tentative`（暂定，可回滚）
- 拍照验证通过 → `committed`（永久，从此永不动）
- 验证失败 → 只撤销这个节点的暂定物体，重采
- 即 "chunk 内线性，chunk 间可重采"，每个生长节点 = 一个 chunk

**验证粒度（成本/延迟命门）**：
- 只验 major anchor 子树（建筑/树丛/区域核心），叶子小物（草/石/桶）跟父节点一起被验
- 几十次 LLM、几分钟级；不是每个物体都验（那样上百次、10-15 分钟）

**五个必须做对的实现点**（today 裸 spawn 全没做，见第八节复盘）：
1. **空间哈希** — `no_overlap` 只查邻近 3×3 格，O(1) 均摊；否则 1000 物体 ×K 重采会慢成几百万次
2. **footprint ≠ visual AABB** — 树冠大但树干占地小，碰撞按 role 配占地半径
3. **拒采会"放不满"** — 密度高时后放的反复撞→跳过，1000 目标可能只成 ~700-800，需接受
4. **落地校正** — `z = -bounds_min.z * scale` 让底部贴地；today z 全=0 故悬浮
5. **大物体先放** — 按 footprint 降序，先占位再填缝，避免大物被小物挤没位置

**关键参数**：`MAX_DEPTH`≈4，`K`≈6，`is_major`/`can_grow` 按 role 配置。

**区域是"花盆"**：先划分区域边界，每区独立递归生长，区域间不互相侵占空间 —— 解决 DFS 先生长分支抢占空间的问题。

### 2.6 Collision Matrix（4×4 channel）

```
              Solid     Surface   Decor      Attach
   Solid      BLOCK     Ignore    BLOCK      Ignore
   Surface    Ignore    Ignore    Ignore     Ignore
   Decor      BLOCK     Ignore    Overlap    Ignore
   Attach     Ignore    Ignore    Ignore     BLOCK
```

- **BLOCK** = 放置失败，retry / 换 candidate
- **Overlap** = 允许重叠但发事件（密度告警用）
- **Ignore** = 不检查

Self-attachment 豁免（lamp 跟它附着的 desk 必然接触）通过查询时的 `ignore_actors` 列表处理，不在矩阵里。

### 2.7 树可视化（已有 demo：tree-3d-demo.html）

| 项 | 选定 |
|---|---|
| 维度 | **3D** |
| Z 轴语义 | 主路径 picked=0，rejected 备选 ±5 偏移（方案 A） |
| 渲染 | Three.js InstancedMesh（10k+ 节点不卡） |
| 布局 | d3-hierarchy + 手加 Z |
| 摄像机 | **WASD + RMB drag look + 双击 fly-to** |
| Labels | HTML overlay div（不用 sprite，文字始终清晰） |
| 大树性能策略 | < 1k 硬画 / 1k-5k 加 frustum culling / >50k 换 PixiJS |

### 2.8 通信架构

```
Browser (Tree UI, Three.js)
        ↕ WebSocket
Python (Lethe MCP + FastAPI 同进程)
        ↕ HTTP (UE Remote Execution)
    UE Editor
```

**第一版**：单向数据流（tree → UE）。
**TODO**：UE 内拖拽回写树（双向同步）。

WebSocket 用 **patch 而非全量推送**，1500 节点也不卡。

### 2.9 LLM 集成策略 + 成本

**完全离线扫库一次，运行时不调 LLM 做元数据决策**：

```
500 个 asset × 3 个候选 metadata × DeepSeek Vision    ~$0.20
低置信度 10% cascade 到 Claude Sonnet                 ~$0.15
随机抽样 5% 用 Claude 复核                            ~$0.08
                                              总：    ~$0.45 一次性
```

**Runtime Judge**：DeepSeek V4 Vision，每 placement ~$0.0002。
50-物体场景 + 30% 走 Judge ≈ **$0.003 / 场景**。

DeepSeek Vision 用 90 tokens / 图（Claude 是 870 tokens），是这种 batch image task 的最优选。

---

## 三、待答问题（TODO）

| ID | 问题 | 状态 / 备注 |
|---|---|---|
| **Q2** | "区域"怎么定义？ | ✅ 收敛：LLM 划区域(Layer1)，区域=递归生长的"花盆"边界 |
| **位置决策主导** | LLM / 程序 / 混合？ | ✅ 混合：LLM 规划高层结构，程序出几何，VLM 验收 |
| **碰撞策略** | 重叠怎么处理？ | ✅ 增量+拒采（撞了重采/跳过，已放置不动） |
| **验证粒度** | 哪些节点拍照问 LLM？ | ✅ 只验 major anchor 子树（几十次/几分钟） |
| **Q5** | Regen 粒度：mute / regen-self / regen-subtree | ⏸ |
| **Q6** | 单根 vs 多根 | ⏸（倾向单根，等确认） |
| Region refs 分区 | 等 Q2 完成后做 multi-region scene_brief | ⏸ |
| 跨子树软引用 | 当前"完全依赖"，未来加 cross-tree soft refs | ⏸ |
| UE → tree 回写 | 拖拽 actor 时自动创建 manual_edit 分支 | ⏸ |
| 大树优化 | > 5k 节点时加 frustum culling + LOD | ⏸ |
| Octree hit-test | > 10k 节点时换 GPU pick | ⏸ |
| Placement bounds 推导算法 | 从 mesh AABB → 投影座面 + use_space_extend | ⏸ |
| 重试状态机细节 | retry 时 seed 怎么变、surface 切换策略 | ⏸ |

---

## 四、当前 deliverables

```
✅ tree-3d-demo.html                          3D 树可视化（已连 UE，实时双向）
   ├─ WASD 移动 + Q/E 上下 + 滚轮调速(1-8档) + RMB 自由视角
   ├─ 单击节点联动 UE 选中 / 双击飞到 / F 聚焦
   ├─ UE 视口选中 → 浏览器节点橙色高亮（双向同步）
   ├─ >120 节点自动切径向布局；节点/雾/相机按树规模自适应
   └─ 实测 1000 节点辐射圆盘 33-60fps

✅ src/lethe/ws_server.py                      FastAPI WebSocket 桥
   ├─ tree → UE 单向（点节点 → UE 切换/选中）
   ├─ poll_loop：400ms 查选中、1.6s 查 actor 数变化自动刷新
   ├─ 大 JSON 走临时文件绕开 UE UDP ~1.5KB 限制
   └─ asyncio.Lock 串行化 UE 调用（避免并发串台）

✅ 素材库（一次性建好，可复用）
   ├─ scripts/download_assets.py  下载50个中世纪模型(1k最低模)→import
   ├─ scripts/_asset_library.json 50个 mesh 的 bounds（落地/碰撞要用）
   └─ scripts/_dump_models.py / _pick_medieval.py  筛选工具

✅ scripts/build_town_v2.py / build_town_1000.py  程序化 spawn+attach
✅ scripts/capture_scene.py                    SceneCapture2D 全景拍照（拍照验证基础设施）

❌ Layer1: LLM 区域规划（先手写区域跑通）       未开始
❌ Layer2: 递归生长几何（增量拒采+空间哈希+落地+footprint）  未开始 ← 核心
❌ Layer3: 节点级 VLM 拍照验证回路              未开始 ← 核心
❌ 地面/地形（Layer 0）                          未开始（today 被误删）
❌ PlacementMetadata schema (pydantic)         未开始
```

---

## 五、下一步路线图（自下而上，先几何后 AI）

```
第一步（纯几何，不接 LLM/VLM，解决 today 80% 问题）：
  ① 铺地面（Layer 0）
  ② 写 Layer2 递归生长：增量拒采 + 空间哈希 + footprint + 落地校正
  ③ 用手写的区域规划（2-3 个区）当 Layer1 的 stub 跑通
  ④ capture_scene 拍照看效果（这次有地面+落地+碰撞）

第二步（接 LLM 规划）：
  ⑤ 把手写区域规划换成 LLM 生成（Layer1）
     接口契约：Region{type,polygon,density,allowed_tags,anchor_slug}

第三步（接 VLM 验证，关闭你最想要的回路）：
  ⑥ grow() 里 major 节点拍照 → DeepSeek 判主题 → 不合格回滚重采
  ⑦ 两阶段 commit：验过永久，没验可回滚

辅助（可并行）：
  · PlacementMetadata schema（is_major/can_grow/footprint/align_up 按 role 配）
  · scan_assets.py 离线给50个素材补全 metadata
```

---

## 六、设计中**否决**的方案（避免回头踩坑）

| 方案 | 否决原因 |
|---|---|
| 马尔科夫链类比 | 本质是带 selector 的贪心序列放置，"无记忆"性误导 |
| 每次放置 LLM 判 up_priority / yaw | 99% 答案显然，不值得 per-call 调 |
| Embedding 表示物体属性 | 黑箱，人工 review 抓瞎 |
| Runtime 用户每步选分支 | 太慢，违背 AI 自治 |
| Eager 树（所有分支全展开） | 节点数指数爆炸 |
| 存全量 snapshot 而非 diff | 大场景下存储爆炸 |
| LMB drag 飞行（UE 风格） | 跟 click 选节点冲突，用双击 fly-to 代替 |
| 给每物体手写 "不能跟谁重叠" 列表 | 维护爆炸，用 UE channel matrix |
| 3D 力导向布局（force-directed） | Z 轴语义为零，位置不稳，找不到节点 |

---

## 七、关键术语速查

| 词 | 含义 |
|---|---|
| **Scene Brief** | 视觉风格 + 故事 + 关键词，整场景共享，immutable |
| **Region** | 场景的一块区域，有自己的 tag 过滤 + 密度上下限（Q2 待定） |
| **Placement Slot** | 一个 "这里要放点什么" 的位置（不绑定具体类型） |
| **Candidate** | Slot 对应的备选物体类型列表，按优先级排 |
| **Variant** | 同一个 type 用不同 seed 生成的几个候选放置 |
| **Judge** | VLM，看 N 个 variant 的截图，挑最贴 brief.refs 的 |
| **Picked node** | 树里实际 commit 的放置 |
| **Rejected node** | 考虑过但没采用的备选，保留为 terminal 分支 |
| **Hard edge** | parent → child，子完全依赖父 |
| **Soft edge** | 跨子树引用（当前未实现，TODO） |
| **PlacementMetadata** | 每 asset 的元数据：tags / attaches_to / yaw_strategy / 等 |
| **grow(node)** | 递归生长函数：广度填充周围 → 拍照验证 → 递归子节点 |
| **major anchor** | 需要拍照验证的大节点（建筑/树丛/区域核心） |
| **tentative / committed** | 暂定（可回滚） / 永久（验过，永不动） |
| **footprint** | 物体的占地投影（碰撞用，≠ visual AABB） |
| **花盆（区域容器）** | Region 作为递归生长的边界，区域间不互相侵占空间 |

---

## 八、复盘：2026-05-29 "1000 actor 裸 spawn" 的失败

把 1000 个物体直接 spawn 进场景，拍照后发现：**悬浮在蓝色虚空、太稀疏、无小镇结构**。诚实定位根因，作为反面教材：

| 现象 | 根因 | 对应修复 |
|---|---|---|
| 全是蓝色天空盒 | clear 时把地面也删了 = 砍了树的 root | Layer 0 先铺地面 |
| 物体悬浮 | z 全 = 0，没按 bounds_min.z 落地 | Layer2 落地校正 |
| 可能大量穿插 | 一次 overlap 检查都没做 | Layer2 增量拒采 + 空间哈希 |
| 太散、不成镇 | 320m 放 1000 个 + 纯随机撒点，无结构 | Layer1 区域规划 + 密度场 |
| 垃圾结果直接进场景 | **验证回路一行都没接** | Layer3 节点级拍照验证 |

**最大教训**：plan.md 设计了完整的"放置→碰撞→拍照→重试"流水线，但 today 的代码只做了第一步 spawn，把验证和约束全跳过了 —— "管线通了" ≠ "算法实现了"。`capture_scene.py` / `verify_actors` 只是截图工具，从未被放置流程调用。这次失败的照片，恰好证明了"拍照验证回路"为什么是必需的，而不是可选的。
