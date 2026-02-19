import csv
import json

from wa_link_parser import db


EXPORT_COLUMNS = ["Sender", "Link", "Title", "Type", "Caption", "Context",
                  "Timestamp", "Domain", "Description"]
EXPORT_KEYS = ["sender", "link", "title", "type", "caption", "context",
               "timestamp", "domain", "description"]


def export_links(group_name, output_path=None, fmt="csv",
                 link_type=None, sender=None, after=None, before=None, domain=None):
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

    if output_path is None:
        safe_name = group_name.replace(" ", "_")
        ext = "json" if fmt == "json" else "csv"
        output_path = f"{safe_name}_links.{ext}"

    if fmt == "json":
        _write_json(links, output_path)
    else:
        _write_csv(links, output_path)

    return output_path, len(links)


def _write_csv(links, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(EXPORT_COLUMNS)

        for link in links:
            writer.writerow([link[k] or "" for k in EXPORT_KEYS])


def _write_json(links, output_path):
    records = []
    for link in links:
        records.append({col: link[key] for col, key in zip(EXPORT_COLUMNS, EXPORT_KEYS)})

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
