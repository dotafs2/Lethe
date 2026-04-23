# Lethe

Unreal Engine MCP server. Claude drives the editor via UE Remote Execution.

```
Claude Desktop  ──MCP──▶  lethe (FastMCP)  ──Remote Execution──▶  UnrealEditor
```

Two parts, both required:

- **`src/lethe/`** — MCP server (runs outside UE, serves Claude).
- **`ue-plugin/Lethe/`** — UE plugin (drop into your project's `Plugins/`, toggle in Plugin Browser).

## Requirements

- Unreal Engine 5.x with `PythonScriptPlugin`
- Python 3.10+
- Claude Desktop

## 1. UE side

1. Copy `ue-plugin/Lethe/` into `YourProject/Plugins/Lethe/`.
2. In `YourProject.uproject`, `Plugins` array, add `{ "Name": "Lethe", "Enabled": true }`.
3. In `YourProject/Config/DefaultEngine.ini`, append:

   ```ini
   [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
   bRemoteExecution=True
   RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766
   RemoteExecutionMulticastBindAddress=127.0.0.1
   ```

4. Open the editor. `Edit → Plugins` → search `Lethe` → confirm enabled. Output Log should show `[Lethe] plugin loaded`.

## 2. Install the MCP server

```powershell
git clone git@github.com:dotafs2/Lethe.git
cd Lethe
uv venv --python 3.12
uv pip install -e .
```

Or with pip: `python -m venv .venv && .venv\Scripts\activate && pip install -e .`

Smoke test (UE must be running):

```powershell
.venv\Scripts\python -c "from lethe.server import spawn_cube; print(spawn_cube(z=300))"
```

A cube should appear in the UE viewport.

## 3. Wire up Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "lethe": {
      "command": "F:\\Lethe\\.venv\\Scripts\\python.exe",
      "args": ["-m", "lethe.server"]
    }
  }
}
```

Quit Claude Desktop from the tray (not just close the window) and reopen.

## Tools

| Tool | Args | What |
|---|---|---|
| `spawn_cube` | `x, y, z` | Spawn a basic cube at world location. Returns the actor name. |
| `execute_python` | `code` | Run arbitrary Python in the editor. Returns stdout. |
| `verify_actors` | `actor_names, views=[top,front,side,hero,context], context_distance_factor=8.0, width=512, height=512, fov=60.0` | Take canonical-view screenshots of the given actors and return them with the union AABB as metadata. Call after each batch of spawn/move ops to close the visual feedback loop. Screenshots are written to `<UEProject>/Saved/LetheShots/`. |

Add your own:

```python
@mcp.tool()
def my_tool(arg: str) -> str:
    """Doc — Claude uses this to decide when to call."""
    return _run_in_ue(f"import unreal; ...")
```

Restart Claude Desktop after adding tools.

## Troubleshooting

- **`No Unreal Editor node discovered`** — UE isn't running, Remote Execution isn't enabled, or a firewall is blocking UDP 239.0.0.1:6766.
- **Claude Desktop doesn't list `lethe`** — JSON syntax error, wrong Python path, or you didn't fully quit before restart.
- **`[Lethe] plugin loaded` doesn't print** — plugin disabled in Plugin Browser, or editor wasn't restarted.
