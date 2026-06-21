"""Lethe MCP server — lets Claude drive an Unreal Engine editor over Remote Execution.

Tools exposed:
    - execute_python(code): run arbitrary Python inside the UE editor.
    - spawn_cube(x, y, z): convenience demo that spawns a basic cube.
    - verify_actors(names, views, ...): take standard screenshots + AABB of actors.
    - polyhaven_search_hdri(query, max_results): list matching HDRIs from PolyHaven.
    - polyhaven_set_sky(slug, resolution): download + apply as HDRIBackdrop sky.
    - polyhaven_search_model(query, max_results): list matching 3D models from PolyHaven.
    - polyhaven_spawn_model(slug, ...): download glTF, import as StaticMesh, spawn actor.
    - material_synth_demo_bundle(prompt, ...): generate a synthetic demo material pack zip.
    - material_synth_corpus_index/search/fetch_manifest(...): manage local shader references.

Integration toggles (hot-switched): read on every tool call from
<UEProject>/Saved/Lethe/config.json, written by the Tools > Lethe menu in UE.
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
import urllib.request
from typing import Any

from PIL import Image as PILImage

from mcp.server.fastmcp import FastMCP, Image

from . import remote_execution as remote
from .material_synth import (
    MaterialCandidate,
    MaterialRequest,
    analyze_validation_report,
    build_reference_context,
    build_offline_demo_report,
    bundle_pack,
    export_material_pack,
    export_candidates_pack,
    generate_candidates,
    load_agent_candidates,
    rank_candidate,
    run_doctor,
    validate_agent_candidate_file,
    verify_pack,
    build_demo_bundle,
    fetch_shader_manifest,
    index_shader_corpus,
    search_shader_corpus,
)
from .material_synth.ue_bridge import build_create_material_script
from .material_synth.validator import validate_candidate, validate_hlsl_body

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


@mcp.tool()
def spawn_box(
    x: float = 0.0, y: float = 0.0, z: float = 100.0,
    sx: float = 1.0, sy: float = 1.0, sz: float = 1.0,
    pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0,
    tag: str = "",
) -> str:
    """Spawn a unit cube and immediately scale + rotate it. Returns actor name.

    A default Engine cube is 100x100x100 uu. Scale 1.0 == 100 uu == 1 m at
    default Unreal scale. Use (sx, sy, sz) to make walls/floors/furniture from
    a single primitive. Optional pitch/yaw/roll in degrees. `tag` is stored as
    an actor tag so the actor can be selected/cleared in bulk later.

    After a batch of spawns, take screenshots through verify_actors (or
    execute_python) to confirm the layout before continuing.
    """
    code = (
        "import unreal\n"
        "s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        "m = unreal.EditorAssetLibrary.load_asset('/Engine/BasicShapes/Cube.Cube')\n"
        f"loc = unreal.Vector({x}, {y}, {z})\n"
        f"rot = unreal.Rotator({roll}, {pitch}, {yaw})\n"
        "a = s.spawn_actor_from_object(m, loc, rot)\n"
        f"a.set_actor_scale3d(unreal.Vector({sx}, {sy}, {sz}))\n"
        f"_tag = {tag!r}\n"
        "if _tag:\n"
        "    a.tags = [unreal.Name(_tag)]\n"
        "print('spawned', a.get_name())\n"
    )
    return _run_in_ue(code)


@mcp.tool()
def clear_tag(tag: str) -> str:
    """Destroy every actor whose tag list contains `tag`. Returns count."""
    code = (
        "import unreal\n"
        "s = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)\n"
        f"_t = unreal.Name({tag!r})\n"
        "killed = 0\n"
        "for a in list(s.get_all_level_actors()):\n"
        "    if _t in a.tags:\n"
        "        s.destroy_actor(a); killed += 1\n"
        f"print('deleted', killed, 'actors with tag {tag}')\n"
    )
    return _run_in_ue(code)


# ---------------------------------------------------------------------------
# HLSL material synthesis
# ---------------------------------------------------------------------------


def _candidate_from_json(candidate_json: str) -> MaterialCandidate:
    try:
        payload = json.loads(candidate_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate_json is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("candidate_json must decode to an object")
    return MaterialCandidate.from_dict(payload)


@mcp.tool()
def material_synth_generate(prompt: str, count: int = 12, seed: int = 0) -> str:
    """Generate HLSL-first material candidates for a natural-language prompt.

    Stage 1 is intentionally computer-friendly: each candidate contains a
    bounded HLSL function body that targets Lethe's fixed material interface.
    The result includes static validation status so broken candidates can be
    rejected before UE sees them.
    """

    request = MaterialRequest(prompt=prompt, count=count, seed=seed)
    candidates = generate_candidates(request)
    return json.dumps(
        {
            "prompt": prompt,
            "count": len(candidates),
            "candidates": [
                {
                    **candidate.to_dict(),
                    "validation": validate_candidate(candidate).to_dict(),
                    "rank": rank_candidate(candidate, prompt),
                }
                for candidate in candidates
            ],
        },
        indent=2,
    )


@mcp.tool()
def material_synth_validate(hlsl_body: str) -> str:
    """Validate a raw Lethe HLSL material body against stage-1 guardrails."""

    return json.dumps(validate_hlsl_body(hlsl_body).to_dict(), indent=2)


@mcp.tool()
def material_synth_ue_script(
    candidate_json: str = "",
    prompt: str = "",
    variant_index: int = 0,
    package_path: str = "/Game/Lethe/GeneratedMaterials",
) -> str:
    """Build the UE Python script that creates a Material from one candidate.

    Pass either a full `candidate_json` object returned by
    `material_synth_generate`, or pass `prompt` and `variant_index` to generate
    locally and select a variant.
    """

    if candidate_json:
        candidate = _candidate_from_json(candidate_json)
    else:
        if not prompt:
            raise ValueError("Provide either candidate_json or prompt")
        candidates = generate_candidates(MaterialRequest(prompt=prompt, count=max(variant_index + 1, 1)))
        candidate = candidates[variant_index]

    validation = validate_candidate(candidate)
    if not validation.ok:
        return json.dumps(
            {
                "error": "candidate failed validation",
                "validation": validation.to_dict(),
            },
            indent=2,
        )
    return build_create_material_script(candidate, package_path=package_path)


@mcp.tool()
def material_synth_create_in_ue(
    prompt: str,
    variant_index: int = 0,
    package_path: str = "/Game/Lethe/GeneratedMaterials",
) -> str:
    """Generate a candidate and execute the material creation script in UE.

    Requires a running Unreal Editor with the Lethe plugin and Remote Execution
    enabled. Use this after `material_synth_generate` when you want the real UE
    asset created and compiled by the editor.
    """

    candidates = generate_candidates(MaterialRequest(prompt=prompt, count=max(variant_index + 1, 1)))
    candidate = candidates[variant_index]
    validation = validate_candidate(candidate)
    if not validation.ok:
        return json.dumps(
            {
                "error": "candidate failed validation",
                "validation": validation.to_dict(),
            },
            indent=2,
        )
    return _run_in_ue(build_create_material_script(candidate, package_path=package_path))


@mcp.tool()
def material_synth_export_pack(
    prompt: str,
    count: int = 12,
    seed: int = 0,
    output_dir: str = "material-packs",
    include_ue_scripts: bool = True,
    corpus_index: str = "",
    reference_limit: int = 5,
    require_reference_allowed: bool = False,
) -> str:
    """Export an offline HLSL material candidate pack for review or UE replay.

    The pack contains `manifest.json`, `index.md`, candidate HLSL files, and
    optional UE Python scripts that create Material assets from each candidate.
    This works without a running Unreal Editor.
    """

    try:
        reference_context = (
            build_reference_context(
                corpus_index,
                prompt,
                limit=reference_limit,
                require_reference_allowed=require_reference_allowed,
            )
            if corpus_index
            else None
        )
        manifest = export_material_pack(
            MaterialRequest(prompt=prompt, count=count, seed=seed),
            output_dir,
            include_ue_scripts=include_ue_scripts,
            reference_context=reference_context,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "prompt": prompt}, indent=2)
    return json.dumps(
        {
            "pack_id": manifest["pack_id"],
            "pack_dir": manifest["pack_dir"],
            "candidate_count": manifest["candidate_count"],
            "reference_matches": len((manifest.get("reference_context") or {}).get("matches", [])),
            "manifest": os.path.join(manifest["pack_dir"], "manifest.json"),
            "index": os.path.join(manifest["pack_dir"], "index.md"),
            "ue_replay_script": (
                os.path.join(manifest["pack_dir"], manifest["files"]["ue_replay_script"])
                if manifest["files"].get("ue_replay_script")
                else None
            ),
            "ue_validation_report": (
                os.path.join(manifest["pack_dir"], manifest["files"]["ue_validation_report"])
                if manifest["files"].get("ue_validation_report")
                else None
            ),
            "preview_dir": (
                os.path.join(manifest["pack_dir"], manifest["files"]["preview_dir"])
                if manifest["files"].get("preview_dir")
                else None
            ),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_export_agent_pack(
    json_path: str,
    output_dir: str = "material-packs",
    include_ue_scripts: bool = True,
) -> str:
    """Export a material pack from external agent candidate JSON."""

    try:
        request, candidates = load_agent_candidates(json_path)
    except Exception as exc:
        return json.dumps({"error": str(exc), "json_path": os.path.abspath(json_path)}, indent=2)
    manifest = export_candidates_pack(
        request,
        candidates,
        output_dir,
        include_ue_scripts=include_ue_scripts,
        source="agent_json",
    )
    return json.dumps(
        {
            "pack_id": manifest["pack_id"],
            "pack_dir": manifest["pack_dir"],
            "candidate_count": manifest["candidate_count"],
            "agent_count": manifest["agent_count"],
            "manifest": os.path.join(manifest["pack_dir"], "manifest.json"),
            "index": os.path.join(manifest["pack_dir"], "index.md"),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_validate_agent_json(json_path: str, report_path: str = "") -> str:
    """Validate external agent candidate JSON before packing or UE replay."""

    try:
        report = validate_agent_candidate_file(json_path, report_path or None)
    except Exception as exc:
        return json.dumps({"error": str(exc), "json_path": os.path.abspath(json_path)}, indent=2)
    return json.dumps(report, indent=2)


@mcp.tool()
def material_synth_replay_pack_in_ue(pack_dir: str) -> str:
    """Run a generated material pack's `run_pack_in_ue.py` inside Unreal Editor.

    Requires a running Unreal Editor with Remote Execution enabled. The pack can
    be produced by `material_synth_export_pack` or the CLI.
    """

    script_path = os.path.abspath(os.path.join(pack_dir, "run_pack_in_ue.py"))
    manifest_path = os.path.abspath(os.path.join(pack_dir, "manifest.json"))
    if not os.path.exists(manifest_path):
        return json.dumps(
            {
                "error": "manifest.json not found",
                "pack_dir": os.path.abspath(pack_dir),
            },
            indent=2,
        )
    if not os.path.exists(script_path):
        return json.dumps(
            {
                "error": "run_pack_in_ue.py not found",
                "pack_dir": os.path.abspath(pack_dir),
            },
            indent=2,
        )
    with open(script_path, "r", encoding="utf-8") as handle:
        return _run_in_ue(handle.read())


@mcp.tool()
def material_synth_analyze_pack(pack_dir: str) -> str:
    """Analyze a pack's UE replay report and write customer_summary files.

    Run this after `material_synth_replay_pack_in_ue` has produced
    `ue_validation_report.json`.
    """

    try:
        summary = analyze_validation_report(pack_dir)
    except FileNotFoundError as exc:
        return json.dumps({"error": str(exc), "pack_dir": os.path.abspath(pack_dir)}, indent=2)
    return json.dumps(
        {
            "pack_dir": summary["pack_dir"],
            "count": summary["count"],
            "created": summary["created"],
            "previewed": summary["previewed"],
            "recommended": summary["recommended"],
            "summary_json": os.path.join(summary["pack_dir"], "customer_summary.json"),
            "summary_md": os.path.join(summary["pack_dir"], "customer_summary.md"),
            "gallery_html": os.path.join(summary["pack_dir"], "customer_gallery.html"),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_demo_pack(pack_dir: str) -> str:
    """Create synthetic previews and customer gallery for an existing pack.

    This does not run Unreal Editor. Use only for offline product demos.
    """

    try:
        result = build_offline_demo_report(pack_dir)
    except Exception as exc:
        return json.dumps({"error": str(exc), "pack_dir": os.path.abspath(pack_dir)}, indent=2)
    return json.dumps(
        {
            "pack_dir": result["pack_dir"],
            "gallery": result["gallery"],
            "count": result["report"]["count"],
            "synthetic_demo": True,
        },
        indent=2,
    )


@mcp.tool()
def material_synth_verify_pack(pack_dir: str, mode: str = "pack") -> str:
    """Verify material pack artifact completeness.

    mode: pack, offline-demo, or ue.
    """

    try:
        report = verify_pack(pack_dir, mode=mode)
    except Exception as exc:
        return json.dumps({"error": str(exc), "pack_dir": os.path.abspath(pack_dir)}, indent=2)
    return json.dumps(report, indent=2)


@mcp.tool()
def material_synth_bundle_pack(
    pack_dir: str,
    output_zip: str = "",
    mode: str = "pack",
    allow_failed: bool = False,
) -> str:
    """Verify and zip a material pack for sharing."""

    try:
        result = bundle_pack(
            pack_dir,
            output_zip=output_zip or None,
            mode=mode,
            allow_failed=allow_failed,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "pack_dir": os.path.abspath(pack_dir)}, indent=2)
    return json.dumps(result, indent=2)


@mcp.tool()
def material_synth_demo_bundle(
    prompt: str,
    count: int = 12,
    seed: int = 0,
    output_dir: str = "material-packs",
    output_zip: str = "",
    corpus_index: str = "",
    reference_limit: int = 5,
    require_reference_allowed: bool = False,
) -> str:
    """Generate, synthetic-preview, verify, and zip a material demo pack."""

    try:
        result = build_demo_bundle(
            prompt,
            output_dir=output_dir,
            count=count,
            seed=seed,
            output_zip=output_zip or None,
            corpus_index=corpus_index or None,
            reference_limit=reference_limit,
            require_reference_allowed=require_reference_allowed,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "prompt": prompt}, indent=2)
    return json.dumps(
        {
            "ok": result["ok"],
            "pack_dir": result["pack_dir"],
            "gallery": result["gallery"],
            "zip": result["zip"],
            "count": result["count"],
            "synthetic_demo": True,
            "reference_matches": len((result.get("reference_context") or {}).get("matches", [])),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_corpus_index(
    roots: list[str],
    output: str = "material-corpus/index.json",
    source_label: str = "local",
    license_label: str = "unknown",
    max_indexed_bytes: int = 524288,
    extensions: str = "",
) -> str:
    """Index local HLSL/GLSL/USH/USF reference files without copying full source."""

    try:
        extension_list = [item.strip() for item in extensions.split(",") if item.strip()] if extensions else None
        result = index_shader_corpus(
            roots,
            output,
            source_label=source_label,
            license_label=license_label,
            max_indexed_bytes=max_indexed_bytes,
            extensions=extension_list,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "roots": roots}, indent=2)
    return json.dumps(
        {
            "index_path": result["index_path"],
            "file_count": result["file_count"],
            "total_bytes": result["total_bytes"],
            "reference_allowed": result["reference_allowed"],
            "skipped": len(result["skipped"]),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_corpus_search(
    index_path: str,
    query: str,
    limit: int = 10,
    require_reference_allowed: bool = False,
) -> str:
    """Search a local shader corpus index and return snippets plus risk notes."""

    try:
        result = search_shader_corpus(
            index_path,
            query,
            limit=limit,
            require_reference_allowed=require_reference_allowed,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "index_path": os.path.abspath(index_path)}, indent=2)
    return json.dumps(
        {
            "ok": result["ok"],
            "query": result["query"],
            "index_path": result["index_path"],
            "license_label": result.get("license_label"),
            "reference_allowed": result.get("reference_allowed"),
            "matches": [
                {
                    "score": item["score"],
                    "path": item["entry"]["path"],
                    "rel_path": item["entry"]["rel_path"],
                    "language": item["entry"]["language"],
                    "license": item["entry"]["license"],
                    "risk_notes": item["risk_notes"],
                    "snippet": item["snippet"],
                }
                for item in result.get("matches", [])
            ],
            "error": result.get("error"),
        },
        indent=2,
    )


@mcp.tool()
def material_synth_corpus_fetch_manifest(
    manifest_json: str,
    output_dir: str = "material-corpus/raw",
    index_output: str = "material-corpus/index.json",
    allow_unsafe: bool = False,
    max_bytes: int = 1048576,
    timeout_seconds: int = 30,
) -> str:
    """Download explicit shader URLs from a manifest, record provenance, and index them.

    This is not a Fab/Marketplace bypass scraper. Unknown or commercial-license
    items are skipped by default; use allow_unsafe only for discovery metadata.
    """

    try:
        report = fetch_shader_manifest(
            manifest_json,
            output_dir=output_dir,
            index_output=index_output,
            allow_unsafe=allow_unsafe,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc), "manifest_json": os.path.abspath(manifest_json)}, indent=2)
    return json.dumps(
        {
            "downloaded": report["downloaded"],
            "skipped": report["skipped_count"],
            "failed": report["failed_count"],
            "raw_root": report["raw_root"],
            "report_path": report["report_path"],
            "index_path": report["index_path"],
            "indexed_files": report["indexed_files"],
            "reference_allowed": report["reference_allowed"],
        },
        indent=2,
    )


@mcp.tool()
def material_synth_doctor(ue_project: str = "") -> str:
    """Read-only readiness check for local material synth and optional UE project."""

    return json.dumps(run_doctor(ue_project or None, repo_root=os.getcwd()), indent=2)


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

    _world = _ued_subsys.get_editor_world()
    _rt = unreal.RenderingLibrary.create_render_target2d(
        _world, LETHE_W, LETHE_H, unreal.TextureRenderTargetFormat.RTF_RGBA8)

    _save_dir = unreal.Paths.convert_relative_path_to_full(
        os.path.join(unreal.Paths.project_saved_dir(), "LetheShots"))
    os.makedirs(_save_dir, exist_ok=True)
    _files = {}
    for _view in LETHE_VIEWS:
        if _view not in _offsets:
            continue
        _ox, _oy, _oz = _offsets[_view]
        _cam = unreal.Vector(_C.x + _ox, _C.y + _oy, _C.z + _oz)
        _rot = _lethe_look_at(_cam, _C)
        _sc = _actor_subsys.spawn_actor_from_class(unreal.SceneCapture2D, _cam, _rot)
        try:
            _comp = _sc.capture_component2d
            _comp.texture_target = _rt
            _comp.fov_angle = LETHE_FOV
            _comp.capture_source = unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR
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
            png_data = f.read()
        buf = io.BytesIO()
        PILImage.open(io.BytesIO(png_data)).convert("RGB").save(buf, format="JPEG", quality=85)
        result.append(Image(data=buf.getvalue(), format="jpeg"))
    return result


# ---------------------------------------------------------------------------
# PolyHaven HDRI — search + apply as HDRIBackdrop sky
# ---------------------------------------------------------------------------

_POLYHAVEN_API = "https://api.polyhaven.com"
_ue_saved_dir_cache: str | None = None
_polyhaven_assets_cache: dict[str, dict] = {}


def _ue_saved_dir() -> str:
    """Query UE for its project Saved dir and cache the absolute path."""
    global _ue_saved_dir_cache
    if _ue_saved_dir_cache is None:
        probe = (
            "import unreal\n"
            "print('LETHE_PATH::' + unreal.Paths.convert_relative_path_to_full("
            "unreal.Paths.project_saved_dir()))\n"
        )
        out = _run_in_ue(probe)
        for line in out.splitlines():
            tag = "LETHE_PATH::"
            idx = line.find(tag)
            if idx >= 0:
                _ue_saved_dir_cache = line[idx + len(tag):].strip()
                break
        if not _ue_saved_dir_cache:
            raise RuntimeError(f"Could not query UE project Saved dir. UE output:\n{out}")
    return _ue_saved_dir_cache


def _read_lethe_config() -> dict:
    """Read Tools > Lethe toggle state from disk — fresh every call (hot-switch)."""
    cfg_path = os.path.join(_ue_saved_dir(), "Lethe", "config.json")
    if not os.path.exists(cfg_path):
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not read %s: %s", cfg_path, e)
        return {}


def _gate(integration: str) -> str | None:
    """Returns None if the integration is enabled, else a message to bounce back to Claude."""
    if not _read_lethe_config().get(integration, False):
        return (
            f"{integration} integration is disabled. In the UE editor, enable it "
            f"via Tools > Lethe > {integration.capitalize()}, then call again. "
            "(Setting is hot-switched — no restart needed.)"
        )
    return None


def _http_get_json(url: str, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "lethe-mcp/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_download(url: str, dest: str, timeout: float = 120.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "lethe-mcp/0.1"})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)


def _polyhaven_assets(asset_type: str = "hdris") -> dict:
    if asset_type not in _polyhaven_assets_cache:
        _polyhaven_assets_cache[asset_type] = _http_get_json(
            f"{_POLYHAVEN_API}/assets?t={asset_type}"
        )
    return _polyhaven_assets_cache[asset_type]


_SET_SKY_SCRIPT = r'''
import unreal, json, os

_PATH = r"{local_path}".replace("\\", "/")
_SLUG = "{slug}"
_PKG_DIR = "/Game/Lethe/HDRI"
_ASSET_PATH = _PKG_DIR + "/" + _SLUG
_ACTOR_TAG = "LetheSky"

# --- Import the .hdr file as a Texture2D asset ----------------------------
_task = unreal.AssetImportTask()
_task.filename = _PATH
_task.destination_path = _PKG_DIR
_task.destination_name = _SLUG
_task.automated = True
_task.replace_existing = True
_task.save = True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([_task])
_tex = unreal.EditorAssetLibrary.load_asset(_ASSET_PATH)

if _tex is None:
    print("LETHE_JSON::" + json.dumps({{"error": "HDR import failed", "path": _PATH}}))
else:
    _subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # --- Find or spawn a single tagged HDRIBackdrop ----------------------
    _backdrop = None
    for _a in _subsys.get_all_level_actors():
        if _a.actor_has_tag(_ACTOR_TAG):
            _backdrop = _a
            break

    _hdri_class = unreal.load_class(None, "/Script/HDRIBackdrop.HDRIBackdrop")
    if _hdri_class is None:
        print("LETHE_JSON::" + json.dumps({{"error": "HDRIBackdrop plugin not enabled. Enable the Lethe plugin (which depends on it) and restart the editor."}}))
    else:
        if _backdrop is None:
            _backdrop = _subsys.spawn_actor_from_class(_hdri_class, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            _backdrop.tags = [_ACTOR_TAG]
            _backdrop.set_actor_label("Lethe_Sky")

        _backdrop.set_editor_property("cubemap", _tex)

        print("LETHE_JSON::" + json.dumps({{
            "ok": True,
            "asset": _ASSET_PATH,
            "actor": _backdrop.get_name(),
            "spawned_new": bool(not _backdrop.actor_has_tag(_ACTOR_TAG + "_existing")),
        }}))
'''


@mcp.tool()
def polyhaven_status() -> str:
    """Report whether PolyHaven integration is currently enabled (via Tools > Lethe).

    If disabled, the other polyhaven_* tools will refuse to run — tell the user
    to enable it in the editor menu first.
    """
    enabled = _read_lethe_config().get("polyhaven", False)
    return json.dumps({
        "polyhaven": "enabled" if enabled else "disabled",
        "hint": None if enabled else "Enable via Tools > Lethe > PolyHaven in the editor.",
    })


@mcp.tool()
def polyhaven_search_hdri(query: str = "", max_results: int = 20) -> str:
    """Search PolyHaven's HDRI library. Returns JSON list of matches.

    Use the returned `slug` as input to `polyhaven_set_sky`. Empty query lists
    recent/featured HDRIs up to max_results.
    """
    gate = _gate("polyhaven")
    if gate:
        return gate

    assets = _polyhaven_assets("hdris")
    q = query.lower().strip()
    hits = []
    for slug, meta in assets.items():
        name = (meta.get("name") or slug).lower()
        cats = [c.lower() for c in meta.get("categories", [])]
        tags = [t.lower() for t in meta.get("tags", [])]
        if not q or q in slug.lower() or q in name or any(q in c for c in cats) or any(q in t for t in tags):
            hits.append({
                "slug": slug,
                "name": meta.get("name") or slug,
                "categories": meta.get("categories", []),
                "tags": meta.get("tags", [])[:6],
            })
            if len(hits) >= max_results:
                break
    return json.dumps({"count": len(hits), "results": hits}, indent=2)


_SPAWN_MODEL_SCRIPT = r'''
import unreal, json, os, glob

_GLTF_PATH = r"{gltf_path}".replace("\\", "/")
_SLUG = "{slug}"
_DEST_DIR = "/Game/Lethe/Models/" + _SLUG
_LOC = unreal.Vector({x}, {y}, {z})
_ROT = unreal.Rotator(0.0, 0.0, {yaw})
_SCALE = {scale}
_TAG = "{tag}"

# --- Import via AssetImportTask (UE5.5 picks Interchange for glTF) ----------
_task = unreal.AssetImportTask()
_task.filename = _GLTF_PATH
_task.destination_path = _DEST_DIR
_task.replace_existing = True
_task.automated = True
_task.save = True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([_task])

# Find the imported StaticMesh (Interchange names it after the gltf basename)
_mesh = None
_reg = unreal.AssetRegistryHelpers.get_asset_registry()
_assets = _reg.get_assets_by_path(_DEST_DIR, recursive=True)
for _ad in _assets:
    _a = _ad.get_asset()
    if isinstance(_a, unreal.StaticMesh):
        _mesh = _a
        break

if _mesh is None:
    print("LETHE_JSON::" + json.dumps({{
        "error": "No StaticMesh imported under " + _DEST_DIR,
        "files_seen": [str(a.asset_name) for a in _assets][:10],
    }}))
else:
    _eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    _actor = _eas.spawn_actor_from_object(_mesh, _LOC, _ROT)
    _actor.set_actor_scale3d(unreal.Vector(_SCALE, _SCALE, _SCALE))
    if _TAG:
        _actor.tags = [unreal.Name(_TAG)]
    print("LETHE_JSON::" + json.dumps({{
        "ok": True,
        "mesh": _mesh.get_path_name(),
        "actor": _actor.get_name(),
    }}))
'''


@mcp.tool()
def polyhaven_search_model(query: str = "", max_results: int = 20) -> str:
    """Search PolyHaven's 3D model library. Returns JSON list of matches.

    Use the returned `slug` as input to `polyhaven_spawn_model`. Empty query
    lists recent/featured models up to max_results. Models are CC0, downloaded
    as glTF and imported via UE5.5 Interchange.
    """
    gate = _gate("polyhaven")
    if gate:
        return gate

    assets = _polyhaven_assets("models")
    q = query.lower().strip()
    hits = []
    for slug, meta in assets.items():
        name = (meta.get("name") or slug).lower()
        cats = [c.lower() for c in meta.get("categories", [])]
        tags = [t.lower() for t in meta.get("tags", [])]
        if not q or q in slug.lower() or q in name or any(q in c for c in cats) or any(q in t for t in tags):
            hits.append({
                "slug": slug,
                "name": meta.get("name") or slug,
                "categories": meta.get("categories", []),
                "tags": meta.get("tags", [])[:6],
            })
            if len(hits) >= max_results:
                break
    return json.dumps({"count": len(hits), "results": hits}, indent=2)


@mcp.tool()
def polyhaven_spawn_model(
    slug: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    yaw: float = 0.0,
    scale: float = 1.0,
    resolution: str = "2k",
    tag: str = "",
) -> str:
    """Download a PolyHaven 3D model (glTF), import as StaticMesh, spawn at (x,y,z).

    Assets cached under <UEProject>/Saved/Lethe/Downloads/Models/<slug>/ and
    imported to /Game/Lethe/Models/<slug>/. Textures bundled in the glTF file
    are downloaded alongside and resolved during import.

    `resolution` controls texture resolution ('1k','2k','4k') — falls back to
    the highest available if requested resolution is missing. `scale` is a
    uniform multiplier (1.0 = source scale; PolyHaven models are real-world
    metric, so 1.0 ≈ 1 m at default Unreal scale).
    """
    gate = _gate("polyhaven")
    if gate:
        return gate

    try:
        files = _http_get_json(f"{_POLYHAVEN_API}/files/{slug}")
    except Exception as e:
        return f"Could not fetch files manifest for slug '{slug}': {e}"

    gltf_section = files.get("gltf") or {}
    if not gltf_section:
        return f"No glTF for '{slug}'. Available formats: {sorted(files.keys())}"

    # Pick resolution: prefer requested, else first available
    if resolution not in gltf_section:
        avail = sorted(gltf_section.keys())
        if not avail:
            return f"No glTF resolutions for '{slug}'."
        resolution = avail[-1]
    gltf_info = gltf_section[resolution].get("gltf") or {}
    gltf_url = gltf_info.get("url")
    if not gltf_url:
        return f"No glTF file URL for '{slug}' at {resolution}. Got: {gltf_section[resolution]}"

    # Set up local cache dir, mirror PolyHaven's "include" map (textures, .bin)
    cache_root = os.path.join(_ue_saved_dir(), "Lethe", "Downloads", "Models", slug)
    os.makedirs(cache_root, exist_ok=True)
    gltf_name = os.path.basename(gltf_url.split("?")[0])
    gltf_local = os.path.join(cache_root, gltf_name)
    if not os.path.exists(gltf_local):
        try:
            _http_download(gltf_url, gltf_local)
        except Exception as e:
            return f"glTF download failed ({gltf_url}): {e}"

    # Download all referenced sidecar files (textures, .bin) into matching paths
    include = gltf_info.get("include") or {}
    for rel_path, info in include.items():
        url = info.get("url")
        if not url:
            continue
        dest = os.path.join(cache_root, rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            try:
                _http_download(url, dest)
            except Exception as e:
                return f"Sidecar download failed ({url} -> {dest}): {e}"

    # Hand off to UE: import + spawn
    script = _SPAWN_MODEL_SCRIPT.format(
        gltf_path=gltf_local.replace("\\", "\\\\"),
        slug=slug,
        x=x, y=y, z=z, yaw=yaw, scale=scale,
        tag=tag,
    )
    stdout = _run_in_ue(script)
    payload = None
    for line in stdout.splitlines():
        tag_marker = "LETHE_JSON::"
        idx = line.find(tag_marker)
        if idx >= 0:
            try:
                payload = json.loads(line[idx + len(tag_marker):])
            except Exception:
                pass
            break
    if payload is None:
        return f"Unexpected UE output:\n{stdout}"
    if "error" in payload:
        return f"polyhaven_spawn_model: {payload['error']}\nFull UE output:\n{stdout}"
    return json.dumps({
        "ok": True,
        "slug": slug,
        "resolution": resolution,
        "local_file": gltf_local,
        "mesh": payload["mesh"],
        "actor": payload["actor"],
    }, indent=2)


@mcp.tool()
def polyhaven_set_sky(slug: str, resolution: str = "2k") -> str:
    """Download a PolyHaven HDRI and set it as the current level's sky.

    Creates or reuses a tagged HDRIBackdrop actor so repeated calls swap the sky
    instead of stacking backdrops. Assets are cached under
    <UEProject>/Saved/Lethe/Downloads/HDRI/ and imported to /Game/Lethe/HDRI/.

    Typical resolutions: '1k', '2k', '4k', '8k'. 2k is a good default.
    """
    gate = _gate("polyhaven")
    if gate:
        return gate

    # Resolve download URL via PolyHaven files API
    try:
        files = _http_get_json(f"{_POLYHAVEN_API}/files/{slug}")
    except Exception as e:
        return f"Could not fetch files manifest for slug '{slug}': {e}"

    hdri_section = files.get("hdri") or {}
    if resolution not in hdri_section:
        return f"No {resolution} HDR for '{slug}'. Available: {sorted(hdri_section.keys())}"
    hdr_info = hdri_section[resolution].get("hdr") or {}
    url = hdr_info.get("url")
    if not url:
        return f"No 'hdr' format for '{slug}' at {resolution}. Got: {hdri_section[resolution]}"

    # Cache download under <UEProject>/Saved/Lethe/Downloads/HDRI/
    cache_dir = os.path.join(_ue_saved_dir(), "Lethe", "Downloads", "HDRI")
    os.makedirs(cache_dir, exist_ok=True)
    local_path = os.path.join(cache_dir, f"{slug}_{resolution}.hdr")
    if not os.path.exists(local_path):
        logger.info("Downloading %s -> %s", url, local_path)
        try:
            _http_download(url, local_path)
        except Exception as e:
            return f"Download failed ({url}): {e}"

    # Hand off to UE: import + apply
    script = _SET_SKY_SCRIPT.format(
        local_path=local_path.replace("\\", "\\\\"),
        slug=slug,
    )
    stdout = _run_in_ue(script)
    payload = None
    for line in stdout.splitlines():
        tag = "LETHE_JSON::"
        idx = line.find(tag)
        if idx >= 0:
            try:
                payload = json.loads(line[idx + len(tag):])
            except Exception:
                pass
            break
    if payload is None:
        return f"Unexpected UE output:\n{stdout}"
    if "error" in payload:
        return f"polyhaven_set_sky: {payload['error']}"
    return json.dumps({
        "ok": True,
        "slug": slug,
        "resolution": resolution,
        "local_file": local_path,
        "asset": payload["asset"],
        "actor": payload["actor"],
    }, indent=2)


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
