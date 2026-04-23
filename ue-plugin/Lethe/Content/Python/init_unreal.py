"""Lethe plugin bootstrap — registers the Tools > Lethe menu at editor startup.

All real logic lives in lethe_menu.py so it's importable from menu callbacks
(don't `import init_unreal` — that has a history of re-triggering startup
side-effects and breaking the menu).
"""
import unreal

import lethe_menu

_VERSION = "0.1.0"
_MAX_TICKS = 100

_tick_handle = None
_tick_count = 0


def _deferred_register(_dt):
    """Slate pre-tick callback: retry menu registration until the Tools menu exists."""
    global _tick_handle, _tick_count
    _tick_count += 1
    if lethe_menu.register_menu():
        _unregister_tick()
        return
    if _tick_count > _MAX_TICKS:
        unreal.log_error(f"[Lethe] gave up waiting for Tools menu after {_MAX_TICKS} ticks")
        _unregister_tick()


def _unregister_tick():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_pre_tick_callback(_tick_handle)
        _tick_handle = None


# Make sure the config file exists on disk so the MCP server can read it
# even before the user has toggled anything.
lethe_menu.save_config(lethe_menu.load_config())

if not lethe_menu.register_menu():
    _tick_handle = unreal.register_slate_pre_tick_callback(_deferred_register)

unreal.log(
    f"[Lethe] plugin loaded v{_VERSION} — "
    f"Remote Execution on UDP 239.0.0.1:6766 — {lethe_menu.summary_line()}"
)
