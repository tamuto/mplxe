"""Text preprocessing utilities."""
from __future__ import annotations

import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def preprocess(text: str | None) -> str:
    """Apply Unicode and whitespace normalization.

    - NFKC: full-width digits/letters/punctuation become half-width, and
      compatibility characters decompose to canonical forms.
    - Whitespace runs collapse to a single space; leading/trailing trimmed.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()
