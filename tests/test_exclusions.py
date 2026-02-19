import json
import os

import pytest

from wa_link_parser import db
from wa_link_parser.exclusions import (
    _DEFAULT_EXCLUDED_DOMAINS,
    _get_excluded_domains,
    filter_excluded_domains,
    reset_exclusion_cache,
)
from wa_link_parser.exporter import export_links


class TestGetExcludedDomains:
    def test_defaults_loaded(self):
        domains = _get_excluded_domains()
        assert "meet.google.com" in domains
        assert "zoom.us" in domains
        assert "bit.ly" in domains

    def test_cache_returns_same_object(self):
        first = _get_excluded_domains()
        second = _get_excluded_domains()
        assert first is second

    def test_reset_cache(self):
        first = _get_excluded_domains()
        reset_exclusion_cache()
        second = _get_excluded_domains()
        assert first is not second
        assert first == second

    def test_user_override_adds_domain(self, tmp_path):
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "exclusions.json").write_text(
                json.dumps(["custom.example.com"])
            )
            reset_exclusion_cache()
            domains = _get_excluded_domains()
            assert "custom.example.com" in domains
            # defaults still present
            assert "meet.google.com" in domains
        finally:
            os.chdir(old_cwd)

    def test_user_override_removes_domain(self, tmp_path):
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "exclusions.json").write_text(
                json.dumps(["!bit.ly"])
            )
            reset_exclusion_cache()
            domains = _get_excluded_domains()
            assert "bit.ly" not in domains
            # other defaults still present
            assert "meet.google.com" in domains
        finally:
            os.chdir(old_cwd)

    def test_bad_json_ignored(self, tmp_path):
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "exclusions.json").write_text("not valid json{{{")
            reset_exclusion_cache()
            domains = _get_excluded_domains()
            # falls back to defaults
            assert domains == _DEFAULT_EXCLUDED_DOMAINS
        finally:
            os.chdir(old_cwd)

    def test_non_list_json_ignored(self, tmp_path):
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / "exclusions.json").write_text(json.dumps({"key": "val"}))
            reset_exclusion_cache()
            domains = _get_excluded_domains()
            assert domains == _DEFAULT_EXCLUDED_DOMAINS
        finally:
            os.chdir(old_cwd)


class TestFilterExcludedDomains:
    def test_explicit_list_filters(self):
        links = [
            {"domain": "youtube.com", "link": "https://youtube.com/1"},
            {"domain": "zoom.us", "link": "https://zoom.us/j/123"},
            {"domain": "reddit.com", "link": "https://reddit.com/r/test"},
        ]
        result = filter_excluded_domains(links, exclude_domains=["zoom.us"])
        assert len(result) == 2
        assert all(l["domain"] != "zoom.us" for l in result)

    def test_empty_list_no_exclusions(self):
        links = [
            {"domain": "zoom.us", "link": "https://zoom.us/j/123"},
            {"domain": "meet.google.com", "link": "https://meet.google.com/abc"},
        ]
        result = filter_excluded_domains(links, exclude_domains=[])
        assert len(result) == 2

    def test_www_normalization(self):
        links = [
            {"domain": "www.zoom.us", "link": "https://www.zoom.us/j/123"},
            {"domain": "youtube.com", "link": "https://youtube.com/1"},
        ]
        result = filter_excluded_domains(links, exclude_domains=["zoom.us"])
        assert len(result) == 1
        assert result[0]["domain"] == "youtube.com"

    def test_www_normalization_in_exclude_list(self):
        links = [
            {"domain": "zoom.us", "link": "https://zoom.us/j/123"},
        ]
        result = filter_excluded_domains(links, exclude_domains=["www.zoom.us"])
        assert len(result) == 0

    def test_none_uses_defaults(self):
        links = [
            {"domain": "meet.google.com", "link": "https://meet.google.com/abc"},
            {"domain": "youtube.com", "link": "https://youtube.com/1"},
            {"domain": "bit.ly", "link": "https://bit.ly/xyz"},
        ]
        result = filter_excluded_domains(links, exclude_domains=None)
        assert len(result) == 1
        assert result[0]["domain"] == "youtube.com"

    def test_none_domain_not_excluded(self):
        links = [
            {"domain": None, "link": "https://example.com"},
            {"domain": "zoom.us", "link": "https://zoom.us/j/123"},
        ]
        result = filter_excluded_domains(links, exclude_domains=["zoom.us"])
        assert len(result) == 1
        assert result[0]["domain"] is None


def _setup_group_with_mixed_links(conn, group_id):
    """Insert test data with both regular and excludable links."""
    c1 = db.create_contact(conn, "Alice", resolved=True)
    db.create_alias(conn, c1, group_id, "Alice")

    m1 = db.insert_message(conn, group_id, c1, "2025-10-01T10:00:00",
                           "Check this video", "h1", False)
    m2 = db.insert_message(conn, group_id, c1, "2025-10-01T11:00:00",
                           "Join the call", "h2", False)
    m3 = db.insert_message(conn, group_id, c1, "2025-10-01T12:00:00",
                           "Short link", "h3", False)

    db.insert_links_batch(conn, [
        (m1, "https://youtube.com/watch?v=1", "youtube.com", "youtube", "context"),
        (m2, "https://meet.google.com/abc-def", "meet.google.com", "other", "context"),
        (m3, "https://bit.ly/xyz", "bit.ly", "other", "context"),
    ])


class TestExportWithExclusions:
    def test_default_export_excludes(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_mixed_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out)
        # meet.google.com and bit.ly should be excluded by default
        assert count == 1

    def test_no_exclude_exports_all(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_mixed_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links("TestGroup", output_path=out, exclude_domains=[])
        assert count == 3

    def test_custom_exclude_list(self, temp_db, tmp_path):
        group_id = db.get_or_create_group("TestGroup")
        with db.get_connection() as conn:
            _setup_group_with_mixed_links(conn, group_id)

        out = str(tmp_path / "out.csv")
        _, count = export_links(
            "TestGroup", output_path=out, exclude_domains=["youtube.com"]
        )
        # only youtube excluded, meet.google.com and bit.ly pass through
        assert count == 2
