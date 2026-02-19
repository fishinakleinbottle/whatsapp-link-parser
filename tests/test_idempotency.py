from wa_link_parser import db
from wa_link_parser.contact_resolver import resolve_contacts_for_import
from wa_link_parser.extractor import extract_links
from wa_link_parser.parser import parse_chat_file


class TestIdempotency:
    def _do_import(self, sample_chat_path, group_name="Test Group"):
        """Helper to run a full import and return stats."""
        group_id = db.get_or_create_group(group_name)
        messages = parse_chat_file(sample_chat_path)

        sender_names = list(dict.fromkeys(
            m.sender for m in messages if not m.is_system
        ))

        new_count = 0
        skipped_count = 0
        link_count = 0

        with db.get_connection() as conn:
            contact_map = resolve_contacts_for_import(group_id, sender_names, conn)
            system_contact_id = db.get_system_contact_id(conn)

            for msg in messages:
                timestamp_iso = msg.timestamp.isoformat()
                message_hash = db.compute_message_hash(timestamp_iso, msg.sender, msg.raw_text)

                if db.message_hash_exists(conn, message_hash):
                    skipped_count += 1
                    continue

                contact_id = system_contact_id if msg.is_system else contact_map[msg.sender]
                message_id = db.insert_message(
                    conn, group_id, contact_id, timestamp_iso,
                    msg.raw_text, message_hash, msg.is_system
                )
                new_count += 1

                if not msg.is_system:
                    links = extract_links(msg.raw_text)
                    if links:
                        link_rows = [
                            (message_id, link.url, link.domain, link.link_type, None)
                            for link in links
                        ]
                        db.insert_links_batch(conn, link_rows)
                        link_count += len(links)

        return new_count, skipped_count, link_count

    def test_first_import_creates_messages(self, temp_db, sample_chat_path):
        new, skipped, links = self._do_import(sample_chat_path)
        assert new > 0
        assert skipped == 0
        assert links > 0

    def test_second_import_skips_all(self, temp_db, sample_chat_path):
        """Importing the same file twice should produce zero new messages."""
        new1, _, links1 = self._do_import(sample_chat_path)
        new2, skipped2, links2 = self._do_import(sample_chat_path)

        assert new2 == 0
        assert skipped2 == new1
        assert links2 == 0

    def test_message_count_unchanged_after_reimport(self, temp_db, sample_chat_path):
        """Total message count should be the same after reimporting."""
        self._do_import(sample_chat_path)

        with db.get_connection() as conn:
            count1 = conn.execute("SELECT COUNT(*) as c FROM message").fetchone()["c"]

        self._do_import(sample_chat_path)

        with db.get_connection() as conn:
            count2 = conn.execute("SELECT COUNT(*) as c FROM message").fetchone()["c"]

        assert count1 == count2

    def test_link_count_unchanged_after_reimport(self, temp_db, sample_chat_path):
        """Total link count should be the same after reimporting."""
        self._do_import(sample_chat_path)

        with db.get_connection() as conn:
            count1 = conn.execute("SELECT COUNT(*) as c FROM link").fetchone()["c"]

        self._do_import(sample_chat_path)

        with db.get_connection() as conn:
            count2 = conn.execute("SELECT COUNT(*) as c FROM link").fetchone()["c"]

        assert count1 == count2

    def test_hash_determinism(self, temp_db):
        """Same inputs should always produce the same hash."""
        h1 = db.compute_message_hash("2025-10-20T10:29:01", "Burhan", "Hello!")
        h2 = db.compute_message_hash("2025-10-20T10:29:01", "Burhan", "Hello!")
        assert h1 == h2

    def test_hash_differs_with_different_input(self, temp_db):
        h1 = db.compute_message_hash("2025-10-20T10:29:01", "Burhan", "Hello!")
        h2 = db.compute_message_hash("2025-10-20T10:29:01", "Burhan", "Hello!!")
        assert h1 != h2
