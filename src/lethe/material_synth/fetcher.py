"""Safe manifest-based shader corpus fetching.

This layer intentionally does not crawl asset stores or bypass plugin/package
downloads. It downloads only URLs supplied in a manifest, keeps provenance next
to the files, and indexes the resulting local shader folder.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .corpus import DEFAULT_EXTENSIONS, index_shader_corpus, license_allows_reference

FETCH_SCHEMA_VERSION = 1
DEFAULT_MAX_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30
USER_AGENT = "LetheMaterialSynth/0.1 (+manifest-shader-corpus-fetch)"


@dataclass(frozen=True)
class FetchManifestOptions:
    manifest_path: Path
    output_dir: Path
    index_output: Path
    allow_unsafe: bool = False
    max_bytes: int = DEFAULT_MAX_BYTES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def fetch_shader_manifest(
    manifest_path: str | Path,
    output_dir: str | Path = "material-corpus/raw",
    index_output: str | Path = "material-corpus/index.json",
    allow_unsafe: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Download explicitly listed shader URLs, write provenance, and index them.

    The manifest can be either:

    - a list of item objects; or
    - an object with `source_label`, `license_label`, and `items`.

    Each item requires `url` and may include `path`, `license`, `source`,
    `author`, and `title`.
    """

    options = FetchManifestOptions(
        manifest_path=Path(manifest_path).resolve(),
        output_dir=Path(output_dir).resolve(),
        index_output=Path(index_output).resolve(),
        allow_unsafe=allow_unsafe,
        max_bytes=max(1, int(max_bytes)),
        timeout_seconds=max(1, int(timeout_seconds)),
    )
    manifest = _load_manifest(options.manifest_path)
    source_label = _clean_label(manifest["source_label"], "manifest")
    license_label = _clean_label(manifest["license_label"], "unknown")
    raw_root = (options.output_dir / _slugify(source_label, "source")).resolve()
    raw_root.mkdir(parents=True, exist_ok=True)

    downloads: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for index, item in enumerate(manifest["items"], start=1):
        normalized = _normalize_item(item, source_label, license_label, index)
        if "error" in normalized:
            skipped.append({"index": index, "reason": normalized["error"], "item": item})
            continue

        item_license = normalized["license"]
        reference_allowed = license_allows_reference(item_license)
        if not reference_allowed and not options.allow_unsafe:
            skipped.append(
                {
                    "index": index,
                    "url": normalized["url"],
                    "path": normalized["rel_path"],
                    "license": item_license,
                    "reason": "license/source label is not reference-safe; pass allow_unsafe only for discovery metadata",
                }
            )
            continue

        destination = (raw_root / normalized["rel_path"]).resolve()
        if not _is_relative_to(destination, raw_root):
            skipped.append(
                {
                    "index": index,
                    "url": normalized["url"],
                    "path": normalized["rel_path"],
                    "reason": "destination path escapes output root",
                }
            )
            continue

        suffix = destination.suffix.lower()
        if suffix not in DEFAULT_EXTENSIONS:
            skipped.append(
                {
                    "index": index,
                    "url": normalized["url"],
                    "path": normalized["rel_path"],
                    "reason": f"extension {suffix or '<none>'} is not a shader extension",
                }
            )
            continue

        try:
            data = _download_bytes(normalized["url"], options.max_bytes, options.timeout_seconds)
        except Exception as exc:
            failed.append(
                {
                    "index": index,
                    "url": normalized["url"],
                    "path": normalized["rel_path"],
                    "reason": str(exc),
                }
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        downloads.append(
            {
                "index": index,
                "url": normalized["url"],
                "path": str(destination),
                "rel_path": destination.relative_to(raw_root).as_posix(),
                "source": normalized["source"],
                "license": item_license,
                "reference_allowed": reference_allowed,
                "author": normalized.get("author"),
                "title": normalized.get("title"),
                "size": len(data),
                "sha1": hashlib.sha1(data).hexdigest(),
            }
        )

    provenance_path = raw_root / "sources.json"
    provenance = {
        "schema_version": FETCH_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(options.manifest_path),
        "source_label": source_label,
        "license_label": license_label,
        "allow_unsafe": options.allow_unsafe,
        "downloads": downloads,
        "skipped": skipped,
        "failed": failed,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")

    index = index_shader_corpus(
        [raw_root],
        options.index_output,
        source_label=source_label,
        license_label=license_label,
    )
    index = _patch_index_with_download_metadata(index["index_path"], downloads)
    report = {
        **provenance,
        "raw_root": str(raw_root),
        "provenance_path": str(provenance_path),
        "index_path": index["index_path"],
        "indexed_files": index["file_count"],
        "downloaded": len(downloads),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "reference_allowed": index["reference_allowed"],
    }
    report_path = raw_root / "download_report.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        return {"source_label": "manifest", "license_label": "unknown", "items": payload}
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object or a list")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("manifest object requires an items list")
    return {
        "source_label": payload.get("source_label") or payload.get("source") or "manifest",
        "license_label": payload.get("license_label") or payload.get("license") or "unknown",
        "items": items,
    }


def _normalize_item(item: Any, source_label: str, license_label: str, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"error": "item must be an object"}
    url = str(item.get("url") or "").strip()
    if not url:
        return {"error": "item requires url"}
    rel_path = str(item.get("path") or "").strip() or _path_from_url(url, index)
    if not rel_path:
        return {"error": "could not infer destination path"}
    safe_rel = _safe_relative_path(rel_path)
    if not safe_rel:
        return {"error": "destination path is empty or unsafe"}
    return {
        "url": url,
        "rel_path": safe_rel,
        "source": _clean_label(item.get("source") or source_label, source_label),
        "license": _clean_label(item.get("license") or license_label, "unknown"),
        "author": item.get("author"),
        "title": item.get("title"),
    }


def _download_bytes(url: str, max_bytes: int, timeout_seconds: int) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"download larger than max_bytes={max_bytes}")
    if not data.strip():
        raise ValueError("downloaded file is empty")
    return data


def _patch_index_with_download_metadata(index_path: str | Path, downloads: list[dict[str, Any]]) -> dict[str, Any]:
    index_file = Path(index_path)
    index = json.loads(index_file.read_text(encoding="utf-8-sig"))
    by_rel = {item["rel_path"]: item for item in downloads}
    all_reference_allowed = bool(downloads)
    for entry in index.get("entries", []):
        downloaded = by_rel.get(entry.get("rel_path"))
        if not downloaded:
            continue
        entry["source"] = downloaded["source"]
        entry["license"] = downloaded["license"]
        entry["reference_allowed"] = bool(downloaded["reference_allowed"])
        all_reference_allowed = all_reference_allowed and bool(downloaded["reference_allowed"])
    if downloads:
        licenses = sorted({item["license"] for item in downloads})
        sources = sorted({item["source"] for item in downloads})
        index["license_label"] = licenses[0] if len(licenses) == 1 else "mixed"
        index["source_label"] = sources[0] if len(sources) == 1 else "mixed"
        index["reference_allowed"] = all_reference_allowed
    index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**index, "index_path": str(index_file.resolve())}


def _path_from_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    name = PurePosixPath(unquote(parsed.path)).name
    if not name:
        return f"shader_{index:04d}.hlsl"
    return name


def _safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    parts = []
    for part in PurePosixPath(normalized).parts:
        if part in {"", ".", ".."}:
            return ""
        parts.append(_sanitize_filename(part))
    return "/".join(part for part in parts if part)


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    return sanitized or "unnamed"


def _slugify(value: str, fallback: str) -> str:
    lowered = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return lowered or fallback


def _clean_label(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
