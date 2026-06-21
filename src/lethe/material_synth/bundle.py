"""Bundle verified material packs into shareable zip artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .verifier import verify_pack


def bundle_pack(
    pack_dir: str | Path,
    output_zip: str | Path | None = None,
    mode: str = "pack",
    allow_failed: bool = False,
) -> dict[str, Any]:
    """Verify a pack and write a zip artifact.

    By default a failing verification blocks bundling. Set `allow_failed=True`
    only for debugging.
    """

    root = Path(pack_dir).resolve()
    report = verify_pack(root, mode=mode)
    if not report["ok"] and not allow_failed:
        return {
            "ok": False,
            "zip": None,
            "pack_dir": str(root),
            "verification": report,
            "error": "verification failed; bundle not written",
        }

    zip_path = Path(output_zip).resolve() if output_zip else root.with_suffix(".zip")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root.parent).as_posix())

    return {
        "ok": True,
        "zip": str(zip_path),
        "pack_dir": str(root),
        "mode": mode,
        "verification": report,
    }
