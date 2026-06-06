# Lethe 设计文档

> Status: v6 — **自动地编逻辑已清零,准备完全重构**
> 上次更新: 2026-06-06

---

## 〇、当前状态(读我)

所有 L0–L5 自动地编规则(地形 / 区域骨架 / 放置 / 碰撞 / BFS 逐层建造 /
optimize loop / 场景树设计)**已全部删除**(整个 `scripts/` 目录被移除)。

保留下来的只有两块**基础设施**,自动地编将在它们之上重新设计:

1. **通信协议** — Python ↔ UE 的桥(MCP + Remote Execution + WebSocket)
2. **HTML 场景/模型展示** — `tree-3d-demo.html` 树可视化 + 双向同步

下面只描述这两块「保留区」。**自动地编(几何生成那一层)是一张白纸**,见 §三。

---

## 一、保留区:通信协议

```
Claude Desktop ──MCP──▶ lethe (FastMCP) ──Remote Execution──▶ UnrealEditor
Browser (tree-3d-demo.html) ──WebSocket──▶ lethe.ws_server ──Remote Execution──▶ UE
```

| 文件 | 职责 |
|---|---|
| `src/lethe/remote_execution.py` | UE Remote Execution 协议(UDP 多播发现 + TCP 执行 Python) |
| `src/lethe/server.py` | FastMCP server,对 Claude 暴露工具:`spawn_cube` / `execute_python` / `verify_actors` / PolyHaven HDRI 等;`_run_in_ue(code)` 是所有 UE 调用的统一入口 |
| `src/lethe/ws_server.py` | FastAPI + WebSocket 桥,给浏览器树用;poll UE 选中(400ms)、actor 数变化(1.6s)自动刷新;大 JSON 走临时文件绕过 UDP ~1.5KB 限制;asyncio.Lock 串行化 UE 调用 |
| `ue-plugin/Lethe/` | UE 侧插件:`init_unreal.py` 启动注册、`lethe_menu.py` 集成开关(PolyHaven/Hunyuan/Tripo,写 `Saved/Lethe/config.json`) |

**约束**:同一时间只能一个 process 持 UE 连接(MCP server 与 ws_server 不能同时跑,
它们共用 Remote Execution 多播端口)。

运行方式见 `HOW_TO_RUN.md`(浏览器树)与 `README.md`(MCP server)。

---

## 二、保留区:HTML 场景/模型展示

`tree-3d-demo.html` — 浏览器端 Three.js 场景树可视化,已与 UE 实时双向同步。

| 能力 | 说明 |
|---|---|
| 拉取 | 连接时从 UE 拉所有 `StaticMeshActor`,按 attach 层级组装成树 |
| 浏览器 → UE | 单击节点 → UE 选中对应 actor;双击 → 浏览器相机飞到该节点 |
| UE → 浏览器 | UE 视口选中 actor → 浏览器对应节点橙色高亮(脉动 wireframe 球) |
| 相机 | WASD 移动 + Q/E 升降 + 滚轮调速 + RMB 自由视角 + F 聚焦 |
| 布局/性能 | d3-hierarchy + Z 偏移;>120 节点切径向布局;InstancedMesh;实测 1000 节点 33–60fps |

**已知 TODO**(来自 HOW_TO_RUN.md):用真 selection event 替代轮询、支持非
StaticMeshActor、节点折叠展开、接入 MCP 让 Claude 也能看树。

---

## 三、自动地编:清零,待重新设计 ⬜

这一层是这次重构的目标,**当前没有任何已敲定的设计**。重新设计时在此填入:

- [ ] 问题定义:输入是什么、输出是什么(只用 box 灰盒,不接真实模型)
- [ ] 主数据结构
- [ ] 空间结构 / 布局算法
- [ ] 与「通信协议」「HTML 展示」两块基础设施的接口契约
- [ ] 验证 / 迭代方式

> 历史教训(唯一值得带走的一条):
> 「管线通了」≠「算法实现了」。2026-05-29 曾把 1000 个物体裸 spawn 进场景,
> 因为验证回路一行没接,结果是悬浮在蓝色虚空、无结构的一堆盒子。
> 新设计里,验证回路从第一天就要是必需项,而不是可选项。
