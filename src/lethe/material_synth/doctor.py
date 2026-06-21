"""Read-only readiness checks for Lethe material synthesis."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
from typing import Any


def run_doctor(ue_project: str | Path | None = None, repo_root: str | Path | None = None) -> dict[str, Any]:
    """Return a read-only readiness report for local and optional UE setup."""

    root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    checks: list[dict[str, Any]] = []
    checks.extend(_local_checks(root))
    ue_info = None
    if ue_project:
        ue_info = _ue_project_checks(Path(ue_project), root)
        checks.extend(ue_info["checks"])

    ok = all(check["status"] != "fail" for check in checks)
    return {
        "ok": ok,
        "repo_root": str(root),
        "python": sys.version.split()[0],
        "ue_project": ue_info["project"] if ue_info else None,
        "checks": checks,
        "required_permissions": _required_permissions(ue_info),
        "next_steps": _next_steps(checks, ue_info),
    }


def _local_checks(root: Path) -> list[dict[str, Any]]:
    return [
        _check("repo_root_exists", root.exists(), str(root), "Run from the Lethe checkout."),
        _check(
            "material_synth_package",
            (root / "src" / "lethe" / "material_synth").exists(),
            str(root / "src" / "lethe" / "material_synth"),
            "Expected src/lethe/material_synth to exist.",
        ),
        _check(
            "pillow_available",
            importlib.util.find_spec("PIL") is not None,
            "Pillow import",
            "Install project dependencies before analyzing preview images.",
        ),
        _optional_tool("dxc", "Optional external HLSL compiler not found; UE compile remains authoritative."),
        _optional_tool(
            "glslangValidator",
            "Optional GLSL/SPIR-V validator not found; this is fine for UE-first validation.",
        ),
    ]


def _ue_project_checks(project: Path, root: Path) -> dict[str, Any]:
    project = project.resolve()
    project_dir = project.parent
    plugin_dir = project_dir / "Plugins" / "Lethe"
    default_engine = project_dir / "Config" / "DefaultEngine.ini"
    source_plugin = root / "ue-plugin" / "Lethe"
    uproject_data = _load_json(project)
    enabled_plugins = _enabled_plugins(uproject_data)
    engine_text = default_engine.read_text(encoding="utf-8-sig") if default_engine.exists() else ""

    checks = [
        _check("uproject_exists", project.exists(), str(project), "Provide a valid .uproject path."),
        _check(
            "source_lethe_plugin_exists",
            source_plugin.exists(),
            str(source_plugin),
            "Expected C:\\Lethe\\ue-plugin\\Lethe to exist.",
        ),
        _check(
            "target_lethe_plugin_installed",
            plugin_dir.exists(),
            str(plugin_dir),
            "Copy C:\\Lethe\\ue-plugin\\Lethe to <UEProject>/Plugins/Lethe.",
        ),
        _check(
            "uproject_lethe_enabled",
            "Lethe" in enabled_plugins,
            "Plugins array",
            "Add {\"Name\":\"Lethe\",\"Enabled\":true} to the .uproject Plugins array.",
        ),
        _check(
            "uproject_python_enabled",
            "PythonScriptPlugin" in enabled_plugins or plugin_dir.exists(),
            "Plugins array",
            "Enable PythonScriptPlugin directly or through the Lethe plugin dependency.",
        ),
        _check(
            "default_engine_exists",
            default_engine.exists(),
            str(default_engine),
            "Create Config/DefaultEngine.ini with Python Remote Execution settings.",
        ),
        _check(
            "remote_execution_enabled",
            "bRemoteExecution=True" in engine_text,
            "DefaultEngine.ini",
            "Add bRemoteExecution=True under PythonScriptPluginSettings.",
        ),
        _check(
            "remote_execution_endpoint",
            "RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766" in engine_text,
            "DefaultEngine.ini",
            "Set RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766.",
        ),
        _check(
            "remote_execution_bind_address",
            "RemoteExecutionMulticastBindAddress=127.0.0.1" in engine_text,
            "DefaultEngine.ini",
            "Set RemoteExecutionMulticastBindAddress=127.0.0.1.",
        ),
    ]
    return {
        "project": str(project),
        "project_dir": str(project_dir),
        "checks": checks,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _enabled_plugins(uproject_data: dict[str, Any]) -> set[str]:
    enabled = set()
    for plugin in uproject_data.get("Plugins", []) or []:
        if plugin.get("Enabled"):
            enabled.add(str(plugin.get("Name")))
    return enabled


def _optional_tool(name: str, hint: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {
        "name": f"optional_tool_{name}",
        "status": "pass" if path else "warn",
        "detail": path or "not found",
        "hint": "Available." if path else hint,
    }


def _check(name: str, passed: bool, detail: str, hint: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "detail": detail,
        "hint": "OK" if passed else hint,
    }


def _required_permissions(ue_info: dict[str, Any] | None) -> list[str]:
    permissions = [
        "No extra permission is needed for offline pack generation and analysis.",
    ]
    if ue_info:
        permissions.extend(
            [
                "Permission to start Unreal Editor for the target project.",
                "Permission to copy/enable the Lethe plugin in the target project if missing.",
                "Permission to edit Config/DefaultEngine.ini if Remote Execution settings are missing.",
                "Permission to create /Game/Lethe/GeneratedMaterials assets.",
                "Permission to write pack reports and previews under the chosen material pack directory.",
            ]
        )
    return permissions


def _next_steps(checks: list[dict[str, Any]], ue_info: dict[str, Any] | None) -> list[str]:
    failed = [check for check in checks if check["status"] == "fail"]
    if not failed and ue_info:
        return [
            "Open the UE project.",
            "Generate a material pack.",
            "Run material_synth_replay_pack_in_ue(pack_dir).",
            "Run material_synth_analyze_pack(pack_dir).",
        ]
    if not ue_info:
        return [
            "Generate and analyze offline packs now.",
            "Provide a .uproject path to check UE replay readiness.",
        ]
    return [check["hint"] for check in failed]
