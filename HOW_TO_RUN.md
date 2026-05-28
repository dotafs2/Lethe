# How to run the UE ↔ 3D tree integration

## Setup（首次）

```powershell
# 装新依赖（fastapi + uvicorn）
pip install -e .
```

## 跑起来

```
1. 打开 UE 编辑器（确认 PythonScriptPlugin + Remote Execution 已启用）
2. ⚠️ 如果 Lethe MCP server 在跑，先停掉（同时只能一个 process 持 UE 连接）
3. 终端执行：

     python -m lethe.ws_server

   或者：

     lethe-ws

4. 浏览器打开：  http://localhost:8765/tree-3d-demo.html
```

## 看到什么

- 浏览器顶部居中显示 `● connected to UE`（绿色）= 连接 OK
- 树自动从 UE 拉取所有 `StaticMeshActor`，按 attach hierarchy 组装
- 顶部多了 `Refresh from UE` 按钮 — 重新拉 actor 列表
- 在 UE 视口里点任意 StaticMeshActor → 浏览器对应节点：
  - HTML 标签变橙黄高亮
  - 节点周围出现脉动的橙色 wireframe 球
- 在浏览器里点节点 → UE 视口里对应 actor 被选中（反向）

## 双击节点

双击浏览器里的节点 → 摄像机平滑飞过去（550ms ease-out）。跟 UE 选中是独立的两件事：单击=选中、双击=飞过去。

## 数据流

```
UE Editor                                Browser (tree-3d-demo.html)
   │                                            │
   │  selection                                 │
   ├───────►  Python (ws_server.py)             │
   │         polls every 400ms                  │
   │                  │                         │
   │                  └─── WS push ────────────►│  setUESelected()
   │                                            │
   │  ◄─── ExecuteFile via Remote Execution ────│
   │       (when browser clicks node)           │
   │                                            │
   │  on connect / refresh:                     │
   │  ────► get all StaticMeshActors ──── WS ──►│  buildScene()
```

## 常见问题

**"WS error" / 红色不连接**
- 检查 `python -m lethe.ws_server` 在跑吗
- 检查 UE 编辑器开着吗
- 检查端口 8765 没被占
- 启动 ws_server 时 log 里看 `Connected to UE editor`

**"WS connected" 但树是空的**
- UE 当前关卡里没有 StaticMeshActor
- 拉一个 cube 进去再点 `Refresh from UE`

**选中 UE 里某个 actor 但浏览器没高亮**
- 那个 actor 可能不是 `StaticMeshActor`（比如 SkeletalMeshActor / BP_Actor）— 当前只追踪 StaticMeshActor
- 控制台日志看有没有错
- Selection 是 400ms 一次轮询，会有一点延迟

**MCP 已经在跑，端口冲突**
- 当前 ws_server 也是用 Remote Execution 多播端口，跟 MCP server 同一个
- 两个不能同时跑。先停 MCP（`Ctrl+C` 或 kill），再起 ws_server

## 接下来 TODO

- [ ] 在 UE 侧用真的 selection event 替代轮询（消除 400ms 延迟）
- [ ] 支持非 StaticMeshActor（BP actors / skeletal）
- [ ] 浏览器节点支持折叠 / 展开子树
- [ ] 接入 Lethe MCP server（让 Claude 也能看树）
- [ ] 双击节点把 UE viewport 也飞过去（不仅是选中）
