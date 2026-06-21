"""Analyze UE replay reports into customer-facing summaries."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any
from html import escape

from PIL import Image, ImageStat


def analyze_validation_report(
    pack_dir: str | Path,
    report_name: str = "ue_validation_report.json",
    summary_json_name: str = "customer_summary.json",
    summary_md_name: str = "customer_summary.md",
    gallery_name: str = "customer_gallery.html",
) -> dict[str, Any]:
    """Read a UE replay report and write ranked customer summary files."""

    root = Path(pack_dir)
    report_path = root / report_name
    if not report_path.exists():
        raise FileNotFoundError(f"UE validation report not found: {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    items = []
    for record in report.get("results", []):
        item = _summarize_record(record)
        items.append(item)

    items.sort(key=lambda item: item["score"], reverse=True)
    summary = {
        "pack_dir": str(root.resolve()),
        "report": str(report_path.resolve()),
        "count": len(items),
        "created": sum(1 for item in items if item["create_ok"]),
        "previewed": sum(1 for item in items if item["preview_ok"]),
        "recommended": items[0] if items else None,
        "files": {
            "summary_json": summary_json_name,
            "summary_md": summary_md_name,
            "gallery_html": gallery_name,
        },
        "candidates": items,
        "notes": [
            "Scores are local acceptance heuristics, not a substitute for final art review.",
            "Preview image metrics are included only when PNG files are available.",
        ],
    }

    (root / summary_json_name).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / summary_md_name).write_text(_summary_markdown(summary), encoding="utf-8")
    (root / gallery_name).write_text(_summary_html(summary), encoding="utf-8")
    return summary


def _summarize_record(record: dict[str, Any]) -> dict[str, Any]:
    preview = record.get("preview") or {}
    compile_info = record.get("compile") or {}
    payload = record.get("payload") or {}
    generation = record.get("generation") or {}
    preview_path = preview.get("path")
    metrics = _image_metrics(preview_path) if preview_path else None

    score = 0.0
    reasons: list[str] = []
    if record.get("create_ok"):
        score += 40.0
        reasons.append("material asset was created")
    else:
        reasons.append("material asset creation failed")

    if compile_info.get("ok") is True:
        score += 25.0
        reasons.append("material recompile API reported success")
    elif compile_info.get("attempted"):
        score += 5.0
        reasons.append("material recompile was attempted but did not confirm success")

    if preview.get("ok"):
        score += 25.0
        reasons.append("preview screenshot was written")
    elif preview.get("attempted"):
        reasons.append("preview capture was attempted but failed")

    if metrics:
        if 0.08 <= metrics["contrast"] <= 0.45:
            score += 5.0
            reasons.append("preview contrast is in a usable range")
        if 0.08 <= metrics["mean_luma"] <= 0.92:
            score += 5.0
            reasons.append("preview brightness is not clipped")
        if metrics["colorfulness"] >= 0.04:
            score += 5.0
            reasons.append("preview has visible color variation")

    return {
        "candidate_id": record.get("candidate_id"),
        "order": record.get("order"),
        "name": record.get("name"),
        "generation": generation,
        "agent_id": generation.get("agent_id"),
        "strategy": generation.get("strategy"),
        "asset": payload.get("asset"),
        "create_ok": bool(record.get("create_ok")),
        "compile_ok": compile_info.get("ok"),
        "compile_error": compile_info.get("error"),
        "preview_ok": bool(preview.get("ok")),
        "preview_path": preview_path,
        "preview_error": preview.get("error"),
        "image_metrics": metrics,
        "score": round(score, 3),
        "reasons": reasons,
        "error": record.get("error"),
    }


def _image_metrics(path: str) -> dict[str, float] | None:
    image_path = Path(path)
    if not image_path.exists():
        return None
    with Image.open(image_path) as image:
        rgb = image.convert("RGB").resize((64, 64))
        stat = ImageStat.Stat(rgb)
        mean_rgb = [value / 255.0 for value in stat.mean]
        std_rgb = [value / 255.0 for value in stat.stddev]
        luma = 0.2126 * mean_rgb[0] + 0.7152 * mean_rgb[1] + 0.0722 * mean_rgb[2]
        contrast = mean(std_rgb)
        colorfulness = max(mean_rgb) - min(mean_rgb)
    return {
        "mean_luma": round(luma, 4),
        "contrast": round(contrast, 4),
        "colorfulness": round(colorfulness, 4),
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Lethe Material Synth Customer Summary",
        "",
        f"Pack: `{summary['pack_dir']}`",
        "",
        f"Candidates: {summary['count']}",
        f"Created: {summary['created']}",
        f"Previewed: {summary['previewed']}",
        "",
    ]
    recommended = summary.get("recommended")
    if recommended:
        lines.extend(
            [
                "## Recommended",
                "",
                f"- ID: `{recommended['candidate_id']}`",
                f"- Name: {recommended['name']}",
                f"- Agent: {recommended.get('agent_id')}",
                f"- Strategy: {recommended.get('strategy')}",
                f"- Score: {recommended['score']}",
                f"- Asset: `{recommended.get('asset')}`",
                f"- Preview: `{recommended.get('preview_path')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Ranked Candidates",
            "",
            "| Rank | Agent | Strategy | ID | Name | Score | Created | Preview | Notes |",
            "|---:|---|---|---|---|---:|---|---|---|",
        ]
    )
    for idx, item in enumerate(summary["candidates"], start=1):
        notes = "; ".join(item["reasons"][:3])
        lines.append(
            "| {rank} | {agent} | {strategy} | `{id}` | {name} | {score} | {created} | {preview} | {notes} |".format(
                rank=idx,
                agent=item.get("agent_id") or "unknown",
                strategy=item.get("strategy") or "unknown",
                id=item["candidate_id"],
                name=item["name"],
                score=item["score"],
                created="yes" if item["create_ok"] else "no",
                preview="yes" if item["preview_ok"] else "no",
                notes=notes,
            )
        )
    lines.extend(
        [
            "",
            "## Caveat",
            "",
            "This is an automated acceptance summary. Final selection still needs visual review against the user's prompt.",
            "",
        ]
    )
    return "\n".join(lines)


def _summary_html(summary: dict[str, Any]) -> str:
    root = Path(summary["pack_dir"])
    cards = []
    for rank, item in enumerate(summary["candidates"], start=1):
        preview_html = _preview_html(root, item)
        metrics = item.get("image_metrics") or {}
        metric_text = " / ".join(
            f"{key}: {value}" for key, value in metrics.items()
        ) or "no image metrics"
        reasons = "".join(f"<li>{escape(reason)}</li>" for reason in item["reasons"])
        status = []
        status.append(_badge("created", item["create_ok"]))
        status.append(_badge("compiled", item["compile_ok"] is True))
        status.append(_badge("preview", item["preview_ok"]))
        if item.get("compile_error"):
            status.append(f"<span class=\"error\">{escape(str(item['compile_error']))}</span>")
        if item.get("preview_error"):
            status.append(f"<span class=\"error\">{escape(str(item['preview_error']))}</span>")
        cards.append(
            f"""
            <article class="card">
              <div class="rank">#{rank}</div>
              {preview_html}
              <div class="body">
                <h2>{escape(str(item['name']))}</h2>
                <p class="id">{escape(str(item['candidate_id']))}</p>
                <p class="id">{escape(str(item.get('agent_id') or 'unknown agent'))} / {escape(str(item.get('strategy') or 'unknown strategy'))}</p>
                <p class="score">{escape(str(item['score']))}</p>
                <div class="badges">{''.join(status)}</div>
                <p class="asset">{escape(str(item.get('asset') or 'no asset'))}</p>
                <p class="metrics">{escape(metric_text)}</p>
                <ul>{reasons}</ul>
              </div>
            </article>
            """
        )

    recommended = summary.get("recommended") or {}
    recommended_name = recommended.get("name") or "none"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lethe Material Gallery</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Segoe UI, Arial, sans-serif;
      background: #111418;
      color: #edf1f5;
    }}
    body {{
      margin: 0;
      padding: 28px;
      background: #111418;
    }}
    header {{
      max-width: 1120px;
      margin: 0 auto 22px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      font-weight: 650;
    }}
    .summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: #aeb8c4;
      font-size: 14px;
    }}
    .grid {{
      max-width: 1120px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .card {{
      position: relative;
      overflow: hidden;
      border: 1px solid #2a333d;
      border-radius: 8px;
      background: #171c22;
    }}
    .rank {{
      position: absolute;
      top: 10px;
      left: 10px;
      z-index: 2;
      padding: 4px 7px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.62);
      font-size: 12px;
      color: white;
    }}
    .preview {{
      width: 100%;
      aspect-ratio: 1.35;
      object-fit: cover;
      display: block;
      background: #222a33;
    }}
    .missing {{
      display: grid;
      place-items: center;
      color: #7d8996;
      font-size: 13px;
    }}
    .body {{
      padding: 12px;
    }}
    h2 {{
      margin: 0 0 4px;
      font-size: 16px;
      line-height: 1.25;
    }}
    .id, .asset, .metrics {{
      margin: 5px 0;
      color: #98a5b3;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .score {{
      margin: 8px 0;
      font-size: 24px;
      font-weight: 700;
      color: #d6f37a;
    }}
    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 6px 0 8px;
    }}
    .badge {{
      border-radius: 999px;
      padding: 3px 7px;
      font-size: 12px;
      background: #2b3440;
      color: #c5d0db;
    }}
    .badge.ok {{
      background: #17432e;
      color: #a9efc9;
    }}
    .badge.fail {{
      background: #4a2228;
      color: #ffb3bf;
    }}
    .error {{
      color: #ff9aa9;
      font-size: 12px;
    }}
    ul {{
      margin: 8px 0 0;
      padding-left: 18px;
      color: #d7dde4;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Lethe Material Gallery</h1>
    <div class="summary">
      <span>Pack: {escape(str(summary['pack_dir']))}</span>
      <span>Candidates: {summary['count']}</span>
      <span>Created: {summary['created']}</span>
      <span>Previewed: {summary['previewed']}</span>
      <span>Recommended: {escape(str(recommended_name))}</span>
    </div>
  </header>
  <main class="grid">
    {''.join(cards)}
  </main>
</body>
</html>
"""


def _preview_html(root: Path, item: dict[str, Any]) -> str:
    path = item.get("preview_path")
    if not path:
        return '<div class="preview missing">no preview</div>'
    preview = Path(path)
    try:
        rel = preview.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = preview.as_posix()
    return f'<img class="preview" src="{escape(rel)}" alt="{escape(str(item.get("name") or item.get("candidate_id")))}">'


def _badge(label: str, ok: bool) -> str:
    cls = "ok" if ok else "fail"
    text = "yes" if ok else "no"
    return f'<span class="badge {cls}">{escape(label)}: {text}</span>'
