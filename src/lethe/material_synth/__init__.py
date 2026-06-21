"""Computer-friendly HLSL material synthesis helpers for Lethe."""

from .analyzer import analyze_validation_report
from .agent_contract import AGENT_CONTRACT_VERSION, load_agent_candidates, validate_agent_candidate_file
from .bundle import bundle_pack
from .corpus import build_reference_context, index_shader_corpus, search_shader_corpus
from .doctor import run_doctor
from .demo import build_offline_demo_report
from .fetcher import fetch_shader_manifest
from .generator import generate_candidates
from .pack import export_material_pack
from .pack import export_candidates_pack
from .ranker import rank_candidate, rank_candidates
from .schema import MaterialCandidate, MaterialRequest, ValidationIssue, ValidationResult
from .validator import validate_candidate, validate_hlsl_body
from .verifier import verify_pack
from .workflow import build_demo_bundle

__all__ = [
    "MaterialCandidate",
    "MaterialRequest",
    "ValidationIssue",
    "ValidationResult",
    "AGENT_CONTRACT_VERSION",
    "analyze_validation_report",
    "build_offline_demo_report",
    "bundle_pack",
    "build_demo_bundle",
    "build_reference_context",
    "index_shader_corpus",
    "export_candidates_pack",
    "export_material_pack",
    "fetch_shader_manifest",
    "generate_candidates",
    "load_agent_candidates",
    "validate_agent_candidate_file",
    "rank_candidate",
    "rank_candidates",
    "run_doctor",
    "search_shader_corpus",
    "validate_candidate",
    "validate_hlsl_body",
    "verify_pack",
]
