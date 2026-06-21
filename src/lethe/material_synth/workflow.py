"""High-level material synthesis workflows for customer-ready artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .bundle import bundle_pack
from .corpus import build_reference_context
from .demo import build_offline_demo_report
from .pack import export_material_pack
from .schema import MaterialRequest
from .verifier import verify_pack


def build_demo_bundle(
    prompt: str,
    output_dir: str | Path = "material-packs",
    count: int = 12,
    seed: int = 0,
    output_zip: str | Path | None = None,
    corpus_index: str | Path | None = None,
    reference_limit: int = 5,
    require_reference_allowed: bool = False,
) -> dict[str, Any]:
    """Generate, preview, verify, and zip a synthetic offline demo pack.

    This is intentionally marked as a synthetic demo artifact. It is useful for
    customer-facing workflow previews before a UE project is connected, but it
    does not claim shader compilation or real render validation.
    """

    reference_context = None
    if corpus_index:
        reference_context = build_reference_context(
            corpus_index,
            prompt,
            limit=reference_limit,
            require_reference_allowed=require_reference_allowed,
        )
    manifest = export_material_pack(
        MaterialRequest(prompt=prompt, count=count, seed=seed),
        Path(output_dir),
        include_ue_scripts=True,
        reference_context=reference_context,
    )
    demo = build_offline_demo_report(manifest["pack_dir"])
    verification = verify_pack(manifest["pack_dir"], mode="offline-demo")
    zip_target = Path(output_zip).resolve() if output_zip else Path(manifest["pack_dir"]).with_suffix(".demo.zip")
    bundle = bundle_pack(manifest["pack_dir"], zip_target, mode="offline-demo")
    return {
        "ok": bool(verification["ok"] and bundle["ok"]),
        "prompt": prompt,
        "count": manifest["candidate_count"],
        "pack_dir": manifest["pack_dir"],
        "gallery": demo["gallery"],
        "zip": bundle["zip"],
        "synthetic_demo": True,
        "reference_context": reference_context,
        "verification": verification,
        "bundle": bundle,
    }
