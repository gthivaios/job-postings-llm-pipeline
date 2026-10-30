"""Text preparation applied before translation."""

import re
import unicodedata

import emoji

_URL = re.compile(r"https?://\S+|www\.\S+")
_WS = re.compile(r"\s+")


def normalize_text(text: str | None, form: str = "NFKD") -> str:
    """Normalize Unicode, strip URLs and emojis, collapse whitespace."""
    if not text:
        return ""
    cleaned = unicodedata.normalize(form, text)
    cleaned = _URL.sub("", cleaned)
    cleaned = emoji.replace_emoji(cleaned, replace="")
    return _WS.sub(" ", cleaned).strip()


def split_text_into_chunks(text: str, max_words: int, max_chars: int) -> list[str]:
    """Split text into chunks respecting both a word-count and a character limit.

    A single word longer than max_chars becomes its own chunk (never split mid-word,
    never an empty chunk).
    """
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0

    for word in text.split():
        added = len(word) + (1 if current else 0)  # +1 for the joining space
        if current and (len(current) >= max_words or current_chars + added > max_chars):
            chunks.append(" ".join(current))
            current, current_chars = [], 0
            added = len(word)
        current.append(word)
        current_chars += added

    if current:
        chunks.append(" ".join(current))
    return chunks
