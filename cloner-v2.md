# Website Cloner v2.0 — Architecture Specification

## Overview

A complete rewrite of the website cloner with a modular, plugin-based architecture. Retains the core engine philosophy (URL→local-path mapping, Content-Type-based extensions) while adding parallel fetching, modern JS framework support, incremental updates, and a React-based web UI.

---

## Directory Structure

```
cloner/
├── core/                  # Engine (Python)
│   ├── crawler.py         # Core crawling logic (BFS/DFS, queue management)
│   ├── fetcher/           # Fetch strategies
│   │   ├── http.py        # requests-based fetcher
│   │   ├── playwright.py  # Playwright-based fetcher
│   │   └── parallel.py    # Parallel fetching (ThreadPoolExecutor)
│   ├── processor/         # Asset processing
│   │   ├── html.py        # HTML parsing (BeautifulSoup)
│   │   ├── css.py         # CSS parsing (url(), @import)
│   │   ├── js.py          # JS parsing (dynamic imports, Webpack)
│   │   └── assets.py      # Asset downloading (images, fonts, etc.)
│   ├── rewriter.py        # URL rewriting logic
│   ├── storage.py         # Local file storage (streaming, deduplication)
│   ├── config.py          # Config schemas (Pydantic)
│   └── exceptions.py      # Custom exceptions
│
├── plugins/               # Plugin system
│   ├── __init__.py        # Plugin loader
│   ├── base.py            # Base Plugin class
│   └── examples/          # Example plugins
│       ├── nextjs.py      # Next.js-specific handler
│       └── warc.py        # WARC export plugin
│
├── cli/                   # CLI (Click)
│   ├── main.py            # CLI entrypoint
│   └── progress.py        # Interactive progress bars
│
├── web/                   # Web UI (React + Flask API)
│   ├── frontend/          # React app
│   │   ├── src/
│   │   │   ├── App.tsx    # Main UI
│   │   │   ├── JobList.tsx # Job tracking
│   │   │   └── ConfigForm.tsx # Presets/config
│   │   └── package.json
│   └── backend/           # Flask API
│       ├── app.py         # API endpoints
│       └── jobs.py        # Job management
│
├── server/                # Lightweight server mode
│   ├── main.py            # FastAPI/Flask server
│   └── static.py          # Static file serving
│
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   ├── golden/            # Golden test cases
│   └── fixtures/          # Test sites (e.g., Next.js demo)
│
├── docs/                  # Documentation
│   ├── user/              # User guides
│   └── dev/               # Developer docs
│
├── scripts/               # Helper scripts
│   ├── build.py           # Build CLI binaries/Docker
│   └── release.py         # CI/CD pipeline
│
├── cloner.py              # Legacy entrypoint (deprecated)
├── app.py                 # Legacy Flask UI (deprecated)
└── requirements.txt       # Python dependencies
```

---

## Key Modules & Functions

### 1. Core Engine (`core/`)

| Module | Key Functions | Responsibilities |
|--------|--------------|------------------|
| `crawler.py` | `crawl()`, `enqueue()`, `is_in_scope()` | BFS/DFS crawling, queue management, scope rules |
| `fetcher/playwright.py` | `fetch_page()`, `scroll_page()`, `click_elements()`, `wait_for_network_idle()` | JS rendering, scroll/click simulation, post-load API fetches |
| `fetcher/parallel.py` | `fetch_parallel()`, `throttle()` | Parallel asset downloading, rate limiting |
| `processor/js.py` | `extract_dynamic_imports()`, `rewrite_webpack_chunks()` | Parse JS for dynamic imports, Webpack chunks |
| `rewriter.py` | `rewrite_url()`, `local_path_for()` | URL rewriting, deterministic local paths |
| `storage.py` | `save_streaming()`, `deduplicate()`, `incremental_update()` | Streaming writes, deduplication, incremental updates |
| `config.py` | `Config`, `Preset` | Pydantic schemas for CLI/web configs (e.g., "static blog" preset) |

### 2. Plugin System (`plugins/`)

| Plugin | Key Functions | Use Case |
|--------|--------------|----------|
| `nextjs.py` | `handle_next_data()`, `rewrite_image_endpoints()` | Next.js `_next/data` and `_next/image` handling |
| `warc.py` | `export_to_warc()` | Export clones as WARC files |
| `singlefile.py` | `bundle_to_single_html()` | Bundle assets into a single HTML file |

### 3. CLI (`cli/`)

| Module | Key Functions | Responsibilities |
|--------|--------------|------------------|
| `main.py` | `cli()`, `validate_config()` | CLI entrypoint, argument parsing |
| `progress.py` | `ProgressBar`, `update_eta()` | Interactive progress bars (e.g., `tqdm`) |

### 4. Web UI (`web/`)

| Module | Key Functions | Responsibilities |
|--------|--------------|------------------|
| `frontend/App.tsx` | `JobList`, `ConfigForm`, `ProgressTracker` | React components for job tracking, config presets |
| `backend/app.py` | `start_job()`, `get_status()`, `download_zip()` | Flask API endpoints for job management |

