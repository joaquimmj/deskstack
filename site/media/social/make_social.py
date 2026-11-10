"""Draws site/media/social-preview.png, the 1280x640 image GitHub shows when the repo is shared.

    python3 site/media/social/make_social.py [--sans PATH] [--mono PATH]

Needs Pillow. Colours are the site's tokens (site/style.css). The cells are Apple's real figures from
examples/apple-dcf-typo: the typed FY2025 revenue and what the 10-K says.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
W, H = 1280, 640
SHEET, PAPER, GRID, INK, INK2, INK3 = "#f6f7f8", "#ffffff", "#e3e6ea", "#111418", "#3b4149", "#6b7280"
GO, GO_SOFT, BAD, BAD_SOFT = "#107c41", "#e7f2ec", "#c42b1c", "#fbeae8"
SANS = ["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/HelveticaNeue.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
MONO = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def font(cands, size, path=None):
    for p in ([path] if path else cands):
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    sys.exit("No font found: pass --sans / --mono")


def main(argv):
    sans_p = argv[argv.index("--sans") + 1] if "--sans" in argv else None
    mono_p = argv[argv.index("--mono") + 1] if "--mono" in argv else None
    tie = json.loads((ROOT / "examples" / "apple-dcf-typo" / "associate.json").read_text())
    bad = next(r for r in tie["rows"] if r["status"] == "mismatch")
    ok = [r for r in tie["rows"] if r["status"] == "match" and r["metric"] == "revenue"]
    k = tie["counts"]

    im = Image.new("RGB", (W, H), SHEET)
    d = ImageDraw.Draw(im)
    # The spreadsheet grid, faint, across the whole card.
    for x in range(0, W, 128):
        d.line((x, 0, x, H), fill=GRID)
    for y in range(0, H, 40):
        d.line((0, y, W, y), fill=GRID)

    title, h1, body, small = font(SANS, 76, sans_p), font(SANS, 40, sans_p), font(SANS, 26, sans_p), font(SANS, 22, sans_p)
    mono, mono_b = font(MONO, 24, mono_p), font(MONO, 26, mono_p)

    # Left: the name and the promise.
    d.rectangle((64, 80, 640, 560), fill=PAPER, outline=GRID)
    d.text((104, 116), "deskstack", font=title, fill=INK)
    d.text((104, 224), "AI-built models get", font=h1, fill=INK)
    d.text((104, 272), "numbers wrong.", font=h1, fill=INK)
    d.text((104, 336), "deskstack checks every one", font=h1, fill=GO)
    d.text((104, 384), "against the filings.", font=h1, fill=GO)
    d.text((104, 480), "Free cited data, US and Europe. Independent", font=small, fill=INK3)
    d.text((104, 510), "reviewers. Nothing ships without your sign-off.", font=small, fill=INK3)

    # Right: three revenue cells from the Apple tie-out, the middle one wrong.
    x0, y0, cw, rh = 704, 136, 512, 72
    rows = [(r["period"], r["value"], r["filed_value"], "ok") for r in sorted(ok, key=lambda r: r["period"])]
    rows.insert(1, (bad["period"], bad["value"], bad["filed_value"], "bad"))
    d.rectangle((x0, y0 - 56, x0 + cw, y0), fill=PAPER, outline=GRID)
    d.text((x0 + 24, y0 - 42), "Apple revenue, USD m", font=body, fill=INK2)
    for i, (per, typed, filed, kind) in enumerate(rows[:3]):
        y = y0 + i * rh
        fill = BAD_SOFT if kind == "bad" else PAPER
        d.rectangle((x0, y, x0 + cw, y + rh), fill=fill, outline=GRID)
        d.text((x0 + 24, y + 22), per, font=mono, fill=INK3)
        d.text((x0 + 150, y + 20), f"{typed:,.0f}", font=mono_b, fill=BAD if kind == "bad" else INK)
        mark = f"filed {filed:,.0f}" if kind == "bad" else "ties"
        d.text((x0 + cw - 24 - mono.getlength(mark), y + 22), mark, font=mono, fill=BAD if kind == "bad" else GO)
    y = y0 + 3 * rh + 28
    d.rectangle((x0, y, x0 + cw, y + 88), fill=PAPER, outline=GRID)
    d.text((x0 + 24, y + 14), "/associate", font=mono_b, fill=INK)
    d.text((x0 + 24, y + 50), f"{k['match']} of {k['match'] + k['mismatch']} match. Two digits swapped.", font=small, fill=BAD)
    d.text((x0, 538), "Independent open-source project. Not affiliated with Anthropic.", font=font(SANS, 18, sans_p), fill=INK3)

    out = ROOT / "site" / "media" / "social-preview.png"
    im.save(out, optimize=True)
    print(f"Wrote {out}: {im.size[0]}x{im.size[1]}, {out.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1:])
