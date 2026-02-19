import csv
import json
import os

import db
from exporter import export_links


def _setup_group_with_links(conn, group_id):
    """Helper to insert test data: 2 contacts, 3 messages, 3 links."""
    c1 = db.create_contact(conn, "Alice", resolved=True)
    db.create_alias(conn, c1, group_id, "Alice")
    c2 = db.create_contact(conn, "Bob", resolved=True)
    db.create_alias(conn, c2, group_id, "Bob")

    m1 = db.insert_message(conn, group_id, c1, "2025-10-01T10:00:00",
                           "Check youtube", "h1", False)
    m2 = db.insert_message(conn, group_id, c2, "2025-10-02T11:00:00",
                           "Reddit link", "h2", False)
    m3 = db.insert_message(conn, group_id, c1, "2025-10-03T12:00:00",
                           "Travel stuff", "h3", False)

    db.insert_links_batch(conn, [
        (m1, "https://youtube.com/watch?v=1", "youtube.com", "youtube", "yt context"),
        (m2, "https://www.reddit.com/r/test", "www.reddit.com", "reddit", "reddit context"),
        (m3, "https://www.airbnb.com/rooms/1", "www.airbnb.com", "travel", "travel context"),
    ])

    # Enrich one link
    db.update_link_metadata(conn, 1, "Cool Video", "A great video")


class TestExportCSV:
    def test_csv_has_new_columns(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        path, count = export_links("TestGroup", output_path=out)
        assert count == 3

        with open(out, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        assert "Title" in rows[0]
        assert "Description" in rows[0]
        assert "Context" in rows[0]

    def test_csv_title_populated(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        export_links("TestGroup", output_path=out)

        with open(out, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        yt_row = [r for r in rows if "youtube" in r["Link"]][0]
        assert yt_row["Title"] == "Cool Video"
        assert yt_row["Description"] == "A great video"


class TestExportJSON:
    def test_json_format(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.json")
        path, count = export_links("TestGroup", output_path=out, fmt="json")
        assert count == 3

        with open(out) as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 3
        assert "Sender" in data[0]
        assert "Title" in data[0]
        assert "Context" in data[0]

    def test_json_default_filename(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("My Group")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        # Change to tmp dir so default file is created there
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            path, _ = export_links("My Group", fmt="json")
            assert path == "My_Group_links.json"
        finally:
            os.chdir(old_cwd)


class TestExportFilters:
    def test_filter_by_type(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out, link_type="youtube")
        assert count == 1

    def test_filter_by_sender(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out, sender="Alice")
        assert count == 2

    def test_filter_by_domain(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out, domain="reddit")
        assert count == 1

    def test_filter_by_date_range(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out,
                                after="2025-10-02", before="2025-10-02T23:59:59")
        assert count == 1

    def test_filter_no_results(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out, link_type="nonexistent")
        assert count == 0

    def test_group_not_found(self, temp_db, tmp_path):
        import pytest
        with pytest.raises(ValueError, match="not found"):
            export_links("NoSuchGroup")
