"""Print current StaticMeshActor list + hierarchy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lethe.server import _run_in_ue

code = """
import unreal
sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sma = [a for a in sub.get_all_level_actors() if isinstance(a, unreal.StaticMeshActor)]
for a in sma:
    p = a.get_attach_parent_actor()
    pl = p.get_actor_label() if p else None
    print(f"{a.get_actor_label():<24s} ({a.get_name()}) parent={pl}")
print(f"total: {len(sma)}")
"""
print(_run_in_ue(code))
