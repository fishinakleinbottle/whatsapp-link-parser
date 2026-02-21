# whatsapp-link-parser

[![PyPI version](https://img.shields.io/pypi/v/whatsapp-link-parser)](https://pypi.org/project/whatsapp-link-parser/)
[![Python](https://img.shields.io/pypi/pyversions/whatsapp-link-parser)](https://pypi.org/project/whatsapp-link-parser/)
[![License: MIT](https://img.shields.io/pypi/l/whatsapp-link-parser)](https://github.com/sreeramramasubramanian/whatsapp-link-parser/blob/main/LICENSE)

Extract, classify, and enrich links from WhatsApp chat exports. Works as a CLI tool or a Python library.

```
Raw .txt → Parse → Extract → Classify → Enrich → Export (CSV/JSON)
```

## Installation

```bash
pip install whatsapp-link-parser
```

## Quick start

The CLI is available as both `whatsapp-links` and `wa-links`.

```bash
wa-links import chat.txt --group "Goa Trip 2025"
wa-links enrich "Goa Trip 2025"
wa-links export "Goa Trip 2025"
```

Output CSV:

```
sender,date,link,domain,type,title,description,context
Arjun,2025-10-12,https://www.youtube.com/watch?v=K3FnLas09mw,youtube.com,youtube,Best Beaches in South Goa 2025,...
Meera,2025-10-14,https://www.airbnb.co.in/rooms/52841379,airbnb.co.in,travel,Beachside Villa in Palolem,...
```

## CLI reference

```bash
wa-links import <file> --group "Name"      # import a chat export
wa-links enrich "Name"                     # fetch page titles and descriptions
wa-links export "Name"                     # export to CSV
wa-links stats "Name"                      # show statistics
wa-links groups                            # list imported groups
wa-links contacts "Name" [--resolve]       # list or resolve contacts
wa-links reset "Name" --yes                # delete all data for a group
```

Export filters:

```bash
wa-links export "Name" --type youtube --format json
wa-links export "Name" --sender "Alice" --after 2025-10-01 --before 2025-11-01
wa-links export "Name" --domain airbnb
wa-links export "Name" --no-exclude        # include Zoom/Meet links too
```

| Flag | Description |
|------|-------------|
| `--output` | Output file path |
| `--type` | Filter by link type (`youtube`, `travel`, `food`, ...) |
| `--sender` | Filter by sender name (substring match) |
| `--after` / `--before` | Date range (`YYYY-MM-DD`) |
| `--domain` | Filter by domain (substring match) |
| `--format` | `csv` (default) or `json` |
| `--no-exclude` | Disable default domain exclusions |

## Library usage

```python
from wa_link_parser import parse_chat_file, extract_links, fetch_metadata, export_links

messages = parse_chat_file("chat.txt")
for msg in messages:
    for link in extract_links(msg.raw_text):
        print(f"{msg.sender}: {link.url} ({link.link_type})")

title, description = fetch_metadata("https://example.com")

export_links("Goa Trip 2025")                                      # default exclusions
export_links("Goa Trip 2025", exclude_domains=[])                  # no exclusions
export_links("Goa Trip 2025", exclude_domains=["zoom.us"])         # custom list
```

| Function | Description |
|----------|-------------|
| `parse_chat_file(path)` | Parse a `.txt` export → `ParsedMessage` list |
| `extract_links(text)` | Extract URLs from text → `ExtractedLink` list |
| `classify_url(url)` | Classify a URL by domain → link type string |
| `fetch_metadata(url)` | Fetch page title and OG description |
| `enrich_links(group_id)` | Enrich all unenriched links for a group |
| `export_links(group, ...)` | Export with filters and exclusions |
| `filter_excluded_domains(links, ...)` | Filter by domain exclusion list |
| `reset_exclusion_cache()` | Clear cached exclusions (for testing) |

Data classes: `ParsedMessage` (`timestamp`, `sender`, `raw_text`, `is_system`), `ExtractedLink` (`url`, `domain`, `link_type`), `ImportStats`.

## Configuration

### Link types

Create `link_types.json` in your working directory to add or override domain mappings:

```json
{
  "tiktok.com": "tiktok",
  "substack.com": "newsletter"
}
```

Built-in types: `youtube`, `google_maps`, `document`, `instagram`, `twitter`, `spotify`, `reddit`, `linkedin`, `article`, `notion`, `github`, `stackoverflow`, `shopping`, `food`, `travel`, `general`.

### Domain exclusions

`export` filters out ephemeral links by default (video calls, email, URL shorteners). Override with `exclusions.json` in your working directory:

```json
["calendly.com", "!bit.ly"]
```

Prefix with `!` to remove a built-in default. All links are still stored in the database — exclusions only apply at export time.

## Supported formats

The parser auto-detects 7 WhatsApp export formats:

| Format | Example |
|--------|---------|
| Indian (bracket, tilde) | `[20/10/2025, 10:29:01 AM] ~ Sender: text` |
| US (bracket, short year) | `[1/15/25, 3:45:30 PM] Sender: text` |
| International (no bracket, 24h) | `20/10/2025, 14:30 - Sender: text` |
| US (no bracket, 12h) | `1/15/25, 3:45 PM - Sender: text` |
| European (short year, 24h) | `20/10/25, 14:30 - Sender: text` |
| German (dots) | `20.10.25, 14:30 - Sender: text` |
| Bracket (no tilde, full year) | `[20/10/2025, 10:29:01 AM] Sender: text` |

## Storage

SQLite (WAL mode). Defaults to `wa_links.db` in the current directory; override with:

```bash
export WA_LINKS_DB_PATH=/path/to/wa_links.db
```

Imports are idempotent — reimporting the same file won't create duplicates.

## License

MIT License

Copyright (c) 2025 Sreeram Ramasubramanian

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
