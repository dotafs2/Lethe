"""Lethe WebSocket bridge — connects the 3D tree viewer to a running UE editor.

How to use:
    1. Open UE with PythonScriptPlugin + Remote Execution enabled.
    2. In a terminal: `python -m lethe.ws_server`
    3. Open browser at: http://localhost:8765/tree-3d-demo.html

The browser receives:
    - {type: "tree", data: [<actor records>]}   on connect / on /refresh
    - {type: "selection", data: [<actor names>]} when UE selection changes

The browser may send:
    - {type: "refresh"}                          re-pull actor tree from UE
    - {type: "select", name: "Cube_07"}          select that actor in UE

NOTE: only one process can hold the UE Remote Execution multicast socket at a
time. If the Lethe MCP server is running, stop it before starting this one.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import tempfile
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .server import _run_in_ue, _ensure_connected

# Temp file UE writes large JSON payloads to (UE Remote Execution UDP can't carry
# more than ~1.5KB reliably, so anything bigger goes via filesystem)
_BRIDGE_FILE = pathlib.Path(tempfile.gettempdir()) / "lethe_bridge.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lethe-ws")

# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------
app = FastAPI(title="Lethe Tree Bridge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

clients: set[WebSocket] = set()
_last_selection: set[str] = set()


# ----------------------------------------------------------------------------
# UE-side scripts (run via Remote Execution)
# ----------------------------------------------------------------------------

GET_TREE_SCRIPT_TMPL = r"""
import unreal, json
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = sub.get_all_level_actors()
sma = [a for a in actors if isinstance(a, unreal.StaticMeshActor)]
out = []
for a in sma:
    try:
        parent_a = a.get_attach_parent_actor()
    except Exception:
        parent_a = None
    loc = a.get_actor_location()
    rot = a.get_actor_rotation()
    mesh_path = None
    try:
        comp = a.static_mesh_component
        if comp is not None:
            sm = comp.static_mesh
            if sm is not None:
                mesh_path = sm.get_path_name()
    except Exception:
        pass
    out.append({
        "name": a.get_name(),
        "label": a.get_actor_label(),
        "parent": parent_a.get_name() if parent_a else None,
        "mesh": mesh_path,
        "location": [loc.x, loc.y, loc.z],
        "rotation": [rot.pitch, rot.yaw, rot.roll],
    })
# UE Remote Execution UDP can't reliably carry >1.5KB. Write to disk instead.
with open(r"{path}", "w", encoding="utf-8") as f:
    json.dump(out, f)
print("__LETHE_OK__" + str(len(out)))
"""

GET_SELECTION_SCRIPT = r"""
import unreal, json
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sel = sub.get_selected_level_actors()
names = [a.get_name() for a in sel if isinstance(a, unreal.StaticMeshActor)]
print("__LETHE_JSON__" + json.dumps(names))
"""

SELECT_BY_NAME_TMPL = r"""
import unreal
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
target_name = {name!r}
for a in sub.get_all_level_actors():
    if a.get_name() == target_name:
        sub.set_selected_level_actors([a])
        # Focus the editor viewport on the actor too
        try:
            unreal.LevelEditorSubsystem
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        except Exception:
            pass
        print("__LETHE_JSON__" + '"ok"')
        break
else:
    print("__LETHE_JSON__" + '"not_found"')
