"""Static guardrails for HLSL candidate bodies."""
from __future__ import annotations

from .schema import MaterialCandidate, ValidationIssue, ValidationResult
from .templates import wrap_hlsl_body

_BANNED_TOKENS = {
    "#include": "external includes are not allowed in generated bodies",
    "#pragma": "preprocessor pragmas are not allowed in generated bodies",
    "Texture2D": "texture resources are not part of the stage-1 fixed interface",
    "SamplerState": "samplers are not part of the stage-1 fixed interface",
    "RWTexture": "writeable resources are not allowed in material candidates",
    "ByteAddressBuffer": "raw buffers are not allowed in material candidates",
    "StructuredBuffer": "buffers are not allowed in material candidates",
    "discard": "discard is not allowed in stage-1 materials",
    "clip(": "clip is not allowed in stage-1 materials",
    "while": "while loops are not allowed; use bounded fixed loops only",
}

_REQUIRED_OUTPUTS = ("BaseColor", "Roughness", "Metallic", "Alpha", "Emissive")


def validate_candidate(candidate: MaterialCandidate) -> ValidationResult:
    return validate_hlsl_body(candidate.hlsl_body)


def validate_hlsl_body(hlsl_body: str) -> ValidationResult:
    issues: list[ValidationIssue] = []
    body = hlsl_body.strip()
    if not body:
        issues.append(ValidationIssue("error", "empty_body", "HLSL body is empty."))
        return ValidationResult(False, issues, None)

    for token, message in _BANNED_TOKENS.items():
        if token in body:
            issues.append(ValidationIssue("error", "banned_token", f"{token}: {message}"))

    if "LetheMaterialOutput O" not in body:
        issues.append(
            ValidationIssue(
                "error",
                "missing_output_struct",
                "Body must declare `LetheMaterialOutput O`.",
            )
        )

    if "return O" not in body:
        issues.append(ValidationIssue("error", "missing_return", "Body must `return O`."))

    for field in _REQUIRED_OUTPUTS:
        if f"O.{field}" not in body:
            issues.append(
                ValidationIssue(
                    "error",
                    "missing_output_field",
                    f"Body must assign O.{field}.",
                )
            )

    for opener, closer, code in (("(", ")", "paren_balance"), ("{", "}", "brace_balance")):
        delta = body.count(opener) - body.count(closer)
        if delta != 0:
            issues.append(
                ValidationIssue(
                    "error",
                    code,
                    f"Unbalanced {opener}{closer}: delta={delta}.",
                )
            )

    if len(body) > 12000:
        issues.append(
            ValidationIssue(
                "error",
                "body_too_large",
                "Stage-1 HLSL bodies must stay below 12000 characters.",
            )
        )

    normalized = None if any(i.severity == "error" for i in issues) else wrap_hlsl_body(body)
    return ValidationResult(ok=normalized is not None, issues=issues, normalized_hlsl=normalized)
