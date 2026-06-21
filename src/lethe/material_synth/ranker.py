"""Local ranking heuristics for material candidates.

This is a cheap pre-UE filter. It does not replace real shader compilation or
visual judging; it simply orders candidates so the expensive steps can spend
time on stronger variants first.
"""
from __future__ import annotations

from .schema import MaterialCandidate
from .validator import validate_candidate


def rank_candidate(candidate: MaterialCandidate, prompt: str) -> dict[str, object]:
    validation = validate_candidate(candidate)
    score = 0.0
    reasons: list[str] = []

    if validation.ok:
        score += 50.0
        reasons.append("passes static HLSL validation")
    else:
        score -= 100.0
        reasons.append("fails static HLSL validation")

    prompt_lower = prompt.lower()
    tag_set = {tag.lower() for tag in candidate.tags}

    if any(token in prompt_lower for token in ("ocean", "sea", "water", "wave", "foam", "海", "水", "浪")):
        overlap = tag_set & {"water", "anime", "procedural"}
        score += len(overlap) * 8.0
        if overlap:
            reasons.append("tags match water/anime prompt")

    body = candidate.hlsl_body
    feature_tokens = {
        "foam": "foam_mask",
        "motion": "I.Time",
        "bands": "floor(",
        "rim": "fresnel",
        "noise": "lethe_fbm",
    }
    for label, token in feature_tokens.items():
        if token in body:
            score += 4.0
            reasons.append(f"contains {label} signal")

    params = candidate.parameters
    if "detail_phase" in params:
        score += min(float(params["detail_phase"]), 5.0)
        reasons.append("has detail phase metadata")

    if len(body) < 900:
        score -= 4.0
        reasons.append("body may be too simple")
    elif len(body) > 7000:
        score -= 8.0
        reasons.append("body may be too large for quick iteration")
    else:
        score += 3.0
        reasons.append("body length is within quick-iteration range")

    return {
        "score": round(score, 3),
        "reasons": reasons,
        "validation_ok": validation.ok,
    }


def rank_candidates(candidates: list[MaterialCandidate], prompt: str) -> list[dict[str, object]]:
    ranked = []
    for candidate in candidates:
        item = {
            "candidate": candidate,
            "rank": rank_candidate(candidate, prompt),
        }
        ranked.append(item)
    ranked.sort(key=lambda item: float(item["rank"]["score"]), reverse=True)
    return ranked