"""


# ----------------------------------------------------------------------------
# UE bridge
# ----------------------------------------------------------------------------

def _extract_json(output: str) -> Any:
    """Find the marker line and parse JSON after it."""
    for line in output.splitlines():
        idx = line.find("__LETHE_JSON__")
        if idx >= 0:
            payload = line[idx + len("__LETHE_JSON__"):].strip()
            try:
                return json.loads(payload)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode failed: {e} — payload={payload[:200]}")
                return None
    return None


async def query_ue(code: str) -> Any:
    """Run Python in UE, parse the `__LETHE_JSON__<json>` line."""
    loop = asyncio.get_event_loop()
    try:
        output = await loop.run_in_executor(None, _run_in_ue, code)
    except Exception as e:
        logger.error(f"UE call failed: {e}")
        return None
    return _extract_json(output or "")


async def fetch_tree() -> list[dict]:
    """Get actor tree by having UE write JSON to disk (UDP can't carry it)."""
    # Clean up any stale file before asking UE to write a new one
    try:
        _BRIDGE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    # Have UE write JSON to _BRIDGE_FILE, then print just the count
    bridge_path = str(_BRIDGE_FILE).replace("\\", "/")
    script = GET_TREE_SCRIPT_TMPL.replace("{path}", bridge_path)

    loop = asyncio.get_event_loop()
    try:
        output = await loop.run_in_executor(None, _run_in_ue, script)
    except Exception as e:
        logger.error(f"UE call failed (fetch_tree): {e}")
        return []

    # Sanity check: the marker should appear
    if "__LETHE_OK__" not in (output or ""):
        logger.warning(f"fetch_tree: no OK marker. output preview: {(output or '')[:200]}")
        return []

    # Read the file UE just wrote
    if not _BRIDGE_FILE.exists():
        logger.warning(f"fetch_tree: bridge file missing at {_BRIDGE_FILE}")
        return []
    try:
        with open(_BRIDGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"fetch_tree: {len(data)} actors loaded from {_BRIDGE_FILE}")
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"fetch_tree: file read/parse failed: {e}")
        return []


async def fetch_selection() -> set[str]:
    data = await query_ue(GET_SELECTION_SCRIPT)
    return set(data) if isinstance(data, list) else set()


# ----------------------------------------------------------------------------
# Broadcasting
# ----------------------------------------------------------------------------

async def broadcast(msg: dict) -> None:
    dead = []
    for c in list(clients):
        try:
            await c.send_json(msg)
        except Exception:
            dead.append(c)
    for c in dead:
        clients.discard(c)


# ----------------------------------------------------------------------------
# WebSocket endpoint
# ----------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    logger.info(f"WS connect ({len(clients)} clients)")

    try:
        # send initial tree
        tree = await fetch_tree()
        await ws.send_json({"type": "tree", "data": tree})
        # send initial selection (may be empty)
        sel = await fetch_selection()
        await ws.send_json({"type": "selection", "data": list(sel)})

        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "refresh":
                tree = await fetch_tree()
                await broadcast({"type": "tree", "data": tree})
            elif t == "select":
                name = msg.get("name")
                if isinstance(name, str) and name:
                    await query_ue(SELECT_BY_NAME_TMPL.format(name=name))
            elif t == "ping":
                await ws.send_json({"type": "pong"})
            else:
                logger.warning(f"unknown msg type: {t}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS handler error: {e}")
    finally:
        clients.discard(ws)
        logger.info(f"WS disconnect ({len(clients)} clients)")


# ----------------------------------------------------------------------------
# Selection polling loop
# ----------------------------------------------------------------------------

async def selection_loop():
    global _last_selection
    while True:
        await asyncio.sleep(0.4)
        if not clients:
            continue
        try:
            sel = await fetch_selection()
        except Exception:
            continue
        if sel != _last_selection:
            _last_selection = sel
            await broadcast({"type": "selection", "data": list(sel)})


# ----------------------------------------------------------------------------
# HTTP convenience endpoint
# ----------------------------------------------------------------------------

@app.get("/refresh")
async def http_refresh():
    tree = await fetch_tree()
    await broadcast({"type": "tree", "data": tree})
    return {"ok": True, "actors": len(tree)}


# ----------------------------------------------------------------------------
# Startup
# ----------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    try:
        _ensure_connected()
        logger.info("Connected to UE editor")
    except Exception as e:
        logger.warning(f"UE not reachable on startup: {e} (will retry on each query)")
    asyncio.create_task(selection_loop())


# ----------------------------------------------------------------------------
# Serve the demo HTML so the browser can connect without CORS surprises
# ----------------------------------------------------------------------------

# repo root = parent of src/lethe/, i.e. /<repo>/
_repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
app.mount("/", StaticFiles(directory=str(_repo_root), html=True), name="root")


def main():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
