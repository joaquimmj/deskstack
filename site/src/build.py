#!/usr/bin/env python3
"""Build site/index.html (EN) and site/fr/index.html (FR) from one template and the copy in content.json.

  python3 site/src/build.py

Static output for GitHub Pages; no dependencies.
"""

import hashlib
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
GH = "https://github.com/joaquimmj/deskstack"
TICK = '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="M4 13.5l5 5L20 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
LOGO = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="2.5" width="19" height="19" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 12.5l3.2 3.2L17.5 8" fill="none" stroke="#107c41" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
FAVICON = "data:image/svg+xml," + LOGO.replace('"', "'").replace("#", "%23").replace("currentColor", "%23111418").replace(' aria-hidden=\'true\'', " xmlns='http://www.w3.org/2000/svg'")

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


ARROW = '<svg class="arr" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
GH_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0a8 8 0 0 0-2.53 15.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.88.87 2.33.66.07-.52.28-.87.5-1.07-1.77-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 8 0z"/></svg>'
CROSS = '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg>'


def panel_analyst(L):
    hist = [("Revenue", "383,285", "391,035", "416,161"), ("EBIT", "114,301", "123,216", "133,050"),
            ("D&A", "11,519", "11,445", "11,698"), ("Capex", "10,959", "9,447", "12,715")]
    words = L["cell_words"]
    names = {"Revenue": words["revenue"], "EBIT": words["ebit"]}
    rows = "".join(f'<tr><th>{names.get(a, a)}</th><td>{b}</td><td>{c}</td><td class="src">{d}</td></tr>' for a, b, c, d in hist)
    ins = "".join(f'<tr><th>{a}</th><td class="in">{b}</td></tr>' for a, b in [("WACC", "9.0%"), ("g", "3.0%"), (words["tax"], "16.0%")])
    return (f'<div class="win"><div class="win-bar"><i></i><i></i><i></i><span>{L["m_title"]}</span></div><div class="win-body two-col">'
            f'<div><p class="cap">{L["m_hist"]}</p><table class="mini"><thead><tr><th></th><th>FY2023</th><th>FY2024</th><th>FY2025</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<p class="tip">{TICK}{L["m_src"]}</p></div>'
            f'<div><p class="cap">{L["m_inputs"]}</p><table class="mini"><tbody>{ins}</tbody></table></div></div></div>')


def panel_associate(L):
    rows = [("Revenue FY2025", "416,161", "416,161", True), ("Revenue FY2024", "391,053", "391,035", False),
            ("EBIT FY2025", "133,050", "133,050", True), ("D&A FY2025", "11,698", "11,698", True), ("Capex FY2025", "12,715", "12,715", True)]
    rev = L["cell_words"]["revenue"]
    body = "".join(f'<tr class="{"" if ok else "bad"}"><th>{a.replace("Revenue", rev)}</th><td>{b}</td><td>{c}</td><td class="st">{TICK if ok else CROSS}</td></tr>' for a, b, c, ok in rows)
    return (f'<div class="win"><div class="win-bar"><i></i><i></i><i></i><span>/associate · verify_value</span></div><div class="win-body">'
            f'<p class="sum bad-sum">{L["m_tie_sum"]}</p>'
            f'<table class="mini wide"><thead><tr><th>{L["m_line"]}</th><th>{L["m_model"]}</th><th>{L["m_filed"]}</th><th></th></tr></thead><tbody>{body}</tbody></table>'
            f'<p class="hint">{L["m_typo"]}</p></div></div>')


def panel_list(L, title, summary, counts, items):
    lis = "".join(f"<li>{TICK}{x}</li>" for x in items)
    c = f'<span class="counts">{counts}</span>' if counts else ""
    return (f'<div class="win"><div class="win-bar"><i></i><i></i><i></i><span>{title}</span></div><div class="win-body">'
            f'<p class="sum ok-sum">{TICK}{summary}{c}</p><ul class="checks">{lis}</ul></div></div>')