### 5. Server Mode (`server/`)

| Module | Key Functions | Responsibilities |
|--------|--------------|------------------|
| `main.py` | `serve_clone()`, `handle_incremental_update()` | FastAPI/Flask server for serving clones |
| `static.py` | `serve_static()` | Static file serving (e.g., for offline browsing) |

---

## Data Flow Diagram (Textual)

```
1. User Input (CLI/Web)
   │
   ▼
2. Config Parser (`config.py`)
   │
   ▼
3. Crawler (`crawler.py`)
   ├── Enqueue seed URL (BFS/DFS)
   ├── Fetch Page (`fetcher/playwright.py` or `fetcher/http.py`)
   │     ├── Scroll/Click/Wait (Playwright)
   │     ├── Extract Assets (HTML/CSS/JS)
   │     └── Discover Links
   ├── Process Assets (`processor/*.py`)
   │     ├── Download Assets (`processor/assets.py`)
   │     ├── Rewrite URLs (`rewriter.py`)
   │     └── Save Locally (`storage.py`)
   └── Enqueue New Links
   │
   ▼
4. Storage (`storage.py`)
   ├── Save HTML/CSS/JS (streaming)
   ├── Deduplicate Assets
   └── Incremental Updates (if enabled)
   │
   ▼
5. Output
   ├── Local Directory
   ├── ZIP (Web UI)
   ├── WARC (Plugin)
   └── Single-file HTML (Plugin)
```

---

## Priority Order for Implementation

| Phase | Focus Area | Key Tasks | Rationale |
|-------|------------|-----------|-----------|
| 1 | Core Engine | - Rewrite `crawler.py` (BFS/DFS, queue management)<br>- Implement `fetcher/parallel.py` (parallel fetching)<br>- Add retry/rate-limiting (`fetcher/parallel.py`) | Foundation for all other features. Immediate performance boost. Robustness for real-world use. |
| 2 | JS/Modern Framework Support | - Enhance `fetcher/playwright.py` (scroll/click/API waits)<br>- Add `processor/js.py` (dynamic imports, Webpack) | Critical for Next.js/Nuxt/SvelteKit. Unlocks modern SPAs. |
| 3 | Plugin System | - Implement `plugins/base.py` (Plugin API)<br>- Add `plugins/nextjs.py` (Next.js handler) | Extensibility for future formats. High-value target framework. |
| 4 | Incremental Updates | - Implement `storage.py` (incremental updates, deduplication) | Reduces bandwidth/time for updates. |
| 5 | Web UI | - Replace Flask template with React (`web/frontend/`) | Modern UX, easier maintenance. |
| 6 | Testing | - Add `tests/golden/` (reference outputs)<br>- Add `tests/integration/` (end-to-end tests) | Ensures regression-free upgrades. Validates real-world scenarios. |
| 7 | Deployment | - Dockerize (`scripts/build.py`)<br>- Pre-built CLI binaries (`scripts/build.py`) | Simplifies setup. Better user experience. |

---

## Risks and Mitigations

| Risk | Mitigation | Example |
|------|------------|---------|
| **JS-Heavy Sites Fail** | - Use Playwright for scroll/click/API waits<br>- Add plugin hooks for framework-specific logic | Next.js sites with infinite scroll (e.g., `remotelyavailable.com`) |
| **Rate Limiting/Bans** | - Adaptive delays (`fetcher/parallel.py`)<br>- User-configurable delays | Sites with aggressive WAF (e.g., Cloudflare) |
| **Memory Explosion** | - Streaming writes (`storage.py`)<br>- Chunked downloads | Large sites (e.g., Wikipedia) |
| **URL Rewriting Bugs** | - Centralized `rewriter.py` with deterministic paths<br>- Golden test cases (`tests/golden/`) | Relative vs. absolute URLs (e.g., `//example.com/image.png`) |
| **Plugin Complexity** | - Clear Plugin API (`plugins/base.py`)<br>- Example plugins (`plugins/examples/`) | Custom asset processors (e.g., image optimization) |
| **Incremental Update Errors** | - Content hashing (`storage.py`)<br>- User confirmation for conflicts | Changed assets with same URLs (e.g., CDN updates) |

---

## Real-World Examples

### 1. Next.js Handling

**Problem**: Next.js uses `/_next/data` for client-side navigation and `/_next/image` for optimized images.

**Solution** (`plugins/nextjs.py`):

```python
def handle_next_data(self, url: str, html: str) -> str:
    # Rewrite /_next/data endpoints to local paths
    return re.sub(r'/_next/data/([^"]+)', self.rewrite_url, html)

def rewrite_image_endpoints(self, url: str) -> str:
    # Rewrite /_next/image?url=... to local paths
    if "_next/image" in url:
        return self.rewrite_url(url, content_type="image/webp")
```

**Solution** (`fetcher/playwright.py`):

```python
async def scroll_page(self, page):
    # Scroll to bottom to trigger lazy-loaded content
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(2000)  # Wait for API fetches
```

### 2. Parallel Fetching

**Problem**: Sequential downloads are slow.

**Solution** (`fetcher/parallel.py`):

```python
def fetch_parallel(self, urls: List[str], max_workers: int = 8) -> List[bytes]:
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(self._download_asset, urls))

def throttle(self, delay: float = 0.5):
    # Adaptive delay based on response headers (e.g., 429)
    time.sleep(delay)
```

### 3. Incremental Updates

**Problem**: Re-downloading unchanged files wastes bandwidth.

**Solution** (`storage.py`):

```python
def incremental_update(self, url: str, content: bytes) -> bool:
    local_path = self.local_path_for(url)
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            if hashlib.md5(f.read()).digest() == hashlib.md5(content).digest():
                return False  # No update needed
    self.save_streaming(local_path, content)
    return True
```

---

## Architecture Decision Record (ADR)

**Title**: Adopt a Plugin-Based Architecture for Cloner 2.0
**Status**: Proposed
**Context**:

- Cloner 1.0 has monolithic logic for asset processing (HTML/CSS/JS).
- Future requirements (WARC, single-file HTML) demand extensibility.
- Framework-specific handling (Next.js, Nuxt) needs modular hooks.

**Decision**:

- Implement a plugin system (`plugins/`) with a base `Plugin` class.
- Plugins can:
  - Hook into asset processing (e.g., `process_html`, `process_js`).
  - Add custom output formats (e.g., `export_to_warc`).
  - Override URL rewriting (e.g., Next.js image endpoints).

**Tradeoffs**:

| Pros | Cons |
|------|------|
| Extensible for new formats | Added complexity |
| Framework-specific logic | Plugin discovery/maintenance overhead |
| Separation of concerns | |

**Alternatives**:

- **Monolithic**: Harder to maintain (rejected).
- **Microservices**: Overkill for a CLI tool (rejected).

**Migration**:

- Phase 1: Extract existing logic into built-in plugins (e.g., `html.py` → `plugins/html.py`).
- Phase 2: Allow user-installed plugins via `~/.cloner/plugins/`.

---

## Next Steps

1. **Phase 1 Implementation**:
   - Rewrite `crawler.py` and `fetcher/parallel.py`.
   - Add `plugins/base.py` and `plugins/nextjs.py`.
   - Test with `books.toscrape.com` (static) and `remotelyavailable.com` (Next.js).

2. **Phase 2 Implementation**:
   - Replace Flask UI with React (`web/frontend/`).
   - Add `storage.py` for incremental updates.

3. **Documentation**:
   - Write `docs/user/quickstart.md` and `docs/dev/plugins.md`.

---

## Compatibility with v1

### Preserved Invariants

- **URL→local-path mapping** centralized in `rewriter.py` (memoized in `url_to_local`).
- **Asset extensions** from `Content-Type`, not URLs (`CONTENT_TYPE_EXT`, `KNOWN_EXTS`).
- **Scope rules**: `same_domain_only` default, external assets under `_external/<domain>/`.
- **Page link enqueue**: HTML-like extensions only (`.html`, `.htm`, `.php`, etc.).

### Breaking Changes

- CLI flags restructured (Click-based, backward-compatible aliases).
- Web UI API endpoints changed (`/api/v2/...`).
- Output directory structure: `cloned_sites/<job_id>/` instead of ad-hoc `-o` dirs.
- Config via YAML/JSON presets instead of CLI-only flags.

### Migration Path

- `cloner.py` and `app.py` remain as deprecated entrypoints.
- Legacy `--js` flag maps to `render_js: true` in config.
- Existing output folders readable by new server mode.

---

## Testing Strategy

### Golden Test Cases (`tests/golden/`)

```
tests/golden/
├── books-toscrape/        # Static site reference
│   ├── expected/          # Expected output directory
│   └── config.yaml        # Clone config
├── remotelyavailable/     # Next.js reference
│   ├── expected/
│   └── config.yaml
└── wordpress-demo/        # Server-rendered reference
    ├── expected/
    └── config.yaml
```

### Integration Tests (`tests/integration/`)

- End-to-end clone of reference sites.
- Compare output against golden references.
- Test incremental updates (run twice, verify no re-download).
- Test plugin outputs (WARC, single-file HTML).

### Unit Tests (`tests/unit/`)

- `rewriter.py`: URL rewriting edge cases.
- `storage.py`: Deduplication, content hashing.
- `config.py`: Schema validation.
- `plugins/nextjs.py`: Next.js URL transformations.

---

## Security Considerations

1. **URL Validation**: Reject `file://`, `javascript:`, `data:` schemes.
2. **Rate Limiting**: Default 1 req/sec per domain, configurable.
3. **Resource Limits**: Max pages (default 1000), max asset size (default 50MB).
4. **Sandboxed Playwright**: Run in isolated context, no filesystem access.
5. **Input Sanitization**: Escape user-provided URLs in logs/UI.

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Static site (100 pages) | < 30 seconds |
| JS site (50 pages, scroll) | < 60 seconds |
| Memory usage (peak) | < 500 MB |
| Parallel workers | 8 (configurable) |
| Incremental update (no changes) | < 5 seconds |

---

*Generated from architect analysis of cloner.md v1.0*
