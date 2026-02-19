# wa-link-parser

Extract, classify, and enrich links from WhatsApp chat exports.

`wa-link-parser` is a Python library and CLI tool that takes a WhatsApp `.txt` export and turns it into a searchable, filterable link catalog. It parses messages, extracts URLs, classifies them by domain (YouTube, Maps, Reddit, etc.), fetches page titles and descriptions, and exports everything to CSV or JSON.

## Why this exists

WhatsApp groups accumulate dozens of links daily -- articles, videos, restaurants, travel ideas -- that disappear into chat scroll. There's no good tool to answer "what was that Airbnb link someone shared last month?" This tool fills that gap.

### The pipeline

```
Raw .txt file
  -> Parse          Structured messages with timestamps + senders
  -> Extract        URLs pulled from message text (TLD-aware, not naive regex)
  -> Attribute      Each link tied to WHO shared it and WHEN
  -> Contextualize  Adjacent messages within 60s grabbed as surrounding context
  -> Classify       Domain mapped to type (youtube->video, swiggy->food, github->code)
  -> Enrich         HTTP fetch of each URL -> page title + OG description
  -> Export         SQLite with relational model -> filtered CSV/JSON
```

## Installation

```bash
pip install wa-link-parser
```

Or install from source:

```bash
git clone https://github.com/sreeramramasubramanian/wa-link-parser.git
cd wa-link-parser
pip install -e .
```

For development (includes pytest):

```bash
pip install -e ".[dev]"
```

## Quick start

### As a CLI

```bash
# Import a chat export
wa-links import chat.txt --group "Bali Trip"

# Enrich links with page titles and descriptions
wa-links enrich "Bali Trip"

# Export to CSV (ephemeral domains like meet.google.com excluded by default)
wa-links export "Bali Trip"

# Export with no exclusions
wa-links export "Bali Trip" --no-exclude

# Export filtered results
wa-links export "Bali Trip" --type youtube --format json
wa-links export "Bali Trip" --sender "Priya" --after 2025-10-01

# View stats
wa-links stats "Bali Trip"
```

### As a library

```python
from wa_link_parser import (
    parse_chat_file,
    extract_links,
    classify_url,
    fetch_metadata,
    enrich_links,
    export_links,
    filter_excluded_domains,
)

# Parse a chat export
messages = parse_chat_file("chat.txt")

# Extract and classify links from messages
for msg in messages:
    links = extract_links(msg.raw_text)
    for link in links:
        print(f"{msg.sender}: {link.url} ({link.link_type})")

# Fetch metadata for a single URL
title, description = fetch_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

# Export with default exclusions (meet.google.com, zoom.us, etc. filtered out)
export_links("Bali Trip")

# Export everything, no exclusions
export_links("Bali Trip", exclude_domains=[])

# Export with a custom exclusion list
export_links("Bali Trip", exclude_domains=["zoom.us", "meet.google.com"])

# Filter links directly (works on any list of dicts with a "domain" key)
all_links = [{"domain": "youtube.com", "link": "..."}, {"domain": "zoom.us", "link": "..."}]
filtered = filter_excluded_domains(all_links)  # uses defaults
filtered = filter_excluded_domains(all_links, exclude_domains=[])  # no filtering
filtered = filter_excluded_domains(all_links, exclude_domains=["zoom.us"])  # custom
```

#### Library API

| Function | Description |
|----------|-------------|
| `parse_chat_file(path)` | Parse a `.txt` export into `ParsedMessage` objects |
| `extract_links(text)` | Extract URLs from text, returns `ExtractedLink` objects |
| `classify_url(url)` | Classify a URL by domain, returns link type string |
| `fetch_metadata(url)` | Fetch page title and description for a URL |
| `enrich_links(group_id)` | Enrich all unenriched links for a group in the DB |
| `export_links(group, ...)` | Export links to CSV/JSON with filters and exclusions |
| `filter_excluded_domains(links, ...)` | Filter link dicts by domain exclusion list |
| `reset_exclusion_cache()` | Clear cached exclusion domains (for testing) |

#### Data classes

| Class | Fields |
|-------|--------|
| `ParsedMessage` | `timestamp`, `sender`, `raw_text`, `is_system` |
| `ExtractedLink` | `url`, `domain`, `link_type` |
| `ImportStats` | `new_messages`, `skipped_messages`, `links_extracted`, `contacts_created` |

**No Click dependency in library modules** -- the CLI layer (`wa_link_parser.cli`) depends on Click, but all library functions use callbacks (`on_progress`, `prompt_fn`) instead, so you can use the library without Click.

## Supported formats

The parser auto-detects WhatsApp export formats from multiple locales:

