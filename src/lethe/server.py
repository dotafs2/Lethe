"""Lethe MCP server — lets Claude drive an Unreal Engine editor over Remote Execution.

Tools exposed:
    - execute_python(code): run arbitrary Python inside the UE editor.
    - spawn_cube(x, y, z): convenience demo that spawns a basic cube.
    - verify_actors(names, views, ...): take standard screenshots + AABB of actors.

UE side requirements:
    - PythonScriptPlugin enabled in the .uproject
    - Remote Execution enabled in Project Settings → Plugins → Python
    - Editor must be running when Claude calls a tool.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def execute_python(code: str) -> str:
    """Execute arbitrary Python inside the running Unreal Editor and return stdout.

    The `unreal` module is available. Prefer editor subsystems for new code:
        import unreal
        s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        mesh = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube.Cube')
        s.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 200), unreal.Rotator(0, 0, 0))

    Use print() to surface values — the return is whatever UE printed.

    If your code spawns or modifies actors, collect their names (actor.get_name())
    and call `verify_actors` afterward so you can visually confirm the result
    before continuing.
    """
    return _run_in_ue(code)


@mcp.tool()
def spawn_cube(x: float = 0.0, y: float = 0.0, z: float = 200.0) -> str:
    """Spawn a basic cube at the given world location. Returns the actor name.

    After a batch of spawn/move operations, call `verify_actors` with the
    affected actor names to visually confirm the result before continuing.
    """
    code = (
        "import unreal\n"
        "s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "m = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube.Cube')\n"
        f"a = s.spawn_actor_from_object(m, unreal.Vector({x}, {y}, {z}), unreal.Rotator(0, 0, 0))\n"
        "print('spawned', a.get_name())\n"
    )
    return _run_in_ue(code)


# ---------------------------------------------------------------------------
# verify_actors — canonical-view screenshots + union AABB
# ---------------------------------------------------------------------------

_DEFAULT_VIEWS = ["top", "front", "side", "hero", "context"]

_VERIFY_SCRIPT_HEADER = """
LETHE_ACTOR_NAMES = {actor_names}
LETHE_VIEWS = {views}
LETHE_CONTEXT_K = {context_k}
LETHE_W = {width}
LETHE_H = {height}
LETHE_FOV = {fov}
"""

# The body uses the LETHE_* globals set by the header. Kept as a raw string
# so dict literals and f-strings inside don't collide with str.format().
_VERIFY_SCRIPT_BODY = r'''
import unreal, json, math, os

def _lethe_look_at(cam, tgt):
    dx = tgt.x - cam.x
    dy = tgt.y - cam.y
    dz = tgt.z - cam.z
    yaw = math.degrees(math.atan2(dy, dx))
    d2 = math.sqrt(dx * dx + dy * dy)
    if d2 < 1e-6:
        pitch = 90.0 if dz > 0 else -90.0
    else:
        pitch = math.degrees(math.atan2(dz, d2))
    return unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0)

_actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
_ued_subsys = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

_all_actors = _actor_subsys.get_all_level_actors()
_by_name = {a.get_name(): a for a in _all_actors}
_wanted = {n: _by_name[n] for n in LETHE_ACTOR_NAMES if n in _by_name}
_missing = [n for n in LETHE_ACTOR_NAMES if n not in _by_name]

if not _wanted:
    print("LETHE_JSON::" + json.dumps({
        "error": "no matching actors found in current level",
        "missing": _missing,
    }))
else:
    _mn = [1e30, 1e30, 1e30]
    _mx = [-1e30, -1e30, -1e30]
    _per = {}
    for _name, _a in _wanted.items():
        _origin, _extent = _a.get_actor_bounds(only_colliding_components=False)
        _lo = [_origin.x - _extent.x, _origin.y - _extent.y, _origin.z - _extent.z]
        _hi = [_origin.x + _extent.x, _origin.y + _extent.y, _origin.z + _extent.z]
        _mn = [min(_mn[i], _lo[i]) for i in range(3)]
        _mx = [max(_mx[i], _hi[i]) for i in range(3)]
        _per[_name] = {
            "origin": [_origin.x, _origin.y, _origin.z],
            "extent": [_extent.x, _extent.y, _extent.z],
        }

    _C = unreal.Vector((_mn[0] + _mx[0]) / 2, (_mn[1] + _mx[1]) / 2, (_mn[2] + _mx[2]) / 2)
    _size = [_mx[0] - _mn[0], _mx[1] - _mn[1], _mx[2] - _mn[2]]
    _L = max(_size[0], _size[1], _size[2], 100.0)  # floor for tiny actors

    _offsets = {
        "top":     (0.0,           0.0,           2.5 * _L),
        "front":   (-2.5 * _L,     0.0,           0.3 * _L),
        "side":    (0.0,           -2.5 * _L,     0.3 * _L),
        "hero":    (-2.0 * _L,     -2.0 * _L,     1.5 * _L),
        "context": (-LETHE_CONTEXT_K * _L,
                    -LETHE_CONTEXT_K * _L,
                    LETHE_CONTEXT_K * 0.75 * _L),
    }

    _rt = unreal.new_object(unreal.TextureRenderTarget2D)
    _rt.init_auto_format(LETHE_W, LETHE_H)

    _save_dir = unreal.Paths.convert_relative_path_to_full(
        os.path.join(unreal.Paths.project_saved_dir(), "LetheShots"))
    os.makedirs(_save_dir, exist_ok=True)

    _world = _ued_subsys.get_editor_world()
    _files = {}
    for _view in LETHE_VIEWS:
        if _view not in _offsets:
            continue
        _ox, _oy, _oz = _offsets[_view]
        _cam = unreal.Vector(_C.x + _ox, _C.y + _oy, _C.z + _oz)
        _rot = _lethe_look_at(_cam, _C)
        _sc = _actor_subsys.spawn_actor_from_class(unreal.SceneCapture2D, _cam, _rot)
        try:
            _comp = _sc.scene_capture_component2d
            _comp.texture_target = _rt
            _comp.fov_angle = LETHE_FOV
            _comp.capture_source = unreal.SceneCaptureSource.FINAL_COLOR_LDR
            _comp.capture_scene()
            _fname = "lethe_" + _view + ".png"
            unreal.RenderingLibrary.export_render_target(_world, _rt, _save_dir, _fname)
            _files[_view] = os.path.join(_save_dir, _fname)
        finally:
            _actor_subsys.destroy_actor(_sc)

    print("LETHE_JSON::" + json.dumps({
        "aabb": {
            "min": _mn,
            "max": _mx,
            "center": [_C.x, _C.y, _C.z],
            "size": _size,
            "longest_axis": _L,
        },
        "actors": _per,
        "missing": _missing,
        "files": _files,
    }))
'''


def _parse_verify_payload(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        tag = "LETHE_JSON::"
        idx = line.find(tag)
        if idx >= 0:
            return json.loads(line[idx + len(tag):])
    raise RuntimeError(f"verify_actors: no JSON payload in UE output:\n{stdout}")


@mcp.tool()
def verify_actors(
    actor_names: list[str],
    views: list[str] = _DEFAULT_VIEWS,
    context_distance_factor: float = 8.0,
    width: int = 512,
    height: int = 512,
    fov: float = 60.0,
) -> list:
    """Take standard verification screenshots of the given actors and return
    them together with the union AABB.

    Call this after every batch of spawn/move operations to visually confirm
    the result before planning the next step. Inspect BOTH the images and the
    AABB JSON — metadata often catches mistakes (wrong axis, wrong scale) that
    the thumbnail doesn't make obvious.

    Views (framed to tightly contain the actors' combined AABB):
      - top     — orthogonal top-down
      - front   — from -X looking along +X
      - side    — from -Y looking along +Y
      - hero    — 3/4 perspective
      - context — pulled far back by `context_distance_factor` to show scene context

    Returns a list: [summary JSON string, Image, Image, ...] — images appear
    in the same order as `views`. Missing actors are listed in the summary.
    """
    if not actor_names:
        return ["verify_actors: empty actor_names list"]

    script = _VERIFY_SCRIPT_HEADER.format(
        actor_names=json.dumps(list(actor_names)),
        views=json.dumps(list(views)),
        context_k=float(context_distance_factor),
        width=int(width),
        height=int(height),
        fov=float(fov),
    ) + _VERIFY_SCRIPT_BODY

    stdout = _run_in_ue(script)
    payload = _parse_verify_payload(stdout)

    if "error" in payload:
        return [f"verify_actors: {payload['error']} missing={payload.get('missing', [])}"]

    summary = {
        "aabb": payload["aabb"],
        "actors": payload["actors"],
        "missing": payload["missing"],
    }
    result: list = [json.dumps(summary, indent=2)]
    for view in views:
        path = payload["files"].get(view)
        if not path or not os.path.exists(path):
            result.append(f"[view {view}] file missing: {path}")
            continue
        with open(path, "rb") as f:
            result.append(Image(data=f.read(), format="png"))
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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
