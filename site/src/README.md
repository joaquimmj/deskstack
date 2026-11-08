# Site source

`index.html` and `fr/index.html` are generated from `template.html` and `content.json` (English and French copy).
Edit those, then run `python3 site/src/build.py`. The Pages workflow fails if the generated pages are stale.

The connector URL lives in `site/config.js`. While it is empty, the page shows "coming soon" and the self-hosting link.
