"""Small typed data model for the first HLSL-first material synthesizer.

The first product milestone is deliberately computer-friendly: generate a
bounded HLSL function body, validate it, and let UE consume it through a fixed
Custom node wrapper. Human-readable graph recipes can be derived later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any


def slugify(value: str, fallback: str = "material") -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return text or fallback


def stable_id(*parts: object, prefix: str = "mat") -> str:
    payload = "\n".join(str(p) for p in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class MaterialRequest:
    """User-facing request normalized for deterministic generation."""

    prompt: str
    count: int = 12
    seed: int = 0
    target: str = "unreal-custom-node"

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty")
        if self.count < 1:
            raise ValueError("count must be >= 1")
        if self.count > 100:
            raise ValueError("count must be <= 100 for a single local batch")


@dataclass(frozen=True)
class MaterialCandidate:
    """One HLSL candidate that fits Lethe's fixed material interface."""

    id: str
    name: str
    prompt: str
    description: str
    hlsl_body: str
    tags: list[str] = field(default_factory=list)
    parameters: dict[str, float | int | str | list[float]] = field(default_factory=dict)
    generation: dict[str, Any] = field(default_factory=dict)
    source_refs: list[dict[str, str]] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "description": self.description,
            "hlsl_body": self.hlsl_body,
            "tags": list(self.tags),
            "parameters": dict(self.parameters),
            "generation": dict(self.generation),
            "source_refs": list(self.source_refs),
            "risk_notes": list(self.risk_notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MaterialCandidate":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            prompt=str(data.get("prompt", "")),
            description=str(data.get("description", "")),
            hlsl_body=str(data["hlsl_body"]),
            tags=list(data.get("tags", [])),
            parameters=dict(data.get("parameters", {})),
            generation=dict(data.get("generation", {})),
            source_refs=list(data.get("source_refs", [])),
            risk_notes=list(data.get("risk_notes", [])),
        )


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue]
    normalized_hlsl: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [issue.to_dict() for issue in self.issues],
            "normalized_hlsl": self.normalized_hlsl,
        }
