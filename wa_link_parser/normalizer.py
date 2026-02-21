"""URL normalization: strip tracking parameters, normalize scheme, sort query params."""

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Known tracking / session parameters that carry no content identity.
TRACKING_PARAMS = frozenset({
    # UTM (Google Analytics)
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
    # Google Ads / Analytics
    "_ga", "_gid", "gclid", "gclsrc", "dclid",
    # Facebook / Instagram
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source", "fb_ref",
    "igshid",
    # Twitter / X
    "twclid",
    # Microsoft Ads
    "msclkid",
    # HubSpot
    "_hsenc", "_hsmi",
    # Mailchimp
    "mc_cid", "mc_eid",
    # Marketo
    "mkt_tok",
    # Spotify share session
    "si",
    # Generic tracking
    "ref", "referral", "trk",
})


def normalize_url(url: str) -> str:
    """Return a normalized, canonical form of the URL.

    Applies the following transformations:
    - Upgrades http:// to https://
    - Lowercases the domain
    - Removes URL fragments (#section)
    - Strips known tracking query parameters
    - Sorts remaining query parameters alphabetically
    - Removes empty query strings (no trailing '?')
    - Non-HTTP schemes (tel:, mailto:, ftp:) are returned unchanged

    If the URL has no scheme, https:// is assumed.
    """
    if not url:
        return url

    # Add scheme if missing so urlparse can parse netloc correctly
    working = url
    if not url.startswith(("http://", "https://", "tel:", "mailto:", "ftp:")):
        working = "https://" + url

    parsed = urlparse(working)

    # Pass through non-HTTP URLs unchanged
    if parsed.scheme not in ("http", "https"):
        return url

    scheme = "https"
    netloc = parsed.netloc.lower()
    path = parsed.path  # path is case-sensitive on many servers, leave as-is

    if parsed.query:
        params = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        params.sort(key=lambda kv: kv[0].lower())
        query = urlencode(params)
    else:
        query = ""

    # fragment is intentionally omitted (stripped)
    return urlunparse((scheme, netloc, path, parsed.params, query, ""))
