from dataclasses import dataclass, field
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


@dataclass
class ImportStats:
    """Summary of an import operation."""
    new_messages: int = 0
    skipped_messages: int = 0
    links_extracted: int = 0
    contacts_created: int = 0
