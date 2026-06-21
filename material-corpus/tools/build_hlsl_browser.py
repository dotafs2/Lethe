"""Build an all-HLSL cloth wind corpus and a static browser page."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
INDEX_PATH = ROOT / "cloth_wind_seed_index.json"
HLSL_ROOT = ROOT / "cloth_wind_hlsl_all_live"
BROWSER_ROOT = ROOT / "cloth_wind_browser_live"
BROWSER_DATA = BROWSER_ROOT / "browser_data.js"
BROWSER_INDEX = BROWSER_ROOT / "index.html"


def main() -> int:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8-sig"))
    _reset_dir(HLSL_ROOT)
    _reset_dir(BROWSER_ROOT)

    entries = []
    for number, entry in enumerate(index.get("entries", []), start=1):
        source_path = Path(entry["path"])
        code = source_path.read_text(encoding="utf-8-sig", errors="replace")
        rel = str(entry.get("rel_path") or source_path.name).replace("\\", "/")
        source_ext = source_path.suffix.lower()
        if source_ext in {".hlsl", ".ush"}:
            hlsl_code = _normalize_hlsl_header(code, entry, source_path)
            conversion = "native_hlsl"
        elif source_ext == ".glsl":
            hlsl_code = _glsl_to_hlsl(code, entry, source_path)
            conversion = "converted_from_glsl"
        else:
            hlsl_code = _normalize_hlsl_header(code, entry, source_path)
            conversion = f"renamed_from_{source_ext.lstrip('.') or 'shader'}"

        dest_rel = _dest_rel(number, rel, source_ext)
        dest = HLSL_ROOT / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(hlsl_code, encoding="utf-8")

        entries.append(
            {
                "id": entry.get("id"),
                "title": _title_for(entry, source_path),
                "path": str(dest.relative_to(REPO)).replace("\\", "/"),
                "abs_path": str(dest),
                "source_path": str(source_path),
                "source_rel_path": rel,
                "browser_rel_path": str(dest_rel).replace("\\", "/"),
                "conversion": conversion,
                "language": "hlsl",
                "source_language": entry.get("language"),
                "license": entry.get("license"),
                "source": entry.get("source"),
                "size": dest.stat().st_size,
                "symbols": entry.get("symbols", []),
                "keywords": entry.get("keywords", []),
                "tags": _tags_for(rel, entry),
                "code": hlsl_code,
            }
        )

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_index": str(INDEX_PATH.relative_to(REPO)).replace("\\", "/"),
        "count": len(entries),
        "hlsl_root": str(HLSL_ROOT.relative_to(REPO)).replace("\\", "/"),
        "entries": entries,
    }
    (HLSL_ROOT / "hlsl_all_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    BROWSER_DATA.write_text("window.CLOTH_WIND_HLSL = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    BROWSER_INDEX.write_text(_html(payload), encoding="utf-8")
    print(json.dumps({"count": len(entries), "hlsl_root": str(HLSL_ROOT), "browser": str(BROWSER_INDEX)}, indent=2))
    return 0


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_rmtree_onerror)
    path.mkdir(parents=True, exist_ok=True)


def _rmtree_onerror(func: Any, path: str, _exc_info: Any) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except PermissionError:
        stale = Path(str(path) + ".stale")
        try:
            Path(path).rename(stale)
        except OSError:
            raise


def _dest_rel(number: int, rel: str, source_ext: str) -> Path:
    clean = rel.replace("\\", "/").strip("/")
    parts = [re.sub(r"[^A-Za-z0-9._-]+", "_", part) for part in clean.split("/") if part]
    if not parts:
        parts = ["shader"]
    if source_ext == ".glsl":
        if parts[0].lower() == "glsl":
            parts[0] = "converted_hlsl"
        else:
            parts.insert(0, "converted_hlsl")
    stem = Path(parts[-1]).stem
    parent = Path(*parts[:-1]) if len(parts) > 1 else Path()
    return parent / f"{number:04d}_{stem}.hlsl"


def _normalize_hlsl_header(code: str, entry: dict[str, Any], source_path: Path) -> str:
    return "\n".join(
        [
            "// Lethe cloth wind HLSL browser corpus.",
            f"// Source entry: {entry.get('rel_path', source_path.name)}",
            f"// Source license: {entry.get('license', 'unknown')}",
            f"// Source label: {entry.get('source', 'unknown')}",
            "",
            code.strip(),
            "",
        ]
    )


def _glsl_to_hlsl(code: str, entry: dict[str, Any], source_path: Path) -> str:
    converted = code
    replacements = [
        (r"\bvec2\b", "float2"),
        (r"\bvec3\b", "float3"),
        (r"\bvec4\b", "float4"),
        (r"\bmat2\b", "float2x2"),
        (r"\bmat3\b", "float3x3"),
        (r"\bmat4\b", "float4x4"),
        (r"\bmix\s*\(", "lerp("),
        (r"\bfract\s*\(", "frac("),
        (r"\bmod\s*\(", "fmod("),
        (r"\btexture2D\s*\(", "Texture2DSample("),
    ]
    for pattern, replacement in replacements:
        converted = re.sub(pattern, replacement, converted)
    converted = _convert_glsl_float_constructors(converted)
    return "\n".join(
        [
            "// Lethe cloth wind HLSL browser corpus.",
            "// Converted for local HLSL-only browsing/reference.",
            f"// Original entry: {entry.get('rel_path', source_path.name)}",
            f"// Source license: {entry.get('license', 'unknown')}",
            f"// Source label: {entry.get('source', 'unknown')}",
            "",
            converted.strip(),
            "",
        ]
    )


def _convert_glsl_float_constructors(text: str) -> str:
    # GLSL allows float2(1.0), HLSL wants float2(1.0, 1.0). Expand the common
    # scalar splats used in generated files and noise helpers.
    for typename, count in [("float2", 2), ("float3", 3), ("float4", 4)]:
        pattern = re.compile(rf"\b{typename}\(\s*([A-Za-z0-9_.$+\-*/ ]+?)\s*\)")

        def repl(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if "," in expr:
                return match.group(0)
            if any(ch in expr for ch in "()"):
                return match.group(0)
            return f"{typename}({', '.join([expr] * count)})"

        text = pattern.sub(repl, text)
    return text


def _title_for(entry: dict[str, Any], source_path: Path) -> str:
    rel = str(entry.get("rel_path") or source_path.name)
    stem = Path(rel).stem
    return stem.replace("_", " ").replace("-", " ").title()


def _tags_for(rel: str, entry: dict[str, Any]) -> list[str]:
    parts = re.split(r"[/_.\-\s]+", rel.lower())
    tags = [part for part in parts if part and len(part) > 1]
    for item in entry.get("keywords", [])[:8]:
        if item not in tags:
            tags.append(item)
    return tags[:24]


def _html(payload: dict[str, Any]) -> str:
    embedded = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lethe Cloth Wind HLSL Browser</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #101312; color: #eef3ef; }
    .app { display: grid; grid-template-columns: minmax(280px, 380px) 1fr; height: 100vh; }
    aside { border-right: 1px solid #2c3733; background: #151a18; min-width: 0; display: flex; flex-direction: column; }
    header { padding: 16px; border-bottom: 1px solid #2c3733; }
    h1 { font-size: 18px; margin: 0 0 10px; font-weight: 700; letter-spacing: 0; }
    .meta { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #aebbb5; }
    .pill { padding: 4px 8px; border: 1px solid #385047; background: #18231f; border-radius: 6px; }
    .controls { padding: 12px 16px; display: grid; gap: 10px; border-bottom: 1px solid #2c3733; }
    input, select { width: 100%; background: #0f1412; color: #eef3ef; border: 1px solid #3a4943; border-radius: 6px; padding: 10px 11px; font-size: 14px; }
    .list { overflow: auto; padding: 8px; }
    .item { width: 100%; text-align: left; color: #dfe8e3; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 10px; cursor: pointer; display: grid; gap: 5px; }
    .item:hover, .item.active { background: #1d2622; border-color: #48675b; }
    .item-title { font-size: 13px; font-weight: 650; overflow-wrap: anywhere; }
    .item-sub { font-size: 11px; color: #9fb0a8; overflow-wrap: anywhere; }
    main { min-width: 0; display: grid; grid-template-rows: auto 1fr; }
    .detail { padding: 16px 18px; border-bottom: 1px solid #2c3733; background: #121715; display: grid; gap: 8px; }
    .detail h2 { margin: 0; font-size: 20px; letter-spacing: 0; }
    .detail-grid { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #b7c6bf; }
    pre { margin: 0; overflow: auto; padding: 18px; font: 12px/1.55 Consolas, Cascadia Mono, monospace; background: #0b0f0e; color: #d7efe4; }
    code { white-space: pre; }
    mark { background: #b8f1a4; color: #112016; border-radius: 2px; padding: 0 1px; }
    @media (max-width: 820px) { .app { grid-template-columns: 1fr; grid-template-rows: 45vh 55vh; } aside { border-right: 0; border-bottom: 1px solid #2c3733; } }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <header>
        <h1>Lethe Cloth Wind HLSL</h1>
        <div class="meta">
          <span class="pill" id="count">0 shaders</span>
          <span class="pill">HLSL only</span>
          <span class="pill">MIT-safe</span>
        </div>
      </header>
      <div class="controls">
        <input id="search" placeholder="Search flag, curtain, storm, wrinkle..." autocomplete="off">
        <select id="filter">
          <option value="">All categories</option>
        </select>
      </div>
      <div class="list" id="list"></div>
    </aside>
    <main>
      <section class="detail">
        <h2 id="title">Select a shader</h2>
        <div class="detail-grid" id="detail"></div>
      </section>
      <pre><code id="code"></code></pre>
    </main>
  </div>
  <script id="embedded-data" type="application/json">__EMBEDDED_DATA__</script>
  <script>
    const data = JSON.parse(document.getElementById('embedded-data').textContent);
    const entries = data.entries || [];
    const search = document.getElementById('search');
    const filter = document.getElementById('filter');
    const list = document.getElementById('list');
    const title = document.getElementById('title');
    const detail = document.getElementById('detail');
    const code = document.getElementById('code');
    let selected = entries[0];

    document.getElementById('count').textContent = `${entries.length} shaders`;
        const cats = [...new Set(entries.map(e => (e.browser_rel_path.split('/')[0] || 'root')))].sort();
    for (const cat of cats) {
      const option = document.createElement('option');
      option.value = cat;
      option.textContent = cat;
      filter.appendChild(option);
    }

    function escapeRegExp(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
    function highlighted(text, q) {
      const safe = htmlEscape(text);
      if (!q) return safe;
      return safe.replace(new RegExp(escapeRegExp(q), 'ig'), m => `<mark>${m}</mark>`);
    }
    function htmlEscape(s) {
      return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function matches(e, q, cat) {
      if (cat && !e.browser_rel_path.startsWith(cat + '/')) return false;
      if (!q) return true;
      const hay = [e.title, e.path, e.browser_rel_path, e.conversion, ...(e.tags || []), ...(e.symbols || [])].join(' ').toLowerCase();
      return hay.includes(q.toLowerCase());
    }
    function renderList() {
      const q = search.value.trim();
      const cat = filter.value;
      const shown = entries.filter(e => matches(e, q, cat)).slice(0, 800);
      list.innerHTML = '';
      for (const e of shown) {
        const button = document.createElement('button');
        button.className = 'item' + (selected === e ? ' active' : '');
        button.innerHTML = `<div class="item-title">${highlighted(e.title, q)}</div><div class="item-sub">${htmlEscape(e.browser_rel_path)} · HLSL</div>`;
        button.onclick = () => { selected = e; renderDetail(q); renderList(); };
        list.appendChild(button);
      }
      if (!shown.includes(selected) && shown[0]) selected = shown[0];
      renderDetail(q);
    }
    function renderDetail(q) {
      if (!selected) return;
      title.textContent = selected.title;
      detail.innerHTML = [
        `path: ${selected.path}`,
        `source: ${selected.source}`,
        `license: ${selected.license}`,
        `conversion: ${selected.conversion}`,
        `bytes: ${selected.size}`
      ].map(x => `<span class="pill">${htmlEscape(x)}</span>`).join('');
      code.innerHTML = highlighted(selected.code, q);
    }
    search.addEventListener('input', renderList);
    filter.addEventListener('change', renderList);
    renderList();
  </script>
</body>
</html>
"""
    return template.replace("__EMBEDDED_DATA__", embedded)


if __name__ == "__main__":
    raise SystemExit(main())
