# Website Cloner — Agent Guide

## Entry points
- `cloner.py` — CLI tool (`python cloner.py <url> [-o output] [-n 100] [--js]`)
- `app.py` — Flask web UI at `http://127.0.0.1:5000`

Both share `WebsiteCloner` in `cloner.py`.

## Setup
- Virtualenv: `venv/` (Linux, Python 3.12). A `wvenv/` for Windows is optional and not present in this repo.
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
- Tests: `tests/test_cloner.py` — pure unit tests with network mocked (no real I/O). Run with `python -m pytest tests/ -v`.
- Default output dir `cloned_sites/` (gitignored).

## Testing / CI
- Unit tests live in `tests/test_cloner.py` and use `unittest` with mocked network calls.
- Run locally: `python -m pytest tests/ -v`
- CI runs automatically on every push and pull request to `main` via `.github/workflows/ci.yml`, executing:
  1. `python -m pytest tests/ -v` (must pass)
  2. `flake8 cloner.py app.py tests/ --max-line-length=120` (must pass)
  3. `black --check cloner.py app.py tests/` (must pass — run `black .` locally first)
  4. `mypy cloner.py --ignore-missing-imports` (non-blocking)
- Linters `flake8`, `black`, `mypy` are installed via `requirements.txt`; `pytest` is also listed there.
