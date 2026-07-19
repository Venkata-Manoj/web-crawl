# Website Cloner v2 — Build Specification

**Status:** Ready to implement  
**Approach:** Extract and harden v1 — do not rewrite from scratch  
**Goals:** Secure by default, modular for scale, honest offline fidelity

This document replaces the earlier aspirational `cloner-v2.md` as the implementation contract. Keep `cloner-v2.md` as historical vision if useful; **build from this file**.

---

## 1. Product definition

Clone websites into a self-contained local folder (HTML + CSS + JS + images + fonts) for offline viewing. Surfaces: CLI and local Web UI. No API keys, no AI models.

### Fidelity levels (set expectations)

| Level | Name | What you get |
|-------|------|----------------|
| L0 | Static HTTP | Server HTML/CSS/assets as fetched |
| L1 | Rendered snapshot | Playwright first paint / network idle |
| L2 | Expanded snapshot | Auto-scroll + short wait for lazy content |
| L3 | Framework-assisted | Best-effort hooks (e.g. Next.js assets) — **not** a full working SPA |

v2 ships L0–L2 solidly; L3 is optional plugins after the core is stable.

### Non-goals (v2.0)

- Bypassing Cloudflare / CAPTCHA / auth walls
- Fully interactive offline React/Next apps
- Distributed crawl cluster / microservices
- Plugin marketplace or remote plugin install
- Replacing the Flask UI with React in v2.0

---

## 2. Design principles

1. **Extract, don’t rewrite** — Split `cloner.py` into packages; public CLI flags and clone behavior stay compatible unless versioned.
2. **Security is default** — SSRF, path traversal, scheme checks, robots, rate limits on by default; unsafe options require explicit flags.
3. **One engine, many surfaces** — CLI and Web UI call the same core; no duplicated crawl logic.
4. **Scale by modules + concurrency knobs** — Thread-safe queue and URL map; parallel **assets**, careful parallel **pages**.
5. **Test before expand** — Unit + fixture integration move with every phase; golden trees from recorded fixtures, not live sites.

---

## 3. Target layout

Package name avoids colliding with `cloner.py`:

```
web_crawl/                 # installable package (or keep as local package)
├── __init__.py
├── config.py              # Pydantic (or dataclasses) — validated config
├── exceptions.py
├── security.py            # SSRF, schemes, path safety, size limits
├── crawler.py             # BFS queue, scope, robots, sitemap seed
├── rewriter.py            # URL → local path (memoized), Content-Type exts
├── storage.py             # safe writes, streaming, optional incremental
├── fetcher/
│   ├── base.py
│   ├── http.py            # requests + retries + 429 backoff
│   ├── playwright.py      # L1/L2 render
│   └── parallel.py        # bounded ThreadPool for assets
├── processor/
│   ├── html.py
│   ├── css.py
│   └── assets.py
└── plugins/               # v2.1+ — stub hooks only in v2.0
    └── base.py

cli/
└── main.py                # Click or argparse wrapper (thin)

web/
├── app.py                 # Flask API + existing UI (evolve, don’t replace)
└── jobs.py                # job store abstraction

tests/
├── unit/
├── integration/           # fixture HTTP server or recorded responses
└── fixtures/              # frozen HTML/CSS/JS samples

cloner.py                  # thin deprecated shim → web_crawl
app.py                     # thin shim → web.app (or keep and re-export)
```

Docker / CI stay; no second FastAPI server in v2.0.

---

## 4. Non-negotiable v1 parity

These must remain green throughout the migration:

| Invariant | Why |
|-----------|-----|
| Central URL→local map (`url_to_local`) | Offline link consistency |
| Asset extension from `Content-Type` when URL has no known ext | Next `/_next/image`, CDN URLs |
| Rewrite `src` **and** `srcset` | Browsers prefer srcset |
| Same-domain crawl by default; external assets under `_external/<domain>/` | Scope safety |
| Enqueue only HTML-like page links | Don’t treat binaries as pages |
| Private IP / SSRF block | Don’t crawl localhost / RFC1918 |
| Path traversal → safe hashed names | Contain output under target dir |
| robots.txt respect (default on) | Legal/ethical default |
| Sitemap seed when available | Better coverage |
| Progress callback `(cloned, total, url)` | Web UI live status |
| POSIX `/` in rewritten HTML paths; `os.path` only at FS boundary | Windows correctness |

---

## 5. Security model

### 5.1 Defaults (always on)

