import re
from datetime import datetime
from pathlib import Path
from typing import List

from models import ParsedMessage

# Matches: [DD/MM/YYYY, H:MM:SS AM/PM] ~ SenderName: message text
MESSAGE_PATTERN = re.compile(
    r'\[(\d{2}/\d{2}/\d{4}),\s(\d{1,2}:\d{2}:\d{2}\s[AP]M)\]\s~\s(.+?):\s(.*)'
)

# Matches any line starting with the timestamp bracket (message or system)
TIMESTAMP_PATTERN = re.compile(
    r'\[(\d{2}/\d{2}/\d{4}),\s(\d{1,2}:\d{2}:\d{2}\s[AP]M)\]\s~\s(.*)'
)

TIMESTAMP_FORMAT = "%d/%m/%Y %I:%M:%S %p"


def _parse_timestamp(date_str, time_str):
    """Parse date and time strings into a datetime object."""
    return datetime.strptime(f"{date_str} {time_str}", TIMESTAMP_FORMAT)


def parse_chat_file(file_path: str) -> List[ParsedMessage]:
    """Parse a WhatsApp chat export file using regex.

    Primary parser: regex-based (handles system messages and multi-line correctly).
    Falls back to whatstk if regex finds no messages.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Chat file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    messages = _parse_with_regex(lines)

    if not messages:
        messages = _parse_with_whatstk(file_path)

    if not messages:
        preview = "\n".join(lines[:5])
        raise ValueError(
            f"Could not parse any messages from the file. First few lines:\n{preview}\n"
            "Please check the file format."
        )

    return messages


def _parse_with_regex(lines: List[str]) -> List[ParsedMessage]:
    """Parse lines using regex. Handles multi-line messages and system messages."""
    messages = []

    for line in lines:
        # Try matching as a regular message (has sender:)
        msg_match = MESSAGE_PATTERN.match(line)
        if msg_match:
            date_str, time_str, sender, text = msg_match.groups()
            timestamp = _parse_timestamp(date_str, time_str)
            messages.append(ParsedMessage(
                timestamp=timestamp,
                sender=sender,
                raw_text=text,
                is_system=False,
            ))
            continue

        # Try matching as a system message (timestamp but no sender:)
        ts_match = TIMESTAMP_PATTERN.match(line)
        if ts_match:
            date_str, time_str, text = ts_match.groups()
            timestamp = _parse_timestamp(date_str, time_str)
            messages.append(ParsedMessage(
                timestamp=timestamp,
                sender="__system__",
                raw_text=text,
                is_system=True,
            ))
            continue

        # Continuation line — append to previous message
        if messages:
            messages[-1].raw_text += "\n" + line

    return messages


def _parse_with_whatstk(file_path: str) -> List[ParsedMessage]:
    """Fallback parser using whatstk library."""
    try:
        from whatstk import WhatsAppChat

        chat = WhatsAppChat.from_source(
            filepath=file_path,
            hformat="[%d/%m/%Y, %I:%M:%S %p] ~ %name:"
        )
        df = chat.df

        messages = []
        for _, row in df.iterrows():
            messages.append(ParsedMessage(
                timestamp=row["date"].to_pydatetime(),
                sender=row["username"],
                raw_text=row["message"],
                is_system=False,
            ))
        return messages
    except Exception:
        return []
