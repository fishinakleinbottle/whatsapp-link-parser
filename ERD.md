# WhatsApp Group Link Extractor — CLI Tool

## Project Overview

A Python CLI tool that parses WhatsApp group chat exports (`.txt` files), stores structured message data in SQLite, extracts all shared links with metadata, and exports them to CSV. Designed for repeated use — importing new chat dumps into the same group without duplicating data, and handling contact name changes gracefully.

The end goal is a clean CSV (or eventually Notion database) of every link shared in a WhatsApp group, with sender, link type, caption, and original message context.

---

## Tech Stack & Dependencies

- **Python 3.10+**
- **SQLite** via `sqlite3` (stdlib) — no ORM, keep it simple with raw SQL and a clean db module
- **`whatstk`** — WhatsApp chat parser (handles format variations across OS/locale)
- **`urlextract`** — robust URL extraction from message text
- **`click`** — CLI framework for commands and interactive prompts
- **`csv`** (stdlib) — export
- **No web framework, no ORM, no async** — this is a straightforward CLI tool

Pin all dependencies in `requirements.txt` with exact versions.

---

## Database Schema

Use SQLite. Store the DB file as `wa_links.db` in the project root (configurable via env var `WA_LINKS_DB_PATH`).

### Tables

```sql
-- Top-level group container
CREATE TABLE IF NOT EXISTS whatsapp_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A person in one or more groups
-- canonical_name is the "real" name we've resolved to
-- display_name is the name as it appeared in the chat export
CREATE TABLE IF NOT EXISTS contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Junction: a contact can appear in multiple groups under different display names
CREATE TABLE IF NOT EXISTS contact_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contact(id),
    group_id INTEGER NOT NULL REFERENCES whatsapp_group(id),
    display_name TEXT NOT NULL,
    UNIQUE(group_id, display_name)
);

-- Individual message from a chat export
CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES whatsapp_group(id),
    contact_id INTEGER NOT NULL REFERENCES contact(id),
    timestamp TIMESTAMP NOT NULL,
    raw_text TEXT NOT NULL,
    message_hash TEXT NOT NULL UNIQUE,  -- SHA256(timestamp_iso + sender_display + raw_text)
    is_system_message BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- A link extracted from a message
CREATE TABLE IF NOT EXISTS link (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES message(id),
    url TEXT NOT NULL,
    domain TEXT,              -- extracted domain e.g. "youtube.com"
    link_type TEXT,           -- classified type: youtube, google_maps, document, instagram, twitter, news, general
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_id, url)   -- same link in same message = one record
);
```

### Important Schema Notes

- `message_hash` is the idempotency key. Before inserting any message, check if the hash exists. If it does, skip silently. This makes re-importing the same (or overlapping) chat export safe.
- Hash formula: `SHA256(timestamp_iso_string + "|" + sender_display_name_as_in_export + "|" + raw_text)`
- System messages (e.g., "X added Y", "Messages and calls are end-to-end encrypted") should be stored with `is_system_message = TRUE` and no contact association (use a sentinel contact or NULL — prefer a sentinel contact named `__system__`).

---

## CLI Commands

Use `click` with a group of subcommands. The entry point is `wa_links.py`.

### 1. `import` — Import a chat export

```
python wa_links.py import <file_path> [--group <group_name>]
```

**Behavior:**

1. If `--group` is provided, use that group (create if new).
2. If `--group` is not provided, list existing groups from the DB and prompt:
   - Show numbered list of existing groups
   - Option to create a new group (prompt for name)
3. Parse the `.txt` file using `whatstk` to extract structured messages (timestamp, sender, text).
4. For each unique sender name in the export:
   - Check if `display_name` exists in `contact_alias` for this group.
   - If yes → map to existing contact. No prompt needed.
   - If no → **Contact Resolution Flow** (see below).
5. For each message:
   - Compute `message_hash`.
   - If hash exists in DB → skip (idempotent).
   - If new → insert message, then extract and store links.
6. Print summary: X new messages imported, Y duplicates skipped, Z links extracted.

**Contact Resolution Flow (for unrecognized display names):**

When a new display name is encountered for a group:

