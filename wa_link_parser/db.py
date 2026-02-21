import hashlib
import os
import sqlite3
from contextlib import contextmanager


SYSTEM_CONTACT_NAME = "__system__"


def get_db_path():
    return os.environ.get("WA_LINKS_DB_PATH", "wa_links.db")


@contextmanager
def get_connection():
    """Context manager that yields a connection with commit/rollback semantics."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(conn, table, column):
    """Check if a column exists in a table using PRAGMA table_info."""
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c["name"] == column for c in cols)


def _migrate_link_table(conn):
    """Add new columns to the link table if they don't exist."""
    for col in ("title", "description", "context", "raw_url"):
        if not _column_exists(conn, "link", col):
            conn.execute(f"ALTER TABLE link ADD COLUMN {col} TEXT")


def init_db():
    """Create all tables and ensure the __system__ sentinel contact exists."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS whatsapp_group (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contact (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                resolved BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contact_alias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL REFERENCES contact(id),
                group_id INTEGER NOT NULL REFERENCES whatsapp_group(id),
                display_name TEXT NOT NULL,
                UNIQUE(group_id, display_name)
            );

            CREATE TABLE IF NOT EXISTS message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES whatsapp_group(id),
                contact_id INTEGER NOT NULL REFERENCES contact(id),
                timestamp TIMESTAMP NOT NULL,
                raw_text TEXT NOT NULL,
                message_hash TEXT NOT NULL UNIQUE,
                is_system_message BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL REFERENCES message(id),
                url TEXT NOT NULL,
                domain TEXT,
                link_type TEXT,
                title TEXT,
                description TEXT,
                context TEXT,
                raw_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, url)
            );
        """)

        # Migrate existing databases
        _migrate_link_table(conn)

        # Ensure __system__ contact exists
        row = conn.execute(
            "SELECT id FROM contact WHERE canonical_name = ?",
            (SYSTEM_CONTACT_NAME,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO contact (canonical_name) VALUES (?)",
                (SYSTEM_CONTACT_NAME,)
            )


def compute_message_hash(timestamp_iso, sender, raw_text):
    """SHA256(timestamp_iso + '|' + sender + '|' + raw_text)"""
    payload = f"{timestamp_iso}|{sender}|{raw_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- Group operations ---

def get_or_create_group(name):
    """Return group id, creating if needed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM whatsapp_group WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO whatsapp_group (name) VALUES (?)", (name,)
        )
        return cursor.lastrowid


def list_groups():
    """Return all groups with message/link/contact counts."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT
                g.id,
                g.name,
                COUNT(DISTINCT m.id) AS message_count,
                COUNT(DISTINCT l.id) AS link_count,
                COUNT(DISTINCT ca.contact_id) AS contact_count
            FROM whatsapp_group g
            LEFT JOIN message m ON m.group_id = g.id
            LEFT JOIN link l ON l.message_id = m.id
            LEFT JOIN contact_alias ca ON ca.group_id = g.id
            GROUP BY g.id
            ORDER BY g.name
        """).fetchall()


def get_group_by_name(name):
    """Return a group row by name, or None."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM whatsapp_group WHERE name = ?", (name,)
        ).fetchone()


# --- Contact operations ---

def get_system_contact_id(conn):
    """Get the __system__ contact id using an existing connection."""
    row = conn.execute(
        "SELECT id FROM contact WHERE canonical_name = ?",
        (SYSTEM_CONTACT_NAME,)
    ).fetchone()
    return row["id"]


def get_contacts_for_group(group_id):
    """Return contacts for a group with their aliases."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT c.id, c.canonical_name, c.resolved,
                   GROUP_CONCAT(ca.display_name, ', ') AS aliases
            FROM contact c
            JOIN contact_alias ca ON ca.contact_id = c.id
            WHERE ca.group_id = ?
            GROUP BY c.id
            ORDER BY c.canonical_name
        """, (group_id,)).fetchall()


