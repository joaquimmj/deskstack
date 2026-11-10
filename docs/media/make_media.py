"""Render docs/media/*.png from the repo's real files, no hand-made content:
- sources-sheet.png: the Sources sheet of examples/apple-dcf/model.xlsx, cell by cell;
- sign-off.png: examples/apple-dcf/sign-off.md, the page /sign-off writes;
- social-preview.png (1280x640): the pitch and the benchmark figures from bench/results/*/ANALYSIS.md.
Each is an HTML page shot by headless Chrome. Run from the repo root: python3 docs/media/make_media.py
(needs openpyxl and Google Chrome)."""
from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "media"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#f6f7f9;font:14px/1.45 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1d2330}
.frame{margin:20px;background:#fff;border:1px solid #d5d9e0;border-radius:8px;overflow:hidden}
.bar{background:#eef1f5;border-bottom:1px solid #d5d9e0;padding:8px 14px;font-weight:600;color:#3a4252}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #e6e9ee;padding:7px 12px;text-align:left;vertical-align:top}
th{background:#fafbfc;color:#566073;font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.src{color:#3a4252;font-size:12.5px}code{font:12.5px ui-monospace,Menlo,monospace;background:#f1f3f6;padding:1px 4px;border-radius:3px}
.pass{color:#0f7b3f;font-weight:600}.missing{color:#8a6100;font-weight:600}.page{padding:6px 18px 14px}
h2{font-size:18px;margin:12px 0 6px}p{margin:8px 0}</style>"""


def shoot(page: str, name: str, w: int, h: int, scale: int = 2) -> None:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "page.html"
        f.write_text(page, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={scale}",
                        f"--window-size={w},{h}", f"--screenshot={OUT / name}", f.as_uri()],
                       check=True, capture_output=True)
    print("wrote", OUT / name)


def sources_sheet(rows: int = 5) -> str:
    ws = openpyxl.load_workbook(ROOT / "examples" / "apple-dcf" / "model.xlsx")["Sources"]
    data = list(ws.iter_rows(values_only=True))
    head, body = data[0], data[1:rows + 1]
    tr = "".join(
        "<tr>" + "".join(
            f'<td class="{"num" if isinstance(v, (int, float)) else ("src" if i == 4 else "")}">'
            f'{html.escape(f"{v:,}" if isinstance(v, (int, float)) else str(v))}</td>' for i, v in enumerate(r)) + "</tr>"
        for r in body)
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in head)
    return (BASE + f'<div class="frame"><div class="bar">examples/apple-dcf/model.xlsx · Sources sheet (first {len(body)} '
            f'of {len(data) - 1} rows)</div><table><tr>{th}</tr>{tr}</table></div>')


def md_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def sign_off() -> str:
    lines = (ROOT / "examples" / "apple-dcf" / "sign-off.md").read_text().splitlines()
    out, table = [], []
    for ln in lines + [""]:
        if ln.startswith("|"):
            if not set(ln) <= set("|- "):
                table.append([c.strip() for c in ln.strip("|").split("|")])
            continue
        if table:
            head, *body = table
            cls = lambda c: f' class="{c}"' if c in ("pass", "missing") else ""
            out.append("<table><tr>" + "".join(f"<th>{md_inline(h)}</th>" for h in head) + "</tr>" + "".join(
                "<tr>" + "".join(f"<td{cls(c)}>{md_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</table>")
            table = []
        if ln.startswith("## "):
            out.append(f"<h2>{md_inline(ln[3:])}</h2>")
        elif ln.strip():
            out.append(f"<p>{md_inline(ln)}</p>")
    return BASE + '<div class="frame"><div class="bar">/sign-off · examples/apple-dcf/sign-off.md</div><div class="page">' + "".join(out) + "</div></div>"


def social() -> str:
    def row(path: str, label: str) -> tuple[int, int]:
        t = (ROOT / "bench" / "results" / path / "ANALYSIS.md").read_text()
        a = re.search(r"\| A: web search only \|[^|]*\| ([\d,]+) \| \*\*(\d+) \(", t)
        b = re.search(r"\| B: deskstack data \|[^|]*\| ([\d,]+) \| \*\*0\*\*", t)
        c = re.search(r"\| C: deskstack \+ associate[^|]*\|[^|]*\| ([\d,]+) \| \*\*0\*\*", t)
        n = lambda m: int(m.group(1).replace(",", ""))
        return n(a), int(a.group(2)), n(b) + n(c)
    d, cmp_ = row("2026-11-09T09-25-07-305Z", "DCF"), row("2026-11-09T13-04-05-468Z", "Comps")
    web_n, web_bad, ds = d[0] + cmp_[0], d[1] + cmp_[1], d[2] + cmp_[2]
    pct = f"{100 * web_bad / web_n:.1f}%"
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;width:1280px;height:640px;background:#14213d;color:#f4f6fa;font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}}
.w{{padding:64px 72px;box-sizing:border-box;height:640px;display:flex;flex-direction:column}}
.n{{font-size:34px;font-weight:700;letter-spacing:.2px;color:#9fb3d9}}.p{{font-size:50px;line-height:1.15;font-weight:700;margin:26px 0 0;max-width:1100px}}
.s{{display:flex;gap:28px;margin-top:auto}}.c{{flex:1;background:#1f2f52;border-radius:14px;padding:26px 30px}}
.v{{font-size:56px;font-weight:800;line-height:1}}.l{{font-size:24px;color:#c9d4ea;margin-top:12px}}.g{{color:#7ee2a8}}.r{{color:#ffb4a2}}
</style><div class="w"><div class="n">deskstack</div>
<div class="p">Claude builds your DCFs and comps from SEC and EU filings. A second agent checks every number.</div>
<div class="s"><div class="c"><div class="v g">0 of {ds:,}</div><div class="l">reported figures wrong with deskstack</div></div>
<div class="c"><div class="v r">{web_bad} of {web_n:,} ({pct})</div><div class="l">wrong with web search only</div></div></div></div>"""


if __name__ == "__main__":
    shoot(sources_sheet(), "sources-sheet.png", 1200, 455)
    shoot(sign_off(), "sign-off.png", 1000, 470)
    shoot(social(), "social-preview.png", 1280, 640, scale=1)  # GitHub wants 1280x640
    sys.exit(0)
