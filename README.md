# wa-link-parser

Extract, classify, and enrich links from WhatsApp chat exports.

Parses WhatsApp `.txt` exports, extracts URLs, classifies them by domain (YouTube, Google Maps, Reddit, etc.), resolves contacts with fuzzy matching, and exports enriched link tables to CSV or JSON. All data is stored in a local SQLite database (`wa_links.db`).

## Setup

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Import a chat export
python wa_links.py import sample_data/sample_chat.txt --group "Bali Trip"

# Enrich links with page titles and descriptions
python wa_links.py enrich "Bali Trip"

# Export to CSV (now includes Title, Description, Context columns)
python wa_links.py export "Bali Trip"

# View stats
python wa_links.py stats "Bali Trip"
```

## Commands

### `import`

Import a WhatsApp chat export file.

```bash
python wa_links.py import <file> --group "Group Name"
python wa_links.py import <file> --group "Group Name" --enrich
```

If `--group` is omitted, you'll be prompted to select an existing group or create a new one.

Use `--enrich` to automatically fetch link metadata (titles/descriptions) after import.

- Deduplicates on reimport (idempotent) — running the same file twice produces 0 new messages
- Resolves contacts with fuzzy matching on subsequent imports
- Extracts and classifies links automatically
- Builds context from adjacent messages by the same sender (within 60s)

### `enrich`

Fetch page titles and descriptions for links that haven't been enriched yet. Results are stored in the database — re-export to see them in your CSV/JSON.

```bash
python wa_links.py enrich "Group Name"
```

- Extracts `og:title` and `og:description` meta tags, falls back to `<title>` tag
- Rate-limited (2 req/sec) with retry on failure
- Progress bar shows enrichment status
- Only fetches metadata for links not yet enriched — safe to run multiple times

### `export`

Export links to CSV or JSON with optional filters.

```bash
python wa_links.py export "Group Name"
python wa_links.py export "Group Name" --format json
python wa_links.py export "Group Name" --type youtube
python wa_links.py export "Group Name" --sender "Narendra" --after 2025-10-01
python wa_links.py export "Group Name" --domain reddit.com
python wa_links.py export "Group Name" --output my_links.csv
```

**Options:**

| Flag | Description |
|------|-------------|
| `--output` | Output file path (default: `<Group_Name>_links.csv`) |
| `--type` | Filter by link type (e.g., `youtube`, `travel`, `shopping`) |
| `--sender` | Filter by sender name (substring match) |
| `--after` | Only links after this date (`YYYY-MM-DD`) |
| `--before` | Only links before this date (`YYYY-MM-DD`) |
| `--domain` | Filter by domain (substring match) |
| `--format` | `csv` (default) or `json` |

**CSV columns:** Sender, Link, Title, Type, Caption, Context, Timestamp, Domain, Description

### `stats`

Show group statistics: message counts, top sharers, link types, and top domains.

```bash
python wa_links.py stats "Group Name"
```

Example output:

```
Group: Bali Trip
  Messages: 27 (3 system)
  Links: 10
  Contacts: 4

Top sharers:
  Narendra Shenoy    5 links
  Burhan Yousuf      2 links

Link types:
  travel       3
  youtube      1
  shopping     1

Top domains:
  www.youtube.com     1
  maps.app.goo.gl     1
```

### `reset`

Delete all data for a group (messages, links, contacts) so it can be reimported fresh. Useful when you want to repopulate enrichment data or context.

```bash
python wa_links.py reset "Group Name"
python wa_links.py reset "Group Name" --yes   # skip confirmation
```

### `groups`

List all imported groups with message, link, and contact counts.

```bash
python wa_links.py groups
```

### `contacts`

List or interactively resolve contacts for a group.

```bash
python wa_links.py contacts "Group Name"
python wa_links.py contacts "Group Name" --resolve
```

Use `--resolve` to interactively merge or rename unresolved contacts.

## Typical Workflow

```bash
# 1. Import your chat export
python wa_links.py import sample_data/sample_chat.txt --group "Bali Trip"

# 2. Enrich links with titles and descriptions
python wa_links.py enrich "Bali Trip"

# 3. Export the enriched data
python wa_links.py export "Bali Trip"

# 4. If you need to start over (e.g., to rebuild context)
python wa_links.py reset "Bali Trip"
python wa_links.py import sample_data/sample_chat.txt --group "Bali Trip" --enrich
python wa_links.py export "Bali Trip"
```

## Project Structure

```
wa-link-parser/
  wa_links.py          # CLI entry point (all commands)
  parser.py            # WhatsApp chat file parsing (regex + whatstk fallback)
  extractor.py         # URL extraction and domain-based classification
  enricher.py          # Fetch page titles/descriptions for links
  exporter.py          # CSV and JSON export with filtering
  db.py                # SQLite database schema, migrations, and queries
  models.py            # Data classes (ParsedMessage, ExtractedLink, ImportStats)
  contact_resolver.py  # Fuzzy contact matching and interactive resolution
  link_types.json      # Domain-to-type mapping (user-customizable)
  requirements.txt     # Python dependencies
  pyproject.toml       # Package metadata
  sample_data/         # Sample WhatsApp chat exports for testing
  tests/               # Test suite (pytest)
```

## Link Types

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

## Customizing Link Types

Create or edit `link_types.json` in your working directory to add or override domain mappings:

```json
{
  "tiktok.com": "tiktok",
  "www.tiktok.com": "tiktok",
  "substack.com": "newsletter"
}
```

User mappings are merged with built-in defaults (user config wins on conflict).

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```