def get_alias_for_group(conn, group_id, display_name):
    """Check if a display_name already has an alias in this group. Returns contact_id or None."""
    row = conn.execute(
        "SELECT contact_id FROM contact_alias WHERE group_id = ? AND display_name = ?",
        (group_id, display_name)
    ).fetchone()
    return row["contact_id"] if row else None


def create_contact(conn, canonical_name, resolved=True):
    """Create a new contact, return its id."""
    cursor = conn.execute(
        "INSERT INTO contact (canonical_name, resolved) VALUES (?, ?)",
        (canonical_name, resolved)
    )
    return cursor.lastrowid


def create_alias(conn, contact_id, group_id, display_name):
    """Create a contact_alias mapping."""
    conn.execute(
        "INSERT OR IGNORE INTO contact_alias (contact_id, group_id, display_name) VALUES (?, ?, ?)",
        (contact_id, group_id, display_name)
    )


def get_unresolved_contacts(group_id):
    """Return unresolved contacts for a group."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT c.id, c.canonical_name, ca.display_name
            FROM contact c
            JOIN contact_alias ca ON ca.contact_id = c.id
            WHERE ca.group_id = ? AND c.resolved = FALSE
            ORDER BY c.canonical_name
        """, (group_id,)).fetchall()


def resolve_contact(contact_id, canonical_name):
    """Mark a contact as resolved and update canonical name."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE contact SET canonical_name = ?, resolved = TRUE WHERE id = ?",
            (canonical_name, contact_id)
        )


# --- Message operations ---

def message_hash_exists(conn, hash_value):
    """Check if a message hash already exists."""
    row = conn.execute(
        "SELECT 1 FROM message WHERE message_hash = ?", (hash_value,)
    ).fetchone()
    return row is not None


def insert_message(conn, group_id, contact_id, timestamp, raw_text, message_hash, is_system=False):
    """Insert a message, return its id."""
    cursor = conn.execute(
        """INSERT INTO message (group_id, contact_id, timestamp, raw_text, message_hash, is_system_message)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (group_id, contact_id, timestamp, raw_text, message_hash, is_system)
    )
    return cursor.lastrowid


