# web-crawl 🕸️

**Website Cloner** — download entire websites for offline viewing with a single command.
Pure Python, no API keys, no AI models. CLI + Flask Web UI.

Clone any website to your local machine with all assets (CSS, JS, images, fonts)
rewritten for seamless offline browsing.

---

## Features

- **BFS crawl** — breadth-first crawling with configurable page cap
- **Asset downloading** — CSS, JS, images, fonts, favicons all saved locally
- **Link rewriting** — all `<a>`, `<img>`, `<link>`, `<script>`, `<source>` tags
  rewritten to local relative paths
- **CSS processing** — `url()` and `@import` references resolved and downloaded
- **Parallel downloads** — multi-threaded asset fetching (4 workers by default)
- **Rate limiting** — per-domain token bucket to avoid hammering servers
- **Retry-After support** — honours `Retry-After` headers on 429 responses
- **Sitemap auto-discovery** — pre-seeds the crawl queue from `sitemap.xml`
- **Robots.txt compliance** — respects crawling disallow rules
- **SSRF protection** — blocks private/internal IPs from being crawled
- **Path traversal protection** — ensures output stays within the target directory
- **Filename length safety** — path components over 200 chars are hashed to
  prevent `ENAMETOOLONG` errors
- **Asset size limits** — per-asset 50 MB cap, global 2 GB total cap
- **Render fidelity** — three levels: static, basic JS, full JS with scroll
- **Presets** — `static-blog`, `spa-snapshot`, `polite` for common use-cases
- **Flask Web UI** — live progress tracking, ZIP download, browser-based cloning
- **Job store** — thread-safe job tracking with automatic TTL-based cleanup
- **64 unit tests** — covering URL normalisation, path safety, domain rules,
  BFS logic, job store, thread safety

---

## Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/Venkata-Manoj/web-crawl.git
cd web-crawl

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# .\venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt

# (Optional) For JS rendering support
pip install playwright && playwright install chromium
```

### CLI Usage

```bash
# Basic clone (5 page limit)
python cloner.py https://example.com -o my_clone -n 5

# Full site
python cloner.py https://example.com -o my_clone

# With JS rendering (for React / Vue / Next.js sites)
python cloner.py https://example.com --render l2 -o my_clone

# Follow links to other domains
python cloner.py https://example.com --all-domains -o my_clone

