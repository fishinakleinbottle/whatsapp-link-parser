import click

from wa_link_parser import db
from wa_link_parser.contact_resolver import (
    find_similar_contacts,
    resolve_contacts_for_import,
)
from wa_link_parser.enricher import enrich_links
from wa_link_parser.exporter import export_links
from wa_link_parser.extractor import extract_links
from wa_link_parser.models import ImportStats
from wa_link_parser.parser import parse_chat_file


def _build_context(messages, idx, time_window=60):
    """Gather adjacent messages from same sender within time_window seconds.

    Looks backward and forward from the message at idx for messages from the
    same sender within the time window. Returns concatenated text separated by ' | '.
    """
    target = messages[idx]
    parts = []

    # Look backward
    for i in range(idx - 1, -1, -1):
        msg = messages[i]
        if msg.is_system:
            continue
        delta = abs((target.timestamp - msg.timestamp).total_seconds())
        if delta > time_window:
            break
        if msg.sender == target.sender:
            parts.insert(0, msg.raw_text.strip())

    # Current message
    parts.append(target.raw_text.strip())

    # Look forward
    for i in range(idx + 1, len(messages)):
        msg = messages[i]
        if msg.is_system:
            continue
        delta = abs((msg.timestamp - target.timestamp).total_seconds())
        if delta > time_window:
            break
        if msg.sender == target.sender:
            parts.append(msg.raw_text.strip())

    return " | ".join(parts)


def _click_prompt_for_contact(display_name, similar):
    """Interactive contact resolution prompt using Click.

    Returns contact_id to merge with, None to create new, or 'skip'.
    """
    click.echo(f'\nNew contact found: "{display_name}"')
    click.echo("Similar existing contacts:")

    for i, (score, contact) in enumerate(similar, 1):
        pct = int(score * 100)
        click.echo(f"  {i}. {contact['canonical_name']} ({pct}% match)")

    click.echo(f"\nOptions:")
    click.echo(f"  [1-{len(similar)}] This is the same person as #N")
    click.echo(f"  [n]   This is a new person")
    click.echo(f"  [s]   Skip for now")

    while True:
        choice = click.prompt("Choice", type=str).strip().lower()

        if choice == "n":
            return None

        if choice == "s":
            return "skip"

        try:
            idx = int(choice)
            if 1 <= idx <= len(similar):
                return similar[idx - 1][1]["id"]
        except ValueError:
            pass

        click.echo("Invalid choice, please try again.")


@click.group()
def cli():
    """WhatsApp Group Link Extractor CLI."""
    db.init_db()


@cli.command("import")
@click.argument("file_path")
@click.option("--group", "group_name", default=None, help="Group name (creates if new)")
@click.option("--enrich", "do_enrich", is_flag=True, help="Enrich links after import")
def import_chat(file_path, group_name, do_enrich):
    """Import a WhatsApp chat export file."""
    # Resolve group
    if group_name is None:
        groups = db.list_groups()
        if groups:
            click.echo("Existing groups:")
            for i, g in enumerate(groups, 1):
                click.echo(f"  {i}. {g['name']} ({g['message_count']} messages)")
            click.echo(f"  {len(groups) + 1}. Create new group")

            choice = click.prompt("Select group", type=int)
            if 1 <= choice <= len(groups):
                group_name = groups[choice - 1]["name"]
            else:
                group_name = click.prompt("Enter new group name")
        else:
            group_name = click.prompt("Enter group name")

    group_id = db.get_or_create_group(group_name)

    # Parse file
    click.echo(f"Parsing {file_path}...")
    messages = parse_chat_file(file_path)
    click.echo(f"Found {len(messages)} messages in export.")

    # Collect unique sender names (excluding system)
    sender_names = list(dict.fromkeys(
        m.sender for m in messages if not m.is_system
    ))

    stats = ImportStats()

    with db.get_connection() as conn:
        # Resolve contacts
        contact_map = resolve_contacts_for_import(
            group_id, sender_names, conn,
            prompt_fn=_click_prompt_for_contact,
        )
        system_contact_id = db.get_system_contact_id(conn)

        # Import messages with progress bar
        with click.progressbar(messages, label="Importing", show_pos=True) as bar:
            for idx, msg in enumerate(bar):
                timestamp_iso = msg.timestamp.isoformat()
                message_hash = db.compute_message_hash(timestamp_iso, msg.sender, msg.raw_text)

                if db.message_hash_exists(conn, message_hash):
                    stats.skipped_messages += 1
                    continue

                if msg.is_system:
                    contact_id = system_contact_id
                else:
                    contact_id = contact_map[msg.sender]

                message_id = db.insert_message(
                    conn, group_id, contact_id, timestamp_iso,
                    msg.raw_text, message_hash, msg.is_system
                )
                stats.new_messages += 1

                # Extract and store links (skip system messages)
                if not msg.is_system:
                    links = extract_links(msg.raw_text)
                    if links:
                        context = _build_context(messages, idx)
                        link_rows = [
                            (message_id, link.url, link.domain, link.link_type, context, link.raw_url)
                            for link in links
                        ]
                        db.insert_links_batch(conn, link_rows)
                        stats.links_extracted += len(links)

    click.echo(f"\nImport complete for group \"{group_name}\":")
    click.echo(f"  {stats.new_messages} new messages imported")
    click.echo(f"  {stats.skipped_messages} duplicates skipped")
    click.echo(f"  {stats.links_extracted} links extracted")

    if do_enrich:
        click.echo()
        _enrich_with_progress(group_id)


