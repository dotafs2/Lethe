# HLSL Selector Common Library

This directory stores small, stable HLSL/USH helpers used by deterministic
imports. The selector can still preview full HLSL in the browser, but UE import
packages should depend on these common helpers instead of copying ad-hoc helper
code into every material graph.

## Stage 1

- `LetheUEImportCommon.ush` is copied into `<UEProject>/Shaders/Lethe/HLSLSelector/Common.ush`.
- Generated shader bodies are copied into `<UEProject>/Shaders/Lethe/HLSLSelector/Generated/`.
- UE materials use Custom nodes that include the generated `.ush` file and call
  fixed wrapper functions.

## Rules

- Keep helpers deterministic and side-effect free.
- Avoid textures, samplers, buffers, and engine pipeline assumptions in this
  stage.
- Prefer tiny composable functions over large effect-specific blocks.
- If a helper becomes domain-specific, split it into a separate module before
  the graph importer starts depending on it.
