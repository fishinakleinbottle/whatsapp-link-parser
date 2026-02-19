from typing import List
from urllib.parse import urlparse

from models import ExtractedLink

LINK_TYPE_MAP = {
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

_url_extractor = None


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


def _classify_url(url):
    """Classify a URL by its domain. Returns (domain, link_type)."""
    # Ensure the URL has a scheme for urlparse
    parsed_url = url
    if not url.startswith(("http://", "https://")):
        parsed_url = "https://" + url

    parsed = urlparse(parsed_url)
    domain = parsed.hostname or ""

    # Try direct lookup first (handles subdomains like maps.app.goo.gl)
    if domain in LINK_TYPE_MAP:
        return domain, LINK_TYPE_MAP[domain]

    # Try with www. stripped
    bare_domain = _normalize_domain(domain)
    if bare_domain in LINK_TYPE_MAP:
        return domain, LINK_TYPE_MAP[bare_domain]

    return domain, "general"


def extract_links(text: str) -> List[ExtractedLink]:
    """Extract all URLs from text and classify them."""
    extractor = _get_extractor()
    urls = extractor.find_urls(text, only_unique=True)

    results = []
    for url in urls:
        domain, link_type = _classify_url(url)
        results.append(ExtractedLink(url=url, domain=domain, link_type=link_type))

    return results