def _enrich_with_progress(group_id):
    """Enrich links with a Click progress bar."""
    links = db.get_unenriched_links(group_id)
    if not links:
        click.echo("No unenriched links found.")
        return 0

    bar = click.progressbar(length=len(links), label="Enriching", show_pos=True)
    enriched = [0]

    def on_progress(current, total):
        bar.update(1)

    with bar:
        enriched_count = enrich_links(group_id, on_progress=on_progress)

    click.echo(f"  {enriched_count} links enriched with metadata")
    return enriched_count


@cli.command("enrich")
@click.argument("group_name")
def enrich(group_name):
    """Fetch title and description for unenriched links."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    enriched = _enrich_with_progress(group["id"])
    click.echo(f"\nEnriched {enriched} links with metadata.")


@cli.command("export")
@click.argument("group_name")
@click.option("--output", default=None, help="Output file path")
@click.option("--type", "link_type", default=None, help="Filter by link type (e.g., youtube)")
@click.option("--sender", default=None, help="Filter by sender name (substring match)")
@click.option("--after", default=None, help="Filter links after this date (YYYY-MM-DD)")
@click.option("--before", default=None, help="Filter links before this date (YYYY-MM-DD)")
@click.option("--domain", default=None, help="Filter by domain (substring match)")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv",
              help="Output format")
@click.option("--no-exclude", is_flag=True, help="Disable default domain exclusions")
@click.option("--dedup", is_flag=True,
              help="Deduplicate: one row per URL, adds 'Times Shared' count")
def export(group_name, output, link_type, sender, after, before, domain, fmt, no_exclude, dedup):
    """Export links for a group to CSV or JSON."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    exclude_domains = [] if no_exclude else None
    output_path, count = export_links(
        group_name, output_path=output, fmt=fmt,
        link_type=link_type, sender=sender, after=after, before=before, domain=domain,
        exclude_domains=exclude_domains, dedup=dedup,
    )
    click.echo(f"Exported {count} links to {output_path}")


