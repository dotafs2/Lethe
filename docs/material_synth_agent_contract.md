# Lethe Material Synth Agent Contract

External LLM agents should emit JSON that Lethe can validate, pack, replay in
Unreal Editor, and rank without changing the downstream pipeline.

## JSON Shape

Preferred shape:

```json
{
  "request": {
    "prompt": "anime ocean foam",
    "seed": 0,
    "target": "unreal-custom-node"
  },
  "candidates": [
    {
      "name": "Agent01_GraphicFoam",
      "description": "High-readability anime ocean with cel foam.",
      "hlsl_body": "    LetheMaterialOutput O;\\n    ...\\n    return O;",
      "tags": ["hlsl", "unreal", "custom-node", "water", "anime"],
      "parameters": {
        "foam_amount": 0.7
      },
      "generation": {
        "agent_id": "agent_01",
        "strategy": "graphic_foam_shapes",
        "strategy_family": "anime_ocean",
        "variant_index": 0,
        "batch_size": 100,
        "provenance": "model_output_no_external_code"
      },
      "source_refs": [],
      "risk_notes": [
        "No external shader code copied."
      ]
    }
  ]
}
```

A bare list of candidate objects is also accepted, but the object form is
better because it records the original request.

## HLSL Body Contract

Agents only write the function body. The body must:

- declare `LetheMaterialOutput O`
- assign `O.BaseColor`
- assign `O.Roughness`
- assign `O.Metallic`
- assign `O.Alpha`
- assign `O.Emissive`
- `return O`

The body must not declare textures, samplers, buffers, includes, pragmas,
`discard`, `clip`, or unbounded `while` loops in stage 1.

## Command

Validate first:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli validate-json agents.json --report agent_validation_report.json
```

Then pack:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli pack-json agents.json --output-dir material-packs
```

Then run the normal flow:

```text
pack-json
-> material_synth_replay_pack_in_ue(pack_dir)
-> material_synth_analyze_pack(pack_dir)
-> customer_gallery.html
```

## Product Rule

Do not emit copied shader code from commercial stores or unknown-license
websites. If an agent used a reference, it must write `source_refs` with URL,
license, and author when available.

Local corpus search results follow the same rule. If an agent uses a result from
`corpus-search`, it should add a `source_refs` item with `path`, `source`,
`license`, and whether the reference was used as inspiration or direct code.
Unknown-license corpus results are not approved for direct code reuse.
