"""Domain-based exclusion list for filtering links at export time."""

import json
import os
from urllib.parse import urlparse

_DEFAULT_EXCLUDED_DOMAINS = frozenset(
    {
        "meet.google.com",
        "zoom.us",
        "teams.microsoft.com",
        "teams.live.com",
        "mail.google.com",
        "outlook.live.com",
        "outlook.office.com",
    }
)

_cached_excluded_domains = None


def _get_excluded_domains():
    """Load and cache the merged exclusion domain set.

    Merges built-in defaults with user-provided exclusions.json (if found in cwd).
    Entries prefixed with '!' remove that domain from the set.
    """
    global _cached_excluded_domains
    if _cached_excluded_domains is not None:
        return _cached_excluded_domains

    result = set(_DEFAULT_EXCLUDED_DOMAINS)

    json_path = os.path.join(os.getcwd(), "exclusions.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            user_list = json.load(f)
        if isinstance(user_list, list):
            for entry in user_list:
                if not isinstance(entry, str):
                    continue
                if entry.startswith("!"):
                    result.discard(entry[1:])
                else:
                    result.add(entry)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    _cached_excluded_domains = frozenset(result)
    return _cached_excluded_domains


def reset_exclusion_cache():
    """Reset the cached exclusion domain set (useful for testing)."""
    global _cached_excluded_domains
    _cached_excluded_domains = None


def _normalize_domain(domain):
    """Strip leading 'www.' from a domain for comparison."""
    if domain and domain.startswith("www."):
        return domain[4:]
    return domain


def filter_excluded_domains(links, exclude_domains=None):
    """Filter out links whose domain is in the exclusion set.

    Args:
        links: List of link dicts (each must have a 'domain' key).
        exclude_domains: Controls exclusion behavior:
            - None: use default exclusion list (built-in + exclusions.json)
            - []: no exclusions, return all links
            - ["x.com", ...]: use this explicit list instead of defaults

    Returns:
        Filtered list of link dicts.
    """
    if exclude_domains is not None:
        if not exclude_domains:
            return links
        excluded = frozenset(_normalize_domain(d) for d in exclude_domains)
    else:
        excluded = frozenset(_normalize_domain(d) for d in _get_excluded_domains())

    if not excluded:
        return links

    return [
        link
        for link in links
        if _normalize_domain(link["domain"] or "") not in excluded
    ]
