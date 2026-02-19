"""wa-link-parser: Extract, classify, and enrich links from WhatsApp chat exports."""

from wa_link_parser.models import ParsedMessage, ExtractedLink, ImportStats
from wa_link_parser.parser import parse_chat_file
from wa_link_parser.extractor import extract_links, classify_url
from wa_link_parser.enricher import fetch_metadata, enrich_links
from wa_link_parser.exporter import export_links

__version__ = "0.2.0"

__all__ = [
    "parse_chat_file",
    "extract_links",
    "classify_url",
    "fetch_metadata",
    "enrich_links",
    "export_links",
    "ParsedMessage",
    "ExtractedLink",
    "ImportStats",
]
