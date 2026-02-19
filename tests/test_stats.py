import db


def _setup_group_with_data(conn, group_id):
    """Helper: create contacts, messages, and links for stats testing."""
    c1 = db.create_contact(conn, "Alice", resolved=True)
    db.create_alias(conn, c1, group_id, "Alice")
    c2 = db.create_contact(conn, "Bob", resolved=True)
    db.create_alias(conn, c2, group_id, "Bob")
    system_id = db.get_system_contact_id(conn)

    # System message
    db.insert_message(conn, group_id, system_id, "2025-01-01T00:00:00",
                      "Group created", "sys_h1", True)

    # Alice: 2 messages, 2 links
    m1 = db.insert_message(conn, group_id, c1, "2025-01-01T01:00:00",
                           "Check youtube", "h1", False)
    m2 = db.insert_message(conn, group_id, c1, "2025-01-01T02:00:00",
                           "Reddit link", "h2", False)

    # Bob: 1 message, 1 link
    m3 = db.insert_message(conn, group_id, c2, "2025-01-01T03:00:00",
                           "Travel stuff", "h3", False)

    db.insert_links_batch(conn, [
        (m1, "https://youtube.com/watch?v=1", "youtube.com", "youtube", None),
        (m2, "https://www.reddit.com/r/test", "www.reddit.com", "reddit", None),
        (m3, "https://www.airbnb.com/rooms/1", "www.airbnb.com", "travel", None),
    ])


class TestGroupSummary:
    def test_counts(self, temp_db):
        group_id = db.get_or_create_group("Stats Test")
        with db.get_connection() as conn:
            _setup_group_with_data(conn, group_id)

        summary = db.get_group_summary(group_id)
        assert summary["message_count"] == 4  # 1 system + 3 regular
        assert summary["system_count"] == 1
        assert summary["link_count"] == 3
        assert summary["contact_count"] == 2  # Alice + Bob (not __system__)

    def test_empty_group(self, temp_db):
        group_id = db.get_or_create_group("Empty")
        summary = db.get_group_summary(group_id)
        assert summary["message_count"] == 0
        assert summary["link_count"] == 0
        assert summary["contact_count"] == 0


class TestLinkStatsBySender:
    def test_ordered_by_count(self, temp_db):
        group_id = db.get_or_create_group("Stats Test")
        with db.get_connection() as conn:
            _setup_group_with_data(conn, group_id)

        stats = db.get_link_stats_by_sender(group_id)
        assert len(stats) == 2
        assert stats[0]["sender"] == "Alice"
        assert stats[0]["count"] == 2
        assert stats[1]["sender"] == "Bob"
        assert stats[1]["count"] == 1


class TestLinkStatsByType:
    def test_all_types_present(self, temp_db):
        group_id = db.get_or_create_group("Stats Test")
        with db.get_connection() as conn:
            _setup_group_with_data(conn, group_id)

        stats = db.get_link_stats_by_type(group_id)
        types = {row["type"]: row["count"] for row in stats}
        assert types["youtube"] == 1
        assert types["reddit"] == 1
        assert types["travel"] == 1


class TestLinkStatsByDomain:
    def test_all_domains_present(self, temp_db):
        group_id = db.get_or_create_group("Stats Test")
        with db.get_connection() as conn:
            _setup_group_with_data(conn, group_id)

        stats = db.get_link_stats_by_domain(group_id)
        domains = {row["domain"]: row["count"] for row in stats}
        assert "youtube.com" in domains
        assert "www.reddit.com" in domains
        assert "www.airbnb.com" in domains
