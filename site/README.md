# Publication site shell

This directory contains the dependency-light static frontend. Do not place generated report or map payloads here by hand.

Build from repository records:

```bash
python scripts/build_site.py --strict --output _site
python -m http.server 8000 --directory _site
```

The builder creates the browser-facing catalog, copies approved report content, and emits a publication-safe GeoJSON map projection.
