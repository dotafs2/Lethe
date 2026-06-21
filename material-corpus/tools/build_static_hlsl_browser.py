"""Build a no-JavaScript static browser for the HLSL cloth wind corpus."""
from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
MANIFEST = ROOT / "cloth_wind_hlsl_all_live" / "hlsl_all_manifest.json"
BROWSER = ROOT / "cloth_wind_browser_live" / "index.html"


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    entries = payload["entries"]
    BROWSER.parent.mkdir(parents=True, exist_ok=True)
    BROWSER.write_text(_html(payload, entries), encoding="utf-8")
    print(json.dumps({"browser": str(BROWSER), "count": len(entries), "mode": "static-no-js"}, indent=2))
    return 0


def _html(payload: dict, entries: list[dict]) -> str:
    categories = sorted({entry["browser_rel_path"].split("/")[0] for entry in entries})
    nav = "\n".join(_nav_item(i, entry) for i, entry in enumerate(entries, start=1))
    sections = "\n".join(_section(i, entry) for i, entry in enumerate(entries, start=1))
    category_text = ", ".join(categories)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lethe Cloth Wind HLSL Browser</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, Segoe UI, Arial, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #101312; color: #eef3ef; }}
    .app {{ display: grid; grid-template-columns: minmax(300px, 430px) 1fr; height: 100vh; }}
    aside {{ border-right: 1px solid #2c3733; background: #151a18; min-width: 0; display: flex; flex-direction: column; }}
    header {{ padding: 16px; border-bottom: 1px solid #2c3733; }}
    h1 {{ font-size: 18px; margin: 0 0 10px; font-weight: 700; letter-spacing: 0; }}
    .meta {{ display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: #aebbb5; }}
    .pill {{ padding: 4px 8px; border: 1px solid #385047; background: #18231f; border-radius: 6px; }}
    .hint {{ padding: 12px 16px; border-bottom: 1px solid #2c3733; color: #aebbb5; font-size: 13px; line-height: 1.45; }}
    nav {{ overflow: auto; padding: 8px; }}
    nav a {{ display: grid; gap: 5px; text-decoration: none; color: #dfe8e3; border: 1px solid transparent; border-radius: 6px; padding: 10px; }}
    nav a:hover {{ background: #1d2622; border-color: #48675b; }}
    .item-title {{ font-size: 13px; font-weight: 650; overflow-wrap: anywhere; }}
    .item-sub {{ font-size: 11px; color: #9fb0a8; overflow-wrap: anywhere; }}
    main {{ min-width: 0; overflow: auto; scroll-behavior: smooth; background: #0b0f0e; }}
    .shader {{ border-bottom: 1px solid #2c3733; }}
    .shader header {{ position: sticky; top: 0; background: #121715; z-index: 1; }}
    .shader h2 {{ margin: 0 0 8px; font-size: 20px; letter-spacing: 0; }}
    .detail-grid {{ display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #b7c6bf; }}
    pre {{ margin: 0; overflow: auto; padding: 18px; font: 12px/1.55 Consolas, Cascadia Mono, monospace; background: #0b0f0e; color: #d7efe4; }}
    code {{ white-space: pre; }}
    @media (max-width: 820px) {{
      .app {{ grid-template-columns: 1fr; grid-template-rows: 42vh 58vh; }}
      aside {{ border-right: 0; border-bottom: 1px solid #2c3733; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <header>
        <h1>Lethe Cloth Wind HLSL</h1>
        <div class="meta">
          <span class="pill">{len(entries)} shaders</span>
          <span class="pill">HLSL only</span>
          <span class="pill">No JavaScript</span>
          <span class="pill">MIT-safe</span>
        </div>
      </header>
      <div class="hint">
        Use browser find Ctrl+F to search. Categories: {html.escape(category_text)}.
      </div>
      <nav>
        {nav}
      </nav>
    </aside>
    <main>
      {sections}
    </main>
  </div>
</body>
</html>
"""


def _nav_item(index: int, entry: dict) -> str:
    title = html.escape(entry["title"])
    rel = html.escape(entry["browser_rel_path"])
    return f"""<a href="#shader-{index:04d}">
  <span class="item-title">{index:04d}. {title}</span>
  <span class="item-sub">{rel}</span>
</a>"""


def _section(index: int, entry: dict) -> str:
    title = html.escape(entry["title"])
    rel = html.escape(entry["browser_rel_path"])
    path = html.escape(entry["path"])
    source = html.escape(str(entry.get("source", "")))
    license_label = html.escape(str(entry.get("license", "")))
    conversion = html.escape(str(entry.get("conversion", "")))
    size = html.escape(str(entry.get("size", "")))
    code = html.escape(entry["code"])
    return f"""<section class="shader" id="shader-{index:04d}">
  <header>
    <h2>{index:04d}. {title}</h2>
    <div class="detail-grid">
      <span class="pill">{rel}</span>
      <span class="pill">{conversion}</span>
      <span class="pill">{license_label}</span>
      <span class="pill">{source}</span>
      <span class="pill">{size} bytes</span>
      <span class="pill">{path}</span>
    </div>
  </header>
  <pre><code>{code}</code></pre>
</section>"""


if __name__ == "__main__":
    raise SystemExit(main())
