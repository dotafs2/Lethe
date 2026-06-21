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
| `polyhaven_status` | — | Report whether the PolyHaven integration is toggled on in the editor menu. |
| `polyhaven_search_hdri` | `query="", max_results=20` | Search PolyHaven's HDRI library. Returns slugs to feed into `polyhaven_set_sky`. |
| `polyhaven_set_sky` | `slug, resolution="2k"` | Download an HDRI and set it as the current level's sky via a single tagged `HDRIBackdrop` actor (repeat calls swap, don't stack). |
| `material_synth_generate` | `prompt, count=12, seed=0` | Generate stage-1 HLSL material candidates and return validation metadata. |
| `material_synth_validate` | `hlsl_body` | Validate a raw Lethe HLSL material body against the fixed stage-1 interface. |
| `material_synth_ue_script` | `candidate_json` or `prompt, variant_index` | Build the UE Python script that creates a Material asset from a candidate. |
| `material_synth_create_in_ue` | `prompt, variant_index=0` | Generate one candidate and execute the UE material creation script through Remote Execution. |
| `material_synth_export_pack` | `prompt, count=12, seed=0, output_dir="material-packs", corpus_index=""` | Export an offline review pack with manifest, HLSL files, reference context, and UE replay scripts. |
| `material_synth_export_agent_pack` | `json_path, output_dir="material-packs"` | Export a pack from external agent candidate JSON. |
| `material_synth_validate_agent_json` | `json_path, report_path=""` | Validate external agent candidate JSON before packing or UE replay. |
| `material_synth_replay_pack_in_ue` | `pack_dir` | Execute a generated pack's `run_pack_in_ue.py` through UE Remote Execution. |
| `material_synth_analyze_pack` | `pack_dir` | Analyze `ue_validation_report.json` and write customer-facing summary files. |
| `material_synth_demo_pack` | `pack_dir` | Create synthetic previews and gallery for an existing pack without Unreal Editor. |
| `material_synth_verify_pack` | `pack_dir, mode="pack"` | Verify pack/demo/UE replay artifact completeness. |
| `material_synth_bundle_pack` | `pack_dir, output_zip="", mode="pack"` | Verify and zip a material pack for sharing. |
| `material_synth_demo_bundle` | `prompt, count=12, seed=0, output_dir="material-packs", output_zip="", corpus_index=""` | Generate, synthetic-preview, verify, and zip a demo pack in one step. |
| `material_synth_corpus_index` | `roots, output="material-corpus/index.json", source_label="local", license_label="unknown"` | Index local shader reference files with provenance metadata. |
| `material_synth_corpus_search` | `index_path, query, limit=10` | Search a local shader reference index and return snippets plus license risk notes. |
| `material_synth_corpus_fetch_manifest` | `manifest_json, output_dir="material-corpus/raw", index_output="material-corpus/index.json"` | Download explicitly listed free shader URLs, write provenance, and index them. |
| `material_synth_doctor` | `ue_project=""` | Read-only readiness check for local tools and optional UE project setup. |

### Integrations (hot-switched)

Open **Tools → Lethe** in the UE editor to toggle integrations with a ☑/☐ checkmark.
Toggles are written to `<UEProject>/Saved/Lethe/config.json` and re-read on every
MCP tool call — no editor or server restart needed.

- **PolyHaven** — HDRI sky. Assets cached at `<UEProject>/Saved/Lethe/Downloads/HDRI/`
  and imported into `/Game/Lethe/HDRI/`. Requires the `HDRIBackdrop` plugin
  (already a dependency of `Lethe.uplugin`).

Add your own:

### Offline HLSL material packs

Without a running Unreal Editor, generate a ranked material candidate pack:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli "anime ocean foam" --count 12 --output-dir material-packs
```

After UE replay writes `ue_validation_report.json`, generate the customer-facing
summary and gallery:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli analyze <pack_dir>
```

After reinstalling the editable package, the `lethe-material-synth` console
script provides the same entrypoint.

The pack includes `run_pack_in_ue.py`, which can be executed inside Unreal
Editor to create all exported candidates, write `ue_validation_report.json`,
and export best-effort preview PNGs under `previews/`.
The analyze step writes `customer_summary.json`, `customer_summary.md`, and
`customer_gallery.html`.
Generated candidates include `generation.agent_id` and `generation.strategy`
metadata so 100-candidate batches already match the future multi-agent shape.
External agents can emit the same candidate JSON and use `pack-json`; see
`docs/material_synth_agent_contract.md`.
Validate external agent output before packing:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli validate-json agents.json --report agent_validation_report.json
```

Build a local shader reference corpus without network access:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-index C:\Path\To\Shaders --output material-corpus\index.json --source-label "local-review" --license-label "MIT"
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-search material-corpus\index.json "anime ocean foam" --limit 10
```

Or fetch a reviewed list of direct shader URLs into the local corpus:

```json
{
  "source_label": "my-free-shader-list",
  "license_label": "MIT",
  "items": [
    {
      "url": "https://example.com/shaders/WaterFoam.hlsl",
      "path": "water/WaterFoam.hlsl",
      "license": "MIT",
      "title": "Water Foam"
    }
  ]
}
```

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-fetch-manifest shader_sources.json --output-dir material-corpus\raw --index-output material-corpus\index.json
```

This manifest fetcher is for explicit free/permissive sources. It is not a
Fab, Marketplace, Unity Asset Store, or paid plugin bypass scraper. Unknown,
commercial, Marketplace, Fab, and Asset Store license labels are skipped by
default.

Use `license-label unknown` for unreviewed folders. Those results include risk
notes and should be treated as inspiration/search leads, not code to copy.
Pass `--corpus-index material-corpus\index.json` to `generate`, `demo-generate`,
or `demo-bundle` to store the retrieval context in the pack manifest.

Check readiness before asking for UE permissions:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli doctor
.\.venv\Scripts\python.exe -m lethe.material_synth.cli doctor --ue-project C:\Path\To\Project.uproject
```

Preview the full customer gallery flow without Unreal Editor:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli demo-generate "anime ocean foam" --count 12 --output-dir material-packs
```

This creates synthetic preview images for product demos only. Real acceptance
still requires UE replay and real screenshots.

Produce a customer-shareable synthetic demo zip in one command:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli demo-bundle "anime ocean foam" --count 12 --output-dir material-packs --output-zip material-packs\anime_ocean_demo.zip
```

This runs generation, synthetic preview creation, offline-demo verification, and
zip bundling. The output is clearly marked as `synthetic_demo`.

Verify generated artifacts:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode pack
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode offline-demo
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode ue
```

Bundle a verified pack:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli bundle-pack <pack_dir> --mode offline-demo --output material-pack.zip
```

For real customer delivery, use `--mode ue` after genuine UE replay succeeds.

See `docs/material_synth_mvp.md` for the product plan and
`docs/material_synth_permissions.md` for the UE validation permission checklist.

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
