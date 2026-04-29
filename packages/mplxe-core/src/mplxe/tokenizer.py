"""Tokenizer interface and a simple default implementation.

The default tokenizer is intentionally light: it segments on whitespace
and a small set of punctuation only, so it can run without any external
NLP engine. Real morphological analysis (e.g. SudachiPy) can be plugged
in by providing any object that satisfies the `Tokenizer` Protocol.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from .models import Token


@runtime_checkable
class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[Token]: ...


# Punctuation/whitespace characters that act as token boundaries.
# Includes both ASCII and common Japanese variants.
_DELIMS = r"\s・、。「」『』【】（）()／/,，.\\|｜:：;；!?！？"
_TOKEN_RE = re.compile(rf"[^{_DELIMS}]+")


class SimpleTokenizer:
    """Whitespace + punctuation tokenizer.

    Returns spans of non-delimiter characters with their byte-aligned
    start/end offsets in the input string. No morphological analysis is
    performed — Japanese phrases like "鶏もも肉" stay as a single token.
    Downstream matchers do their own substring / regex matching, so this
    is sufficient for v1.
    """

    def tokenize(self, text: str) -> list[Token]:
        return [
            Token(text=m.group(), start=m.start(), end=m.end())
            for m in _TOKEN_RE.finditer(text)
        ]