| Format | Example |
|--------|---------|
| Indian (bracket, tilde) | `[20/10/2025, 10:29:01 AM] ~ Sender: text` |
| US (bracket, short year) | `[1/15/25, 3:45:30 PM] Sender: text` |
| International (no bracket, 24h) | `20/10/2025, 14:30 - Sender: text` |
| US (no bracket, 12h) | `1/15/25, 3:45 PM - Sender: text` |
| European (short year, 24h) | `20/10/25, 14:30 - Sender: text` |
| German (dots) | `20.10.25, 14:30 - Sender: text` |
| Bracket (no tilde, full year) | `[20/10/2025, 10:29:01 AM] Sender: text` |

## CLI commands

### `import`

Import a WhatsApp chat export file.

```bash
wa-links import <file> --group "Group Name"
wa-links import <file> --group "Group Name" --enrich
```

- Deduplicates on reimport (idempotent)
- Resolves contacts with fuzzy matching on subsequent imports
- Builds context from adjacent messages by the same sender (within 60s)

### `enrich`

Fetch page titles and descriptions for unenriched links.

```bash
wa-links enrich "Group Name"
```

- Extracts `og:title` and `og:description`, falls back to `<title>` tag
- Rate-limited (2 req/sec) with retry on failure
- Safe to run multiple times -- only fetches metadata for new links

### `export`

Export links to CSV or JSON with optional filters.

```bash
wa-links export "Group Name"
wa-links export "Group Name" --format json
wa-links export "Group Name" --type youtube --sender "Alice" --after 2025-10-01
wa-links export "Group Name" --no-exclude
```

| Flag | Description |
|------|-------------|
| `--output` | Output file path |
| `--type` | Filter by link type (e.g., `youtube`, `travel`, `shopping`) |
| `--sender` | Filter by sender name (substring match) |
| `--after` | Only links after this date (`YYYY-MM-DD`) |
| `--before` | Only links before this date (`YYYY-MM-DD`) |
| `--domain` | Filter by domain (substring match) |
| `--format` | `csv` (default) or `json` |
| `--no-exclude` | Disable default domain exclusions |

### `stats`

Show group statistics.

```bash
wa-links stats "Group Name"
```

### `groups`

List all imported groups.

### `contacts`

List or resolve contacts.

```bash
wa-links contacts "Group Name"
wa-links contacts "Group Name" --resolve
```

### `reset`

Delete all data for a group to reimport fresh.

```bash
wa-links reset "Group Name" --yes
```

## Link types

| Type | Domains |
|------|---------|
| youtube | youtube.com, youtu.be |
| google_maps | maps.google.com, maps.app.goo.gl |
| document | docs.google.com, drive.google.com |
| instagram | instagram.com |
| twitter | twitter.com, x.com |
| spotify | open.spotify.com, spotify.link |
| reddit | reddit.com |
| linkedin | linkedin.com |
| article | medium.com |
| notion | notion.so |
| github | github.com |
| stackoverflow | stackoverflow.com |
| shopping | amazon.in, amazon.com, flipkart.com |
| food | swiggy.com, zomato.com |
| travel | airbnb.com, tripadvisor.com |
| general | everything else |

### Custom link types

Create a `link_types.json` in your working directory to add or override mappings:

```json
{
  "tiktok.com": "tiktok",
  "www.tiktok.com": "tiktok",
  "substack.com": "newsletter"
}
```

## Domain exclusions

By default, `export` filters out ephemeral/temporary links that clutter exports:

| Category | Domains |
|----------|---------|
| Video calls | meet.google.com, zoom.us, teams.microsoft.com, teams.live.com |
| Email | mail.google.com, outlook.live.com, outlook.office.com |
| URL shorteners | bit.ly, tinyurl.com, t.co, we.tl |

All links are still stored in the database -- exclusions only apply at export time.

### Custom exclusions

Create an `exclusions.json` in your working directory. It's a JSON array of domains to add. Prefix with `!` to remove a built-in default:

```json
[
  "calendly.com",
  "!bit.ly"
]
```

This adds `calendly.com` to the exclusion list and removes `bit.ly` from it.

### Programmatic control

```python
# Default exclusions applied
export_links("Group")

# No exclusions
export_links("Group", exclude_domains=[])

# Custom exclusion list (replaces defaults entirely)
export_links("Group", exclude_domains=["zoom.us", "calendly.com"])
```

## Storage

Data is stored in a SQLite database (WAL mode). Set the path with:

```bash
export WA_LINKS_DB_PATH=/path/to/wa_links.db
```

Defaults to `wa_links.db` in the current directory.

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
