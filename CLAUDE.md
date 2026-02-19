# CLAUDE.md

## Project overview

`wa-link-parser` is a Python library + CLI for extracting, classifying, and enriching links from WhatsApp chat exports. It parses `.txt` exports into structured data, stores everything in SQLite, and exports filtered CSV/JSON.

## Architecture

- **Package layout**: `wa_link_parser/` (flat, not src/)
- **CLI**: `wa_link_parser/cli.py` — Click-based, entry point `wa-links` (defined in `pyproject.toml` under `[project.scripts]`)
- **Library modules** have no Click dependency — they use callbacks (`on_progress`, `prompt_fn`) for progress/interaction

### Modules

| Module | Responsibility |
|--------|---------------|
| `models.py` | Data classes: `ParsedMessage`, `ExtractedLink`, `ImportStats` |
| `parser.py` | Parse `.txt` exports — auto-detects 7 WhatsApp formats via scoring first 30 lines |
| `extractor.py` | Extract URLs from text (TLD-aware via `urlextract`), classify by domain |
| `enricher.py` | Fetch page titles/descriptions via HTTP (OG tags, fallback to `<title>`) |
| `exporter.py` | Export links to CSV/JSON with DB query filters + domain exclusions |
| `exclusions.py` | Domain-based exclusion list for filtering ephemeral links at export time |
| `contact_resolver.py` | Fuzzy contact matching and resolution |
| `db.py` | SQLite database layer (WAL mode), path via `WA_LINKS_DB_PATH` env var |
| `cli.py` | Click CLI commands: import, enrich, export, stats, groups, contacts, reset |

### Public API (`__init__.py`)

```python
from wa_link_parser import (
    parse_chat_file,        # parser.py
    extract_links,          # extractor.py
    classify_url,           # extractor.py
    fetch_metadata,         # enricher.py
    enrich_links,           # enricher.py
    export_links,           # exporter.py
    filter_excluded_domains,# exclusions.py
    reset_exclusion_cache,  # exclusions.py
    ParsedMessage,          # models.py
    ExtractedLink,          # models.py
    ImportStats,            # models.py
)
```

### CWD config files

- `link_types.json` — user overrides for domain-to-type mapping (merged with built-in defaults)
- `exclusions.json` — user overrides for export exclusion domains (JSON array, `!` prefix removes defaults)

Both use the same pattern: load from `os.getcwd()`, cache globally, provide `reset_*_cache()` for testing.

### Domain exclusions (export)

`export_links()` has a three-state `exclude_domains` parameter:
- `None` (default): apply built-in defaults + `exclusions.json`
- `[]`: no exclusions, export everything
- `["x.com", ...]`: use this explicit list only

Filtering is Python-side after the DB query. `www.` is normalized for matching.

## Build & test

```bash
# Setup
pip install -e ".[dev]"

# Run tests
pytest

# Build backend
setuptools.build_meta  # (not _legacy)
```

- Python 3.10+ required
- 91 tests in `tests/`, all should pass
- `temp_db` fixture in `conftest.py` gives each test an isolated SQLite DB
- Autouse `_reset_caches` fixture resets exclusion and link-type caches between tests
- License field in `pyproject.toml` means no `License ::` classifier (newer setuptools rejects both)

## Key conventions

- No Click imports outside `cli.py`
- Library functions use `on_progress` callbacks (not Click progress bars)
- Contact resolution uses `prompt_fn` callback (not Click prompts)
- DB functions return `sqlite3.Row` objects (support `row["key"]` access but not `.get()`)
- Idempotent imports via message hash deduplication
