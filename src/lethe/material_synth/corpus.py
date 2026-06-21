"""Local shader reference corpus indexing and search.

The corpus layer is deliberately local-first and provenance-first. It indexes
shader files without copying full source into the index, so a large reference
folder can stay reviewable and license-aware.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .schema import stable_id

CORPUS_SCHEMA_VERSION = 1
DEFAULT_EXTENSIONS = {
    ".hlsl",
    ".usf",
    ".ush",
    ".glsl",
    ".frag",
    ".vert",
    ".comp",
    ".geom",
    ".tesc",
    ".tese",
    ".shader",
    ".cginc",
}
PERMISSIVE_LICENSE_TOKENS = {
    "mit",
    "apache",
    "bsd",
    "zlib",
    "isc",
    "public-domain",
    "public domain",
    "cc0",
    "unlicense",
}
BLOCKED_LICENSE_TOKENS = {
    "unknown",
    "proprietary",
    "commercial",
    "marketplace",
    "fab",
    "asset store",
}
MAX_INDEXED_BYTES = 512 * 1024


@dataclass(frozen=True)
class CorpusIndexOptions:
    roots: list[Path]
    output_path: Path
    source_label: str = "local"
    license_label: str = "unknown"
    max_indexed_bytes: int = MAX_INDEXED_BYTES
    extensions: set[str] | None = None


def index_shader_corpus(
    roots: Iterable[str | Path],
    output_path: str | Path,
    source_label: str = "local",
    license_label: str = "unknown",
    max_indexed_bytes: int = MAX_INDEXED_BYTES,
    extensions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Index local shader files into a compact JSON manifest."""

    root_paths = [Path(root).resolve() for root in roots]
    if not root_paths:
        raise ValueError("at least one corpus root is required")
    missing = [str(root) for root in root_paths if not root.exists()]
    if missing:
        raise FileNotFoundError(f"corpus root not found: {missing[0]}")

    ext_set = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in (extensions or DEFAULT_EXTENSIONS)}
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for root in root_paths:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in ext_set:
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped.append({"path": str(path), "reason": f"stat failed: {exc}"})
                continue
            if size > max_indexed_bytes:
                skipped.append({"path": str(path), "reason": f"larger than max_indexed_bytes={max_indexed_bytes}"})
                entries.append(_metadata_only_entry(path, root, size, source_label, license_label))
                continue
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                skipped.append({"path": str(path), "reason": f"read failed: {exc}"})
                continue
            entries.append(_entry_from_text(path, root, text, source_label, license_label, size))

    index = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roots": [str(root) for root in root_paths],
        "source_label": source_label,
        "license_label": license_label,
        "reference_allowed": _license_allows_reference(license_label),
        "extensions": sorted(ext_set),
        "file_count": len(entries),
        "total_bytes": sum(int(entry.get("size", 0)) for entry in entries),
        "skipped": skipped,
        "entries": entries,
    }
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**index, "index_path": str(out)}


def search_shader_corpus(
    index_path: str | Path,
    query: str,
    limit: int = 10,
    require_reference_allowed: bool = False,
) -> dict[str, Any]:
    """Search a corpus index using deterministic local token scoring."""

    if not query.strip():
        raise ValueError("query cannot be empty")
    index_file = Path(index_path)
    index = json.loads(index_file.read_text(encoding="utf-8-sig"))
    reference_allowed = bool(index.get("reference_allowed"))
    if require_reference_allowed and not reference_allowed:
        return {
            "ok": False,
            "query": query,
            "index_path": str(index_file.resolve()),
            "matches": [],
            "error": "index license/source metadata is not marked reference_allowed",
            "license_label": index.get("license_label", "unknown"),
        }

    query_tokens = _tokens(query)
    ranked = []
    for entry in index.get("entries", []):
        score = _score_entry(entry, query_tokens)
        if score <= 0:
            continue
        ranked.append(
            {
                "score": score,
                "entry": entry,
                "snippet": _snippet_for_entry(entry, query_tokens),
                "risk_notes": _entry_risk_notes(entry, reference_allowed),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["entry"].get("rel_path", "")))
    return {
        "ok": True,
        "query": query,
        "index_path": str(index_file.resolve()),
        "license_label": index.get("license_label", "unknown"),
        "reference_allowed": reference_allowed,
        "matches": ranked[: max(1, min(int(limit), 100))],
    }


def build_reference_context(
    index_path: str | Path,
    query: str,
    limit: int = 5,
    require_reference_allowed: bool = False,
) -> dict[str, Any]:
    """Return compact, manifest-safe retrieval context for a material request."""

    result = search_shader_corpus(
        index_path,
        query,
        limit=limit,
        require_reference_allowed=require_reference_allowed,
    )
    return {
        "ok": result["ok"],
        "query": query,
        "index_path": result["index_path"],
        "license_label": result.get("license_label"),
        "reference_allowed": result.get("reference_allowed"),
        "error": result.get("error"),
        "matches": [
            {
                "score": item["score"],
                "id": item["entry"]["id"],
                "path": item["entry"]["path"],
                "rel_path": item["entry"]["rel_path"],
                "language": item["entry"]["language"],
                "source": item["entry"]["source"],
                "license": item["entry"]["license"],
                "risk_notes": item["risk_notes"],
                "snippet": item["snippet"],
            }
            for item in result.get("matches", [])
        ],
    }


