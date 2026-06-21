"""UE Python script generation for HLSL material candidates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import MaterialCandidate, slugify
from .templates import build_channel_custom_code


def build_create_material_script(
    candidate: MaterialCandidate,
    package_path: str = "/Game/Lethe/GeneratedMaterials",
) -> str:
    """Return a UE Python script that creates a material from a candidate.

    This script is meant for Unreal Remote Execution. It creates a Material
    asset, wires a small set of engine expression inputs into Custom HLSL nodes,
    connects BaseColor/Emissive/Roughness/Alpha, then saves the asset.
    """

    material_name = "M_" + slugify(candidate.name, fallback=candidate.id)[:54]
    base_code = build_channel_custom_code(candidate, "BaseColor")
    emissive_code = build_channel_custom_code(candidate, "Emissive")
    roughness_code = build_channel_custom_code(candidate, "Roughness")
    alpha_code = build_channel_custom_code(candidate, "Alpha")
    metadata = json.dumps(candidate.to_dict(), ensure_ascii=True)

    return f"""
import json
import unreal

PACKAGE_PATH = {package_path!r}
MATERIAL_NAME = {material_name!r}
METADATA = json.loads({metadata!r})

BASE_CODE = {base_code!r}
EMISSIVE_CODE = {emissive_code!r}
ROUGHNESS_CODE = {roughness_code!r}
ALPHA_CODE = {alpha_code!r}

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
factory = unreal.MaterialFactoryNew()
mat = asset_tools.create_asset(MATERIAL_NAME, PACKAGE_PATH, unreal.Material, factory)
if mat is None:
    mat = unreal.EditorAssetLibrary.load_asset(PACKAGE_PATH + "/" + MATERIAL_NAME)

if mat is None:
    raise RuntimeError("Could not create or load material asset")

mat.set_editor_property("use_material_attributes", False)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT)

mel = unreal.MaterialEditingLibrary

uv = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -900, -300)
time_node = mel.create_material_expression(mat, unreal.MaterialExpressionTime, -900, -160)
world = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -900, -20)
normal = mel.create_material_expression(mat, unreal.MaterialExpressionPixelNormalWS, -900, 120)
camera = mel.create_material_expression(mat, unreal.MaterialExpressionCameraVectorWS, -900, 260)

def make_custom(code, output_type, x, y):
    node = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, x, y)
    node.set_editor_property("code", code)
    node.set_editor_property("description", "Lethe generated HLSL")
    node.set_editor_property("output_type", output_type)
    inputs = []
    for name in ["UV", "WorldPos", "Normal", "CameraVector", "Time"]:
        inp = unreal.CustomInput()
        try:
            inp.set_editor_property("input_name", name)
        except Exception:
            inp.input_name = name
        inputs.append(inp)
    node.set_editor_property("inputs", inputs)
    mel.connect_material_expressions(uv, "", node, "UV")
    mel.connect_material_expressions(world, "", node, "WorldPos")
    mel.connect_material_expressions(normal, "", node, "Normal")
    mel.connect_material_expressions(camera, "", node, "CameraVector")
    mel.connect_material_expressions(time_node, "", node, "Time")
    return node

base = make_custom(BASE_CODE, unreal.CustomMaterialOutputType.CMOT_FLOAT3, -420, -220)
emissive = make_custom(EMISSIVE_CODE, unreal.CustomMaterialOutputType.CMOT_FLOAT3, -420, 40)
roughness = make_custom(ROUGHNESS_CODE, unreal.CustomMaterialOutputType.CMOT_FLOAT1, -420, 300)
alpha = make_custom(ALPHA_CODE, unreal.CustomMaterialOutputType.CMOT_FLOAT1, -420, 520)

mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.connect_material_property(roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(alpha, "", unreal.MaterialProperty.MP_OPACITY)

unreal.EditorAssetLibrary.set_metadata_tag(mat, "LetheCandidateId", METADATA["id"])
unreal.EditorAssetLibrary.set_metadata_tag(mat, "LethePrompt", METADATA["prompt"])
unreal.EditorAssetLibrary.set_metadata_tag(mat, "LetheDescription", METADATA["description"])

unreal.EditorAssetLibrary.save_loaded_asset(mat)
mel.layout_material_expressions(mat)

print("LETHE_MATERIAL_JSON::" + json.dumps({{
    "ok": True,
    "asset": mat.get_path_name(),
    "candidate_id": METADATA["id"],
    "name": MATERIAL_NAME,
}}))
""".strip()


def build_pack_replay_script(
    manifest: dict[str, Any],
    pack_dir: str | Path,
    report_name: str = "ue_validation_report.json",
) -> str:
    """Return a UE Python script that replays every candidate script in a pack.

    The replay script is designed to live in the pack root. It executes each
    per-candidate UE script, captures the `LETHE_MATERIAL_JSON` payload, writes
    a machine-readable report, and prints a summary marker for Remote Execution.
    """

    pack_root = str(Path(pack_dir).resolve())
    replay_items = []
    for candidate in manifest.get("candidates", []):
        files = candidate.get("files", {})
        ue_script = files.get("ue_script")
        if not ue_script:
            continue
        replay_items.append(
            {
                "id": candidate["id"],
                "order": candidate.get("order"),
                "name": candidate.get("name"),
                "generation": candidate.get("generation", {}),
                "ue_script": ue_script,
            }
        )

    return f"""
import contextlib
import io
import json
import os
import traceback
import unreal

PACK_DIR = {pack_root!r}
REPORT_PATH = os.path.join(PACK_DIR, {report_name!r})
PREVIEW_DIR = os.path.join(PACK_DIR, "previews")
ITEMS = json.loads({json.dumps(replay_items, ensure_ascii=True)!r})
PREVIEW_TAG = "LetheMaterialSynthPreview"
os.makedirs(PREVIEW_DIR, exist_ok=True)

def _extract_payload(stdout):
    marker = "LETHE_MATERIAL_JSON::"
    for line in stdout.splitlines():
        idx = line.find(marker)
        if idx >= 0:
            return json.loads(line[idx + len(marker):])
    return None

def _try_recompile(asset_path):
    result = {{"attempted": False, "ok": None, "error": None}}
    try:
        mat = unreal.EditorAssetLibrary.load_asset(asset_path)
        if mat is None:
            result["error"] = "asset load returned None"
            return result
        mel = unreal.MaterialEditingLibrary
        if hasattr(mel, "recompile_material"):
            result["attempted"] = True
            mel.recompile_material(mat)
            result["ok"] = True
        elif hasattr(mel, "update_material_function"):
            result["error"] = "recompile_material unavailable in this UE Python API"
        else:
            result["error"] = "no known material recompile API exposed"
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
    return result

def _look_at(cam, tgt):
    import math
    dx = tgt.x - cam.x
    dy = tgt.y - cam.y
    dz = tgt.z - cam.z
    yaw = math.degrees(math.atan2(dy, dx))
    d2 = math.sqrt(dx * dx + dy * dy)
    pitch = math.degrees(math.atan2(dz, d2)) if d2 > 1e-6 else (90.0 if dz > 0 else -90.0)
    return unreal.Rotator(pitch=pitch, yaw=yaw, roll=0.0)

def _clear_preview_actors(actor_subsys):
    killed = 0
    for actor in list(actor_subsys.get_all_level_actors()):
        try:
            if actor.actor_has_tag(PREVIEW_TAG):
                actor_subsys.destroy_actor(actor)
                killed += 1
        except Exception:
            pass
    return killed

def _capture_preview(asset_path, candidate_id, order):
    result = {{"attempted": True, "ok": False, "path": None, "error": None}}
    actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    editor_subsys = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor_subsys.get_editor_world()
    mat = unreal.EditorAssetLibrary.load_asset(asset_path)
    mesh = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane.Plane")
    if mat is None:
        result["error"] = "material asset load returned None"
        return result
    if mesh is None:
        result["error"] = "preview plane mesh not found"
        return result

    x = float((order or 1) - 1) * 240.0
    actor = None
    capture = None
    key_light = None
    sun = None
    try:
        actor = actor_subsys.spawn_actor_from_object(mesh, unreal.Vector(x, 0, 80), unreal.Rotator(0, 0, 0))
        actor.tags = [unreal.Name(PREVIEW_TAG)]
        actor.set_actor_label("LethePreview_" + str(candidate_id))
        actor.set_actor_scale3d(unreal.Vector(5.0, 5.0, 1.0))
        comp = actor.static_mesh_component
        comp.set_material(0, mat)

        try:
            key_light = actor_subsys.spawn_actor_from_class(
                unreal.PointLight,
                unreal.Vector(x - 180, -260, 280),
                unreal.Rotator(0, 0, 0),
            )
            key_light.tags = [unreal.Name(PREVIEW_TAG)]
            key_comp = key_light.get_component_by_class(unreal.PointLightComponent)
            if key_comp:
                key_comp.set_editor_property("intensity", 1400.0)
                key_comp.set_editor_property("attenuation_radius", 900.0)
        except Exception:
            key_light = None

        try:
            sun = actor_subsys.spawn_actor_from_class(
                unreal.DirectionalLight,
                unreal.Vector(x - 120, -160, 320),
                unreal.Rotator(-45, -35, 0),
            )
            sun.tags = [unreal.Name(PREVIEW_TAG)]
            sun_comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
            if sun_comp:
                sun_comp.set_editor_property("intensity", 4.0)
        except Exception:
            sun = None

        rt = unreal.RenderingLibrary.create_render_target2d(
            world, 512, 512, unreal.TextureRenderTargetFormat.RTF_RGBA8)
        unreal.RenderingLibrary.clear_render_target2d(world, rt, unreal.LinearColor(0.04, 0.08, 0.12, 1.0))
        target = unreal.Vector(x, 0, 100)
        cam = unreal.Vector(x, -520, 360)
        capture = actor_subsys.spawn_actor_from_class(unreal.SceneCapture2D, cam, _look_at(cam, target))
        capture.tags = [unreal.Name(PREVIEW_TAG)]
        cap = capture.capture_component2d
        cap.texture_target = rt
        cap.fov_angle = 38.0
        try:
            cap.capture_source = unreal.SceneCaptureSource.SCS_BASE_COLOR
        except Exception:
            cap.capture_source = unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR
        cap.show_flag_settings = []
        try:
            unreal.EditorLevelLibrary.editor_invalidate_viewports()
        except Exception:
            pass
        cap.capture_scene()
        file_name = str(order).zfill(3) + "_" + str(candidate_id) + ".png"
        unreal.RenderingLibrary.export_render_target(world, rt, PREVIEW_DIR, file_name)
        result["path"] = os.path.join(PREVIEW_DIR, file_name)
        result["ok"] = os.path.exists(result["path"])
        if not result["ok"]:
            result["error"] = "preview file was not written"
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        for spawned in [capture, sun, key_light, actor]:
            try:
                if spawned is not None:
                    actor_subsys.destroy_actor(spawned)
            except Exception:
                pass
    return result

results = []
_clear_preview_actors(unreal.get_editor_subsystem(unreal.EditorActorSubsystem))
for item in ITEMS:
    script_path = os.path.join(PACK_DIR, item["ue_script"].replace("/", os.sep))
    record = {{
        "candidate_id": item["id"],
        "order": item["order"],
        "name": item["name"],
        "generation": item.get("generation") or {{}},
        "script": script_path,
        "create_ok": False,
        "payload": None,
        "stdout": "",
        "error": None,
        "traceback": None,
        "compile": {{"attempted": False, "ok": None, "error": None}},
        "preview": {{"attempted": False, "ok": None, "path": None, "error": None}},
    }}
    try:
        with open(script_path, "r", encoding="utf-8") as handle:
            code = handle.read()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(code, script_path, "exec"), {{}})
        record["stdout"] = buf.getvalue()
        payload = _extract_payload(record["stdout"])
        record["payload"] = payload
        record["create_ok"] = bool(payload and payload.get("ok"))
        if payload and payload.get("asset"):
            record["compile"] = _try_recompile(payload["asset"])
            record["preview"] = _capture_preview(payload["asset"], item["id"], item["order"])
    except Exception as exc:
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc()
    results.append(record)

report = {{
    "pack_dir": PACK_DIR,
    "count": len(results),
    "created": sum(1 for r in results if r["create_ok"]),
    "previewed": sum(1 for r in results if r["preview"].get("ok")),
    "preview_dir": PREVIEW_DIR,
    "results": results,
    "notes": [
        "This report proves UE script replay and asset creation attempts.",
        "Preview screenshots are best-effort and should be inspected before customer acceptance.",
        "A full customer acceptance pass still requires visual ranking against the prompt.",
    ],
}}

with open(REPORT_PATH, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)

print("LETHE_PACK_REPLAY_JSON::" + json.dumps({{
    "report": REPORT_PATH,
    "count": report["count"],
    "created": report["created"],
    "previewed": report["previewed"],
    "preview_dir": PREVIEW_DIR,
}}))
""".strip()
