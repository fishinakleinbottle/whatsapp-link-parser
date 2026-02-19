from difflib import SequenceMatcher

import click

import db

SIMILARITY_THRESHOLD = 0.4
MAX_SUGGESTIONS = 5


def resolve_contacts_for_import(group_id, sender_names, conn):
    """Resolve sender names to contact IDs for an import.

    On first import (no existing contacts): auto-creates all contacts + aliases silently.
    On subsequent imports: prompts for each unrecognized name.

    Returns a dict mapping display_name -> contact_id.
    """
    contact_map = {}

    # Get existing aliases for this group
    existing_aliases = conn.execute(
        "SELECT display_name, contact_id FROM contact_alias WHERE group_id = ?",
        (group_id,)
    ).fetchall()
    for alias in existing_aliases:
        contact_map[alias["display_name"]] = alias["contact_id"]

    # Find new sender names not yet in the group
    new_names = [name for name in sender_names if name not in contact_map]
    if not new_names:
        return contact_map

    # Check if this is a first import (no existing contacts in the group)
    is_first_import = len(existing_aliases) == 0

    if is_first_import:
        # Auto-create all contacts silently
        for name in new_names:
            contact_id = db.create_contact(conn, name, resolved=True)
            db.create_alias(conn, contact_id, group_id, name)
            contact_map[name] = contact_id
    else:
        # Prompt for each new name
        existing_contacts = conn.execute("""
            SELECT c.id, c.canonical_name
            FROM contact c
            JOIN contact_alias ca ON ca.contact_id = c.id
            WHERE ca.group_id = ?
            GROUP BY c.id
            ORDER BY c.canonical_name
        """, (group_id,)).fetchall()

        for name in new_names:
            contact_id = _prompt_for_contact(conn, group_id, name, existing_contacts)
            contact_map[name] = contact_id

    return contact_map


def _similarity(a, b):
    """Case-insensitive similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_similar_contacts(display_name, existing_contacts, conn, group_id):
    """Return top matching contacts sorted by similarity score (descending).

    Compares against both canonical_name and all aliases for the group.
    Only returns matches above SIMILARITY_THRESHOLD, capped at MAX_SUGGESTIONS.
    """
    scores = {}  # contact_id -> (best_score, contact_row)

    for contact in existing_contacts:
        # Score against canonical name
        best = _similarity(display_name, contact["canonical_name"])

        # Also score against each alias in this group
        aliases = conn.execute(
            "SELECT display_name FROM contact_alias WHERE contact_id = ? AND group_id = ?",
            (contact["id"], group_id)
        ).fetchall()
        for alias in aliases:
            score = _similarity(display_name, alias["display_name"])
            if score > best:
                best = score

        if best >= SIMILARITY_THRESHOLD:
            scores[contact["id"]] = (best, contact)

    ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    return ranked[:MAX_SUGGESTIONS]


def _prompt_for_contact(conn, group_id, display_name, existing_contacts):
    """Prompt the user to resolve a new display name.

    Uses fuzzy matching to show only the most likely matches.
    If no similar names found, auto-creates as new contact.
    """
    similar = _find_similar_contacts(display_name, existing_contacts, conn, group_id)

    if not similar:
        # No similar names — auto-create silently
        contact_id = db.create_contact(conn, display_name, resolved=True)
        db.create_alias(conn, contact_id, group_id, display_name)
        click.echo(f'New contact created: "{display_name}" (no similar names found)')
        return contact_id

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
            contact_id = db.create_contact(conn, display_name, resolved=True)
            db.create_alias(conn, contact_id, group_id, display_name)
            return contact_id

        if choice == "s":
            contact_id = db.create_contact(conn, display_name, resolved=False)
            db.create_alias(conn, contact_id, group_id, display_name)
            return contact_id

        try:
            idx = int(choice)
            if 1 <= idx <= len(similar):
                contact_id = similar[idx - 1][1]["id"]
                db.create_alias(conn, contact_id, group_id, display_name)
                return contact_id
        except ValueError:
            pass

        click.echo("Invalid choice, please try again.")


def resolve_unresolved_contacts(group_id):
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
