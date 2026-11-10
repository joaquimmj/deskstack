"""Renders demo.cast to ../demo.gif: 800 px wide, one frame per output event.

    python3 site/media/demo/render_gif.py [--font PATH]

Needs Pillow. Plays the subset of a terminal that make_cast.py writes: text, \\r\\n, and the SGR codes for bold, dim,
red, green, blue and reset. Any asciinema player shows the same cast; `agg demo.cast demo.gif` renders it too.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
WIDTH = 800
FONTS = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
BG, WINDOW, BAR, BORDER = (243, 244, 246), (255, 255, 255), (229, 231, 235), (209, 213, 219)
FG, MUTED = (17, 24, 39), (107, 114, 128)
COLORS = {"31": (190, 18, 60), "32": (21, 128, 61), "34": (29, 78, 216)}
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _font(path: str | None, size: int, bold: bool = False):
    for p in ([path] if path else FONTS):
        if p and Path(p).exists():
            # Menlo.ttc: face 0 regular, 1 bold.
            return ImageFont.truetype(p, size, index=1 if bold and p.endswith(".ttc") else 0)
    sys.exit("No monospace font found: pass --font /path/to/a/mono.ttf")


class Screen:
    def __init__(self, rows: int):
        self.rows = rows
        self.lines: list[list[tuple[str, tuple]]] = [[]]
        self.style = (FG, False)

    def feed(self, text: str) -> None:
        pos = 0
        for m in SGR.finditer(text):
            self._text(text[pos:m.start()])
            self._sgr(m.group(1))
            pos = m.end()
        self._text(text[pos:])

    def _sgr(self, codes: str) -> None:
        color, bold = self.style
        for c in (codes or "0").split(";"):
            if c == "0":
                color, bold = FG, False
            elif c == "1":
                bold = True
            elif c == "2":
                color = MUTED
            elif c in COLORS:
                color = COLORS[c]
        self.style = (color, bold)

    def _text(self, s: str) -> None:
        for part in re.split(r"(\r\n)", s):
            if part == "\r\n":
                self.lines.append([])
            elif part:
                self.lines[-1].append((part, self.style))
        self.lines = self.lines[-self.rows:]


def render(cast: Path, out: Path, font_path: str | None = None) -> None:
    head, *events = [json.loads(line) for line in cast.read_text().splitlines()]
    cols, rows = head["width"], head["height"]
    pad, bar_h, margin = 22, 34, 14
    size = 13
    reg, bold, small = _font(font_path, size), _font(font_path, size, True), _font(font_path, 12)
    cw = reg.getlength("M")
    lh = 19
    assert margin * 2 + pad * 2 + cw * cols <= WIDTH, "the cast is too wide for 800 px at this font size"
    height = int(margin * 2 + bar_h + pad * 2 + lh * rows)
    screen = Screen(rows)
    frames, durations = [], []

    def frame() -> Image.Image:
        im = Image.new("RGB", (WIDTH, height), BG)
        d = ImageDraw.Draw(im)
        box = (margin, margin, WIDTH - margin, height - margin)
        d.rounded_rectangle(box, 10, fill=WINDOW, outline=BORDER)
        d.rounded_rectangle((margin, margin, WIDTH - margin, margin + bar_h), 10, fill=BAR)
        d.rectangle((margin + 1, margin + bar_h - 10, WIDTH - margin - 1, margin + bar_h), fill=BAR)
        for i, c in enumerate([(220, 38, 38), (217, 159, 32), (22, 163, 74)]):
            x = margin + 18 + i * 18
            d.ellipse((x - 6, margin + bar_h / 2 - 6, x + 6, margin + bar_h / 2 + 6), fill=c)
        title = head.get("title", "")
        d.text(((WIDTH - small.getlength(title)) / 2, margin + 10), title, font=small, fill=MUTED)
        y = margin + bar_h + pad
        for line in screen.lines:
            x = margin + pad
            for text, (color, b) in line:
                d.text((x, y), text, font=bold if b else reg, fill=color)
                x += cw * len(text)
            y += lh
        return im

    t_prev = 0.0
    for t, kind, text in events:
        if kind != "o":
            continue
        if frames:
            durations.append(max(20, round((t - t_prev) * 1000)))
        screen.feed(text)
        frames.append(frame())
        t_prev = t
    durations.append(1000)
    # One palette for every frame, from the last one (it has every colour): per-frame palettes lose the few
    # saturated pixels and turn red and green grey.
    ref = frames[-1].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    pal = [f.quantize(palette=ref, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"Wrote {out}: {len(frames)} frames, {sum(durations) / 1000:.1f} s, {out.stat().st_size / 1e6:.2f} MB, {WIDTH}x{height}")


if __name__ == "__main__":
    fp = sys.argv[sys.argv.index("--font") + 1] if "--font" in sys.argv else None
    render(HERE / "demo.cast", HERE.parent / "demo.gif", fp)
