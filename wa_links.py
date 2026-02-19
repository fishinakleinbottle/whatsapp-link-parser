import click

import db
from contact_resolver import resolve_contacts_for_import, resolve_unresolved_contacts
from exporter import export_links_to_csv
from extractor import extract_links
from models import ImportStats
from parser import parse_chat_file


@click.group()
def cli():
    """WhatsApp Group Link Extractor CLI."""
    db.init_db()


@cli.command("import")
@click.argument("file_path")
@click.option("--group", "group_name", default=None, help="Group name (creates if new)")
def import_chat(file_path, group_name):
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
        contact_map = resolve_contacts_for_import(group_id, sender_names, conn)
        system_contact_id = db.get_system_contact_id(conn)

        # Import messages
        for msg in messages:
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
                    link_rows = [
                        (message_id, link.url, link.domain, link.link_type)
                        for link in links
                    ]
                    db.insert_links_batch(conn, link_rows)
                    stats.links_extracted += len(links)

    click.echo(f"\nImport complete for group \"{group_name}\":")
    click.echo(f"  {stats.new_messages} new messages imported")
    click.echo(f"  {stats.skipped_messages} duplicates skipped")
    click.echo(f"  {stats.links_extracted} links extracted")


@cli.command("export")
@click.argument("group_name")
@click.option("--output", default=None, help="Output CSV file path")
def export(group_name, output):
    """Export links for a group to CSV."""
    group = db.get_group_by_name(group_name)
    if not group:
        click.echo(f'Group "{group_name}" not found.')
        return

    output_path, count = export_links_to_csv(group_name, output)
    click.echo(f"Exported {count} links to {output_path}")


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
        resolve_unresolved_contacts(group["id"])
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


if __name__ == "__main__":
    cli()
