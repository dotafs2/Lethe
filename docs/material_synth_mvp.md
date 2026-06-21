# Lethe HLSL Material Synthesizer MVP

Status: stage-1 implementation skeleton landed in `src/lethe/material_synth/`.

## Product Goal

Build a customer-usable Unreal Engine assistant that turns a natural-language
material request into many compileable HLSL candidates, validates them in UE,
renders previews, ranks the results, and lets the user iterate with follow-up
language.

The stage-1 product is HLSL-first and computer-friendly. Human-readable
Material Graph recipes are a later layer.

## Customer Flow

```text
User prompt
  -> Generate N HLSL candidates
  -> Static validation
  -> UE material asset creation
  -> UE shader compilation
  -> Preview render
  -> Automatic ranking
  -> User selects or asks for variants
```

Example prompt:

```text
I want an anime ocean material with turquoise water, graphic foam, and a
toon/cel-shaded look.
```

## Stage-1 HLSL Contract

The generator only writes the body of this function:

```hlsl
LetheMaterialOutput LetheMain(LetheMaterialInput I)
{
    // generated candidate body
}
```

The fixed input/output interface is:

```hlsl
struct LetheMaterialInput
{
    float2 UV;
    float3 WorldPos;
    float3 Normal;
    float3 CameraVector;
    float Time;
};

struct LetheMaterialOutput
{
    float3 BaseColor;
    float Roughness;
    float Metallic;
    float Alpha;
    float3 Emissive;
};
```

This keeps generation bounded. The AI should not write arbitrary UE shader
pipeline code in the first milestone.

## Implemented Now

- `MaterialRequest` and `MaterialCandidate` schema.
- Deterministic local candidate generation for anime/ocean/water prompts.
- Generic procedural fallback candidates.
- Static HLSL guardrails:
  - required `LetheMaterialOutput O`
  - required assignments for `BaseColor`, `Roughness`, `Metallic`, `Alpha`,
    and `Emissive`
  - required `return O`
  - banned resource declarations and unsafe tokens such as `Texture2D`,
    `SamplerState`, `RWTexture`, `discard`, `clip`, and unbounded `while`
  - balanced brace/parenthesis checks
- UE Python script generation for Material assets using Custom nodes.
- Local pre-UE ranking heuristics so larger batches can be ordered before
  expensive editor validation.
- Offline material pack export:
  - `manifest.json`
  - `index.md`
  - candidate HLSL files
  - optional UE Python replay scripts
  - `run_pack_in_ue.py` batch replay script
  - expected `ue_validation_report.json` output after UE replay
  - expected `previews/` screenshot directory after UE replay
- Multi-agent-ready metadata:
  - `generation.agent_id`
  - `generation.strategy`
  - `generation.strategy_family`
  - `generation.provenance`
- External agent JSON import through `pack-json` and
  `material_synth_export_agent_pack`.
- Local shader reference corpus:
  - `corpus-index` scans local `.hlsl`, `.ush`, `.usf`, `.glsl`, and related
    files.
  - `corpus-search` retrieves compact snippets and license/source risk notes.
  - `corpus-fetch-manifest` downloads explicitly listed shader URLs, writes a
    provenance report, and indexes the downloaded local folder.
  - The index stores metadata, hashes, symbols, keywords, and snippets rather
    than full source copies, which keeps large corpora manageable.
- Lethe MCP tools:
  - `material_synth_generate`
  - `material_synth_validate`
  - `material_synth_ue_script`
  - `material_synth_create_in_ue`
  - `material_synth_export_pack`
  - `material_synth_export_agent_pack`
  - `material_synth_validate_agent_json`
  - `material_synth_replay_pack_in_ue`
  - `material_synth_analyze_pack`
  - `material_synth_demo_pack`
  - `material_synth_verify_pack`
  - `material_synth_bundle_pack`
  - `material_synth_demo_bundle`
  - `material_synth_corpus_index`
  - `material_synth_corpus_search`
  - `material_synth_corpus_fetch_manifest`
  - `material_synth_doctor`
- Unit tests for generation, validation, UE script generation, pack export,
  demo bundling, corpus indexing/search, artifact verification, and server
  import.

## Required Permissions For Full Validation

The local skeleton does not require extra permissions. Full customer-grade
validation needs:

1. A target Unreal project path with a `.uproject`.
2. Permission to copy or enable `ue-plugin/Lethe` in that project.
3. Permission to edit the target project's `Config/DefaultEngine.ini` so Python
   Remote Execution is enabled.
4. Permission to start Unreal Editor.
5. Permission to create test assets under `/Game/Lethe/GeneratedMaterials`.
6. Permission to write screenshots and temporary files under the UE project's
   `Saved/Lethe/`.
7. Network permission only when adding external reference retrieval, dependency
   installs, or online model/API calls.

Local corpus indexing does not need network permission. It does need a local
folder path and an honest `license_label`. Manifest fetching does need network
permission and should only be pointed at direct shader URLs that are free and
permissive enough to use. Unknown-license corpora should be used for discovery
and stylistic inspiration only, not direct code reuse.

