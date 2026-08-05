# Static publication site

## Purpose

The publication site is a build-time projection of approved repository records. It is not a browser over the full research repository and must never expose draft, embargoed, delayed, withheld, or otherwise non-public material.

## Source and output

- `site/` contains the static HTML, CSS, and JavaScript shell.
- `scripts/build_site.py` scans approved report manifests and the latest approved map snapshot.
- `_site/` is generated output and is not canonical source data.
- `data/catalog.json` is the browser-facing report index.
- `data/map.geojson` is the browser-facing publication-safe map projection.
- report Markdown and report manifests are copied to `content/` under deterministic report-ID paths.

The shell uses hash routes so it works beneath a GitHub Pages project path without server-side rewrites:

- `#/latest`
- `#/daily`
- `#/report/{report_id}`
- `#/map`
- `#/about`

## Report publication boundary

A report is included only when:

1. its manifest is under `data/reports/`;
2. `record_status` is `approved`;
3. its repository-relative `content_path` resolves inside the repository;
4. the referenced Markdown file exists.

The generated catalog contains publication metadata and stable URLs, not arbitrary repository traversal capabilities.

## Map publication boundary

The builder chooses the newest approved map snapshot whose `publication_cutoff` has elapsed. It reads only the snapshot's declared `feature_files` and includes a feature only when:

1. it is a GeoJSON `Feature` with non-null geometry;
2. `record_status` is `approved`;
3. `publication_status` is `public` or `coarsened`;
4. `publish_not_before` is not later than the build time.

Delayed, withheld, draft, rejected, superseded, withdrawn, malformed, or future-embargoed geometry is excluded before files reach the browser.

## Build and preview

```bash
python scripts/build_site.py --strict --output _site
python -m http.server 8000 --directory _site
```

Open `http://localhost:8000/`.

## GitHub Pages deployment

`.github/workflows/deploy-pages.yml` is the production publication path. On relevant pushes to `main`, or on manual dispatch, it:

1. checks out the exact `main` revision;
2. runs the site-builder tests;
3. builds `_site/` in strict mode;
4. verifies the generated catalog, map projection, entry page, and `.nojekyll` marker;
5. uploads `_site/` as the `github-pages` artifact;
6. deploys that artifact to the protected `github-pages` environment.

The workflow grants only `contents: read`, `pages: write`, and `id-token: write`. The build workflow remains separate and validates publication generation on pull requests and pushes independently of deployment.
