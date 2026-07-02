# web-crawl 🕸️

**Website Cloner** — download entire websites for offline viewing with a single command. Pure Python, no API keys, no AI models. CLI + Flask Web UI.

Clone any static website to your local machine with all assets (CSS, JS, images, fonts) rewritten for offline browsing.

---

## Features

- **BFS crawl** — breadth-first crawling with configurable page cap
- **Asset downloading** — CSS, JS, images, fonts, favicons all saved locally
- **Link rewriting** — all `<a>`, `<img>`, `<link>`, `<script>`, `<source>` tags rewritten to local relative paths
- **CSS processing** — `url()` and `@import` references resolved and downloaded
- **Sitemap auto-discovery** — pre-seeds the crawl queue from `sitemap.xml`
- **Robots.txt compliance** — respects crawling rules
- **SSRF protection** — blocks private/internal IPs from being crawled
- **Path traversal protection** — ensures output stays within the target directory
- **JS rendering mode** — optional Playwright for SPAs (React, Vue, Next.js)
- **Flask Web UI** — live progress tracking, ZIP download, browser-based cloning
- **52 unit tests** — covering URL normalization, path safety, domain rules, BFS logic

---

## Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/Venkata-Manoj/web-crawl.git
cd web-crawl

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
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

# Full site (no limit)
python cloner.py https://example.com -o my_clone

# With JS rendering (for React/Vue/Next.js sites)
python cloner.py https://example.com --js -o my_clone

# Follow links to other domains
python cloner.py https://example.com --all-domains -o my_clone

# Throttled crawl (0.5s delay between requests)
python cloner.py https://example.com --delay 0.5 -o my_clone
```

### Web UI

```bash
python app.py
# Open http://127.0.0.1:5000
```

Enter a URL, pick your settings, and hit Start. Watch progress in real-time and download a ZIP when done.

---

## Example Output

```
my_clone/
├── index.html              ← Homepage (links rewritten to local paths)
├── about.html
├── contact.html
├── css/
│   └── styles.css          ← Downloaded & CSS url() references rewritten
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

**Tested on:** `books.toscrape.com` (41 files, 1.6 MB), `apple.com` (565 files, 95 MB)

---

## Test Suite

```bash
python -m unittest discover tests -v
```

52 tests covering:
- URL normalization and slugging
- Domain and link-type detection
- Path traversal prevention
- Private IP / SSRF safety checks
- BFS crawl behaviour with mocked integration
- CSS url() and @import processing

---

## Architecture

Two files, one engine:

| File | Purpose |
|------|---------|
| `cloner.py` | Core `WebsiteCloner` class + CLI entry point |
| `app.py` | Flask web UI wrapper with live progress + ZIP download |

Both share the same `WebsiteCloner` engine in `cloner.py`.

### Pipeline

1. **Fetch** — HTTP (`requests`) or headless browser (Playwright)
2. **Process** — walk DOM tree, download assets, rewrite paths
3. **Save & enqueue** — write rewritten HTML, crawl discovered links

---

## Tech Stack

- Python 3.12
- `requests` — HTTP fetching
- `beautifulsoup4` + `lxml` — HTML parsing
- `Playwright` — optional JS rendering
- `Flask` — web UI

---

## License

MIT
