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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, url)
            );
        """)

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
    """Insert multiple links using executemany. links is a list of tuples (message_id, url, domain, link_type)."""
    conn.executemany(
        "INSERT OR IGNORE INTO link (message_id, url, domain, link_type) VALUES (?, ?, ?, ?)",
        links
    )


# --- Export query ---

def get_links_for_export(group_id):
    """Return all links for a group, joined with message and contact data."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT
                c.canonical_name AS sender,
                l.url AS link,
                l.link_type AS type,
                m.raw_text AS caption,
                m.timestamp,
                l.domain
            FROM link l
            JOIN message m ON m.id = l.message_id
            JOIN contact c ON c.id = m.contact_id
            WHERE m.group_id = ?
            ORDER BY m.timestamp DESC
        """, (group_id,)).fetchall()
