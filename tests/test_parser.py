from datetime import datetime

from parser import parse_chat_file


class TestParser:
    def test_parses_all_messages(self, sample_chat_path):
        messages = parse_chat_file(sample_chat_path)
        # 32 lines: 3 system (lines 1, 18, 28) + 24 regular messages
        # Lines 10-11 are continuations of line 9; lines 30-31 are continuations of line 29
        assert len(messages) == 27

    def test_system_message_detection(self, sample_chat_path):
        messages = parse_chat_file(sample_chat_path)
        system_msgs = [m for m in messages if m.is_system]
        assert len(system_msgs) == 3

        # First message is the encryption notice
        assert "end-to-end encrypted" in system_msgs[0].raw_text
        # "Priya Sharma added Arjun Menon"
        assert "added" in system_msgs[1].raw_text
        # "Your security code with Narendra Shenoy changed"
        assert "security code" in system_msgs[2].raw_text

    def test_system_message_sender_is_system(self, sample_chat_path):
        messages = parse_chat_file(sample_chat_path)
        system_msgs = [m for m in messages if m.is_system]
        for msg in system_msgs:
            assert msg.sender == "__system__"

    def test_multiline_message_concatenation(self, sample_chat_path):
        """Lines 9-11: 'This place is amazing...' + 'Highly recommend...' + 'The crowd is less...'"""
        messages = parse_chat_file(sample_chat_path)
        # Find the multi-line message from Narendra Shenoy about sunset views
        multiline = [m for m in messages if "amazing for sunset" in m.raw_text]
        assert len(multiline) == 1
        msg = multiline[0]
        assert "Highly recommend going around 4pm" in msg.raw_text
        assert "The crowd is less" in msg.raw_text
        assert msg.sender == "Narendra Shenoy"

    def test_url_in_continuation_line(self, sample_chat_path):
        """Line 29-31: message with URL on continuation line (reddit URL)."""
        messages = parse_chat_file(sample_chat_path)
        reddit_msgs = [m for m in messages if "reddit.com" in m.raw_text]
        assert len(reddit_msgs) == 1
        msg = reddit_msgs[0]
        assert "budget tips" in msg.raw_text.lower()
        assert msg.sender == "Narendra Shenoy"

    def test_timestamp_parsing(self, sample_chat_path):
        messages = parse_chat_file(sample_chat_path)
        first_non_system = [m for m in messages if not m.is_system][0]
        assert first_non_system.timestamp == datetime(2025, 10, 20, 10, 29, 1)

    def test_sender_extraction(self, sample_chat_path):
        messages = parse_chat_file(sample_chat_path)
        senders = set(m.sender for m in messages if not m.is_system)
        assert senders == {"Burhan Yousuf", "Narendra Shenoy", "Priya Sharma", "Arjun Menon"}

    def test_file_not_found(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            parse_chat_file("/nonexistent/file.txt")
