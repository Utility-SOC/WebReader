# Developing WebReader

How the pieces fit together, how to run and test them, and the conventions that keep the project accessible and private. For what WebReader is and how to use it, see the [README](../README.md).

## What's in the repository

```
backend/             FastAPI app, Celery worker, extraction, accessibility checks, document library
  main.py            routes, deployment-mode gate, /fetch_url, TTS, PDF page/box endpoints
  tasks.py           background processing (Celery) for uploads and library sync
  utils.py           PDF / EPUB / MOBI / image text extraction
  pdf_auto.py        column and reading-order logic for PDF text
  ocr_pdf.py         OCR fallback (tesseract) and the "can we trust this PDF's text?" planner
  extract_docx.py / extract_pptx.py / extract_pdf.py   build a format-neutral structure (structure.py)
  pdf_tags.py        inspects a PDF's real tag tree
  a11y_checks.py     the accessibility issues (each has a WCAG criterion and a fix class)
  report.py, report_guidance.py   admin accessibility report and its plain-language guidance
  connectors/        how a repository is read (folder today); deny-by-default allow rules
  library_models.py, ingest.py, search.py, library_api.py, library_cli.py   the document library
  providers.py, captioning.py   AI image captioning (local model or an API, chosen by environment variables)
  safe_http.py       SSRF-safe URL fetching
  tests/             pytest suite; pdfgen.py builds test PDFs
frontend/            React 19 + Vite + Tailwind v4 (components/: Library, Modal, PdfManualEditor, RSVPDisplay, ...)
charts/webreader/    Helm chart            deploy/   standalone Docker Compose and Kubernetes release bundles
scripts/             setup, demo data, browser checks, notices generator (see below)
THIRD_PARTY_LICENSES/   generated notices and licence texts
```

```
 browser ──► frontend (Vite) ──► backend (FastAPI) ──► Redis ◄── worker (Celery)
                                     │                              │
                                     └────── SQLite (data/webreader.db) + temp_uploads/ ◄┘
```

The backend and worker share the same image (`backend/Dockerfile`); they differ only by command. The database is SQLite created with `create_all`: **there are no migrations yet**, so don't change existing tables without adding a migration story first.

## Running it

**With Docker (recommended)**

```bash
docker compose up -d --build        # frontend :5173, backend :8000, plus worker and Redis
./scripts/demo-seed.sh              # optional: a sample repository loaded into the library
```

Open http://localhost:5173 (library at `#/library`). The backend code is mounted into the containers, so after a backend change `docker compose restart backend worker` is enough; the frontend has no mount, so rebuild it with `docker compose up -d --build frontend`. If you ever reset `data/webreader.db`, restart the backend and worker afterwards: they keep reading the file they had open.

**Without Docker:** `run_linux.sh`, `run_windows.ps1` / `.bat` (these need Python, Node, Redis and Tesseract; see the README).

Node is not required on the host: run npm and the linters in a container, for example

```bash
docker run --rm -v "$PWD/frontend:/app" -w /app -u "$(id -u):$(id -g)" -e HOME=/tmp node:22-alpine \
  sh -c 'npm ci --silent && npx eslint src && npx vite build'
```

## Deployment modes

`WEBREADER_MODE=personal` (default) is for reading your own files: uploads, URL fetching and the AI/TTS endpoints are on.

`WEBREADER_MODE=reading_room` is for a public library of documents an administrator has released. Every route except `/health` and `/library/*` answers 404 (an allowlist, so a route added later cannot become public by accident), request logging is switched off, CORS is same-origin, and the UI shows the library instead of an upload control. An unrecognised value of `WEBREADER_MODE` stops the app from starting rather than falling back to personal mode. Features that need a server-side speech service are hidden in this mode.

## Configuration

All optional.

| Variable | Default | Purpose |
|---|---|---|
| `WEBREADER_MODE` | `personal` | `personal` or `reading_room` (above) |
| `WEBREADER_CORS_ORIGINS` | all in personal mode, none in reading room | comma-separated allowed origins |
| `WEBREADER_CAPTION_PROVIDER` | `local` | `local`, `none`, `openai`, `deepseek`, `kimi`, `custom`, `gemini`, `anthropic` |
| `WEBREADER_LLM_API_KEY`, `_MODEL`, `_BASE_URL`, `_TIMEOUT` | | for the API providers (`scripts/setup-ai.sh` writes them to `.env`, mode 600) |
| `WEBREADER_FETCH_ALLOW_PRIVATE` | off | `1` lets `/fetch_url` reach private addresses (desktop use) |
| `WEBREADER_MAX_FETCH_MB` | `200` | download size limit for `/fetch_url` |
| `WEBREADER_OCR_DPI`, `_OCR_LANG` | `200`, `eng` | OCR resolution and language |
| `WEBREADER_OCR_VERIFY` | `auto` | `auto` / `always` / `never`: check a PDF's text layer against OCR of sampled pages |
| `WEBREADER_UPLOAD_ANALYSIS` | off | `1` runs the accessibility analysis on PDFs uploaded to read (the library always runs it) |
| `WEBREADER_TABLES` | `image` | `image` (a table needs a description) or `structured` (header-row checks) |
| `WEBREADER_MAX_STRUCTURE_PAGES` | `400` | page cap for structure analysis |
| `WEBREADER_CACHE_DIR`, `WEBREADER_DATA_DIR` | next to the source | OCR cache and (desktop) data location |

## The document library