| Control | Default | Notes |
|---------|---------|--------|
| Block private/link-local/metadata IPs | ON | Resolve host; reject RFC1918, loopback, link-local, AWS/GCP metadata ranges |
| Allow only `http`/`https` | ON | Reject `file:`, `javascript:`, `data:` as crawl targets |
| Path containment | ON | All writes under `output_dir` after `realpath` |
| robots.txt | ON | `--ignore-robots` explicit opt-out |
| Max pages | 1000 | Configurable; Web UI should cap lower for demos |
| Max asset size | 50 MB | Abort single asset over limit |
| Max total bytes | 2 GB | Soft stop with clear error |
| Request delay | 0 (CLI) / 0.2s (Web) | Parallelism uses per-domain token bucket |
| Parallel workers | 4 assets | Cap pages at 1–2 concurrent fetches unless configured |
| User-Agent | identifiable | e.g. `WebCrawl/2.0 (+local; +respect-robots)` |
| Playwright | no host FS; isolated context | No downloads of arbitrary files outside output |

### 5.2 Explicit unsafe flags (logged loudly)

- `--allow-private` — disable SSRF checks (local lab only)
- `--ignore-robots`
- `--all-domains` — follow other hosts for **pages** (assets already partially allowed)

### 5.3 Web UI hardening

- Bind `127.0.0.1` by default (not `0.0.0.0`)
- Validate/sanitize URL input; never reflect raw URL into HTML without escape
- Job IDs: opaque random IDs (not timestamps alone)
- Download ZIP only for jobs owned by this process; path stays under output root
- Optional: simple token / local auth if binding beyond localhost later
- CSP on preview routes (v1 already sandboxes preview — keep it)

### 5.4 What we do not promise

Aggressive WAFs, authenticated scrapes, or ToS-violating crawls. Document user responsibility in README.

---

## 6. Scalability model

### 6.1 Concurrency

```
Pages:   sequential or small pool (1–2) — Playwright is heavy; HTML rewrite must stay consistent
Assets:  ThreadPoolExecutor (N workers) with per-domain rate limit
Shared:  Lock around url_to_local + visited + queue enqueue
```

**Rule:** Never mutate the URL map without the lock. Prefer “claim URL → download → register path” so two workers don’t write the same file differently.

### 6.2 Memory

- Stream asset downloads to disk (`iter_content` / chunked writes)
- Bound in-memory HTML size; skip or truncate pathological pages with a warning
- One Playwright browser per job; reuse pages; always cleanup in `finally`
- Jobs dict: TTL + max concurrent jobs (e.g. 3) + disk-backed status optional later

### 6.3 Incremental updates (v2.0 optional, design now)

Prefer conditional HTTP over “download then hash”:

1. Store sidecar meta: `ETag`, `Last-Modified`, content hash, URL  
2. Re-fetch with `If-None-Match` / `If-Modified-Since`  
3. On 304 → skip write  
4. Hash compare only if server sends no validators  

### 6.4 Horizontal scale later (out of v2.0, design-compatible)

- Pure functions: fetch / process / rewrite take config + bytes, no globals  
- Job store interface: `InMemoryJobStore` now → Redis/SQLite later  
- No assumption that Flask process == only crawler (queue interface ready)

---

## 7. Config surface

Single validated config object (YAML/JSON + CLI + Web form):

```yaml
url: https://example.com
output: ./cloned_sites/example
max_pages: 100
render: l0          # l0 | l1 | l2
same_domain_only: true
delay_seconds: 0.2
asset_workers: 4
respect_robots: true
allow_private: false
max_asset_bytes: 52428800
max_total_bytes: 2147483648
```

**Presets** (optional convenience):

| Preset | Intent |
|--------|--------|
| `static-blog` | L0, higher page cap, 4 workers |
| `spa-snapshot` | L2, lower page cap, 2 workers, delay 0.3 |
| `polite` | delay 1.0, workers 2, robots on |

CLI keeps v1 flags with aliases (`--js` → `render: l1` or `l2`).

---

## 8. Implementation phases

Each phase has an exit criterion. Do not start the next phase until green.

### Phase 0 — Safety net (before moves)

- Fix Windows path rewrite: store `/` in HTML, convert only at write time  
- Ensure CI: pytest + flake8 + black on existing tree  
- Snapshot current public CLI behavior in a short compatibility note  

**Exit:** 52+ tests pass on Windows and Linux CI.

### Phase 1 — Package extract (behavior-identical)

- Move engine into `web_crawl/` modules listed above  
- `cloner.py` / `app.py` become thin entrypoints  
- No new features  

**Exit:** Same tests + smoke clone of `example.com` / fixture site.

### Phase 2 — Parallel assets + resilient HTTP

- `fetcher/parallel.py` with locks and per-domain throttle  
- Retries with exponential backoff; honor `Retry-After` on 429  
- Streaming writes + size limits enforced  

**Exit:** Fixture site clones ≥2× faster than sequential baseline; no race flake in tests.

### Phase 3 — Render fidelity L1/L2

- Playwright: network idle, configurable scroll passes, wait budget  
- Document fidelity levels in CLI help / UI  

**Exit:** Fixture SPA shows lazy-loaded block present under L2, absent under L0.

### Phase 4 — Web jobs + API cleanup

- Extract `jobs.py` with `InMemoryJobStore`  
- Stable JSON API under `/api/v1/...` (avoid premature `/v2` break)  
- Keep current HTML UI; no React  

