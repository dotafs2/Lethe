# Lethe 自动地编工具 — 设计文档

> Status: v2（重新开始版本，v1 已删，可在 git 历史 `2dbf587` 查看）
> 上次更新: 2026-05-27
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

### 2.5 放置流程（per placement slot）

```
for type in candidates_by_tag(region.brief):  # 按优先级排序
    spawn N=3 variants (不同 seed) 并行试
    每个 variant: UE collision check
    
    if 至少一个通过:
        所有过的 → Judge VLM 用 Scene Brief.refs 对比
        Judge 自动挑 best
        if best.score > 阈值:
            commit, done
    
    # 这个 type 失败 → 试下一个 candidate
    continue

# 全部 candidate 失败 → SKIP this slot（不放也行）
```

**关键设计**：
- 用户不在循环里，AI 自治
- candidates 必须 ≥ 3-4 个备选（chair → stove → bench → barrel）
- 最后一项可以是兜底装饰品
- 失败就跳过，不阻塞 generation

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
| **Q2** | "区域"怎么定义？(painted / derived / emergent / global) | ⏸ 先关注小场景 |
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
✅ tree-3d-demo.html                          3D 树可视化原型
   ├─ WASD 移动 + Q/E 上下 + Shift 加速
   ├─ RMB drag 自由视角
   ├─ 单击节点 → info 面板显示数据
   ├─ 双击节点 → 摄像机平滑飞过去（550ms ease-out）
   ├─ Regenerate 按钮 → 重新生成 sample tree
   └─ Toggle Rejected → 只显示主线/全部

❌ PlacementMetadata schema (pydantic)         未开始
❌ scan_assets.py（离线 LLM 扫库）             未开始
❌ review_cli.py（low-confidence 人工 review） 未开始
❌ placement.py（实际放置算法）                未开始
❌ Python FastAPI WebSocket server             未开始
❌ UE Remote Execution 接入                    未开始
```

---

## 五、下一步路线图（按依赖排序）

```
1. PlacementMetadata schema
   → src/lethe/placement/schema.py
   → pydantic 模型 + YAML 序列化

2. scan_assets.py
   → 跑 10 个样本 asset，验证 DeepSeek 输出质量
   → 如果质量 OK 再全量扫

3. review_cli.py
   → 把 low-confidence 队列过一遍

4. WebSocket server
   → FastAPI + asyncio，跟 Lethe MCP 同进程
   → 协议：tree_update / navigate / regen_subtree

5. placement.py（核心算法）
   → 输入 region + brief
   → 输出 tree node + UE spawn 指令
   → 整合 metadata + collision matrix + Scene Brief

6. UE 接入
   → Remote Execution Python script
   → spawn / destroy / get_collision_overlap

7. 整合：tree-3d-demo → WebSocket → placement → UE
   → 端到端跑通"加一个 region"流程

8. VLM validation loop
   → DeepSeek photo capture + Judge prompt
   → 关闭决策环

每步独立可测；前 4 步在 Python + 浏览器里就能跑通，不需要 UE。
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