def insert_links_batch(conn, links):
    """Insert multiple links.

    Each element of links must be a tuple:
        (message_id, url, domain, link_type, context, raw_url)
    where url is the normalized URL and raw_url is the original.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO link (message_id, url, domain, link_type, context, raw_url) VALUES (?, ?, ?, ?, ?, ?)",
        links
    )


# --- Enrichment operations ---

def get_unenriched_links(group_id):
    """Return links where title IS NULL, for a given group."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT l.id, l.url
            FROM link l
            JOIN message m ON m.id = l.message_id
            WHERE m.group_id = ? AND l.title IS NULL
            ORDER BY l.id
        """, (group_id,)).fetchall()


def update_link_metadata(conn, link_id, title, description):
    """Set title and description on a link."""
    conn.execute(
        "UPDATE link SET title = ?, description = ? WHERE id = ?",
        (title, description, link_id)
    )


# --- Export query ---

def get_links_for_export(group_id):
    """Return all links for a group, joined with message and contact data."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT
                c.canonical_name AS sender,
                l.url AS link,
                l.title,
                l.link_type AS type,
                m.raw_text AS caption,
                l.context,
                m.timestamp,
                l.domain,
                l.description
            FROM link l
            JOIN message m ON m.id = l.message_id
            JOIN contact c ON c.id = m.contact_id
            WHERE m.group_id = ?
            ORDER BY m.timestamp DESC
        """, (group_id,)).fetchall()


def get_links_for_export_filtered(group_id, link_type=None, sender=None,
                                  after=None, before=None, domain=None):
    """Return links for a group with optional filters."""
    query = """
        SELECT
            c.canonical_name AS sender,
            l.url AS link,
            l.title,
            l.link_type AS type,
            m.raw_text AS caption,
            l.context,
            m.timestamp,
            l.domain,
            l.description
        FROM link l
        JOIN message m ON m.id = l.message_id
        JOIN contact c ON c.id = m.contact_id
        WHERE m.group_id = ?
    """
    params = [group_id]

    if link_type:
        query += " AND l.link_type = ?"
        params.append(link_type)
    if sender:
        query += " AND c.canonical_name LIKE ?"
        params.append(f"%{sender}%")
    if after:
        query += " AND m.timestamp >= ?"
        params.append(after)
    if before:
        query += " AND m.timestamp <= ?"
        params.append(before)
    if domain:
        query += " AND l.domain LIKE ?"
        params.append(f"%{domain}%")

    query += " ORDER BY m.timestamp DESC"

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


# --- Reset operations ---

def delete_group_data(group_id):
    """Delete all data for a group: links, messages, contact_aliases, and orphaned contacts.

    Does NOT delete the group row itself so the name can be reused on reimport.
    """
    with get_connection() as conn:
        # Delete links (child of message)
        conn.execute("""
            DELETE FROM link WHERE message_id IN (
                SELECT id FROM message WHERE group_id = ?
            )
        """, (group_id,))

        # Delete messages
        conn.execute("DELETE FROM message WHERE group_id = ?", (group_id,))

        # Get contact IDs for this group before deleting aliases
        contact_ids = [row["contact_id"] for row in conn.execute(
            "SELECT DISTINCT contact_id FROM contact_alias WHERE group_id = ?",
            (group_id,)
        ).fetchall()]

        # Delete aliases for this group
        conn.execute("DELETE FROM contact_alias WHERE group_id = ?", (group_id,))

        # Delete orphaned contacts (no remaining aliases, not __system__)
        for cid in contact_ids:
            remaining = conn.execute(
                "SELECT 1 FROM contact_alias WHERE contact_id = ?", (cid,)
            ).fetchone()
            if remaining is None:
                conn.execute(
                    "DELETE FROM contact WHERE id = ? AND canonical_name != ?",
                    (cid, SYSTEM_CONTACT_NAME)
                )

        # Delete the group row itself
        conn.execute("DELETE FROM whatsapp_group WHERE id = ?", (group_id,))


# --- Stats queries ---

def get_group_summary(group_id):
    """Return message count, link count, system message count, contact count."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) AS message_count,
                SUM(CASE WHEN is_system_message THEN 1 ELSE 0 END) AS system_count
            FROM message
            WHERE group_id = ?
        """, (group_id,)).fetchone()

        link_count = conn.execute("""
            SELECT COUNT(*) AS cnt
            FROM link l
            JOIN message m ON m.id = l.message_id
            WHERE m.group_id = ?
        """, (group_id,)).fetchone()["cnt"]

        contact_count = conn.execute("""
            SELECT COUNT(DISTINCT contact_id) AS cnt
            FROM contact_alias
            WHERE group_id = ?
        """, (group_id,)).fetchone()["cnt"]

        return {
            "message_count": row["message_count"],
            "system_count": row["system_count"],
            "link_count": link_count,
            "contact_count": contact_count,
        }


def get_link_stats_by_sender(group_id):
    """COUNT links GROUP BY sender, ordered by count descending."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT c.canonical_name AS sender, COUNT(*) AS count
            FROM link l
            JOIN message m ON m.id = l.message_id
            JOIN contact c ON c.id = m.contact_id
            WHERE m.group_id = ?
            GROUP BY c.id
            ORDER BY count DESC
        """, (group_id,)).fetchall()


def get_link_stats_by_type(group_id):
    """COUNT links GROUP BY link_type, ordered by count descending."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT l.link_type AS type, COUNT(*) AS count
            FROM link l
            JOIN message m ON m.id = l.message_id
            WHERE m.group_id = ?
            GROUP BY l.link_type
            ORDER BY count DESC
        """, (group_id,)).fetchall()


def get_link_stats_by_domain(group_id):
    """COUNT links GROUP BY domain, ordered by count descending."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT l.domain, COUNT(*) AS count
            FROM link l
            JOIN message m ON m.id = l.message_id
            WHERE m.group_id = ?
            GROUP BY l.domain
            ORDER BY count DESC
        """, (group_id,)).fetchall()
