import csv

import db


def export_links_to_csv(group_name, output_path=None):
    """Export all links for a group to a CSV file.

    Returns the output file path and number of links exported.
    """
    group = db.get_group_by_name(group_name)
    if not group:
        raise ValueError(f'Group "{group_name}" not found.')

    if output_path is None:
        safe_name = group_name.replace(" ", "_")
        output_path = f"{safe_name}_links.csv"

    links = db.get_links_for_export(group["id"])

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["Sender", "Link", "Type", "Caption", "Timestamp", "Domain"])

        for link in links:
            writer.writerow([
                link["sender"],
                link["link"],
                link["type"],
                link["caption"],
                link["timestamp"],
                link["domain"],
            ])

    return output_path, len(links)
