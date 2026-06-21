"""Offline material pack export.

The pack is the smallest customer-inspectable artifact for stage 1. It lets us
generate, rank, review, and archive HLSL candidates before a UE project is
available for real compilation and screenshots.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .generator import generate_candidates
from .ranker import rank_candidate, rank_candidates
from .schema import MaterialCandidate, MaterialRequest, slugify, stable_id
from .templates import wrap_hlsl_body
from .ue_bridge import build_create_material_script, build_pack_replay_script
from .validator import validate_candidate


def export_material_pack(
    request: MaterialRequest,
    output_dir: str | Path,
    include_ue_scripts: bool = True,
    reference_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate candidates and export a local review pack.

    Returns the manifest dictionary that was written to `manifest.json`.
    """

    candidates = generate_candidates(request)
    return export_candidates_pack(
        request,
        candidates,
        output_dir,
        include_ue_scripts=include_ue_scripts,
        source="local_generator",
        reference_context=reference_context,
    )


def export_candidates_pack(
    request: MaterialRequest,
    candidates: list[MaterialCandidate],
    output_dir: str | Path,
    include_ue_scripts: bool = True,
    source: str = "external_candidates",
    reference_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export a material pack from an explicit candidate list."""

    out = Path(output_dir)
    pack_id = stable_id(
        request.prompt,
        len(candidates),
        request.seed,
        request.target,
        source,
        prefix="pack",
    )
    pack_slug = slugify(request.prompt, fallback="material_pack")[:48]
    pack_dir = out / f"{pack_slug}_{pack_id}"
    candidates_dir = pack_dir / "candidates"
    scripts_dir = pack_dir / "ue_scripts"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    if include_ue_scripts:
        scripts_dir.mkdir(parents=True, exist_ok=True)

    ranked = rank_candidates(candidates, request.prompt)

    manifest_candidates = []
    for order, item in enumerate(ranked, start=1):
        candidate = item["candidate"]
        assert isinstance(candidate, MaterialCandidate)
        rank = item["rank"]
        validation = validate_candidate(candidate)

        file_stem = f"{order:03d}_{candidate.id}_{slugify(candidate.name, fallback='candidate')[:48]}"
        body_path = candidates_dir / f"{file_stem}.body.hlsl"
        wrapped_path = candidates_dir / f"{file_stem}.wrapped.hlsl"
        body_path.write_text(candidate.hlsl_body.strip() + "\n", encoding="utf-8")
        wrapped_path.write_text(wrap_hlsl_body(candidate.hlsl_body), encoding="utf-8")

        ue_script_rel = None
        if include_ue_scripts and validation.ok:
            ue_script_path = scripts_dir / f"{file_stem}.create_material.py"
            ue_script_path.write_text(build_create_material_script(candidate), encoding="utf-8")
            ue_script_rel = _rel(ue_script_path, pack_dir)

        manifest_candidates.append(
            {
                **candidate.to_dict(),
                "order": order,
                "rank": rank,
                "validation": validation.to_dict(),
                "files": {
                    "body_hlsl": _rel(body_path, pack_dir),
                    "wrapped_hlsl": _rel(wrapped_path, pack_dir),
                    "ue_script": ue_script_rel,
                },
            }
        )

    manifest = {
        "pack_id": pack_id,
        "pack_dir": str(pack_dir.resolve()),
        "request": asdict(request),
        "source": source,
        "reference_context": reference_context or None,
        "candidate_count": len(manifest_candidates),
        "agent_count": len({
            candidate.get("generation", {}).get("agent_id")
            for candidate in manifest_candidates
            if candidate.get("generation", {}).get("agent_id")
        }),
        "strategy_counts": _strategy_counts(manifest_candidates),
        "include_ue_scripts": include_ue_scripts,
        "candidates": manifest_candidates,
        "files": {
            "manifest": "manifest.json",
            "index": "index.md",
            "ue_replay_script": "run_pack_in_ue.py" if include_ue_scripts else None,
            "ue_validation_report": "ue_validation_report.json" if include_ue_scripts else None,
            "preview_dir": "previews" if include_ue_scripts else None,
        },
        "next_steps": [
            "Run run_pack_in_ue.py in a project with Lethe Remote Execution enabled.",
            "Compile materials in Unreal Editor.",
            "Render preview screenshots.",
            "Rank compiled candidates by visual match and shader cost.",
        ],
    }

    if include_ue_scripts:
        (pack_dir / "run_pack_in_ue.py").write_text(
            build_pack_replay_script(manifest, pack_dir),
            encoding="utf-8",
        )
    (pack_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (pack_dir / "index.md").write_text(_build_index_markdown(manifest), encoding="utf-8")
    return manifest


def _rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _strategy_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        strategy = candidate.get("generation", {}).get("strategy") or "unknown"
        counts[str(strategy)] = counts.get(str(strategy), 0) + 1
    return dict(sorted(counts.items()))


def _build_index_markdown(manifest: dict[str, Any]) -> str:
    request = manifest["request"]
    lines = [
        f"# Lethe Material Pack `{manifest['pack_id']}`",
        "",
        f"Prompt: `{request['prompt']}`",
        "",
        f"Count: {manifest['candidate_count']}",
        f"Agents: {manifest.get('agent_count', 0)}",
        "",
    ]
    reference_context = manifest.get("reference_context")
    if reference_context:
        lines.extend(
            [
                "## Reference Context",
                "",
                f"Query: `{reference_context.get('query', '')}`",
                f"Reference allowed: {reference_context.get('reference_allowed')}",
                "",
                "| Score | Language | License | Path | Risk |",
                "|---:|---|---|---|---|",
            ]
        )
        for match in reference_context.get("matches", [])[:10]:
            lines.append(
                "| {score} | {language} | {license} | `{path}` | {risk} |".format(
                    score=match.get("score", 0),
                    language=match.get("language", ""),
                    license=match.get("license", ""),
                    path=match.get("rel_path") or match.get("path", ""),
                    risk=", ".join(match.get("risk_notes", [])) or "none",
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Candidates",
            "",
            "| Order | Agent | Strategy | ID | Name | Score | Static OK | Files |",
            "|---:|---|---|---|---|---:|---|---|",
        ]
    )
    for candidate in manifest["candidates"]:
        files = candidate["files"]
        generation = candidate.get("generation", {})
        links = [
            f"[body]({files['body_hlsl']})",
            f"[wrapped]({files['wrapped_hlsl']})",
        ]
        if files.get("ue_script"):
            links.append(f"[ue script]({files['ue_script']})")
        lines.append(
            "| {order} | {agent} | {strategy} | `{id}` | {name} | {score} | {ok} | {files} |".format(
                order=candidate["order"],
                agent=generation.get("agent_id", "unknown"),
                strategy=generation.get("strategy", "unknown"),
                id=candidate["id"],
                name=candidate["name"],
                score=candidate["rank"]["score"],
                ok="yes" if candidate["validation"]["ok"] else "no",
                files=", ".join(links),
            )
        )
    lines.extend(
        [
            "",
        "## Notes",
        "",
        "- This pack is statically validated only.",
        "- Real acceptance still requires Unreal shader compilation and preview screenshots.",
        "- Generated candidates are local Lethe templates unless `source_refs` says otherwise.",
        "- If UE scripts were exported, run `run_pack_in_ue.py` inside Unreal Editor to create all candidates and write `ue_validation_report.json`.",
        "",
    ]
    )
    return "\n".join(lines)
