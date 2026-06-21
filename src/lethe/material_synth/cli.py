"""Command line entrypoint for offline material pack generation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .analyzer import analyze_validation_report
from .agent_contract import load_agent_candidates, validate_agent_candidate_file
from .bundle import bundle_pack
from .corpus import build_reference_context, index_shader_corpus, search_shader_corpus
from .demo import build_offline_demo_report
from .doctor import run_doctor
from .fetcher import fetch_shader_manifest
from .pack import export_candidates_pack, export_material_pack
from .schema import MaterialRequest
from .verifier import verify_pack
from .workflow import build_demo_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lethe HLSL material synthesis tools.")
    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser("generate", help="Generate a material candidate pack.")
    generate.add_argument("prompt", help="Natural-language material request.")
    generate.add_argument("--count", type=int, default=12, help="Number of candidates, 1-100.")
    generate.add_argument("--seed", type=int, default=0, help="Deterministic variant seed.")
    generate.add_argument(
        "--output-dir",
        default="material-packs",
        help="Directory that will receive the generated pack.",
    )
    generate.add_argument(
        "--no-ue-scripts",
        action="store_true",
        help="Skip UE Python script files and export HLSL/manifest only.",
    )
    _add_reference_args(generate)
    analyze = subparsers.add_parser("analyze", help="Analyze a UE replay report.")
    analyze.add_argument("pack_dir", help="Material pack directory containing ue_validation_report.json.")
    demo = subparsers.add_parser("demo", help="Create synthetic previews and gallery for an existing pack.")
    demo.add_argument("pack_dir", help="Material pack directory containing manifest.json.")
    demo_generate = subparsers.add_parser("demo-generate", help="Generate a pack and synthetic gallery without UE.")
    demo_generate.add_argument("prompt", help="Natural-language material request.")
    demo_generate.add_argument("--count", type=int, default=12, help="Number of candidates, 1-100.")
    demo_generate.add_argument("--seed", type=int, default=0, help="Deterministic variant seed.")
    demo_generate.add_argument("--output-dir", default="material-packs", help="Directory for the generated pack.")
    _add_reference_args(demo_generate)
    demo_bundle = subparsers.add_parser("demo-bundle", help="Generate, preview, verify, and zip a synthetic demo pack.")
    demo_bundle.add_argument("prompt", help="Natural-language material request.")
    demo_bundle.add_argument("--count", type=int, default=12, help="Number of candidates, 1-100.")
    demo_bundle.add_argument("--seed", type=int, default=0, help="Deterministic variant seed.")
    demo_bundle.add_argument("--output-dir", default="material-packs", help="Directory for the generated pack.")
    demo_bundle.add_argument("--output-zip", default=None, help="Optional output zip path.")
    _add_reference_args(demo_bundle)
    pack_json = subparsers.add_parser("pack-json", help="Export a pack from external agent candidate JSON.")
    pack_json.add_argument("json_path", help="Path to agent candidate JSON.")
    pack_json.add_argument(
        "--output-dir",
        default="material-packs",
        help="Directory that will receive the generated pack.",
    )
    pack_json.add_argument(
        "--no-ue-scripts",
        action="store_true",
        help="Skip UE Python script files and export HLSL/manifest only.",
    )
    validate_json = subparsers.add_parser("validate-json", help="Validate external agent candidate JSON.")
    validate_json.add_argument("json_path", help="Path to agent candidate JSON.")
    validate_json.add_argument(
        "--report",
        default=None,
        help="Optional path to write agent_validation_report.json.",
    )
    doctor = subparsers.add_parser("doctor", help="Check local and optional UE project readiness.")
    doctor.add_argument("--ue-project", default=None, help="Optional path to a .uproject file.")
    verify = subparsers.add_parser("verify-pack", help="Verify material pack artifact completeness.")
    verify.add_argument("pack_dir", help="Material pack directory.")
    verify.add_argument(
        "--mode",
        choices=["pack", "offline-demo", "ue"],
        default="pack",
        help="Verification strictness.",
    )
    bundle = subparsers.add_parser("bundle-pack", help="Verify and zip a material pack.")
    bundle.add_argument("pack_dir", help="Material pack directory.")
    bundle.add_argument("--output", default=None, help="Optional output zip path.")
    bundle.add_argument(
        "--mode",
        choices=["pack", "offline-demo", "ue"],
        default="pack",
        help="Verification strictness before bundling.",
    )
    bundle.add_argument(
        "--allow-failed",
        action="store_true",
        help="Write zip even when verification fails.",
    )
    corpus_index = subparsers.add_parser("corpus-index", help="Index local shader reference files.")
    corpus_index.add_argument("roots", nargs="+", help="One or more local directories to scan.")
    corpus_index.add_argument(
        "--output",
        default="material-corpus/index.json",
        help="Output corpus index JSON path.",
    )
    corpus_index.add_argument("--source-label", default="local", help="Source/provenance label for indexed files.")
    corpus_index.add_argument("--license-label", default="unknown", help="License label for indexed files.")
    corpus_index.add_argument(
        "--max-indexed-bytes",
        type=int,
        default=512 * 1024,
        help="Maximum per-file bytes to read for symbols/snippets.",
    )
    corpus_index.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated extension allowlist, for example .hlsl,.ush,.glsl.",
    )
    corpus_search = subparsers.add_parser("corpus-search", help="Search a local shader corpus index.")
    corpus_search.add_argument("index_path", help="Path to corpus index JSON.")
    corpus_search.add_argument("query", help="Search query.")
    corpus_search.add_argument("--limit", type=int, default=10, help="Maximum matches, 1-100.")
    corpus_search.add_argument(
        "--require-reference-allowed",
        action="store_true",
        help="Return no matches unless the corpus license metadata is reference-safe.",
    )
    corpus_fetch = subparsers.add_parser(
        "corpus-fetch-manifest",
        help="Download explicitly listed shader URLs and index the local corpus.",
    )
    corpus_fetch.add_argument("manifest_json", help="Path to a shader source manifest JSON.")
    corpus_fetch.add_argument(
        "--output-dir",
        default="material-corpus/raw",
        help="Directory that will receive downloaded shader files.",
    )
    corpus_fetch.add_argument(
        "--index-output",
        default="material-corpus/index.json",
        help="Output corpus index JSON path.",
    )
    corpus_fetch.add_argument(
        "--allow-unsafe",
        action="store_true",
        help="Download unknown/non-permissive license items for discovery only; they remain marked unsafe.",
    )
    corpus_fetch.add_argument(
        "--max-bytes",
        type=int,
        default=1024 * 1024,
        help="Maximum bytes to download per shader file.",
    )
    corpus_fetch.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Network timeout per file.",
    )
    return parser


def _add_reference_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--corpus-index", default=None, help="Optional shader corpus index for retrieval context.")
    parser.add_argument("--reference-limit", type=int, default=5, help="Maximum corpus matches to record in manifest.")
    parser.add_argument(
        "--require-reference-allowed",
        action="store_true",
        help="Fail corpus retrieval unless index license metadata allows reference use.",
    )


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    commands = {
        "generate",
        "analyze",
        "demo",
        "demo-generate",
        "demo-bundle",
        "pack-json",
        "validate-json",
        "doctor",
        "verify-pack",
        "bundle-pack",
        "corpus-index",
        "corpus-search",
        "corpus-fetch-manifest",
        "-h",
        "--help",
    }
    if argv and argv[0] not in commands:
        argv = ["generate", *argv]
    args = build_parser().parse_args(argv)
    command = args.command or "generate"
    if command == "generate":
        reference_context = _reference_context_from_args(args)
        manifest = export_material_pack(
            MaterialRequest(prompt=args.prompt, count=args.count, seed=args.seed),
            Path(args.output_dir),
            include_ue_scripts=not args.no_ue_scripts,
            reference_context=reference_context,
        )
        print(json.dumps({"pack_dir": manifest["pack_dir"], "count": manifest["candidate_count"]}, indent=2))
    elif command == "analyze":
        summary = analyze_validation_report(args.pack_dir)
        print(
            json.dumps(
                {
                    "summary": str(Path(args.pack_dir).resolve() / "customer_summary.json"),
                    "markdown": str(Path(args.pack_dir).resolve() / "customer_summary.md"),
                    "gallery": str(Path(args.pack_dir).resolve() / "customer_gallery.html"),
                    "recommended": summary["recommended"],
                },
                indent=2,
            )
        )
    elif command == "demo":
        result = build_offline_demo_report(args.pack_dir)
        print(
            json.dumps(
                {
                    "pack_dir": result["pack_dir"],
                    "gallery": result["gallery"],
                    "count": result["report"]["count"],
                    "synthetic_demo": True,
                },
                indent=2,
            )
        )
    elif command == "demo-generate":
        reference_context = _reference_context_from_args(args)
        manifest = export_material_pack(
            MaterialRequest(prompt=args.prompt, count=args.count, seed=args.seed),
            Path(args.output_dir),
            include_ue_scripts=True,
            reference_context=reference_context,
        )
        result = build_offline_demo_report(manifest["pack_dir"])
        print(
            json.dumps(
                {
                    "pack_dir": result["pack_dir"],
                    "gallery": result["gallery"],
                    "count": result["report"]["count"],
                    "synthetic_demo": True,
                },
                indent=2,
            )
        )
    elif command == "demo-bundle":
        result = build_demo_bundle(
            args.prompt,
            output_dir=args.output_dir,
            count=args.count,
            seed=args.seed,
            output_zip=args.output_zip,
            corpus_index=args.corpus_index,
            reference_limit=args.reference_limit,
            require_reference_allowed=args.require_reference_allowed,
        )
        print(
            json.dumps(
                {
                    "ok": result["ok"],
                    "pack_dir": result["pack_dir"],
                    "gallery": result["gallery"],
                    "zip": result["zip"],
                    "count": result["count"],
                    "synthetic_demo": True,
                },
                indent=2,
            )
        )
    elif command == "pack-json":
        request, candidates = load_agent_candidates(args.json_path)
        manifest = export_candidates_pack(
            request,
            candidates,
            Path(args.output_dir),
            include_ue_scripts=not args.no_ue_scripts,
            source="agent_json",
        )
        print(json.dumps({"pack_dir": manifest["pack_dir"], "count": manifest["candidate_count"]}, indent=2))
    elif command == "validate-json":
        report = validate_agent_candidate_file(args.json_path, args.report)
        print(
            json.dumps(
                {
                    "loaded": report["loaded"],
                    "valid": report["valid"],
                    "invalid": report["invalid"],
                    "report": str(Path(args.report).resolve()) if args.report else None,
                },
                indent=2,
            )
        )
    elif command == "doctor":
        print(json.dumps(run_doctor(args.ue_project), indent=2))
    elif command == "verify-pack":
        report = verify_pack(args.pack_dir, mode=args.mode)
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "mode": report["mode"],
                    "failures": len(report["failures"]),
                    "warnings": len(report["warnings"]),
                    "pack_dir": report["pack_dir"],
                },
                indent=2,
            )
        )
    elif command == "bundle-pack":
        result = bundle_pack(
            args.pack_dir,
            output_zip=args.output,
            mode=args.mode,
            allow_failed=args.allow_failed,
        )
        print(
            json.dumps(
                {
                    "ok": result["ok"],
                    "zip": result["zip"],
                    "pack_dir": result["pack_dir"],
                    "mode": args.mode,
                    "error": result.get("error"),
                },
                indent=2,
            )
        )
    elif command == "corpus-index":
        extensions = args.extensions.split(",") if args.extensions else None
        index = index_shader_corpus(
            args.roots,
            args.output,
            source_label=args.source_label,
            license_label=args.license_label,
            max_indexed_bytes=args.max_indexed_bytes,
            extensions=extensions,
        )
        print(
            json.dumps(
                {
                    "index_path": index["index_path"],
                    "file_count": index["file_count"],
                    "total_bytes": index["total_bytes"],
                    "reference_allowed": index["reference_allowed"],
                    "skipped": len(index["skipped"]),
                },
                indent=2,
            )
        )
    elif command == "corpus-search":
        result = search_shader_corpus(
            args.index_path,
            args.query,
            limit=args.limit,
            require_reference_allowed=args.require_reference_allowed,
        )
        print(
            json.dumps(
                {
                    "ok": result["ok"],
                    "query": result["query"],
                    "matches": [
                        {
                            "score": item["score"],
                            "path": item["entry"]["path"],
                            "rel_path": item["entry"]["rel_path"],
                            "language": item["entry"]["language"],
                            "license": item["entry"]["license"],
                            "risk_notes": item["risk_notes"],
                            "snippet": item["snippet"],
                        }
                        for item in result["matches"]
                    ],
                    "error": result.get("error"),
                },
                indent=2,
            )
        )
    elif command == "corpus-fetch-manifest":
        report = fetch_shader_manifest(
            args.manifest_json,
            output_dir=args.output_dir,
            index_output=args.index_output,
            allow_unsafe=args.allow_unsafe,
            max_bytes=args.max_bytes,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            json.dumps(
                {
                    "downloaded": report["downloaded"],
                    "skipped": report["skipped_count"],
                    "failed": report["failed_count"],
                    "raw_root": report["raw_root"],
                    "report_path": report["report_path"],
                    "index_path": report["index_path"],
                    "indexed_files": report["indexed_files"],
                    "reference_allowed": report["reference_allowed"],
                },
                indent=2,
            )
        )
    else:
        raise SystemExit(f"unknown command: {command}")
    return 0


def _reference_context_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    corpus_index = getattr(args, "corpus_index", None)
    if not corpus_index:
        return None
    return build_reference_context(
        corpus_index,
        args.prompt,
        limit=getattr(args, "reference_limit", 5),
        require_reference_allowed=getattr(args, "require_reference_allowed", False),
    )


if __name__ == "__main__":
    raise SystemExit(main())
