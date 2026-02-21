import csv
import json

from wa_link_parser import db
from wa_link_parser.exclusions import filter_excluded_domains


EXPORT_COLUMNS = ["Sender", "Link", "Title", "Type", "Caption", "Context",
                  "Timestamp", "Domain", "Description"]
EXPORT_KEYS = ["sender", "link", "title", "type", "caption", "context",
               "timestamp", "domain", "description"]

DEDUP_EXTRA_COLUMN = "Times Shared"


def export_links(group_name, output_path=None, fmt="csv",
                 link_type=None, sender=None, after=None, before=None, domain=None,
                 exclude_domains=None, dedup=False):
    """Export links for a group to CSV or JSON, with optional filters.

    Args:
        group_name: Name of the WhatsApp group.
        output_path: Output file path (auto-generated if None).
        fmt: Output format, 'csv' or 'json'.
        link_type: Filter by link type (e.g., 'youtube').
        sender: Filter by sender name (substring match).
        after: Filter links after this date (YYYY-MM-DD).
        before: Filter links before this date (YYYY-MM-DD).
        domain: Filter by domain (substring match).
        exclude_domains: Controls domain exclusion:
            - None: use default exclusion list (built-in + exclusions.json)
            - []: no exclusions, export all links
            - ["x.com", ...]: use this explicit list
        dedup: If True, deduplicate by normalized URL. Keeps the most recently
            shared occurrence of each URL and adds a 'Times Shared' column
            showing how many times that URL appeared in the result set.

    Returns:
        Tuple of (output_path, count) where count is number of links exported.
    """
    group = db.get_group_by_name(group_name)
    if not group:
        raise ValueError(f'Group "{group_name}" not found.')

    has_filters = any(v is not None for v in (link_type, sender, after, before, domain))

    if has_filters:
        links = db.get_links_for_export_filtered(
            group["id"],
            link_type=link_type,
            sender=sender,
            after=after,
            before=before,
            domain=domain,
        )
    else:
        links = db.get_links_for_export(group["id"])

    links = filter_excluded_domains(links, exclude_domains)

    counts = None
    if dedup:
        links, counts = _dedup_links(links)

    if output_path is None:
        safe_name = group_name.replace(" ", "_")
        ext = "json" if fmt == "json" else "csv"
        output_path = f"{safe_name}_links.{ext}"

    if fmt == "json":
        _write_json(links, output_path, counts=counts)
    else:
        _write_csv(links, output_path, counts=counts)

    return output_path, len(links)


def _dedup_links(links):
    """Deduplicate links by URL.

    Iterates in query order (newest-first). Keeps the first occurrence of each
    URL encountered (most recently shared). Counts all occurrences of each URL.

    Returns:
        (deduped_links, counts) where counts maps url -> times_shared.
    """
    seen = {}   # url -> first (most recent) link row
    counts = {}

    for link in links:
        url = link["link"]
        counts[url] = counts.get(url, 0) + 1
        if url not in seen:
            seen[url] = link

    return list(seen.values()), counts


def _write_csv(links, output_path, counts=None):
    columns = EXPORT_COLUMNS + ([DEDUP_EXTRA_COLUMN] if counts is not None else [])
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(columns)

        for link in links:
            row = [link[k] or "" for k in EXPORT_KEYS]
            if counts is not None:
                row.append(counts.get(link["link"], 1))
            writer.writerow(row)


def _write_json(links, output_path, counts=None):
    records = []
    for link in links:
        record = {col: link[key] for col, key in zip(EXPORT_COLUMNS, EXPORT_KEYS)}
        if counts is not None:
            record[DEDUP_EXTRA_COLUMN] = counts.get(link["link"], 1)
        records.append(record)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
