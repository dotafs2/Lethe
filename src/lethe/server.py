"""Lethe MCP server — lets Claude drive an Unreal Engine editor over Remote Execution.

Tools exposed:
    - execute_python(code): run arbitrary Python inside the UE editor.
    - spawn_cube(x, y, z): convenience demo that spawns a basic cube.

UE side requirements:
    - PythonScriptPlugin enabled in the .uproject
    - Remote Execution enabled in Project Settings → Plugins → Python
    - Editor must be running when Claude calls a tool.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import remote_execution as remote

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lethe")

mcp = FastMCP("Lethe")

_rx: remote.RemoteExecution | None = None
_NODE_DISCOVERY_TIMEOUT = 5.0


def _get_session() -> remote.RemoteExecution:
    global _rx
    if _rx is None:
        logger.info("Starting RemoteExecution session")
        _rx = remote.RemoteExecution(remote.RemoteExecutionConfig())
        _rx.start()
    return _rx


def _ensure_connected() -> remote.RemoteExecution:
    rx = _get_session()
    deadline = time.time() + _NODE_DISCOVERY_TIMEOUT
    while not rx.remote_nodes and time.time() < deadline:
        time.sleep(0.1)
    if not rx.remote_nodes:
        raise RuntimeError(
            "No Unreal Editor node discovered. Open the editor with "
            "PythonScriptPlugin + Remote Execution enabled."
        )
    if not rx.has_command_connection():
        node_id = rx.remote_nodes[0]["node_id"]
        logger.info("Opening command connection to node %s", node_id)
        rx.open_command_connection(node_id)
    return rx


def _run_in_ue(code: str) -> str:
    rx = _ensure_connected()
    result: dict[str, Any] = rx.run_command(code, exec_mode=remote.MODE_EXEC_FILE)

    output_items = result.get("output") or []
    lines = []
    for item in output_items:
        text = item.get("output", "") if isinstance(item, dict) else str(item)
        if text:
            lines.append(text.rstrip())
    output_text = "\n".join(lines)

    if not result.get("success", True):
        return f"[UE ERROR] {result.get('result', '')}\n{output_text}".strip()
    return output_text or "ok"


@mcp.tool()
def execute_python(code: str) -> str:
    """Execute arbitrary Python inside the running Unreal Editor and return stdout.

    The `unreal` module is available. Prefer editor subsystems for new code:
        import unreal
        s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        mesh = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube.Cube')
        s.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 200), unreal.Rotator(0, 0, 0))

    Use print() to surface values — the return is whatever UE printed.
    """
    return _run_in_ue(code)


@mcp.tool()
def spawn_cube(x: float = 0.0, y: float = 0.0, z: float = 200.0) -> str:
    """Spawn a basic cube at the given world location in the current UE level."""
    code = (
        "import unreal\n"
        "s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "m = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube.Cube')\n"
        f"a = s.spawn_actor_from_object(m, unreal.Vector({x}, {y}, {z}), unreal.Rotator(0, 0, 0))\n"
        "print('spawned', a.get_name())\n"
    )
    return _run_in_ue(code)


def main() -> None:
    try:
        mcp.run()
    finally:
        global _rx
        if _rx is not None:
            try:
                _rx.stop()
            except Exception:
                pass
            _rx = None


if __name__ == "__main__":
    main()
