"""External agent contract for Lethe material candidates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import MaterialCandidate, MaterialRequest, slugify, stable_id
from .validator import validate_candidate


AGENT_CONTRACT_VERSION = "lethe.material_candidate.v1"


def load_agent_candidates(path: str | Path) -> tuple[MaterialRequest, list[MaterialCandidate]]:
    """Load candidates emitted by external LLM/agent workers.

    Supported JSON shapes:
    - {"request": {...}, "candidates": [{...}]}
    - [{...}, {...}]
    """

    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        candidates_data = payload
        prompt = _first_prompt(candidates_data) or "external material candidates"
        request = MaterialRequest(prompt=prompt, count=len(candidates_data))
    elif isinstance(payload, dict):
        candidates_data = payload.get("candidates")
        if not isinstance(candidates_data, list):
            raise ValueError("agent candidate JSON object must contain a candidates list")
        request_data = payload.get("request") or {}
        prompt = str(request_data.get("prompt") or _first_prompt(candidates_data) or "external material candidates")
        request = MaterialRequest(
            prompt=prompt,
            count=len(candidates_data),
            seed=int(request_data.get("seed", 0)),
            target=str(request_data.get("target", "unreal-custom-node")),
        )
    else:
        raise ValueError("agent candidate JSON must be an object or a list")

    candidates = [
        _candidate_from_agent_dict(item, request, idx, str(source_path))
        for idx, item in enumerate(candidates_data)
    ]
    return request, candidates


def validate_agent_candidate_file(
    path: str | Path,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate external agent JSON without exporting a pack."""

    request, candidates = load_agent_candidates(path)
    items = []
    for idx, candidate in enumerate(candidates):
        validation = validate_candidate(candidate)
        provenance = candidate.generation.get("provenance")
        source_refs = candidate.source_refs
        risk_notes = list(candidate.risk_notes)
        warnings = []
        if not provenance:
            warnings.append("generation.provenance is missing")
        if not source_refs and "external" not in candidate.generation.get("provenance", ""):
            warnings.append("source_refs are empty; confirm no external shader code was copied")
        items.append(
            {
                "index": idx,
                "id": candidate.id,
                "name": candidate.name,
                "agent_id": candidate.generation.get("agent_id"),
                "strategy": candidate.generation.get("strategy"),
                "ok": validation.ok,
                "issues": [issue.to_dict() for issue in validation.issues],
                "warnings": warnings,
                "risk_notes": risk_notes,
            }
        )
    report = {
        "contract_version": AGENT_CONTRACT_VERSION,
        "source": str(Path(path).resolve()),
        "request": {
            "prompt": request.prompt,
            "count": request.count,
            "seed": request.seed,
            "target": request.target,
        },
        "loaded": len(candidates),
        "valid": sum(1 for item in items if item["ok"]),
        "invalid": sum(1 for item in items if not item["ok"]),
        "items": items,
    }
    if report_path:
        Path(report_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return report


def _candidate_from_agent_dict(
    data: dict[str, Any],
    request: MaterialRequest,
    idx: int,
    source_path: str,
) -> MaterialCandidate:
    if not isinstance(data, dict):
        raise ValueError(f"candidate {idx} must be an object")
    if not str(data.get("hlsl_body", "")).strip():
        raise ValueError(f"candidate {idx} is missing hlsl_body")

    prompt = str(data.get("prompt") or request.prompt)
    name = str(data.get("name") or f"{slugify(prompt)}_external_{idx + 1:03d}")
    candidate_id = str(data.get("id") or stable_id(prompt, idx, name, source_path))
    generation = dict(data.get("generation", {}))
    generation.setdefault("generator", "external_agent")
    generation.setdefault("agent_id", f"external_agent_{idx + 1:02d}")
    generation.setdefault("strategy", "external_submission")
    generation.setdefault("strategy_family", "external")
    generation.setdefault("variant_index", idx)
    generation.setdefault("batch_size", request.count)
    generation.setdefault("provenance", f"loaded_from:{source_path}")
    generation.setdefault("contract_version", AGENT_CONTRACT_VERSION)

    return MaterialCandidate(
        id=candidate_id,
        name=name,
        prompt=prompt,
        description=str(data.get("description", "External agent supplied HLSL material candidate.")),
        hlsl_body=str(data["hlsl_body"]),
        tags=list(data.get("tags", ["hlsl", "unreal", "custom-node", "external"])),
        parameters=dict(data.get("parameters", {})),
        generation=generation,
        source_refs=list(data.get("source_refs", [])),
        risk_notes=list(data.get("risk_notes", ["External candidate; verify license/provenance before customer use."])),
    )


def _first_prompt(candidates_data: list[Any]) -> str | None:
    for item in candidates_data:
        if isinstance(item, dict) and item.get("prompt"):
            return str(item["prompt"])
    return None
