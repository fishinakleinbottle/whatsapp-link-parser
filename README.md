# wa-link-parser

Extract, classify, and enrich links from WhatsApp chat exports.

`wa-link-parser` takes a WhatsApp `.txt` export and turns it into a searchable, filterable link catalog. It parses messages, extracts URLs, classifies them by domain (YouTube, Maps, Reddit, etc.), fetches page titles and descriptions, and exports everything to CSV or JSON.

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

## Quick start

### As a CLI

```bash
# Import a chat export
wa-links import chat.txt --group "Bali Trip"

# Enrich links with page titles and descriptions
wa-links enrich "Bali Trip"

# Export to CSV
wa-links export "Bali Trip"

# Export filtered results
wa-links export "Bali Trip" --type youtube --format json
wa-links export "Bali Trip" --sender "Priya" --after 2025-10-01

# View stats
wa-links stats "Bali Trip"
```

### As a library

```python
from wa_link_parser import parse_chat_file, extract_links, fetch_metadata

# Parse a chat export
messages = parse_chat_file("chat.txt")

# Extract links from a message
for msg in messages:
    links = extract_links(msg.raw_text)
    for link in links:
        print(f"{msg.sender}: {link.url} ({link.link_type})")

# Fetch metadata for a URL
title, description = fetch_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
```

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

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
