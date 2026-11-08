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
TICK = '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="M4 13.5l5 5L20 6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
CIRCLE = '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path pathLength="1" d="M12 3.2c5 0 8.8 3.7 8.6 8.9-.2 5-4 8.6-9 8.5-4.8-.1-8.4-3.9-8.2-8.8C3.6 6.8 7.3 3.1 12.6 3.4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>'
LOGO = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2.5" y="2.5" width="19" height="19" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 12.5l3.2 3.2L17.5 8" fill="none" stroke="#c8102e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>'
FAVICON = "data:image/svg+xml," + LOGO.replace('"', "'").replace("#", "%23").replace("currentColor", "%2314213d").replace(' aria-hidden=\'true\'', " xmlns='http://www.w3.org/2000/svg'")


def render(L: dict, prefix: str, home: str) -> str:
    t = (HERE / "template.html").read_text()
    rows = []
    for line, period, value, ok in L["rows"]:
        cls = "" if ok else ' class="flag"'
        rows.append(f'<tr{cls}><td>{line}</td><td>{period}</td><td class="num">{value}</td><td class="mark"><span class="visually-hidden">{L["ok"] if ok else L["bad"]}</span>{TICK if ok else CIRCLE}</td></tr>')
    roles = []
    for cmd, desc in L["roles"]:
        cls = ' class="gate"' if cmd == "/sign-off" else ""
        roles.append(f"<li{cls}><code>{cmd}</code><p>{desc}</p></li>")
    data = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in L["data"])
    limits = "".join(f"<li>{x}</li>" for x in L["limits"])
    values = {**{k: v for k, v in L.items() if isinstance(v, str)}, "prefix": prefix, "home": home, "gh": GH, "logo": LOGO,
              "favicon": FAVICON, "tick": TICK, "circle": CIRCLE, "rows": "\n".join(rows), "roles": "".join(roles),
              "data_rows": data, "limit_items": limits, "desc_attr": html.escape(L["desc"], quote=True),
              "title_text": html.escape(L["title"])}
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
