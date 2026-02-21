import json
import os
from importlib import resources
from typing import List
from urllib.parse import urlparse

from wa_link_parser.models import ExtractedLink
from wa_link_parser.normalizer import normalize_url

_DEFAULT_LINK_TYPE_MAP = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "youtu.be": "youtube",
    "maps.google.com": "google_maps",
    "maps.app.goo.gl": "google_maps",
    "goo.gl": "google_maps",
    "docs.google.com": "document",
    "drive.google.com": "document",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "twitter.com": "twitter",
    "www.twitter.com": "twitter",
    "x.com": "twitter",
    "open.spotify.com": "spotify",
    "spotify.link": "spotify",
    "reddit.com": "reddit",
    "www.reddit.com": "reddit",
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
    "medium.com": "article",
    "notion.so": "notion",
    "github.com": "github",
    "www.github.com": "github",
    "stackoverflow.com": "stackoverflow",
    "www.stackoverflow.com": "stackoverflow",
    "amazon.in": "shopping",
    "www.amazon.in": "shopping",
    "amazon.com": "shopping",
    "www.amazon.com": "shopping",
    "flipkart.com": "shopping",
    "www.flipkart.com": "shopping",
    "swiggy.com": "food",
    "www.swiggy.com": "food",
    "zomato.com": "food",
    "www.zomato.com": "food",
    "airbnb.com": "travel",
    "www.airbnb.com": "travel",
    "tripadvisor.com": "travel",
    "www.tripadvisor.com": "travel",
}

# Cached merged map (built-in defaults + user overrides)
_merged_link_type_map = None

_url_extractor = None


def _get_link_type_map():
    """Load and cache the merged link type map.

    Merges built-in defaults with user-provided link_types.json (if found in cwd).
    User config wins on conflict.
    """
    global _merged_link_type_map
    if _merged_link_type_map is not None:
        return _merged_link_type_map

    merged = dict(_DEFAULT_LINK_TYPE_MAP)

    json_path = os.path.join(os.getcwd(), "link_types.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            user_map = json.load(f)
        if isinstance(user_map, dict):
            merged.update(user_map)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    _merged_link_type_map = merged
    return _merged_link_type_map


def reset_link_type_cache():
    """Reset the cached link type map (useful for testing)."""
    global _merged_link_type_map
    _merged_link_type_map = None


def _get_extractor():
    """Lazy-initialize URLExtract (TLD list loading is expensive)."""
    global _url_extractor
    if _url_extractor is None:
        from urlextract import URLExtract
        _url_extractor = URLExtract()
    return _url_extractor


def _normalize_domain(domain):
    """Strip www. prefix for LINK_TYPE_MAP lookup."""
    return domain.lstrip("www.").lstrip(".")


def classify_url(url):
    """Classify a URL by its domain.

    Returns (domain, link_type) where link_type is a category string
    like 'youtube', 'travel', 'shopping', or 'general' for unknown domains.
    """
    link_type_map = _get_link_type_map()

    # Ensure the URL has a scheme for urlparse
    parsed_url = url
    if not url.startswith(("http://", "https://")):
        parsed_url = "https://" + url

    parsed = urlparse(parsed_url)
    domain = parsed.hostname or ""

    # Try direct lookup first (handles subdomains like maps.app.goo.gl)
    if domain in link_type_map:
        return domain, link_type_map[domain]

    # Try with www. stripped
    bare_domain = _normalize_domain(domain)
    if bare_domain in link_type_map:
        return domain, link_type_map[bare_domain]

    return domain, "general"


# Keep backwards-compatible alias
_classify_url = classify_url


def extract_links(text: str) -> List[ExtractedLink]:
    """Extract all URLs from text, normalize them, and classify by domain.

    Returns a list of ExtractedLink objects. Each has:
    - url: normalized form (tracking params stripped, scheme upgraded, domain lowercased)
    - raw_url: original URL as it appeared in the text
    - domain, link_type: from classification

    URLs that normalize to the same canonical form within a single message are
    deduplicated (only the first raw occurrence is kept).
    """
    extractor = _get_extractor()
    urls = extractor.find_urls(text, only_unique=True)

    results = []
    seen_normalized = set()
    for raw_url in urls:
        normalized = normalize_url(raw_url)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        domain, link_type = classify_url(normalized)
        results.append(ExtractedLink(url=normalized, domain=domain, link_type=link_type, raw_url=raw_url))

    return results
