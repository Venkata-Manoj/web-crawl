# Website Cloner — Agent Guide

## Entry points
- `cloner.py` — CLI tool (`python cloner.py <url> [-o output] [-n 100] [--js]`)
- `app.py` — Flask web UI at `http://127.0.0.1:5000`

Both share `WebsiteCloner` in `cloner.py`.

## Setup
- Two virtualenvs exist: `venv/` (Linux, Python 3.12) and `wvenv/` (Windows, Python 3.11).
- Dependencies in `requirements.txt`.
- JS rendering via Playwright is optional: `pip install playwright && playwright install chromium`.

## Commands
```bash
python cloner.py https://example.com -n 50          # basic clone
python cloner.py https://example.com --js             # with JS rendering
python cloner.py https://example.com --all-domains    # follow external links
python app.py                                         # start web UI
```

Available linters (all in `requirements.txt`): `flake8`, `black`, `mypy`.

## Architecture
- BFS crawl from seed URL, rewrites asset paths for offline viewing.
- Progress callback (`cloned, total, url`) drives the web UI's live status.
- No tests exist.
- Default output dir `cloned_sites/` (gitignored).
