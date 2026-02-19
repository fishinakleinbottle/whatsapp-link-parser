import sys
import time
from typing import Callable, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from wa_link_parser import db

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 10
MAX_TITLE_LEN = 200
MAX_DESC_LEN = 500
RATE_LIMIT_DELAY = 0.5
RETRY_DELAY = 2


def fetch_metadata(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch title and description from a URL via OG tags or <title> fallback.

    Args:
        url: The URL to fetch metadata from.

    Returns:
        Tuple of (title, description), or (None, None) on failure.
    """
    # Ensure URL has a scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    for attempt in range(2):
        try:
            resp = requests.get(
                url,
                timeout=TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try OG tags first
            title = None
            description = None

            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()

            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                description = og_desc["content"].strip()

            # Fallback to <title> tag
            if not title:
                title_tag = soup.find("title")
                if title_tag and title_tag.string:
                    title = title_tag.string.strip()

            # Fallback to meta description
            if not description:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"].strip()

            # Truncate
            if title:
                title = title[:MAX_TITLE_LEN]
            if description:
                description = description[:MAX_DESC_LEN]

            return title, description

        except (requests.RequestException, Exception) as e:
            if attempt == 0:
                time.sleep(RETRY_DELAY)
                continue
            print(f"  Failed to fetch {url}: {e}", file=sys.stderr)
            return None, None

    return None, None


def enrich_links(group_id: int, on_progress: Optional[Callable] = None) -> int:
    """Fetch title + description for all unenriched links in a group.

    Args:
        group_id: The database ID of the group to enrich.
        on_progress: Optional callback called with (current, total) after each link.

    Returns:
        Number of links successfully enriched with metadata.
    """
    links = db.get_unenriched_links(group_id)

    if not links:
        return 0

    enriched_count = 0
    total = len(links)

    for i, link in enumerate(links):
        url = link["url"]

        # Skip non-HTTP URLs
        if not url.startswith(("http://", "https://")) and "." not in url:
            if on_progress:
                on_progress(i + 1, total)
            continue

        title, description = fetch_metadata(url)

        if title or description:
            with db.get_connection() as conn:
                db.update_link_metadata(conn, link["id"], title, description)
            enriched_count += 1
        else:
            # Mark as attempted so we don't retry -- store empty string
            with db.get_connection() as conn:
                db.update_link_metadata(conn, link["id"], title or "", description or "")

        if on_progress:
            on_progress(i + 1, total)

        time.sleep(RATE_LIMIT_DELAY)

    return enriched_count
