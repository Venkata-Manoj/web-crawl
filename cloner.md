# What this is

A website cloner that downloads an entire site (HTML pages + CSS, JS, images, fonts) to a local folder so it runs offline as a self-contained copy. Pure Python automation — no API keys, no AI models. Two delivery surfaces share one engine: a CLI and a local Flask web app.

## Commands

This environment uses Windows + PowerShell. Python 3.12 is installed but `pip` is **not** on PATH — always use `python -m pip`.

```powershell
# Install dependencies
python -m pip install -r requirements.txt

# Install the headless browser (required only for JS render mode)
python -m playwright install chromium

# Run the web UI -> http://127.0.0.1:5000
python app.py

# Run the cloner directly (CLI)
python cloner.py https://example.com -o out_dir -n 50          # static, 50-page cap
python cloner.py https://example.com --js                       # JS render mode
python cloner.py https://example.com --all-domains --delay 0.5  # follow other domains, throttle
```

## Tests

52 unit tests live in [`tests/test_cloner.py`](tests/test_cloner.py) covering:
- URL normalization & slugging
- Domain/link-type detection
- Path traversal protection
- IP/SSRF safety checks
- BFS crawl behaviour (mocked integration)

Run them with:

```powershell
python -m unittest discover tests -v
```

Linters (`flake8`, `black`, `mypy`) are listed in `requirements.txt`.

When testing in PowerShell, set `$env:PYTHONIOENCODING="utf-8"` first to avoid Unicode log errors, and clean up generated output folders (`cloned_sites/`, ad-hoc `-o` dirs) afterward.

## Architecture

Two files, one engine:

- **[cloner.py](cloner.py)** — the `WebsiteCloner` class is the whole engine, plus a `__main__` CLI wrapper. Playwright is imported optionally (`PLAYWRIGHT_AVAILABLE`); the tool degrades to HTTP-only if it's missing.
- **[app.py](app.py)** — Flask wrapper. Runs each clone in a background thread, tracks jobs in an in-memory `JOBS` dict keyed by timestamp ID, polls `/status/<id>` for live progress, and zips the output folder in memory for `/download/<id>`. The entire HTML/CSS/JS frontend is one inline `PAGE` string template — there is no separate templates/ or static/ dir.

### The clone pipeline (cloner.py)

Breadth-first crawl from a queue, capped by `max_pages`. Per page:

1. **Fetch** — `_fetch_page` uses either `requests` (fast, static) or Playwright `networkidle` (renders JS for React/Vue/Next). Mode is chosen by the `render_js` flag.
2. **Process** — `_process_page` walks the BeautifulSoup tree, downloads every asset referenced by `ASSET_ATTRS` (tag→attribute map), recurses into CSS (`_process_css` handles `url(...)` and `@import`), and rewrites all references to relative local paths.
3. **Save & enqueue** — writes the rewritten HTML, enqueues newly discovered in-scope `<a>` links.

### Two invariants that are easy to break

- **URL→local-path mapping is centralized in `_local_path_for`** and memoized in `self.url_to_local`. Every link/asset rewrite resolves through it, so the saved copy is internally consistent. Changing the naming scheme affects both where files land and how references point at them — keep it deterministic and idempotent.
- **Asset extensions come from the response `Content-Type`, not the URL.** Extension-less endpoints (e.g. Next.js `/_next/image?url=...`, which returns real images) would otherwise be saved as `.html` and not render. `_download_asset` fetches first, then calls `_local_path_for(..., content_type=...)`, which appends an extension from `CONTENT_TYPE_EXT` when the URL path lacks a known one (`KNOWN_EXTS`). Both `src` and `srcset` must be rewritten — browsers prefer `srcset`.

### Scope & link rules

- `same_domain_only` (default true) keeps the crawl on the start domain; out-of-domain assets still download but land under `_external/<domain>/`. Out-of-scope page links are left as absolute URLs (still clickable online).
- Only `<a>` links that look HTML-like (no extension, or `.html/.htm/.php/.asp/.aspx`) are enqueued as pages; binary extensions are skipped from crawling.

## Known limitation (don't treat as a bug)

Static cloning captures a React/Next.js page **as rendered at load**. Sections that appear only on scroll, click, hover, or after a post-load API fetch won't be in the single Playwright snapshot. Server-rendered sites (e.g. WordPress) clone exactly; client-rendered apps yield a visual replica of the initial view, not a fully working app. Improving this means adding auto-scroll and a wait delay before snapshotting in `_fetch_page`'s browser branch.
