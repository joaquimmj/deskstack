# Site source

`index.html` and `fr/index.html` are generated. Edit the copy in `copy.py` (English and French; every number there
comes from a published benchmark analysis or the live data), the layout in `template.html` and `build.py`, and the
look in `../style.css`. Then run:

    python3 site/src/copy.py && python3 site/src/build.py

`copy.py` writes `content.json`; `build.py` writes both pages and stamps the CSS and JS links with a hash of their
contents, so a deploy never pairs new HTML with cached old assets. The Pages workflow fails if the generated pages
are stale.

Layout after univer.ai's; colour values taken from aptence.app's palette (values only, no code or assets). Fonts:
Geist and Geist Mono (Google Fonts).

The connector URL lives in `site/config.js`. While it is empty, the page shows "coming soon" and the self-hosting link.
