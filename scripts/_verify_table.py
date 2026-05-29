"""Verify the table-decor fix: count chandeliers (should be 0) and shoot a
close-up of the first WoodenTable."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from lethe.server import _run_in_ue

UE = r'''
import unreal, os, json, math
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = les.get_editor_world()

chand = 0
table = None
for a in eas.get_all_level_actors():
    if not isinstance(a, unreal.StaticMeshActor):
        continue
    lbl = a.get_actor_label()
    if "chandelier" in lbl:
        chand += 1
    if table is None and lbl.startswith("WoodenTable_01"):
        table = a

info = {"chandeliers": chand, "shot": None}
if table is not None:
    c = table.get_actor_location()
    rt = unreal.RenderingLibrary.create_render_target2d(world, 1280, 720, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    save = unreal.Paths.convert_relative_path_to_full(os.path.join(unreal.Paths.project_saved_dir(), "LetheShots"))
    os.makedirs(save, exist_ok=True)
    ex, ey, ez = c.x - 230, c.y - 230, c.z + 170
    dx, dy, dz = c.x-ex, c.y-ey, c.z-ez
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.sqrt(dx*dx+dy*dy)))
    sc = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(ex,ey,ez), unreal.Rotator(0,pitch,yaw))
    try:
        comp = sc.capture_component2d
        comp.texture_target = rt
        comp.fov_angle = 60.0
        comp.capture_source = unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR
        comp.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, rt, save, "table_closeup.png")
        info["shot"] = os.path.join(save, "table_closeup.png")
    finally:
        eas.destroy_actor(sc)

print("LETHE_JSON::" + json.dumps(info))
'''
out = _run_in_ue(UE)
for line in out.splitlines():
    i = line.find("LETHE_JSON::")
    if i >= 0:
        print(json.loads(line[i+len("LETHE_JSON::"):]))
        break
else:
    print(out[:600])