```
New contact found: "Naren Shenoy"

This name doesn't match any existing contacts in group "Bali Trip".
Existing contacts in this group:
  1. Narendra Shenoy
  2. Burhan Yousuf
  3. Priya Sharma

Options:
  [1-3] This is the same person as #N (alias will be saved)
  [n]   This is a new person
  [s]   Skip for now (messages will be stored, contact resolved later)

Choice:
```

- If user picks an existing contact → create a `contact_alias` row mapping the new display name to that contact.
- If user picks "new" → create a new `contact` with `canonical_name = display_name`, and a `contact_alias` row.
- If user picks "skip" → create a temporary contact, flag for later resolution (add a `resolved BOOLEAN DEFAULT TRUE` column to `contact` — set to FALSE for skipped ones).

**For the first import into a new group**, every sender is new. Don't prompt for each — just auto-create contacts and aliases. Only prompt during subsequent imports when new names appear AND existing contacts exist in the group.

### 2. `export` — Export links to CSV

```
python wa_links.py export <group_name> [--output <file_path>]
```

**Behavior:**

1. Query all links for the given group, joined with message and contact data.
2. Output CSV with columns:
   - `Sender` — contact's `canonical_name`
   - `Link` — full URL
   - `Type` — classified link type
   - `Caption` — the full message text that contained the link (this serves as context/caption)
   - `Timestamp` — when the message was sent
   - `Domain` — extracted domain
3. Default output file: `{group_name}_links.csv` in current directory.
4. Sort by timestamp descending (most recent first).

### 3. `groups` — List all groups

```
python wa_links.py groups
```

Shows all groups with message count and link count.

### 4. `contacts` — List/manage contacts for a group

```
python wa_links.py contacts <group_name>
```

Shows all contacts in the group with their aliases. Optionally add `--resolve` flag to go through unresolved contacts interactively.

---

## Parsing Logic

### WhatsApp Export Format

