# wa-link-parser

[![PyPI version](https://img.shields.io/pypi/v/wa-link-parser)](https://pypi.org/project/wa-link-parser/)
[![Python](https://img.shields.io/pypi/pyversions/wa-link-parser)](https://pypi.org/project/wa-link-parser/)
[![License: MIT](https://img.shields.io/pypi/l/wa-link-parser)](https://github.com/sreeramramasubramanian/wa-link-parser/blob/main/LICENSE)

**Turn WhatsApp chat exports into a searchable link catalog.**

`wa-link-parser` takes a WhatsApp `.txt` export and extracts every URL -- classifying them by domain, fetching page titles and descriptions, and exporting everything to CSV or JSON. Works as a CLI tool or a Python library.

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

## Features

- **Multi-format parsing** -- auto-detects 7 WhatsApp export formats (Indian, US, European, German, and more)
- **TLD-aware URL extraction** -- uses `urlextract`, not naive regex, so it catches real URLs and skips noise
- **Domain classification** -- maps 30+ domains to types like `youtube`, `travel`, `food`, `shopping`, `code`
- **Metadata enrichment** -- fetches page titles and OG descriptions with rate limiting and retry
- **SQLite storage** -- relational model with WAL mode; imports are idempotent via message hashing
- **Filtered export** -- CSV or JSON with filters by sender, date range, link type, and domain
- **Domain exclusions** -- auto-filters ephemeral links (Zoom, Google Meet, bit.ly) at export time
- **CLI + library** -- full Click CLI for quick use, clean Python API with no Click dependency for integration

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

## Quick start

Three commands, and you have a searchable link catalog:

```bash
# 1. Import a chat export
wa-links import chat.txt --group "Goa Trip 2025"

# 2. Enrich links with page titles and descriptions
wa-links enrich "Goa Trip 2025"

# 3. Export to CSV
wa-links export "Goa Trip 2025"
```

That's it. You'll get a CSV file with every link from the chat, classified and enriched.

Need something more specific? Add filters:

```bash
wa-links export "Goa Trip 2025" --type youtube --format json
wa-links export "Goa Trip 2025" --sender "Priya" --after 2025-10-01
wa-links export "Goa Trip 2025" --no-exclude  # include Zoom/Meet links too
```

## Sample output

**CSV** (`wa-links export "Goa Trip 2025"`):

```
sender,date,link,domain,type,title,description,context
Arjun,2025-10-12,https://www.youtube.com/watch?v=K3FnLas09mw,youtube.com,youtube,Best Beaches in South Goa 2025,A complete guide to Goa's hidden beaches...,guys check this out before we finalize
Meera,2025-10-14,https://www.airbnb.co.in/rooms/52841379,airbnb.co.in,travel,Beachside Villa in Palolem,Entire villa · 4 beds · Pool,this one has a pool and is close to the beach
Priya,2025-10-15,https://github.com/sreeramramasubramanian/wa-link-parser,github.com,code,wa-link-parser: Extract links from WhatsApp chats,Python library and CLI for...,use this to save all our links lol
```

**JSON** (`wa-links export "Goa Trip 2025" --format json`):

```json
[
  {
    "sender": "Arjun",
    "date": "2025-10-12",
    "link": "https://www.youtube.com/watch?v=K3FnLas09mw",
    "domain": "youtube.com",
    "type": "youtube",
    "title": "Best Beaches in South Goa 2025",
    "description": "A complete guide to Goa's hidden beaches...",
    "context": "guys check this out before we finalize"
  }
]
```

## Library usage

All library functions work without Click -- use callbacks for progress and interaction.

```python
from wa_link_parser import parse_chat_file, extract_links, fetch_metadata, export_links

# Parse a chat export
messages = parse_chat_file("chat.txt")

# Extract and classify links from messages
for msg in messages:
    links = extract_links(msg.raw_text)
    for link in links:
        print(f"{msg.sender}: {link.url} ({link.link_type})")

# Fetch metadata for a single URL
title, description = fetch_metadata("https://www.youtube.com/watch?v=K3FnLas09mw")

# Export with default exclusions
export_links("Goa Trip 2025")

# Export everything, no exclusions
export_links("Goa Trip 2025", exclude_domains=[])
```

### API reference

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

### Data classes

| Class | Fields |
|-------|--------|
| `ParsedMessage` | `timestamp`, `sender`, `raw_text`, `is_system` |
| `ExtractedLink` | `url`, `domain`, `link_type` |
| `ImportStats` | `new_messages`, `skipped_messages`, `links_extracted`, `contacts_created` |

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

## CLI reference

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

## Configuration

### Link types

Built-in domain-to-type mappings:

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

To add or override mappings, create a `link_types.json` in your working directory:

```json
{
  "tiktok.com": "tiktok",
  "www.tiktok.com": "tiktok",
  "substack.com": "newsletter"
}
```

### Domain exclusions

By default, `export` filters out ephemeral/temporary links that clutter exports:

| Category | Domains |
|----------|---------|
| Video calls | meet.google.com, zoom.us, teams.microsoft.com, teams.live.com |
| Email | mail.google.com, outlook.live.com, outlook.office.com |
| URL shorteners | bit.ly, tinyurl.com, t.co, we.tl |

All links are still stored in the database -- exclusions only apply at export time.

To customize, create an `exclusions.json` in your working directory. It's a JSON array of domains to add. Prefix with `!` to remove a built-in default:

```json
[
  "calendly.com",
  "!bit.ly"
]
```

This adds `calendly.com` to the exclusion list and removes `bit.ly` from it.

Programmatic control:

```python
export_links("Group")                                          # default exclusions
export_links("Group", exclude_domains=[])                      # no exclusions
export_links("Group", exclude_domains=["zoom.us", "calendly.com"])  # custom list
```

## Storage

Data is stored in a SQLite database (WAL mode). Set the path with:

```bash
export WA_LINKS_DB_PATH=/path/to/wa_links.db
```

Defaults to `wa_links.db` in the current directory.

## Development

```bash
pip install -e ".[dev]"
pytest
```

91 tests covering parsing, extraction, classification, enrichment, export, and exclusions. Python 3.10+ required.

## License

MIT
