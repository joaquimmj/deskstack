"""The site (stars brief lot 10): built pages are current, and each has Open Graph tags whose image exists at 1280x640."""

from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"


def test_built_pages_are_current(tmp_path):
    before = {p: (SITE / p).read_text() for p in ("index.html", "fr/index.html")}
    subprocess.run([sys.executable, str(SITE / "src" / "build.py")], check=True, capture_output=True)
    for p, text in before.items():
        assert (SITE / p).read_text() == text, f"site/{p} is stale: run python3 site/src/build.py"


def test_open_graph_and_hreflang():
    w, h = struct.unpack(">II", (SITE / "media" / "social-preview.png").read_bytes()[16:24])
    assert (w, h) == (1280, 640)
    for page, url in (("index.html", "https://joaquimmj.github.io/deskstack/"), ("fr/index.html", "https://joaquimmj.github.io/deskstack/fr/")):
        t = (SITE / page).read_text()
        og = dict(re.findall(r'<meta property="og:([a-z:_]+)" content="([^"]*)">', t))
        assert og["image"] == "https://joaquimmj.github.io/deskstack/media/social-preview.png"
        assert og["url"] == url and og["title"] and og["description"] and og["image:alt"]
        assert '<meta name="twitter:card" content="summary_large_image">' in t
        assert all(href.startswith("https://") for href in re.findall(r'<link rel="alternate" hreflang="[^"]+" href="([^"]+)"', t))


def test_the_home_page_carries_the_readme_top():
    t = (SITE / "index.html").read_text()
    for s in ("AI-built models get numbers wrong.", "deskstack checks every one against the filings.", 'id="catches"',
              'id="cli"', 'id="examples"', "pipx run deskstack-check", "tree/main/examples/errors-caught"):
        assert s in t, s
