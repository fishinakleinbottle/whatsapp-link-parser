from unittest.mock import patch, MagicMock

import db
from enricher import _fetch_metadata, enrich_links


class TestFetchMetadata:
    def test_extracts_og_tags(self):
        html = """
        <html><head>
            <meta property="og:title" content="My Page Title">
            <meta property="og:description" content="A great description">
        </head><body></body></html>
        """
        with patch("enricher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            title, desc = _fetch_metadata("https://example.com")
            assert title == "My Page Title"
            assert desc == "A great description"

    def test_falls_back_to_title_tag(self):
        html = "<html><head><title>Fallback Title</title></head><body></body></html>"
        with patch("enricher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            title, desc = _fetch_metadata("https://example.com")
            assert title == "Fallback Title"
            assert desc is None

    def test_falls_back_to_meta_description(self):
        html = """
        <html><head>
            <title>Page</title>
            <meta name="description" content="Meta desc">
        </head><body></body></html>
        """
        with patch("enricher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            title, desc = _fetch_metadata("https://example.com")
            assert title == "Page"
            assert desc == "Meta desc"

    def test_truncates_long_title(self):
        long_title = "A" * 300
        html = f'<html><head><title>{long_title}</title></head><body></body></html>'
        with patch("enricher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            title, _ = _fetch_metadata("https://example.com")
            assert len(title) == 200

    def test_handles_request_failure(self):
        import requests as req
        with patch("enricher.requests.get", side_effect=req.ConnectionError("fail")):
            with patch("enricher.RETRY_DELAY", 0):
                title, desc = _fetch_metadata("https://example.com")
                assert title is None
                assert desc is None

    def test_adds_scheme_if_missing(self):
        html = "<html><head><title>No Scheme</title></head><body></body></html>"
        with patch("enricher.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            _fetch_metadata("example.com/page")
            call_url = mock_get.call_args[0][0]
            assert call_url.startswith("https://")


class TestEnrichLinks:
    def test_enrich_stores_metadata(self, temp_db):
        """End-to-end: insert a link, enrich it, verify metadata stored."""
        group_id = db.get_or_create_group("Test")

        with db.get_connection() as conn:
            system_id = db.get_system_contact_id(conn)
            msg_id = db.insert_message(
                conn, group_id, system_id, "2025-01-01T00:00:00",
                "Check https://example.com", "hash123", False
            )
            db.insert_links_batch(conn, [
                (msg_id, "https://example.com", "example.com", "general", None)
            ])

        html = "<html><head><title>Example</title></head><body></body></html>"
        with patch("enricher.requests.get") as mock_get, \
             patch("enricher.RATE_LIMIT_DELAY", 0):
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            count = enrich_links(group_id)

        assert count == 1

        # Verify stored in DB
        with db.get_connection() as conn:
            row = conn.execute("SELECT title FROM link WHERE id = 1").fetchone()
            assert row["title"] == "Example"

    def test_skips_already_enriched(self, temp_db):
        """Links with title already set should not be re-fetched."""
        group_id = db.get_or_create_group("Test")

        with db.get_connection() as conn:
            system_id = db.get_system_contact_id(conn)
            msg_id = db.insert_message(
                conn, group_id, system_id, "2025-01-01T00:00:00",
                "Check https://example.com", "hash456", False
            )
            db.insert_links_batch(conn, [
                (msg_id, "https://example.com", "example.com", "general", None)
            ])
            db.update_link_metadata(conn, 1, "Already Set", "Desc")

        with patch("enricher.requests.get") as mock_get:
            count = enrich_links(group_id)

        assert count == 0
        mock_get.assert_not_called()