def _metadata_only_entry(path: Path, root: Path, size: int, source_label: str, license_label: str) -> dict[str, Any]:
    rel = _safe_rel(path, root)
    return {
        "id": stable_id(str(path), size, prefix="src"),
        "path": str(path),
        "rel_path": rel,
        "extension": path.suffix.lower(),
        "language": _language_for_extension(path.suffix),
        "size": size,
        "line_count": None,
        "sha1": None,
        "symbols": [],
        "keywords": [],
        "snippet": "",
        "source": source_label,
        "license": license_label,
        "reference_allowed": _license_allows_reference(license_label),
        "metadata_only": True,
    }


def _entry_from_text(path: Path, root: Path, text: str, source_label: str, license_label: str, size: int) -> dict[str, Any]:
    rel = _safe_rel(path, root)
    return {
        "id": stable_id(str(path), text[:4096], prefix="src"),
        "path": str(path),
        "rel_path": rel,
        "extension": path.suffix.lower(),
        "language": _language_for_extension(path.suffix),
        "size": size,
        "line_count": text.count("\n") + 1 if text else 0,
        "sha1": hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest(),
        "symbols": _extract_symbols(text),
        "keywords": _top_keywords(text),
        "snippet": _first_meaningful_lines(text),
        "source": source_label,
        "license": license_label,
        "reference_allowed": _license_allows_reference(license_label),
        "metadata_only": False,
    }


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _language_for_extension(ext: str) -> str:
    value = ext.lower()
    if value in {".hlsl", ".usf", ".ush", ".cginc"}:
        return "hlsl"
    if value in {".glsl", ".frag", ".vert", ".comp", ".geom", ".tesc", ".tese"}:
        return "glsl"
    return "shader"


def license_allows_reference(label: str) -> bool:
    """Return whether a license/source label is safe for direct reference use."""

    return _license_allows_reference(label)


def _license_allows_reference(label: str) -> bool:
    lowered = label.strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in BLOCKED_LICENSE_TOKENS):
        return False
    return any(token in lowered for token in PERMISSIVE_LICENSE_TOKENS)


def _extract_symbols(text: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:float|float[234]|half|half[234]|fixed|fixed[234]|vec[234]|mat[234]|void)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    )
    return sorted(set(pattern.findall(text)))[:64]


def _top_keywords(text: str) -> list[str]:
    ignore = {
        "float",
        "float2",
        "float3",
        "float4",
        "half",
        "vec2",
        "vec3",
        "vec4",
        "return",
        "const",
        "uniform",
        "void",
        "main",
    }
    counts = Counter(token for token in _tokens(text) if token not in ignore and len(token) > 2)
    return [token for token, _count in counts.most_common(32)]


def _first_meaningful_lines(text: str, max_lines: int = 12) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped[:180])
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text.lower())


def _score_entry(entry: dict[str, Any], query_tokens: list[str]) -> int:
    fields = " ".join(
        [
            str(entry.get("rel_path", "")),
            str(entry.get("language", "")),
            " ".join(entry.get("symbols", [])),
            " ".join(entry.get("keywords", [])),
            str(entry.get("snippet", "")),
        ]
    ).lower()
    score = 0
    for token in query_tokens:
        if token in fields:
            score += 2
        if token in entry.get("symbols", []):
            score += 5
        if token in entry.get("keywords", []):
            score += 3
    return score


def _snippet_for_entry(entry: dict[str, Any], query_tokens: list[str]) -> str:
    snippet = str(entry.get("snippet", ""))
    path = entry.get("path")
    if not path or entry.get("metadata_only"):
        return snippet
    source_path = Path(path)
    if not source_path.exists() or source_path.stat().st_size > MAX_INDEXED_BYTES:
        return snippet
    try:
        lines = source_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return snippet
    lowered_tokens = set(query_tokens)
    for idx, line in enumerate(lines):
        if any(token in line.lower() for token in lowered_tokens):
            start = max(0, idx - 2)
            end = min(len(lines), idx + 5)
            return "\n".join(lines[start:end])
    return snippet


def _entry_risk_notes(entry: dict[str, Any], corpus_reference_allowed: bool) -> list[str]:
    notes = []
    if not corpus_reference_allowed or not entry.get("reference_allowed"):
        notes.append("License/source metadata is not marked safe for direct reference reuse.")
    if entry.get("metadata_only"):
        notes.append("File was too large for snippet indexing; inspect source manually before use.")
    return notes