def panel_signoff(L):
    rows = "".join(f'<tr><th>{a}</th><td><span class="pill ok">{b}</span></td><td>{c}</td></tr>' for a, b, c in L["m_s_rows"])
    return (f'<div class="win"><div class="win-bar"><i></i><i></i><i></i><span>/sign-off</span></div><div class="win-body">'
            f'<table class="mini wide"><tbody>{rows}</tbody></table>'
            f'<div class="gate"><p>{L["m_s_token"]} <code>3ba96d58cd17</code></p><p class="wait">{L["m_s_wait"]}</p>'
            f'<span class="btn go sm fake" aria-hidden="true">{L["m_s_btn"]}</span></div></div></div>')


VERIFY_JSON = (
    '{\n  "metric": "revenue",\n  "period": "FY2024",\n  "status": <b class="r">"mismatch"</b>,\n'
    '  "claimed": 391053,\n  "filed": <b class="g">391035</b>,\n'
    '  "accessions": ["0000320193-25-000079"],\n'
    '  "hints": [<b class="y">"Typo: two adjacent digits look swapped"</b>]\n}'
)


def render(L: dict, prefix: str, home: str) -> str:
    t = (HERE / "template.html").read_text()
    cells = []
    for i, (x, y, kind, text) in enumerate(HERO_CELLS):
        text = text.format(**L["cell_words"])
        mark = TICK if kind == "ok" else ""
        cells.append(f'<span class="c {kind}" style="--x:{x};--y:{y};--i:{i}">{mark}{text}</span>')
    stats = "".join(f'<li><b>{n}</b><span>{lab}</span></li>' for n, lab in L["stats"])

    panels_by = {
        "analyst": panel_analyst(L), "associate": panel_associate(L),
        "vp": panel_list(L, "/vp-review · deskstack-check", L["m_vp_sum"], L["m_vp_counts"], L["vp_checks"]),
        "compliance": panel_list(L, "/compliance", L["m_c_sum"], "", L["c_checks"]),
        "signoff": panel_signoff(L),
    }
    tabs, panels = [], []
    for n, (key, cmd, name, desc) in enumerate(L["tabs"]):
        sel = "true" if n == 0 else "false"
        tabs.append(f'<button class="tab" role="tab" id="tab-{key}" aria-controls="panel-{key}" aria-selected="{sel}" tabindex="{0 if n == 0 else -1}">'
                    f'<span class="tab-h"><code>{cmd}</code> {name}</span><span class="tab-p">{desc}</span></button>')
        panels.append(f'<div class="panel" role="tabpanel" id="panel-{key}" aria-labelledby="tab-{key}" tabindex="0"{"" if n == 0 else " hidden"}>{panels_by[key]}</div>')

    steps = L["ln_steps"]
    lane_steps = "".join(f'<li class="{"you" if k == len(steps) - 1 else "agent"}"><i></i><span data-who="{L["ln_you"] if k == len(steps) - 1 else ""}">{s}</span></li>' for k, s in enumerate(steps))
    dk_steps = "".join(f'<li><i>{k + 1}</i><span>{s}</span></li>' for k, s in enumerate(L["dk_steps"]))
    hints = "".join(f'<li><b>{a}</b><span>{b}</span></li>' for a, b in L["dk_hints"])

    tables = []
    for tb in L["benches"]:
        rows = []
        for arm, pct, detail, cost, secs, width in tb["rows"]:
            bar = f'<span class="meter" style="--w:{width}"></span>' if width else '<span class="meter zero"></span>'
            rows.append(f'<tr><th scope="row">{arm}</th><td class="wrong">{bar}<b>{pct}</b> <span>{detail}</span></td><td class="r">{cost}</td><td class="r">{secs}</td></tr>')
        head = f'<thead><tr><th scope="col">{L["b_h_arm"]}</th><th scope="col">{L["b_h_wrong"]}</th><th scope="col" class="r">{L["b_h_cost"]}</th><th scope="col" class="r">{L["b_h_time"]}</th></tr></thead>'
        link = f'<a href="{GH}/blob/main/{tb["analysis"]}">{L["b_link"]} {ARROW}</a>'
        tables.append(f'<div class="bcard"><div class="bcard-h"><h3>{tb["t"]}</h3>{link}</div><div class="scroll"><table>{head}<tbody>{"".join(rows)}</tbody></table></div></div>')
    b_cards = []
    for k, (h, p) in enumerate(L["b_cards"]):
        extra = f'<a href="{GH}/blob/main/bench/ROBUSTNESS.md">{L["b_robust"]} {ARROW}</a>' if k == 1 else ""
        b_cards.append(f'<article class="card"><h3>{h}</h3><p>{p}</p>{extra}</article>')
    data_cards = "".join(f'<article class="src-card"><span class="src-tag">{a}</span><h3>{b}</h3><p>{c}</p></article>' for a, b, c in L["data"])
    plans = []
    for k, c in enumerate(L["p_cards"]):
        href = c["href"].replace("GH", GH)
        badge = f'<span class="badge">{c["badge"]}</span>' if c["badge"] else ""
        ms = "".join(f'<div><b>{a}</b><span>{b}</span></div>' for a, b in c["m"])
        items = "".join(f"<li>{TICK}{x}</li>" for x in c["items"])
        plans.append(f'<article class="plan{" dark" if k == 0 else ""}"><div class="plan-h"><h3>{c["name"]}</h3>{badge}</div><p class="plan-lede">{c["lede"]}</p>'
                     f'<p class="price"><b>{c["price"]}</b> <span>{c["per"]}</span></p>'
                     f'<a class="btn {"light" if k == 0 else "ink"} wide" href="{href}">{c["btn"]} {ARROW}</a>'
                     f'<div class="plan-m">{ms}</div><ul class="plan-list">{items}</ul></article>')
    faq = "".join(f'<details><summary>{q}<i aria-hidden="true"></i></summary><p>{a}</p></details>' for q, a in L["faq"])

    fl = L["f_links"]
    col = lambda items: "".join(f'<a href="{u}">{fl[k] if k in fl else k}</a>' for k, u in items)
    tut_path = "docs/TUTORIEL.md" if L["lang"] == "fr" else "docs/TUTORIAL.md"
    f_col1 = col([(L["n_install"], "#install"), ("bench", f"{GH}/blob/main/docs/BENCHMARK.md"), ("GitHub", GH)])
    f_col2 = col([("tutorial", f"{GH}/blob/main/{tut_path}"), ("tools", f"{GH}/blob/main/docs/TOOLS.md"), ("roles", f"{GH}/blob/main/docs/ROLES.md"), ("data", f"{GH}/blob/main/docs/DATA_SOURCES.md"), ("self", f"{GH}/blob/main/docs/SELF_HOSTING.md")])
    f_col3 = col([("privacy", f"{GH}/blob/main/PRIVACY.md"), ("license", f"{GH}/blob/main/LICENSE")])

    values = {
        **{k: v for k, v in L.items() if isinstance(v, str)},
        "prefix": prefix, "home": home, "gh": GH, "logo": LOGO, "favicon": FAVICON, "tick": TICK, "arrow": ARROW, "gh_icon": GH_ICON,
        "col_heads": "".join(f"<span>{c}</span>" for c in COLS),
        "row_heads": "".join(f"<span>{r}</span>" for r in range(1, ROWS + 1)),
        "hero_cells": "".join(cells), "stats": stats, "tabs": "".join(tabs), "panels": "".join(panels),
        "lane_steps": lane_steps, "dk_steps": dk_steps, "dk_hints": hints, "verify_json": VERIFY_JSON,
        "bench_tables": "".join(tables), "b_cards": "".join(b_cards), "data_cards": data_cards, "faq": faq,
        "f_col1": f_col1, "f_col2": f_col2, "f_col3": f_col3, "tut_path": tut_path, "plans": "".join(plans),
        "comps_analysis": L["benches"][1]["analysis"],
        "desc_attr": html.escape(L["desc"], quote=True), "title_text": html.escape(L["title"]),
        # Cache-busting: a hash of the assets, so a deploy never serves new HTML with old CSS or JS.
        "ver": hashlib.sha256(b"".join((SITE / f).read_bytes() for f in ("style.css", "app.js", "config.js"))).hexdigest()[:10],
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