# Use a preset profile
python cloner.py https://example.com --preset polite         # slow and respectful
python cloner.py https://example.com --preset spa-snapshot   # heavy JS rendering
python cloner.py https://example.com --preset static-blog    # static site
```

### Web UI

```bash
python app.py
# Open http://127.0.0.1:5000
```

Enter a URL, pick your settings, and hit Start. Watch progress in real-time and
download a ZIP when done.

---

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `url` | — | Seed URL to start cloning from |
| `-o, --output` | `cloned_sites` | Output directory |
| `-n, --max-pages` | `100` | Maximum HTML pages to clone |
| `--render` | `l0` | Render fidelity: `l0` (static), `l1` (basic JS), `l2` (full JS) |
| `--js` | — | Shorthand for `--render l2` |
| `--preset` | — | Config profile: `static-blog`, `spa-snapshot`, `polite` |
| `--all-domains` | `False` | Follow links to other domains |
| `--delay` | `0.2` | Seconds between HTTP requests |
| `--timeout` | `30` | Request timeout in seconds |
| `--scroll-depth` | `5` | Scroll iterations for lazy content |
| `--wait-ms` | `2000` | Extra wait after scroll (JS mode) |
| `-v, --verbose` | `False` | Enable debug logging |

### Render Fidelity Levels

| Level | Name | Behaviour |
|-------|------|-----------|
| **L0** | Static | `requests` only, no browser. Fast and lightweight. |
| **L1** | Basic JS | Playwright, `networkidle` wait, 1 scroll pass. Catches lazy-loaded content. |
| **L2** | Full JS | Full Playwright with multi-scroll, button clicks, API data intercept. Best for SPAs. |

### Presets

| Preset | delay | workers | render | pages | Use-case |
|--------|-------|---------|--------|-------|----------|
| `static-blog` | 0.5s | 2 | L0 | 500 | Respectful scraper for static content |
| `spa-snapshot` | 0s | 4 | L2 | 100 | Heavy JS for React/Vue/Next.js |
| `polite` | 2s | 1 | L0 | 50 | Maximum respect, slowest speed |

Individual flags override preset values. Example:
```bash
python cloner.py https://example.com --preset polite --delay 1
```
Applies `polite` presets but uses a 1-second delay instead of 2.

---

## Security

Built-in safeguards to prevent abuse and accidents:

| Protection | What it does |
|------------|-------------|
| **SSRF guard** | Blocks URLs pointing to private, loopback, or link-local IPs |
| **Scheme validation** | Only http / https URLs are allowed |
| **Path traversal guard** | Ensures all output stays within the target directory | 
| **Filename length guard** | Path components over 200 chars are hashed |
| **Asset size limit** | Per-asset cap at 50 MB |
| **Total size limit** | Global cap at 2 GB |
| **Robots.txt** | Respects `Disallow` rules by default |

---

## Example Output

```
my_clone/
├── index.html              ← Homepage (links rewritten to local paths)
├── about.html
├── contact.html
├── css/
│   └── styles.css          ← Downloaded & CSS url() refs rewritten
├── js/
│   └── main.js
├── images/
│   ├── logo.png
│   └── hero.jpg
├── fonts/
│   ├── font.woff
│   └── font.ttf
└── favicon.ico
```

**Tested on:** `books.toscrape.com` (41 files, 1.6 MB),
`apple.com` (565 files, 95 MB)

---

## Architecture

### Package layout

```
web-crawl/
├── cloner.py                    # Thin CLI shim → web_crawl
├── app.py                       # Flask Web UI (uses JobStore)
├── web_crawl/
│   ├── __init__.py              # Public API re-exports
│   ├── config.py                # Constants, Config dataclass, presets
│   ├── security.py              # SSRF, path traversal, scheme, filename length
│   ├── rewriter.py              # URL→local path mapping + normalisation
│   ├── storage.py               # File I/O with size tracking
│   ├── rate_limiter.py          # Per-domain token bucket rate limiter
│   ├── fetcher.py               # HTTP, Playwright, parallel asset downloads
│   ├── processor.py             # HTML + CSS processing
│   ├── crawler.py               # WebsiteCloner orchestrator + CLI
│   ├── webjobs.py               # JobStore (thread-safe, TTL-based)
│   └── plugins.py               # Plugin base class (v2.1+)
└── tests/
    ├── test_cloner.py           # 52 unit tests (URL, domain, BFS, CSS, security)
    └── test_webjobs.py          # 12 unit tests (job store CRUD, TTL pruning)
```

### Pipeline

1. **Fetch** — HTTP (`requests`) or headless browser (Playwright) with per-domain
   rate limiting and Retry-After support
2. **Process** — walk DOM tree, discover assets, download in parallel (4 workers)
3. **Save & enqueue** — write rewritten HTML, crawl discovered links

### API

The Web UI exposes both legacy (`/api/`) and namespaced (`/api/v1/`) endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/clone` | POST | Start a new clone job |
| `/api/v1/jobs` | GET | List all jobs |
| `/api/v1/jobs/<id>` | GET | Get single job status |
| `/download/<id>` | GET | Download cloned site as ZIP |
| `/output/<id>` | GET | Browse cloned files |

---

## Test Suite

```bash
pytest tests/ -v
```

**64 tests** covering:
- URL normalisation and slugging
- Domain and link-type detection
- Path traversal prevention (including edge cases)
- Private IP / SSRF safety checks
- BFS crawl behaviour with mocked integration
- CSS `url()` and `@import` processing
- Job store CRUD and TTL-based pruning
- Thread safety (lock acquisition)

---

## Tech Stack

- Python 3.12
- `requests` — HTTP fetching
- `beautifulsoup4` + `lxml` — HTML parsing
- `Playwright` — optional JS rendering
- `Flask` — Web UI

---

## License

MIT