**Exit:** UI works; jobs cleaned after TTL; bind localhost only.

### Phase 5 — Incremental + polish

- Sidecar validators + conditional GET  
- Optional ZIP streaming to disk for large clones  
- Docs: security defaults, fidelity levels, presets  

**Exit:** Second run with no changes completes under performance target without rewriting files.

### Phase 6 (v2.1+) — Plugins

Only after Phases 0–5:

- `Plugin` hooks: `after_html`, `map_url`, `export`  
- First plugins: Next.js asset hints, WARC export, single-file bundle  

Do **not** build plugin discovery from `~/.cloner/plugins` until one built-in plugin proves the API.

---

## 9. Data flow

```
CLI / Web form
    → Config (validated)
    → Security gate (scheme, SSRF, limits)
    → Crawler (BFS)
         → Fetch page (http | playwright)
         → Process HTML/CSS
         → Parallel fetch assets (bounded)
         → Rewriter (locked map)
         → Storage (contained paths, stream)
         → Enqueue in-scope links
    → Output dir (+ optional ZIP / later WARC)
```

---

## 10. Testing strategy

### Unit

- Rewriter edge cases (`//cdn`, query strings, Content-Type ext)  
- Security: private IPs, `file://`, traversal  
- Config validation  
- Path separator contract (Windows)  

### Integration (fixtures, not live internet)

```
tests/fixtures/
├── static-mini/          # tiny static site
├── css-imports/
└── spa-lazy/             # minimal HTML+JS that loads on scroll
```

Serve via `http.server` or `pytest-httpserver`; assert file set + key rewritten links.

### Golden

Store **expected file lists + hashes of critical files**, not entire live production sites. Update goldens deliberately in PRs.

### Performance smoke (optional CI job)

| Metric | Target |
|--------|--------|
| Static fixture ~100 pages | < 30s on CI-class machine |
| Peak RSS typical job | < 500 MB |
| Incremental no-op | < 5s for same fixture |
| Asset workers default | 4 |

---

## 11. Compatibility

### Preserve

- CLI: `python cloner.py <url> [-o] [-n] [--js] [--all-domains] [--delay]`  
- Web: local UI with progress + ZIP download  
- Output usable as static files opened from disk or simple static server  

### Allowed breaks (versioned, documented)

- New config file format  
- New `/api/v1` JSON shapes (old form POSTs can remain)  
- Deprecation warnings on shim entrypoints  

### Avoid in v2.0

- Forcing `cloned_sites/<job_id>/` as the only output layout for CLI  
- Dual Flask + FastAPI stacks  
- React frontend requirement  

---

## 12. Ops & packaging

- Keep single Dockerfile (gunicorn + Flask); Playwright optional multi-stage later  
- `requirements.txt` split optional: `requirements-dev.txt` for flake8/black/mypy/pytest  
- Structured logging (level, job_id, url) — no secrets in logs  
- Healthcheck remains on Web UI  

---

## 13. Taken from prior v2 draft (kept)

- Modular core (crawler / fetcher / processor / rewriter / storage)  
- Parallel asset downloading  
- Stronger Playwright waits / scroll  
- Config presets  
- Incremental updates (redesigned to use HTTP validators)  
- Plugin **direction** (deferred to v2.1)  
- Performance targets  
- ADR spirit: extensibility without microservices  

## 14. Dropped or deferred from prior draft

| Item | Decision |
|------|----------|
| Full rewrite + React UI | Deferred — low ROI for local tool |
| FastAPI second server | Dropped for v2.0 |
| Plugins in Phase 1 | Deferred to v2.1 |
| Live-site golden trees | Replaced with fixtures |
| DFS crawl as equal peer | BFS default; DFS not required |
| Hash-after-full-download “incremental” | Replaced with conditional GET |
| Pre-built binaries in first ship | Optional later |

---

## 15. Definition of done (v2.0 release)

- [ ] Package layout as in §3; shims work  
- [ ] All §4 invariants covered by tests  
- [ ] Security defaults in §5 enforced and documented  
- [ ] Parallel assets + retries live  
- [ ] L0 / L1 / L2 selectable  
- [ ] Flask UI on localhost with job TTL  
- [ ] Fixture integration tests in CI  
- [ ] Windows path tests pass  
- [ ] README: fidelity levels, security flags, presets  
- [ ] No React / no plugin marketplace required  

---

## 16. Suggested first tickets

1. Fix `_safe_path` / rewrite separators for Windows; add regression test  
2. Introduce `web_crawl/security.py` + move SSRF/path checks  
3. Introduce `web_crawl/rewriter.py` + keep memoization  
4. Thin `WebsiteCloner` façade over new modules (still one class for UI)  
5. Parallel asset downloader behind a feature flag, then default on  

---

*Build from this spec. Use prior `cloner-v2.md` only as optional feature backlog for v2.1+.*
