# Site source

`index.html` and `fr/index.html` are generated. Edit the copy in `content.json` (English and French; every number there
comes from a published benchmark analysis or the live data), the layout in `template.html` and `build.py`, and the
look in `../style.css`. Then run:

    python3 site/src/build.py

French copy uses a non-breaking space before : ; ? ! % and $, and a narrow one in thousands, as French typography
does: keep them when you edit. (Until 2026-11-10 `copy.py` generated `content.json`; later edits went to
`content.json` directly, so it became the source and `copy.py` was removed.)

`build.py` writes both pages and stamps the CSS and JS links with a hash of their
contents, so a deploy never pairs new HTML with cached old assets. The Pages workflow fails if the generated pages
are stale.

Layout after univer.ai's; colour values taken from aptence.app's palette (values only, no code or assets). Fonts:
Geist and Geist Mono (Google Fonts).

The connector URL lives in `site/config.js`. While it is empty, the page shows "coming soon" and the self-hosting link.
