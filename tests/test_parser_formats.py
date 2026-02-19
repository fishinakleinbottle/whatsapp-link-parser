"""Tests for multi-format WhatsApp export parsing."""
import tempfile
from datetime import datetime
from pathlib import Path

from wa_link_parser.parser import parse_chat_file, _detect_format, FORMATS


class TestFormatDetection:
    def test_detects_indian_format(self):
        lines = [
            "[20/10/2025, 10:28:45 AM] ~ Messages and calls are end-to-end encrypted.",
            "[20/10/2025, 10:29:01 AM] ~ Burhan Yousuf: Hey everyone!",
        ]
        fmt = _detect_format(lines)
        assert fmt is not None
        assert fmt.name == "india_bracket_tilde"

    def test_detects_us_bracket_format(self):
        lines = [
            "[1/15/25, 3:45:30 PM] Messages and calls are end-to-end encrypted.",
            "[1/15/25, 3:46:00 PM] John Smith: Hello everyone!",
        ]
        fmt = _detect_format(lines)
        assert fmt is not None
        assert fmt.name == "us_bracket_short_year"

    def test_detects_no_bracket_24h_format(self):
        lines = [
            "20/10/2025, 14:30 - Messages and calls are end-to-end encrypted.",
            "20/10/2025, 14:31 - Alice: Hey there!",
        ]
        fmt = _detect_format(lines)
        assert fmt is not None
        assert fmt.name == "intl_no_bracket_24h"

    def test_detects_us_no_bracket_12h(self):
        lines = [
            "1/15/25, 3:45 PM - Messages and calls are end-to-end encrypted.",
            "1/15/25, 3:46 PM - John Smith: Hello!",
        ]
        fmt = _detect_format(lines)
        assert fmt is not None
        assert fmt.name == "us_no_bracket_12h"

    def test_detects_german_format(self):
        lines = [
            "20.10.25, 14:30 - Nachrichten sind verschlüsselt.",
            "20.10.25, 14:31 - Hans: Hallo!",
        ]
        fmt = _detect_format(lines)
        assert fmt is not None
        assert fmt.name == "german_dots"

    def test_returns_none_for_garbage(self):
        lines = ["This is not a chat file", "Just random text"]
        fmt = _detect_format(lines)
        assert fmt is None


class TestMultiFormatParsing:
    def _write_and_parse(self, content):
        """Write content to a temp file and parse it."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(content)
            f.flush()
            return parse_chat_file(f.name)

    def test_indian_format_full(self):
        content = (
            "[20/10/2025, 10:28:45 AM] ~ Messages and calls are end-to-end encrypted.\n"
            "[20/10/2025, 10:29:01 AM] ~ Burhan Yousuf: Hey everyone!\n"
            "[20/10/2025, 10:29:15 AM] ~ Narendra: Check this https://youtube.com\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert messages[0].is_system
        assert messages[1].sender == "Burhan Yousuf"
        assert messages[2].sender == "Narendra"

    def test_no_bracket_24h_format(self):
        content = (
            "20/10/2025, 14:30 - Messages and calls are end-to-end encrypted.\n"
            "20/10/2025, 14:31 - Alice: Hey there!\n"
            "20/10/2025, 14:32 - Bob: How are you?\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert messages[0].is_system
        assert messages[1].sender == "Alice"
        assert messages[1].timestamp == datetime(2025, 10, 20, 14, 31)

    def test_us_no_bracket_12h_format(self):
        content = (
            "1/15/25, 3:45 PM - Messages and calls are end-to-end encrypted.\n"
            "1/15/25, 3:46 PM - John Smith: Hello!\n"
            "1/15/25, 3:47 PM - Jane: Hi John!\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert messages[0].is_system
        assert messages[1].sender == "John Smith"
        assert messages[1].timestamp == datetime(2025, 1, 15, 15, 46)

    def test_german_format(self):
        content = (
            "20.10.25, 14:30 - Nachrichten sind verschlüsselt.\n"
            "20.10.25, 14:31 - Hans: Hallo!\n"
            "20.10.25, 14:32 - Greta: Guten Tag!\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert messages[0].is_system
        assert messages[1].sender == "Hans"

    def test_multiline_in_no_bracket_format(self):
        content = (
            "20/10/2025, 14:30 - Messages and calls are end-to-end encrypted.\n"
            "20/10/2025, 14:31 - Alice: This is a long message\n"
            "that continues on the next line\n"
            "and even a third line\n"
            "20/10/2025, 14:32 - Bob: Got it!\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert "continues on the next line" in messages[1].raw_text
        assert "third line" in messages[1].raw_text

    def test_us_bracket_short_year_format(self):
        content = (
            "[1/15/25, 3:45:30 PM] Messages and calls are end-to-end encrypted.\n"
            "[1/15/25, 3:46:00 PM] John Smith: Hello!\n"
            "[1/15/25, 3:47:00 PM] Jane: Hi!\n"
        )
        messages = self._write_and_parse(content)
        assert len(messages) == 3
        assert messages[0].is_system
        assert messages[1].sender == "John Smith"
        assert messages[1].timestamp == datetime(2025, 1, 15, 15, 46, 0)