## Non-Goals For Stage 1

- Do not scrape Unity Asset Store, Unreal Marketplace, or other commercial
  asset stores.
- Do not promise "all materials on the internet."
- Do not use copied shader code without license provenance.
- Do not convert everything into human-readable graph recipes yet.
- Do not train or build a dataset from sources whose license forbids it.

## Next Engineering Steps

1. Run `material_synth_create_in_ue` against a real UE project.
2. Inspect and fix UE Python API differences for Custom node inputs if needed.
3. Add a preview scene: plane, sphere, ocean mesh, and lit neutral environment.
4. Add screenshot capture and automatic result JSON:

   ```json
   {
     "candidate_id": "...",
     "asset": "/Game/Lethe/GeneratedMaterials/M_...",
     "compile_ok": true,
     "preview": "Saved/Lethe/MaterialShots/...",
     "shader_errors": []
   }
   ```

5. Add a post-UE visual ranking step:
   - prompt match
   - compile success
   - visible contrast
   - animation signal
   - shader complexity budget

6. Replace the local deterministic generator with an agent pool that emits the
   same `MaterialCandidate` schema, including `generation.agent_id` and
   `generation.strategy`.

## Test Commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import lethe.server; print('server import ok')"
```

## Offline Pack Command

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli "anime ocean foam" --count 12 --output-dir material-packs
```

This writes a reviewable pack containing ranked candidates and UE replay
scripts. It is the best local artifact to inspect before a UE project path is
available.

Inside Unreal Editor, the generated `run_pack_in_ue.py` script replays every
candidate creation script, tries to render a preview PNG for each material, and
writes `ue_validation_report.json`. That report proves creation attempts,
captures per-candidate errors, and records preview paths. Visual acceptance
still requires inspecting or ranking those previews.

Through MCP, call `material_synth_replay_pack_in_ue(pack_dir)` to execute the
same replay script via Remote Execution once the target UE project is open.
Before that, use `material_synth_doctor(ue_project)` to check whether the Lethe
plugin and Python Remote Execution settings are present.

After replay, call `material_synth_analyze_pack(pack_dir)` or:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli analyze <pack_dir>
```

This writes `customer_summary.json`, `customer_summary.md`, and
`customer_gallery.html`, with a ranked recommendation based on asset creation,
compile status, preview presence, and simple preview image metrics.

For offline product demos before a UE project is available, use:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli demo-generate "anime ocean foam" --count 12 --output-dir material-packs
```

This writes synthetic previews and a gallery. It is not a substitute for real
UE replay, shader compilation, or screenshot validation.

For a one-command customer demo artifact, use:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli demo-bundle "anime ocean foam" --count 12 --output-dir material-packs --output-zip material-packs\anime_ocean_demo.zip
```

This creates the pack, writes synthetic previews, verifies `offline-demo`
completeness, and zips the output. The artifact remains marked
`synthetic_demo=true` so it cannot be confused with real UE validation.

Use `verify-pack` to check artifact completeness:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode pack
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode offline-demo
.\.venv\Scripts\python.exe -m lethe.material_synth.cli verify-pack <pack_dir> --mode ue
```

The `ue` mode intentionally fails synthetic demo packs so offline demos cannot
be mistaken for real Unreal validation.

## Local Reference Corpus

The safe first version of the "100GB reference set" is a local indexer, not a
scraper. Point it at folders you are allowed to inspect:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-index C:\Path\To\Shaders --output material-corpus\index.json --source-label "local-review" --license-label "MIT"
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-search material-corpus\index.json "anime ocean foam" --limit 10
```

The index records path, extension, language, size, line count, hash, discovered
symbols, keywords, snippet, source label, license label, and whether direct
reference use looks permitted. Large files are retained as metadata-only entries
so the corpus can scale without copying huge source blobs into JSON.

Pass `--corpus-index material-corpus\index.json` to `generate`,
`demo-generate`, or `demo-bundle` to record the prompt's retrieval context in
`manifest.json` and `index.md`.

For sources you have already reviewed, use a manifest to fetch only explicit
shader files:

```json
{
  "source_label": "reviewed-free-shaders",
  "license_label": "MIT",
  "items": [
    {
      "url": "https://example.com/shaders/AnimeWater.hlsl",
      "path": "water/AnimeWater.hlsl",
      "license": "MIT"
    }
  ]
}
```

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli corpus-fetch-manifest shader_sources.json --output-dir material-corpus\raw --index-output material-corpus\index.json
```

The fetcher records `sources.json`, `download_report.json`, per-file hashes,
licenses, and whether the file is reference-safe. It skips unknown,
proprietary, commercial, Marketplace, Fab, and Asset Store labels by default.
Use `--allow-unsafe` only when building a discovery-only folder that still must
not be copied into generated customer code.

Verified packs can be bundled:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
.\.venv\Scripts\python.exe -m lethe.material_synth.cli bundle-pack <pack_dir> --mode ue --output material-pack.zip
```

Use `--mode offline-demo` only for synthetic product demos; use `--mode ue` for
real customer delivery.
