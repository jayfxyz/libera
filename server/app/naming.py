"""Making metadata safe to use in a file or folder name."""

from __future__ import annotations

import re
import unicodedata

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ASIN_SUFFIX = re.compile(r" \[([^\[\]]+)\]$")  # the " [B002UZMLXM]" a file or folder name ends with
_COLON = re.compile(r"\s*:\s*")
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?=\.|$)", re.IGNORECASE)  # Windows device names
MAX_NAME_BYTES = 200  # filesystems allow 255 bytes per name; leave room for " - 01 - chapter", ".part"


def clean_name(s: str) -> str:
    """Metadata made safe inside a file or folder name: "Dune: Part One" → "Dune - Part One", no "/" etc.
    Accents are composed (NFC) so a name reads the same on Linux, Windows and macOS shares."""
    return _UNSAFE.sub("_", _COLON.sub(" - ", unicodedata.normalize("NFC", s)))


def sanitize_filename(s: str, reserve: int = 0) -> str:
    """A whole file or folder name: cleaned, without leading or trailing dots and spaces (no "..", no hidden
    folders, nothing Windows or SMB shares reject), and at most MAX_NAME_BYTES - reserve of UTF-8."""
    s = clean_name(s).strip(" .")
    s = s.encode()[:MAX_NAME_BYTES - reserve].decode(errors="ignore").rstrip(" .")
    return _RESERVED.sub(r"\1_", s) or "audiobook"


def legacy_file_name(title: str) -> str:
    """What a title was called on disk before November 2026, when ":" became "_" (e.g. "Found_ Book")."""
    return _UNSAFE.sub("_", title).strip()[:200]
