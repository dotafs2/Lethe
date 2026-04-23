"""Lethe menu — stateful toggles under LevelEditor > Tools > Lethe.

Each integration is a menu entry whose label carries its current state (☑ / ☐).
Clicking flips the bit in <Project>/Saved/Lethe/config.json and re-registers
the menu so the checkmark updates. Pure Python, no UMG asset needed.

Importable: the menu string-commands call `lethe_menu.toggle('polyhaven')`,
so this module must be importable by name. UE auto-adds every enabled plugin's
Content/Python/ folder to sys.path, so dropping this file next to init_unreal.py
is enough.
"""
from __future__ import annotations

import json
import os
import traceback

import unreal

# ---------------------------------------------------------------------------
# Integrations — add one tuple per toggle you want in the menu.
# The `key` is what gets written to config.json. `display` is the menu label.
# ---------------------------------------------------------------------------

INTEGRATIONS: list[tuple[str, str]] = [
    ("polyhaven", "PolyHaven"),
    ("hunyuan", "Hunyuan"),
    ("tripo", "Tripo"),
]

# Default state for a brand-new config.json.
_DEFAULTS: dict[str, bool] = {
    "polyhaven": True,
    "hunyuan": False,
    "tripo": False,
}

_MENU_PATH = "LevelEditor.MainMenu.Tools"
_SECTION_NAME = "LetheSection"
_SECTION_LABEL = "Lethe"


# ---------------------------------------------------------------------------
# Config IO — <Project>/Saved/Lethe/config.json, also read by the MCP server
# ---------------------------------------------------------------------------

def config_path() -> str:
    return os.path.join(unreal.Paths.project_saved_dir(), "Lethe", "config.json")


def load_config() -> dict:
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Fill in any missing keys with defaults so new integrations light up.
            for k, v in _DEFAULTS.items():
                data.setdefault(k, v)
            return data
        except Exception as e:
            unreal.log_warning(f"[Lethe] config read failed, using defaults: {e}")
    return dict(_DEFAULTS)


def save_config(cfg: dict) -> None:
    p = config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def is_enabled(key: str) -> bool:
    return bool(load_config().get(key, False))


def toggle(key: str) -> None:
    cfg = load_config()
    cfg[key] = not cfg.get(key, False)
    save_config(cfg)
    state = "ON" if cfg[key] else "OFF"
    unreal.log(f"[Lethe] {key} -> {state}")
    # Re-register so the checkmark in the label updates.
    register_menu()


# ---------------------------------------------------------------------------
# Menu registration
# ---------------------------------------------------------------------------

def _label_for(key: str, display: str) -> str:
    mark = "\u2611" if is_enabled(key) else "\u2610"  # ☑ or ☐
    return f"{mark}  {display}"


def register_menu() -> bool:
    """Register (or re-register) the Tools > Lethe section. Returns True on success."""
    try:
        menus = unreal.ToolMenus.get()
        tools = menus.find_menu(_MENU_PATH)
        if tools is None:
            # Tools menu not materialized yet. Caller should retry on next tick.
            return False

        # add_section is idempotent when the section already exists.
        tools.add_section(_SECTION_NAME, _SECTION_LABEL)

        for key, display in INTEGRATIONS:
            entry = unreal.ToolMenuEntry(
                name=f"LetheToggle_{key}",
                type=unreal.MultiBlockType.MENU_ENTRY,
            )
            entry.set_label(_label_for(key, display))
            entry.set_tool_tip(f"Toggle {display} integration for Lethe MCP")
            entry.set_string_command(
                type=unreal.ToolMenuStringCommandType.PYTHON,
                custom_type="",
                string=f"import lethe_menu; lethe_menu.toggle({key!r})",
            )
            # Adding an entry with the same name replaces the previous one,
            # so re-registration updates the label in place.
            tools.add_menu_entry(_SECTION_NAME, entry)

        menus.refresh_all_widgets()
        unreal.log(f"[Lethe] menu registered: Tools > {_SECTION_LABEL}")
        return True
    except Exception as e:
        unreal.log_error(f"[Lethe] menu registration failed: {e}")
        unreal.log_error(traceback.format_exc())
        return False


def summary_line() -> str:
    cfg = load_config()
    parts = [f"{k}={'on' if cfg.get(k) else 'off'}" for k, _ in INTEGRATIONS]
    return ", ".join(parts)
