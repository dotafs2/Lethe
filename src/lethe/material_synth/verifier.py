"""Artifact completeness checks for material packs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def verify_pack(pack_dir: str | Path, mode: str = "pack") -> dict[str, Any]:
    """Verify generated material pack artifacts.

    Modes:
    - pack: manifest/index/HLSL/UE scripts are present.
    - offline-demo: pack + synthetic report/summary/gallery/previews.
    - ue: pack + non-synthetic replay report/summary/gallery/previews.
    """

    root = Path(pack_dir)
    checks: list[dict[str, Any]] = []
    manifest_path = root / "manifest.json"
    checks.append(_check("pack_dir_exists", root.exists(), str(root), "Pack directory is missing."))
    checks.append(_check("manifest_exists", manifest_path.exists(), str(manifest_path), "manifest.json is missing."))

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            checks.append(_check("manifest_parse", True, str(manifest_path), "OK"))
        except Exception as exc:
            checks.append(_check("manifest_parse", False, str(exc), "manifest.json is not valid JSON."))

    checks.append(_check("index_exists", (root / "index.md").exists(), str(root / "index.md"), "index.md is missing."))
    _candidate_file_checks(root, manifest, checks)

    if mode in {"offline-demo", "ue"}:
        _report_checks(root, checks, require_synthetic=(mode == "offline-demo"), require_real=(mode == "ue"))

    ok = all(check["status"] != "fail" for check in checks)
    return {
        "ok": ok,
        "mode": mode,
        "pack_dir": str(root.resolve()),
        "checks": checks,
        "failures": [check for check in checks if check["status"] == "fail"],
        "warnings": [check for check in checks if check["status"] == "warn"],
    }


def _candidate_file_checks(root: Path, manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    candidates = manifest.get("candidates", []) if manifest else []
    checks.append(_check("candidate_count_positive", len(candidates) > 0, str(len(candidates)), "No candidates in manifest."))
    for candidate in candidates:
        cid = candidate.get("id", "unknown")
        files = candidate.get("files", {})
        for key in ("body_hlsl", "wrapped_hlsl"):
            rel = files.get(key)
            checks.append(
                _check(
                    f"candidate_{cid}_{key}",
                    bool(rel) and (root / rel).exists(),
                    str(rel),
                    f"{key} missing for candidate {cid}.",
                )
            )
        ue_script = files.get("ue_script")
        if manifest.get("include_ue_scripts"):
            checks.append(
                _check(
                    f"candidate_{cid}_ue_script",
                    bool(ue_script) and (root / ue_script).exists(),
                    str(ue_script),
                    f"UE script missing for candidate {cid}.",
                )
            )
    if manifest.get("include_ue_scripts"):
        replay = manifest.get("files", {}).get("ue_replay_script") or "run_pack_in_ue.py"
        checks.append(_check("ue_replay_script", (root / replay).exists(), replay, "run_pack_in_ue.py is missing."))


def _report_checks(root: Path, checks: list[dict[str, Any]], require_synthetic: bool, require_real: bool) -> None:
    report_path = root / "ue_validation_report.json"
    checks.append(_check("ue_validation_report_exists", report_path.exists(), str(report_path), "UE validation report is missing."))
    report: dict[str, Any] = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
            checks.append(_check("ue_validation_report_parse", True, str(report_path), "OK"))
        except Exception as exc:
            checks.append(_check("ue_validation_report_parse", False, str(exc), "UE validation report is invalid JSON."))
    synthetic = bool(report.get("synthetic_demo"))
    if require_synthetic:
        checks.append(_check("synthetic_demo_report", synthetic, str(synthetic), "Expected synthetic_demo=true."))
    if require_real:
        checks.append(_check("real_ue_report", not synthetic, str(synthetic), "Expected a real UE replay report, not synthetic demo output."))
    created = int(report.get("created", 0) or 0)
    checks.append(_check("created_positive", created > 0, str(created), "No material creations were reported."))
    previewed = int(report.get("previewed", 0) or 0)
    checks.append(_check("previewed_positive", previewed > 0, str(previewed), "No preview screenshots were reported."))
    preview_dir = root / "previews"
    png_count = len(list(preview_dir.glob("*.png"))) if preview_dir.exists() else 0
    checks.append(_check("preview_png_files", png_count > 0, str(png_count), "No preview PNG files found."))
    if require_real and png_count > 0:
        nonblank = _nonblank_preview_count(preview_dir)
        checks.append(
            _check(
                "preview_png_nonblank",
                nonblank > 0,
                str(nonblank),
                "Preview PNG files appear blank/black; rerun UE replay after fixing capture.",
            )
        )

    for name in ("customer_summary.json", "customer_summary.md", "customer_gallery.html"):
        checks.append(_check(f"{name}_exists", (root / name).exists(), str(root / name), f"{name} is missing."))


def _check(name: str, passed: bool, detail: str, hint: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "detail": detail,
        "hint": "OK" if passed else hint,
    }


def _nonblank_preview_count(preview_dir: Path) -> int:
    try:
        from PIL import Image, ImageStat
    except Exception:
        return 0
    count = 0
    for path in preview_dir.glob("*.png"):
        if path.name.endswith("_synthetic.png"):
            continue
        try:
            with Image.open(path) as image:
                stat = ImageStat.Stat(image.convert("L"))
                mean = float(stat.mean[0]) if stat.mean else 0.0
                extrema = image.convert("L").getextrema()
                contrast = float((extrema[1] - extrema[0]) if extrema else 0.0)
            if mean > 2.0 and contrast > 1.0:
                count += 1
        except Exception:
            continue
    return count
