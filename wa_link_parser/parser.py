import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from wa_link_parser.models import ParsedMessage


@dataclass
class ChatFormat:
    """Definition of a WhatsApp export timestamp/message format."""
    name: str
    # Regex that captures (datetime_str, sender, text) for regular messages
    message_pattern: re.Pattern
    # Regex that captures (datetime_str, text) for system/headerless lines
    system_pattern: re.Pattern
    # strptime format for the captured datetime string
    timestamp_format: str
    # Index positions: (datetime_groups, sender_group, text_group)
    # datetime_groups are concatenated with space before parsing


# --- Format definitions ---
# Each format covers a known WhatsApp export locale/OS variant.
# The message_pattern must capture: group(1)=datetime, group(2)=sender, group(3)=text
# The system_pattern must capture: group(1)=datetime, group(2)=text

FORMATS = [
    # Format 1: India / some Android — [DD/MM/YYYY, H:MM:SS AM/PM] ~ Sender: text
    ChatFormat(
        name="india_bracket_tilde",
        message_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s~\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s~\s(.*)'
        ),
        timestamp_format="%d/%m/%Y, %I:%M:%S %p",
    ),
    # Format 2: US / iOS — [M/DD/YY, H:MM:SS AM/PM] Sender: text (no tilde)
    ChatFormat(
        name="us_bracket_short_year",
        message_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s(.*)'
        ),
        timestamp_format="%m/%d/%y, %I:%M:%S %p",
    ),
    # Format 3: Android international — DD/MM/YYYY, HH:MM - Sender: text (no brackets, 24h)
    ChatFormat(
        name="intl_no_bracket_24h",
        message_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2})\s-\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2})\s-\s(.*)'
        ),
        timestamp_format="%d/%m/%Y, %H:%M",
    ),
    # Format 4: US Android — M/DD/YY, H:MM AM/PM - Sender: text (no brackets)
    ChatFormat(
        name="us_no_bracket_12h",
        message_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2}\s[APap][Mm])\s-\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2}\s[APap][Mm])\s-\s(.*)'
        ),
        timestamp_format="%m/%d/%y, %I:%M %p",
    ),
    # Format 5: European Android — DD/MM/YY, HH:MM - Sender: text (short year, 24h)
    ChatFormat(
        name="eu_no_bracket_short_24h",
        message_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2})\s-\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'(\d{1,2}/\d{1,2}/\d{2},\s\d{1,2}:\d{2})\s-\s(.*)'
        ),
        timestamp_format="%d/%m/%y, %H:%M",
    ),
    # Format 6: German — DD.MM.YY, HH:MM - Sender: text (dots, 24h)
    ChatFormat(
        name="german_dots",
        message_pattern=re.compile(
            r'(\d{1,2}\.\d{1,2}\.\d{2},\s\d{1,2}:\d{2})\s-\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'(\d{1,2}\.\d{1,2}\.\d{2},\s\d{1,2}:\d{2})\s-\s(.*)'
        ),
        timestamp_format="%d.%m.%y, %H:%M",
    ),
    # Format 7: Bracket no tilde, full year — [DD/MM/YYYY, H:MM:SS AM/PM] Sender: text
    ChatFormat(
        name="bracket_no_tilde_full_year",
        message_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s(.+?):\s(.*)'
        ),
        system_pattern=re.compile(
            r'\[(\d{1,2}/\d{1,2}/\d{4},\s\d{1,2}:\d{2}:\d{2}\s[APap][Mm])\]\s(.*)'
        ),
        timestamp_format="%d/%m/%Y, %I:%M:%S %p",
    ),
]


def _try_parse_timestamp(ts_str: str, fmt: str) -> Optional[datetime]:
    """Try to parse a timestamp string, return None on failure."""
    try:
        return datetime.strptime(ts_str, fmt)
    except ValueError:
        return None


def _detect_format(lines: List[str]) -> Optional[ChatFormat]:
    """Auto-detect the WhatsApp export format by trying each format on the first lines.

    Returns the format that successfully matches the most lines (minimum 1 match).
    """
    # Check up to the first 20 non-empty lines
    sample = [l for l in lines[:30] if l.strip()]

    best_format = None
    best_score = 0

    for fmt in FORMATS:
        score = 0
        for line in sample:
            msg_match = fmt.message_pattern.match(line)
            if msg_match:
                ts = _try_parse_timestamp(msg_match.group(1), fmt.timestamp_format)
                if ts:
                    score += 1
                continue
            sys_match = fmt.system_pattern.match(line)
            if sys_match:
                ts = _try_parse_timestamp(sys_match.group(1), fmt.timestamp_format)
                if ts:
                    score += 1

        if score > best_score:
            best_score = score
            best_format = fmt

    return best_format if best_score > 0 else None


def _parse_with_format(lines: List[str], fmt: ChatFormat) -> List[ParsedMessage]:
    """Parse all lines using a specific detected format."""
    messages = []

    for line in lines:
        # Try matching as a regular message (has sender:)
        msg_match = fmt.message_pattern.match(line)
        if msg_match:
            ts_str, sender, text = msg_match.group(1), msg_match.group(2), msg_match.group(3)
            timestamp = _try_parse_timestamp(ts_str, fmt.timestamp_format)
            if timestamp:
                messages.append(ParsedMessage(
                    timestamp=timestamp,
                    sender=sender,
                    raw_text=text,
                    is_system=False,
                ))
                continue

        # Try matching as a system message (timestamp but no sender:)
        sys_match = fmt.system_pattern.match(line)
        if sys_match:
            ts_str, text = sys_match.group(1), sys_match.group(2)
            timestamp = _try_parse_timestamp(ts_str, fmt.timestamp_format)
            if timestamp:
                messages.append(ParsedMessage(
                    timestamp=timestamp,
                    sender="__system__",
                    raw_text=text,
                    is_system=True,
                ))
                continue

        # Continuation line -- append to previous message
        if messages:
            messages[-1].raw_text += "\n" + line

    return messages


def parse_chat_file(file_path: str) -> List[ParsedMessage]:
    """Parse a WhatsApp chat export file into structured messages.

    Auto-detects the export format from the file content. Supports multiple
    WhatsApp export formats including:
    - Indian format: [DD/MM/YYYY, H:MM:SS AM/PM] ~ Sender: text
    - US format: [M/DD/YY, H:MM:SS AM/PM] Sender: text
    - European format: DD/MM/YYYY, HH:MM - Sender: text
    - Android US: M/DD/YY, H:MM AM/PM - Sender: text
    - German format: DD.MM.YY, HH:MM - Sender: text
    - And more variants

    Falls back to the whatstk library if auto-detection fails.

    Args:
        file_path: Path to the WhatsApp .txt export file.

    Returns:
        List of ParsedMessage objects with timestamp, sender, text, and system flag.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If no messages could be parsed from the file.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Chat file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Try auto-detection across all known formats
    fmt = _detect_format(lines)
    if fmt:
        messages = _parse_with_format(lines, fmt)
        if messages:
            return messages

    # Fallback to whatstk
    messages = _parse_with_whatstk(file_path)

    if not messages:
        preview = "\n".join(lines[:5])
        raise ValueError(
            f"Could not parse any messages from the file. First few lines:\n{preview}\n"
            "Please check the file format."
        )

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
