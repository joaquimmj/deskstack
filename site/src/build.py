#!/usr/bin/env python3
"""Build site/index.html (EN) and site/fr/index.html (FR) from one template and the copy in content.json.

  python3 site/src/build.py

Static output for GitHub Pages; no dependencies.
"""

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
GH = "https://github.com/joaquimmj/deskstack"
ANALYSIS = "bench/results/2026-11-09T09-25-07-305Z/ANALYSIS.md"
TICK = '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="M4 13.5l5 5L20 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
LOGO = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="2.5" width="19" height="19" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 12.5l3.2 3.2L17.5 8" fill="none" stroke="#0b7a3e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
FAVICON = "data:image/svg+xml," + LOGO.replace('"', "'").replace("#", "%23").replace("currentColor", "%230e1a2b").replace(' aria-hidden=\'true\'', " xmlns='http://www.w3.org/2000/svg'")

COLS = "ABCDEFGHIJKL"
ROWS = 14

# Apple's FY2023-25 10-K figures (USD millions), as the hero's workbook. One cell carries the swapped digits the
# associate flags. Kinds: h = header/label, ok = tied out to the filing, bad = doesn't tie out, in = typed assumption,
# f = formula or status. Positions are 1-based (column, row); the headline's selection covers B4:K8 and the lede
# sits on the empty rows 9-11.
HERO_CELLS = [
    (1, 1, "h", "USD m"), (2, 1, "h", "FY2023"), (3, 1, "h", "FY2024"), (4, 1, "h", "FY2025"),
    (1, 2, "h", "{revenue}"), (2, 2, "ok", "383,285"), (3, 2, "bad", "391,053"), (4, 2, "ok", "416,161"),
    (1, 3, "h", "{ebit}"), (2, 3, "ok", "114,301"), (3, 3, "ok", "123,216"), (4, 3, "ok", "133,050"),
    (10, 1, "h", "WACC"), (11, 1, "in", "9.0%"), (10, 2, "h", "g"), (11, 2, "in", "3.0%"),
    (10, 3, "h", "{tax}"), (11, 3, "in", "16.0%"),
    (1, 12, "h", "D&A"), (2, 12, "ok", "11,519"), (3, 12, "ok", "11,445"), (4, 12, "ok", "11,698"),
    (1, 13, "h", "Capex"), (2, 13, "ok", "10,959"), (3, 13, "ok", "9,447"), (4, 13, "ok", "12,715"),
    (1, 14, "h", "{netdebt}"), (4, 14, "ok", "43,960"),
    (10, 13, "h", "Sign-off"), (11, 13, "f", "{awaiting}"),
    (10, 14, "h", "{tieout}"), (11, 14, "f", "13/14"),
]


def render(L: dict, prefix: str, home: str) -> str:
    t = (HERE / "template.html").read_text()
    cells = []
    for i, (x, y, kind, text) in enumerate(HERO_CELLS):
        text = text.format(**L["cell_words"])
        cls = f"c {kind}"
        mark = TICK if kind == "ok" else ""
        cells.append(f'<span class="{cls}" style="--x:{x};--y:{y};--i:{i}">{mark}{text}</span>')
    stats = "".join(f'<li><span class="num">{n}</span><span class="lab">{lab}</span></li>' for n, lab in L["stats"])
    lanes = []
    for cmd, who, desc in L["roles"]:
        lanes.append(f'<li class="{who}"><span class="who">{L["who_" + who]}</span><code>{cmd}</code><p>{desc}</p></li>')
    bench = []
    for arm, pct, detail, cost, secs, width in L["bench"]:
        bar = f'<span class="bar" style="--w:{width}"></span>' if width else '<span class="bar zero"></span>'
        bench.append(f'<tr><th scope="row">{arm}</th><td class="wrong">{bar}<b>{pct}</b> <span>{detail}</span></td><td class="r">{cost}</td><td class="r">{secs}</td></tr>')
    data = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in L["data"])
    limits = "".join(f"<li>{x}</li>" for x in L["limits"])
    values = {
        **{k: v for k, v in L.items() if isinstance(v, str)},
        "prefix": prefix, "home": home, "gh": GH, "analysis": ANALYSIS, "logo": LOGO, "favicon": FAVICON, "tick": TICK,
        "col_heads": "".join(f"<span>{c}</span>" for c in COLS),
        "row_heads": "".join(f"<span>{r}</span>" for r in range(1, ROWS + 1)),
        "hero_cells": "".join(cells), "stats": stats, "lanes": "".join(lanes), "bench_rows": "".join(bench),
        "data_rows": data, "limit_items": limits, "desc_attr": html.escape(L["desc"], quote=True),
        "title_text": html.escape(L["title"]),
    }
    for k, v in values.items():
        t = t.replace("{{" + k + "}}", v)
    if "{{" in t:
        raise SystemExit("unfilled placeholder: " + t[t.index("{{"):t.index("{{") + 40])
    return t


if __name__ == "__main__":
    content = json.loads((HERE / "content.json").read_text())
    (SITE / "index.html").write_text(render(content["en"], "", "./"))
    (SITE / "fr").mkdir(exist_ok=True)
    (SITE / "fr" / "index.html").write_text(render(content["fr"], "../", "./"))
    print("Wrote site/index.html and site/fr/index.html")
