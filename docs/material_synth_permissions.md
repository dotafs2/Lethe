# Lethe Material Synth Permissions

This is the permission checklist for moving the HLSL material synthesizer from
offline pack generation to real Unreal Editor validation.

## Already Works Without Extra Permission

- Generate local HLSL candidates.
- Validate candidates with static guardrails.
- Rank candidates with cheap local heuristics.
- Export offline material packs under a chosen local directory.
- Index and search local shader reference folders that you provide.
- Generate UE Python replay scripts.
- Run unit tests.
- Run the read-only readiness checker:

  ```powershell
  $env:PYTHONPATH=(Resolve-Path src).Path
  .\.venv\Scripts\python.exe -m lethe.material_synth.cli doctor
  ```

## Needed For UE Editor Validation

Grant these together when you want the real compile/screenshot loop:

1. Target Unreal project `.uproject` path.
2. Permission to start Unreal Editor for that project.
3. Permission to copy or enable `C:\Lethe\ue-plugin\Lethe` under the target
   project's `Plugins/Lethe`.
4. Permission to edit the target project's `Config/DefaultEngine.ini` to enable
   Python Remote Execution.
5. Permission to create assets under `/Game/Lethe/GeneratedMaterials`.
6. Permission to create or modify a throwaway preview map or preview actors.
7. Permission to write screenshots and JSON reports under
   `<UEProject>/Saved/Lethe/`.

Before changing the project, run:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli doctor --ue-project C:\Path\To\Project.uproject
```

The doctor command is read-only. It reports missing plugin/config steps without
editing the UE project.

## Needed For Online Reference Retrieval

Grant network permission only when adding online retrieval:

- GitHub permissive-license shader repositories.
- Official Unreal/Unity samples whose license allows local reference use.
- Shadertoy references with source URL and author provenance.
- PolyHaven or other explicitly permissive assets.

Do not grant blanket permission to scrape commercial stores. Unity Asset Store,
Unreal Marketplace/Fab assets, and paid shader packs require separate license
review and should not be treated as a training/reference dataset by default.

## Needed For Local Reference Corpus

No network permission is required. Provide:

1. One or more local folders containing shader files.
2. A truthful source label, for example `official-sample`, `internal-library`,
   or `local-review`.
3. A truthful license label, for example `MIT`, `Apache-2.0`, or `unknown`.

Use unknown-license results only as search leads. Do not copy code from them
into generated materials without separate license review.

## Needed For Real Agent Generation

The current generator is deterministic and local. Real multi-agent generation
needs:

1. Model/API key or approved local model runtime.
2. Budget cap per batch.
3. Candidate count policy, for example:
   - interactive: 8-16 candidates
   - background exploration: 100 candidates
4. Storage location for generated packs and screenshots.

## Recommended First UE Test

Use a blank UE project and ask Lethe for:

```text
anime ocean material, turquoise water, graphic white foam, cel shaded
```

Acceptance for the first test:

- At least one material asset is created.
- UE shader compilation succeeds.
- `ue_validation_report.json` is written by `run_pack_in_ue.py`.
- At least one preview screenshot is written under the pack's `previews/`
  directory.
- `customer_summary.json`, `customer_summary.md`, and `customer_gallery.html`
  are written after analyzing the replay report.
- `verify-pack <pack_dir> --mode ue` passes.
- The manifest records candidate id, asset path, compile result, and screenshot
  path.