@cli.command("stats")
@click.argument("group_name")
def stats(group_name):
    """Show statistics for a group."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    group_id = group["id"]
    summary = db.get_group_summary(group_id)

    click.echo(f"Group: {group_name}")
    click.echo(f"  Messages: {summary['message_count']} ({summary['system_count']} system)")
    click.echo(f"  Links: {summary['link_count']}")
    click.echo(f"  Contacts: {summary['contact_count']}")

    # Top sharers
    by_sender = db.get_link_stats_by_sender(group_id)
    if by_sender:
        click.echo("\nTop sharers:")
        for row in by_sender:
            label = "link" if row["count"] == 1 else "links"
            click.echo(f"  {row['sender']:<20s} {row['count']} {label}")

    # Link types
    by_type = db.get_link_stats_by_type(group_id)
    if by_type:
        click.echo("\nLink types:")
        for row in by_type:
            click.echo(f"  {row['type']:<16s} {row['count']}")

    # Top domains
    by_domain = db.get_link_stats_by_domain(group_id)
    if by_domain:
        click.echo("\nTop domains:")
        for row in by_domain:
            click.echo(f"  {row['domain']:<24s} {row['count']}")


@cli.command("reset")
@click.argument("group_name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def reset(group_name, yes):
    """Delete all data for a group so it can be reimported fresh."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    summary = db.get_group_summary(group["id"])
    click.echo(f'Group "{group_name}": {summary["message_count"]} messages, '
               f'{summary["link_count"]} links, {summary["contact_count"]} contacts')

    if not yes:
        click.confirm("Delete all data for this group?", abort=True)

    db.delete_group_data(group["id"])
    click.echo(f'Group "{group_name}" has been reset. You can now reimport.')


@cli.command("groups")
def groups():
    """List all groups with stats."""
    all_groups = db.list_groups()
    if not all_groups:
        click.echo("No groups found.")
        return

    for g in all_groups:
        click.echo(
            f"  {g['name']}: {g['message_count']} messages, "
            f"{g['link_count']} links, {g['contact_count']} contacts"
        )


@cli.command("contacts")
@click.argument("group_name")
@click.option("--resolve", is_flag=True, help="Interactively resolve unresolved contacts")
def contacts(group_name, resolve):
    """List or resolve contacts for a group."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    if resolve:
        _resolve_unresolved_contacts(group["id"])
        return

    contact_list = db.get_contacts_for_group(group["id"])
    if not contact_list:
        click.echo("No contacts found.")
        return

    for c in contact_list:
        resolved_marker = "" if c["resolved"] else " [unresolved]"
        click.echo(f"  {c['canonical_name']}{resolved_marker}")
        if c["aliases"]:
            click.echo(f"    Aliases: {c['aliases']}")


def _resolve_unresolved_contacts(group_id):
    """Interactive resolution of unresolved contacts for the 'contacts --resolve' command."""
    unresolved = db.get_unresolved_contacts(group_id)
    if not unresolved:
        click.echo("No unresolved contacts.")
        return

    existing_contacts = db.get_contacts_for_group(group_id)

    click.echo(f"\n{len(unresolved)} unresolved contact(s):\n")

    for contact in unresolved:
        click.echo(f'Resolving: "{contact["display_name"]}" (current name: {contact["canonical_name"]})')
        click.echo("Existing contacts:")

        resolved_contacts = [c for c in existing_contacts if c["resolved"]]
        for i, c in enumerate(resolved_contacts, 1):
            click.echo(f"  {i}. {c['canonical_name']} (aliases: {c['aliases']})")

        click.echo(f"\n  [1-{len(resolved_contacts)}] Merge with existing contact")
        click.echo(f"  [k]   Keep as-is (mark resolved)")

        while True:
            choice = click.prompt("Choice", type=str).strip().lower()

            if choice == "k":
                db.resolve_contact(contact["id"], contact["canonical_name"])
                click.echo(f"  Kept as {contact['canonical_name']}")
                break

            try:
                idx = int(choice)
                if 1 <= idx <= len(resolved_contacts):
                    target = resolved_contacts[idx - 1]
                    # Reassign messages and alias to the target contact
                    with db.get_connection() as conn:
                        conn.execute(
                            "UPDATE message SET contact_id = ? WHERE contact_id = ?",
                            (target["id"], contact["id"])
                        )
                        conn.execute(
                            "UPDATE contact_alias SET contact_id = ? WHERE contact_id = ?",
                            (target["id"], contact["id"])
                        )
                        conn.execute(
                            "DELETE FROM contact WHERE id = ?",
                            (contact["id"],)
                        )
                    click.echo(f"  Merged with {target['canonical_name']}")
                    break
            except ValueError:
                pass

            click.echo("Invalid choice, please try again.")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
