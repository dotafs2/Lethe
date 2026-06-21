import json
import ast
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lethe.material_synth.analyzer import analyze_validation_report
from lethe.material_synth.agent_contract import load_agent_candidates, validate_agent_candidate_file
from lethe.material_synth.bundle import bundle_pack
from lethe.material_synth.cli import main as material_synth_cli
from lethe.material_synth.corpus import index_shader_corpus, search_shader_corpus
from lethe.material_synth.demo import build_offline_demo_report
from lethe.material_synth.doctor import run_doctor
from lethe.material_synth.fetcher import fetch_shader_manifest
from lethe.material_synth.generator import generate_candidates
from lethe.material_synth.pack import export_material_pack
from lethe.material_synth.pack import export_candidates_pack
from lethe.material_synth.ranker import rank_candidate, rank_candidates
from lethe.material_synth.schema import MaterialRequest
from lethe.material_synth.templates import build_channel_custom_code
from lethe.material_synth.ue_bridge import build_create_material_script, build_pack_replay_script
from lethe.material_synth.validator import validate_candidate, validate_hlsl_body
from lethe.material_synth.verifier import verify_pack
from lethe.material_synth.workflow import build_demo_bundle


class MaterialSynthTests(unittest.TestCase):
    def test_ocean_candidates_validate(self):
        candidates = generate_candidates(MaterialRequest("二次元海的材质", count=8))
        self.assertEqual(len(candidates), 8)
        self.assertTrue(any("water" in c.tags for c in candidates))
        for candidate in candidates:
            result = validate_candidate(candidate)
            self.assertTrue(result.ok, json.dumps(result.to_dict(), indent=2))
            self.assertIn("LetheMaterialOutput LetheMain", result.normalized_hlsl)

    def test_validator_rejects_unsafe_tokens(self):
        result = validate_hlsl_body(
            """
    LetheMaterialOutput O;
    Texture2D BadTexture;
    O.BaseColor = float3(1, 0, 0);
    O.Roughness = 1;
    O.Metallic = 0;
    O.Alpha = 1;
    O.Emissive = float3(0, 0, 0);
    return O;
"""
        )
        self.assertFalse(result.ok)
        self.assertTrue(any(issue.code == "banned_token" for issue in result.issues))

    def test_custom_channel_code_is_single_channel_wrapper(self):
        candidate = generate_candidates("anime ocean foam", count=1)[0]
        code = build_channel_custom_code(candidate, "BaseColor")
        self.assertIn("return O_BaseColor", code)
        self.assertIn("float3 O_BaseColor", code)
        self.assertNotIn("LetheMaterialOutput", code)
        self.assertNotIn("LetheMain_", code)

    def test_ue_script_contains_material_creation_payload(self):
        candidate = generate_candidates("anime ocean foam", count=1)[0]
        script = build_create_material_script(candidate)
        self.assertIn("MaterialFactoryNew", script)
        self.assertIn("LETHE_MATERIAL_JSON::", script)
        self.assertIn(candidate.id, script)
        ast.parse(script)

    def test_ranker_orders_valid_ocean_candidates(self):
        candidates = generate_candidates("anime ocean foam", count=6)
        ranked = rank_candidates(candidates, "anime ocean foam")
        self.assertEqual(len(ranked), 6)
        self.assertGreaterEqual(
            ranked[0]["rank"]["score"],
            ranked[-1]["rank"]["score"],
        )
        self.assertTrue(rank_candidate(candidates[0], "anime ocean foam")["validation_ok"])

    def test_generation_metadata_supports_100_candidate_agent_batches(self):
        candidates = generate_candidates("anime ocean foam", count=100)
        agents = {candidate.generation["agent_id"] for candidate in candidates}
        self.assertEqual(len(candidates), 100)
        self.assertEqual(len(agents), 10)
        self.assertTrue(all(candidate.generation["strategy"] for candidate in candidates))

    def test_export_material_pack_writes_review_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=3),
                tmp,
                include_ue_scripts=True,
            )
            pack_dir = Path(manifest["pack_dir"])
            self.assertTrue((pack_dir / "manifest.json").exists())
            self.assertTrue((pack_dir / "index.md").exists())
            self.assertTrue((pack_dir / "run_pack_in_ue.py").exists())
            self.assertEqual(manifest["candidate_count"], 3)
            self.assertGreaterEqual(manifest["agent_count"], 1)
            self.assertTrue(manifest["strategy_counts"])
            self.assertEqual(manifest["files"]["preview_dir"], "previews")
            first = manifest["candidates"][0]
            self.assertTrue((pack_dir / first["files"]["body_hlsl"]).exists())
            self.assertTrue((pack_dir / first["files"]["wrapped_hlsl"]).exists())
            self.assertTrue((pack_dir / first["files"]["ue_script"]).exists())
            ast.parse((pack_dir / "run_pack_in_ue.py").read_text(encoding="utf-8"))
            loaded = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["pack_id"], manifest["pack_id"])

    def test_pack_replay_script_parses(self):
        candidate = generate_candidates("anime ocean foam", count=1)[0]
        manifest = {
            "candidates": [
                {
                    **candidate.to_dict(),
                    "order": 1,
                    "files": {"ue_script": "ue_scripts/create.py"},
                }
            ]
        }
        script = build_pack_replay_script(manifest, "C:/Temp/Lethe Pack")
        self.assertIn("LETHE_PACK_REPLAY_JSON::", script)
        self.assertIn("PREVIEW_DIR", script)
        self.assertIn("_capture_preview", script)
        self.assertIn('"previewed": report["previewed"]', script)
        ast.parse(script)

    def test_analyze_validation_report_writes_customer_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp)
            preview_dir = pack_dir / "previews"
            preview_dir.mkdir()
            preview_path = preview_dir / "001_mat_test.png"
            Image.new("RGB", (32, 32), (20, 150, 210)).save(preview_path)
            report = {
                "pack_dir": str(pack_dir),
                "count": 1,
                "created": 1,
                "previewed": 1,
                "results": [
                    {
                        "candidate_id": "mat_test",
                        "order": 1,
                        "name": "M_Test",
                        "generation": {
                            "agent_id": "agent_01",
                            "strategy": "graphic_foam_shapes",
                        },
                        "create_ok": True,
                        "payload": {"asset": "/Game/Lethe/GeneratedMaterials/M_Test"},
                        "compile": {"attempted": True, "ok": True, "error": None},
                        "preview": {
                            "attempted": True,
                            "ok": True,
                            "path": str(preview_path),
                            "error": None,
                        },
                    }
                ],
            }
            (pack_dir / "ue_validation_report.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            summary = analyze_validation_report(pack_dir)
            self.assertEqual(summary["recommended"]["candidate_id"], "mat_test")
            self.assertEqual(summary["recommended"]["agent_id"], "agent_01")
            self.assertTrue((pack_dir / "customer_summary.json").exists())
            self.assertTrue((pack_dir / "customer_summary.md").exists())
            gallery = pack_dir / "customer_gallery.html"
            self.assertTrue(gallery.exists())
            self.assertIn("001_mat_test.png", gallery.read_text(encoding="utf-8"))
            self.assertIsNotNone(summary["recommended"]["image_metrics"])

    def test_cli_generate_legacy_prompt_form_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = material_synth_cli(["anime ocean foam", "--count", "1", "--output-dir", tmp])
            self.assertEqual(rc, 0)
            self.assertEqual(len(list(Path(tmp).glob("*/manifest.json"))), 1)

    def test_agent_candidate_json_can_be_exported_as_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "agents.json"
            source.write_text(
                json.dumps(
                    {
                        "request": {"prompt": "anime ocean foam"},
                        "candidates": [
                            {
                                "name": "ExternalOcean",
                                "hlsl_body": """
    LetheMaterialOutput O;
    O.BaseColor = float3(0.0, 0.4, 0.8);
    O.Roughness = 0.5;
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = float3(0.0, 0.0, 0.0);
    return O;
""",
                                "generation": {
                                    "agent_id": "agent_ext_01",
                                    "strategy": "external_test",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            request, candidates = load_agent_candidates(source)
            self.assertEqual(request.prompt, "anime ocean foam")
            self.assertEqual(candidates[0].generation["agent_id"], "agent_ext_01")
            manifest = export_candidates_pack(request, candidates, tmp, source="agent_json")
            self.assertEqual(manifest["source"], "agent_json")
            self.assertEqual(manifest["agent_count"], 1)
            first = manifest["candidates"][0]
            self.assertEqual(first["generation"]["strategy"], "external_test")
            self.assertTrue((Path(manifest["pack_dir"]) / first["files"]["ue_script"]).exists())

    def test_cli_pack_json_exports_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "agents.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "prompt": "anime ocean foam",
                            "hlsl_body": """
    LetheMaterialOutput O;
    O.BaseColor = float3(0.0, 0.5, 1.0);
    O.Roughness = 0.4;
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = float3(0.0, 0.0, 0.0);
    return O;
""",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            out = Path(tmp) / "packs"
            rc = material_synth_cli(["pack-json", str(source), "--output-dir", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(len(list(out.glob("*/manifest.json"))), 1)

    def test_validate_agent_json_reports_invalid_hlsl(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "agents.json"
            source.write_text(
                json.dumps(
                    {
                        "request": {"prompt": "anime ocean foam"},
                        "candidates": [
                            {
                                "name": "Good",
                                "hlsl_body": """
    LetheMaterialOutput O;
    O.BaseColor = float3(0.0, 0.5, 1.0);
    O.Roughness = 0.4;
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = float3(0.0, 0.0, 0.0);
    return O;
""",
                            },
                            {
                                "name": "Bad",
                                "hlsl_body": """
    LetheMaterialOutput O;
    O.BaseColor = float3(1.0, 0.0, 0.0);
    O.Roughness = 0.4;
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    return O;
""",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report_path = Path(tmp) / "agent_validation_report.json"
            report = validate_agent_candidate_file(source, report_path)
            self.assertEqual(report["valid"], 1)
            self.assertEqual(report["invalid"], 1)
            self.assertTrue(report_path.exists())
            self.assertTrue(any(item["name"] == "Bad" and not item["ok"] for item in report["items"]))

    def test_cli_validate_json_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "agents.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "prompt": "anime ocean foam",
                            "hlsl_body": """
    LetheMaterialOutput O;
    O.BaseColor = float3(0.0, 0.5, 1.0);
    O.Roughness = 0.4;
    O.Metallic = 0.0;
    O.Alpha = 1.0;
    O.Emissive = float3(0.0, 0.0, 0.0);
    return O;
""",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            report_path = Path(tmp) / "report.json"
            rc = material_synth_cli(["validate-json", str(source), "--report", str(report_path)])
            self.assertEqual(rc, 0)
            self.assertTrue(report_path.exists())

    def test_offline_demo_report_writes_synthetic_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=2),
                tmp,
                include_ue_scripts=True,
            )
            result = build_offline_demo_report(manifest["pack_dir"])
            pack_dir = Path(result["pack_dir"])
            report = json.loads((pack_dir / "ue_validation_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["synthetic_demo"])
            self.assertEqual(report["previewed"], 2)
            self.assertEqual(len(list((pack_dir / "previews").glob("*.png"))), 2)
            self.assertTrue((pack_dir / "customer_gallery.html").exists())

    def test_cli_demo_generate_writes_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = material_synth_cli(["demo-generate", "anime ocean foam", "--count", "1", "--output-dir", tmp])
            self.assertEqual(rc, 0)
            pack_dirs = list(Path(tmp).glob("*"))
            self.assertEqual(len(pack_dirs), 1)
            self.assertTrue((pack_dirs[0] / "customer_gallery.html").exists())

    def test_verify_pack_passes_pack_and_offline_demo_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=2),
                tmp,
                include_ue_scripts=True,
            )
            pack_report = verify_pack(manifest["pack_dir"], mode="pack")
            self.assertTrue(pack_report["ok"], pack_report)
            build_offline_demo_report(manifest["pack_dir"])
            demo_report = verify_pack(manifest["pack_dir"], mode="offline-demo")
            self.assertTrue(demo_report["ok"], demo_report)
            ue_report = verify_pack(manifest["pack_dir"], mode="ue")
            self.assertFalse(ue_report["ok"])
            self.assertTrue(any(check["name"] == "real_ue_report" for check in ue_report["failures"]))

    def test_verify_pack_rejects_blank_real_ue_previews(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                tmp,
                include_ue_scripts=True,
            )
            pack_dir = Path(manifest["pack_dir"])
            preview_dir = pack_dir / "previews"
            preview_dir.mkdir(exist_ok=True)
            preview_path = preview_dir / "001_black.png"
            Image.new("RGB", (32, 32), (0, 0, 0)).save(preview_path)
            report = {
                "pack_dir": str(pack_dir),
                "count": 1,
                "created": 1,
                "previewed": 1,
                "preview_dir": str(preview_dir),
                "results": [
                    {
                        "candidate_id": "mat_test",
                        "order": 1,
                        "name": "M_Test",
                        "create_ok": True,
                        "compile": {"attempted": True, "ok": True, "error": None},
                        "preview": {"attempted": True, "ok": True, "path": str(preview_path), "error": None},
                    }
                ],
            }
            (pack_dir / "ue_validation_report.json").write_text(json.dumps(report), encoding="utf-8")
            analyze_validation_report(pack_dir)
            ue_report = verify_pack(pack_dir, mode="ue")
            self.assertFalse(ue_report["ok"])
            self.assertTrue(any(check["name"] == "preview_png_nonblank" for check in ue_report["failures"]))

    def test_cli_verify_pack_reports_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                tmp,
                include_ue_scripts=True,
            )
            rc = material_synth_cli(["verify-pack", manifest["pack_dir"], "--mode", "pack"])
            self.assertEqual(rc, 0)

    def test_bundle_pack_writes_zip_after_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                tmp,
                include_ue_scripts=True,
            )
            build_offline_demo_report(manifest["pack_dir"])
            zip_path = Path(tmp) / "bundle.zip"
            result = bundle_pack(manifest["pack_dir"], zip_path, mode="offline-demo")
            self.assertTrue(result["ok"], result)
            self.assertTrue(zip_path.exists())

    def test_bundle_pack_blocks_failed_ue_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                tmp,
                include_ue_scripts=True,
            )
            build_offline_demo_report(manifest["pack_dir"])
            zip_path = Path(tmp) / "bundle.zip"
            result = bundle_pack(manifest["pack_dir"], zip_path, mode="ue")
            self.assertFalse(result["ok"])
            self.assertFalse(zip_path.exists())
            failure_names = {check["name"] for check in result["verification"]["failures"]}
            self.assertIn("real_ue_report", failure_names)

    def test_cli_bundle_pack_writes_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                tmp,
                include_ue_scripts=True,
            )
            build_offline_demo_report(manifest["pack_dir"])
            zip_path = Path(tmp) / "cli_bundle.zip"
            rc = material_synth_cli([
                "bundle-pack",
                manifest["pack_dir"],
                "--mode",
                "offline-demo",
                "--output",
                str(zip_path),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(zip_path.exists())

    def test_demo_bundle_writes_verified_zip_and_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "demo.zip"
            result = build_demo_bundle(
                "anime ocean foam",
                output_dir=Path(tmp) / "packs",
                count=2,
                output_zip=zip_path,
            )
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["synthetic_demo"])
            self.assertTrue(zip_path.exists())
            self.assertTrue(Path(result["gallery"]).exists())
            self.assertTrue(result["verification"]["ok"])

    def test_cli_demo_bundle_writes_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "cli_demo.zip"
            rc = material_synth_cli([
                "demo-bundle",
                "anime ocean foam",
                "--count",
                "1",
                "--output-dir",
                str(Path(tmp) / "packs"),
                "--output-zip",
                str(zip_path),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(zip_path.exists())

    def test_corpus_index_and_search_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shaders"
            root.mkdir()
            (root / "OceanFoam.hlsl").write_text(
                """
float3 AnimeOceanFoam(float2 uv, float time)
{
    float foam = smoothstep(0.4, 0.8, sin(uv.x * 12.0 + time));
    return lerp(float3(0.0, 0.5, 0.9), float3(1.0, 1.0, 0.9), foam);
}
""",
                encoding="utf-8",
            )
            (root / "unrelated.txt").write_text("not a shader", encoding="utf-8")
            index_path = Path(tmp) / "index.json"
            index = index_shader_corpus(
                [root],
                index_path,
                source_label="unit-test",
                license_label="MIT",
            )
            self.assertEqual(index["file_count"], 1)
            self.assertTrue(index["reference_allowed"])
            self.assertEqual(index["entries"][0]["language"], "hlsl")
            self.assertEqual(index["entries"][0]["source"], "unit-test")
            self.assertEqual(index["entries"][0]["license"], "MIT")
            result = search_shader_corpus(index_path, "anime ocean foam", limit=5)
            self.assertTrue(result["ok"], result)
            self.assertEqual(len(result["matches"]), 1)
            self.assertIn("AnimeOceanFoam", result["matches"][0]["snippet"])
            self.assertEqual(result["matches"][0]["risk_notes"], [])

    def test_corpus_unknown_license_can_be_blocked_for_reference_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shaders"
            root.mkdir()
            (root / "Water.glsl").write_text(
                "vec3 waterFoam(vec2 uv) { return vec3(uv, 1.0); }",
                encoding="utf-8",
            )
            index_path = Path(tmp) / "index.json"
            index_shader_corpus([root], index_path, license_label="unknown")
            result = search_shader_corpus(index_path, "water foam", require_reference_allowed=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["matches"], [])

    def test_export_pack_can_record_corpus_reference_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "refs"
            root.mkdir()
            (root / "OceanFoam.hlsl").write_text(
                "float3 OceanFoam(float2 uv) { return float3(0.0, 0.6, 1.0); }",
                encoding="utf-8",
            )
            index_path = Path(tmp) / "corpus.json"
            index_shader_corpus([root], index_path, license_label="MIT")
            reference_context = search_shader_corpus(index_path, "ocean foam", limit=2)
            manifest = export_material_pack(
                MaterialRequest("anime ocean foam", count=1),
                Path(tmp) / "packs",
                reference_context={
                    "ok": reference_context["ok"],
                    "query": reference_context["query"],
                    "index_path": reference_context["index_path"],
                    "reference_allowed": reference_context["reference_allowed"],
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
                        for item in reference_context["matches"]
                    ],
                },
            )
            pack_dir = Path(manifest["pack_dir"])
            loaded = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(loaded["reference_context"])
            self.assertEqual(len(loaded["reference_context"]["matches"]), 1)
            self.assertIn("Reference Context", (pack_dir / "index.md").read_text(encoding="utf-8"))

    def test_cli_corpus_index_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shaders"
            root.mkdir()
            (root / "CelWater.ush").write_text(
                "float3 CelWaterFoam(float2 uv) { return float3(0.1, 0.7, 1.0); }",
                encoding="utf-8",
            )
            index_path = Path(tmp) / "index.json"
            rc = material_synth_cli([
                "corpus-index",
                str(root),
                "--output",
                str(index_path),
                "--source-label",
                "unit-test",
                "--license-label",
                "Apache-2.0",
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(index_path.exists())
            rc = material_synth_cli(["corpus-search", str(index_path), "cel water foam", "--limit", "1"])
            self.assertEqual(rc, 0)

    def test_fetch_manifest_downloads_permissive_shader_and_indexes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            shader = source / "AnimeWater.hlsl"
            shader.write_text(
                "float3 AnimeWaterFoam(float2 uv) { return float3(0.0, 0.8, 1.0); }",
                encoding="utf-8",
            )
            manifest_path = Path(tmp) / "sources.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_label": "unit-free-shaders",
                        "license_label": "MIT",
                        "items": [
                            {
                                "url": shader.as_uri(),
                                "path": "water/AnimeWater.hlsl",
                                "license": "MIT",
                                "title": "Anime Water",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            index_path = Path(tmp) / "index.json"
            report = fetch_shader_manifest(
                manifest_path,
                output_dir=Path(tmp) / "raw",
                index_output=index_path,
            )
            self.assertEqual(report["downloaded"], 1)
            self.assertEqual(report["skipped_count"], 0)
            self.assertTrue(Path(report["report_path"]).exists())
            self.assertTrue((Path(report["raw_root"]) / "water" / "AnimeWater.hlsl").exists())
            result = search_shader_corpus(index_path, "anime water foam", limit=1)
            self.assertEqual(len(result["matches"]), 1)
            self.assertEqual(result["matches"][0]["entry"]["license"], "MIT")

    def test_fetch_manifest_skips_unknown_license_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            shader = source / "Unsafe.hlsl"
            shader.write_text("float3 UnsafeWater(float2 uv) { return float3(1, 1, 1); }", encoding="utf-8")
            manifest_path = Path(tmp) / "sources.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_label": "unit-unsafe",
                        "license_label": "unknown",
                        "items": [
                            {"url": shader.as_uri(), "path": "Unsafe.hlsl", "license": "unknown"},
                            {"url": shader.as_uri(), "path": "../escape.hlsl", "license": "MIT"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = fetch_shader_manifest(
                manifest_path,
                output_dir=Path(tmp) / "raw",
                index_output=Path(tmp) / "index.json",
            )
            self.assertEqual(report["downloaded"], 0)
            self.assertEqual(report["skipped_count"], 2)
            self.assertFalse((Path(tmp) / "escape.hlsl").exists())

    def test_cli_corpus_fetch_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            shader = Path(tmp) / "CelWater.ush"
            shader.write_text(
                "float3 CelWaterFoam(float2 uv) { return float3(0.1, 0.7, 1.0); }",
                encoding="utf-8",
            )
            manifest_path = Path(tmp) / "sources.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "source_label": "cli-free-shaders",
                        "license_label": "Apache-2.0",
                        "items": [{"url": shader.as_uri(), "path": "CelWater.ush"}],
                    }
                ),
                encoding="utf-8",
            )
            index_path = Path(tmp) / "index.json"
            rc = material_synth_cli([
                "corpus-fetch-manifest",
                str(manifest_path),
                "--output-dir",
                str(Path(tmp) / "raw"),
                "--index-output",
                str(index_path),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(index_path.exists())

    def test_doctor_local_checks_report_material_synth(self):
        report = run_doctor(repo_root=Path(__file__).resolve().parents[1])
        names = {check["name"]: check for check in report["checks"]}
        self.assertEqual(names["material_synth_package"]["status"], "pass")
        self.assertIn("required_permissions", report)

    def test_doctor_detects_configured_ue_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "Project"
            project_dir.mkdir()
            plugins = project_dir / "Plugins" / "Lethe"
            plugins.mkdir(parents=True)
            config = project_dir / "Config"
            config.mkdir()
            uproject = project_dir / "Project.uproject"
            uproject.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "Plugins": [
                            {"Name": "Lethe", "Enabled": True},
                            {"Name": "PythonScriptPlugin", "Enabled": True},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (config / "DefaultEngine.ini").write_text(
                "\n".join(
                    [
                        "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]",
                        "bRemoteExecution=True",
                        "RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766",
                        "RemoteExecutionMulticastBindAddress=127.0.0.1",
                    ]
                ),
                encoding="utf-8",
            )
            report = run_doctor(uproject, repo_root=Path(__file__).resolve().parents[1])
            names = {check["name"]: check for check in report["checks"]}
            self.assertEqual(names["target_lethe_plugin_installed"]["status"], "pass")
            self.assertEqual(names["remote_execution_enabled"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