An administrator points the library at a repository and decides what to publish. This is done with a command-line tool on purpose, not an HTTP API, so there is nothing for an anonymous visitor to reach.

```bash
python -m backend.library_cli add-source NAME --root /data/docs --include 'public/**' --exclude 'public/drafts/**' \
    --rule 'public/planning/=Planning Commission:zoning,minutes'
python -m backend.library_cli sync NAME --dry-run     # shows what would change; changes nothing
python -m backend.library_cli sync NAME
python -m backend.library_cli held NAME               # processed but not yet public
python -m backend.library_cli release NAME
python -m backend.library_cli report NAME --html report.html --csv issues.csv
```

Concepts worth knowing before changing this code:

- **Deny by default.** A source with no `--include` pattern publishes nothing, and the CLI refuses to create one.
- **Hold queue.** New items are processed but invisible to readers until released.
- **Provenance.** Every metadata value records where it came from (`original`, `rule`, `machine`, `human`) and is never overwritten; a revision adds a row and marks the old one superseded, so the history is kept. Anything a machine inferred is labelled as such wherever readers see it.
- **Connectors** only list and fetch (read-only) with a cheap change fingerprint. Allow rules, change detection and processing are shared, so a new kind of repository needs only a new connector (`connectors/base.py`).
- **Public API** (`library_api.py`) returns only released items and never exposes repository paths. Search terms are used to build one query and then dropped: never log or store them.

## Accessibility checks and the report

`a11y_checks.py` and `pdf_tags.py` raise `Issue`s with a code, severity, location, WCAG criterion and a fix class (`auto`, `suggest`, `manual`). They report what a program can detect; they do not make a document accessible and are never a compliance claim.

When you add a check you must also add its plain-language guidance to `report_guidance.py` (and a name for any new WCAG criterion): a test fails the build otherwise.

## Testing

**Backend** (pytest; the image has the tools it needs, tesseract included):

```bash
docker build -q -f backend/Dockerfile -t webreader-backend-test .
docker run --rm -v "$PWD/backend:/app/backend" -e PYTHONPATH=/app -e WEBREADER_DATA_DIR=/tmp/wr \
  webreader-backend-test sh -c 'pip install -q pytest httpx python-pptx && cd /app && python -m pytest backend/tests -q'
```

`backend/tests/pdfgen.py` builds PDFs on demand: fonts, words positioned **without** space characters (as many real PDFs are), images, ruled tables, scans (with Pillow-rendered text), invisible text layers, tagged structure trees. **Test on real documents before you call something done.** Synthetic files have repeatedly hidden bugs that real ones exposed: PDFs with no space glyphs or with spaces mapped to Unicode non-characters, Word-exported tag trees that crash pdfplumber, and OCR that is far slower than it looks on modest hardware.

**Browser checks** (real Chromium, Firefox and WebKit through Playwright, with axe-core). They run in a container and need Docker:

| Command | Checks |
|---|---|
| `./scripts/privacy-check.sh` | no third-party requests, cookies, service workers or stored document names (`EXPECT_READING_ROOM=1` for a reading room) |
| `BASE=http://localhost:5173 ./scripts/ui-check.sh` | the library UI: axe in light and dark, keyboard-only search, paging and focus, labelling, privacy, 320px reflow (needs `./scripts/demo-seed.sh`) |
| `BASE=http://localhost:5173 ./scripts/ui-check.sh box` | PDF editor selection boxes keep the text under them readable: 3 browsers × 10 configurations, including forced-colors and a forced-opaque worst case |
| `./scripts/report-check.sh report.html` | the admin report page |

A change to the UI should keep these green and should itself meet WCAG 2.2 AA: everything operable by keyboard with a visible focus ring, names and labels on every control, sufficient contrast in light and dark, no horizontal scroll at 320px, no information conveyed by colour alone.

## Conventions

- **Privacy first.** No requests from the browser to third parties (fonts are bundled), no cookies, no analytics, nothing about what a reader searched for or opened stored or logged. Anything that sends data to an outside service must be an explicit administrator choice with disclosure.
- **Machine output is labelled.** Anything generated by a model is marked as machine-generated in the data and in the UI until a person has reviewed it.
- **Licences.** The project is MIT. After any dependency change run `./scripts/generate-notices.sh` (it rebuilds `THIRD_PARTY_LICENSES/THIRD_PARTY_NOTICES.md` from real package metadata). Check the licence of anything new, especially copyleft ones.
- **Commits and PRs.** One slice per branch and PR, branched from `main`, with tests. Check `git status` before `git add -A` (generated folders such as `demo-repo/` and `node_modules/` are ignored, but check). CI builds the images and release on every push to `main`.

## Gotchas

- **Fonts** are imported in `frontend/src/main.jsx`, not in CSS: Tailwind inlines CSS imports, which breaks the font file URLs.
- **Tailwind v4** has no `bg-opacity-*` utilities; opacity modifiers compile to `color-mix` with a hex fallback.
- **Stacking contexts:** a `z-index` makes an isolated layer, and `mix-blend-mode` inside it cannot reach what is behind it. The editor's selection tint is therefore a sibling of the page image.
- **`docker run -v /path/to/file:/x`** creates a directory if the file does not exist yet.
- **OCR is slow** on modest CPUs (seconds per page): certain signals go to OCR, doubtful pages are verified by sampling one page first, and results are cached by file hash.

## Known limitations

SQLite only (no migrations), the library reads folders only, OCR is English-only without fine deskew or table detection, the frontend image runs the Vite development server, and the tests and linters do not yet run in CI.