The primary format to support (based on the user's sample):

```
[DD/MM/YYYY, HH:MM:SS AM/PM] ~ Sender Name: Message text
```

**Use `whatstk` for parsing.** It handles:
- Bracket vs no-bracket timestamps
- 12h vs 24h time formats
- DD/MM vs MM/DD date formats
- Multi-line messages

**If `whatstk` fails** to auto-detect the format, fall back to a custom regex parser targeting the exact format above:

```python
pattern = r'\[(\d{2}/\d{2}/\d{4}),\s(\d{1,2}:\d{2}:\d{2}\s[AP]M)\]\s~\s(.+?):\s(.+)'
```

Handle multi-line messages: if a line doesn't match the message pattern, it's a continuation of the previous message — append to previous message's raw_text.

### System Messages

Detect system messages (no sender/colon pattern):
- "Messages and calls are end-to-end encrypted"
- "X added Y"
- "X left"
- "X changed the group description"
- "Your security code with X changed"

Store these with `is_system_message = TRUE`. Don't extract links from system messages.

### Link Extraction

Use `urlextract` to pull URLs from message text. For each URL:

1. Extract domain using `urllib.parse.urlparse`.
2. Classify link type based on domain mapping:

```python
LINK_TYPE_MAP = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "maps.google.com": "google_maps",
    "maps.app.goo.gl": "google_maps",
    "goo.gl/maps": "google_maps",
    "docs.google.com": "document",
    "drive.google.com": "document",
    "instagram.com": "instagram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "open.spotify.com": "spotify",
    "spotify.link": "spotify",
    "reddit.com": "reddit",
    "linkedin.com": "linkedin",
    "medium.com": "article",
    "notion.so": "notion",
    "github.com": "github",
    "stackoverflow.com": "stackoverflow",
    "amazon.in": "shopping",
    "amazon.com": "shopping",
    "flipkart.com": "shopping",
    "swiggy.com": "food",
    "zomato.com": "food",
}
# Default: "general"
```

3. Store each unique (message_id, url) pair in the `link` table.

### Caption Logic

The "caption" for a link is the full `raw_text` of the message it was found in. In WhatsApp, people often send a link followed by a separate message explaining it. For v1, just use the message containing the link as the caption. Don't try to associate adjacent messages — that's a v2 feature.

---

## Project Structure

```
wa-link-extractor/
├── CLAUDE.md              # This file — project requirements and context
├── README.md              # User-facing docs: setup, usage, examples
├── requirements.txt       # Pinned dependencies
├── wa_links.py            # CLI entry point (click app)
├── db.py                  # Database initialization, connection, queries
├── parser.py              # Chat file parsing logic (whatstk + fallback regex)
├── extractor.py           # Link extraction and classification
├── models.py              # Pure data classes (dataclasses) for Message, Contact, Link, Group
├── contact_resolver.py    # Interactive contact matching logic
├── exporter.py            # CSV export logic
├── sample_data/           # Sample WhatsApp export for testing
│   └── sample_chat.txt
└── tests/
    ├── test_parser.py     # Test parsing with various WhatsApp formats
    ├── test_extractor.py  # Test link extraction and classification
    └── test_idempotency.py # Test that reimporting doesn't duplicate
```

### Why this structure (not one monolith):

- `db.py` is isolated so schema changes are in one place
- `parser.py` can be swapped if WhatsApp changes format or we add Signal/Telegram support
- `models.py` uses `@dataclass` — no ORM, just clean typed containers that flow between modules
- `contact_resolver.py` encapsulates the interactive prompting — easy to replace with a web UI later

---

## Data Classes (models.py)

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ParsedMessage:
    """Output of the parser — not yet in DB."""
    timestamp: datetime
    sender: str          # display name as in export
    raw_text: str
    is_system: bool = False

@dataclass
class ExtractedLink:
    """A link found in a message."""
    url: str
    domain: str
    link_type: str       # from LINK_TYPE_MAP or "general"
```

---

## Key Behavioral Requirements

### Idempotency
- The `message_hash` (SHA256 of timestamp + sender + text) is the single source of truth for deduplication.
- Re-importing the same file or an overlapping file must produce zero duplicates.
- Links are keyed on (message_id, url) — also idempotent.

### Error Handling
- If the file can't be parsed, print a clear error with the first few lines of the file and suggest checking the format.
- If the DB is locked (rare with SQLite), retry with a short delay.
- Wrap the entire import in a transaction — if anything fails, roll back cleanly.

### Performance
- Batch inserts where possible (use `executemany`).
- For a typical WhatsApp export (5k-50k messages), this should complete in under 30 seconds.

### Output Quality
- CSV should be clean and directly importable to Notion, Google Sheets, or Excel.
- Use UTF-8 encoding with BOM for Excel compatibility.
- Escape/quote fields properly (use `csv.writer` with `QUOTE_ALL`).

---

## Sample Usage Flow

```bash
# First time: import a chat export
python wa_links.py import ~/Downloads/WhatsApp\ Chat\ -\ Bali\ Trip.txt
# → Prompts to select/create group
# → Auto-creates all contacts (first import)
# → Prints: "Imported 2,847 messages, extracted 156 links"

# Export links to CSV
python wa_links.py export "Bali Trip"
# → Creates Bali_Trip_links.csv

# Later: import newer export from same group
python wa_links.py import ~/Downloads/WhatsApp\ Chat\ -\ Bali\ Trip_2.txt --group "Bali Trip"
# → Skips existing messages, imports only new ones
# → Prompts for any new contact names: "Naren" might be "Narendra Shenoy"
# → Prints: "Imported 312 new messages (2,847 skipped), extracted 23 new links"

# Check groups
python wa_links.py groups
# → Bali Trip: 3,159 messages, 179 links, 12 contacts
```

---

## Out of Scope for v1

- No web UI (CLI only)
- No Notion API integration (manual CSV import for now)
- No link preview fetching (no HTTP requests to resolve titles/thumbnails)
- No adjacent-message caption stitching
- No media message handling (images, videos, voice notes — just log as system-type)
- No multi-language support for system messages (English only)
- No fuzzy contact name matching (exact match only, manual resolution via prompt)

---

## Testing Requirements

Include tests for:

1. **Parser tests** — Parse the sample chat format, verify correct timestamp/sender/text extraction. Test multi-line messages. Test system message detection.
2. **Extractor tests** — Verify URL extraction from various message formats. Verify link type classification for all mapped domains. Verify "general" fallback.
3. **Idempotency tests** — Import same file twice, verify message count doesn't change. Import overlapping file, verify only new messages are added.
4. **Contact resolution tests** — Verify auto-create on first import. Verify prompt triggers on subsequent import with new name.

Use `pytest`. Include the sample chat data as a fixture.
