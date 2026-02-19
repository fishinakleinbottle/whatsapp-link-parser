from difflib import SequenceMatcher

from wa_link_parser import db

SIMILARITY_THRESHOLD = 0.4
MAX_SUGGESTIONS = 5


def similarity(a, b):
    """Case-insensitive similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_similar_contacts(display_name, existing_contacts, conn, group_id):
    """Return top matching contacts sorted by similarity score (descending).

    Compares against both canonical_name and all aliases for the group.
    Only returns matches above SIMILARITY_THRESHOLD, capped at MAX_SUGGESTIONS.

    Returns list of (score, contact_row) tuples.
    """
    scores = {}  # contact_id -> (best_score, contact_row)

    for contact in existing_contacts:
        # Score against canonical name
        best = similarity(display_name, contact["canonical_name"])

        # Also score against each alias in this group
        aliases = conn.execute(
            "SELECT display_name FROM contact_alias WHERE contact_id = ? AND group_id = ?",
            (contact["id"], group_id)
        ).fetchall()
        for alias in aliases:
            score = similarity(display_name, alias["display_name"])
            if score > best:
                best = score

        if best >= SIMILARITY_THRESHOLD:
            scores[contact["id"]] = (best, contact)

    ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    return ranked[:MAX_SUGGESTIONS]


def auto_resolve_contacts(group_id, sender_names, conn):
    """Resolve sender names to contact IDs non-interactively.

    On first import (no existing contacts): auto-creates all contacts + aliases.
    On subsequent imports: auto-creates new contacts without prompting.

    Returns a dict mapping display_name -> contact_id.
    """
    contact_map = {}

    existing_aliases = conn.execute(
        "SELECT display_name, contact_id FROM contact_alias WHERE group_id = ?",
        (group_id,)
    ).fetchall()
    for alias in existing_aliases:
        contact_map[alias["display_name"]] = alias["contact_id"]

    new_names = [name for name in sender_names if name not in contact_map]
    if not new_names:
        return contact_map

    for name in new_names:
        contact_id = db.create_contact(conn, name, resolved=True)
        db.create_alias(conn, contact_id, group_id, name)
        contact_map[name] = contact_id

    return contact_map


def resolve_contacts_for_import(group_id, sender_names, conn,
                                prompt_fn=None):
    """Resolve sender names to contact IDs for an import.

    On first import (no existing contacts): auto-creates all contacts + aliases silently.
    On subsequent imports: uses prompt_fn for each unrecognized name if provided,
    otherwise auto-creates.

    Args:
        group_id: The group to resolve contacts for.
        sender_names: List of sender display names from the chat export.
        conn: Active database connection.
        prompt_fn: Optional callback for interactive resolution.
            Called with (display_name, similar_contacts) where similar_contacts
            is a list of (score, contact_row) tuples.
            Should return a contact_id or None to create new.

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
        # Get existing contacts for similarity matching
        existing_contacts = conn.execute("""
            SELECT c.id, c.canonical_name
            FROM contact c
            JOIN contact_alias ca ON ca.contact_id = c.id
            WHERE ca.group_id = ?
            GROUP BY c.id
            ORDER BY c.canonical_name
        """, (group_id,)).fetchall()

        for name in new_names:
            similar = find_similar_contacts(name, existing_contacts, conn, group_id)

            if not similar or prompt_fn is None:
                # No similar names or no interactive prompt -- auto-create
                contact_id = db.create_contact(conn, name, resolved=True)
                db.create_alias(conn, contact_id, group_id, name)
                contact_map[name] = contact_id
            else:
                # Use the prompt function to resolve
                result = prompt_fn(name, similar)
                if result is None:
                    # Create new contact
                    contact_id = db.create_contact(conn, name, resolved=True)
                    db.create_alias(conn, contact_id, group_id, name)
                    contact_map[name] = contact_id
                elif result == "skip":
                    contact_id = db.create_contact(conn, name, resolved=False)
                    db.create_alias(conn, contact_id, group_id, name)
                    contact_map[name] = contact_id
                else:
                    # Merge with existing contact
                    db.create_alias(conn, result, group_id, name)
                    contact_map[name] = result

    return contact_map
