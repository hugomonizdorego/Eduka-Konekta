"""Client-side chat rules: word filter and sending rate limit."""

from __future__ import annotations

import re
import time
from collections import deque

# Explicit insults only. Everyday words that are also used as insults (for
# example animal names) are left out so normal lessons are not censored;
# teachers can add school-specific words in Settings.
DEFAULT_BLOCKED_WORDS = (
    "bangsat", "bajingan", "keparat", "brengsek", "goblok", "tolol", "kontol", "memek",
    "ngentot", "jancok", "jancuk", "fuck", "fucking", "shit", "bitch", "asshole", "bastard",
    "caralho", "porra", "merda", "puta", "foda-se", "fdp",
)


def parse_word_list(value: str) -> list[str]:
    words = []
    for item in re.split(r"[,;\n]+", value):
        word = item.strip().casefold()
        if word and len(word) <= 40 and word not in words:
            words.append(word)
    return words[:200]


def filter_text(text: str, extra_words: list[str] | tuple[str, ...] = ()) -> str:
    """Mask blocked words as the first letter followed by asterisks."""
    words = {word.casefold() for word in (*DEFAULT_BLOCKED_WORDS, *extra_words) if word}
    if not words or not text:
        return text
    pattern = re.compile(
        r"(?<![\w])(" + "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True)) + r")(?![\w])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: match.group(0)[0] + "*" * (len(match.group(0)) - 1), text)


class RateLimiter:
    """Allow at most ``limit`` actions per ``window`` seconds (anti-spam)."""

    def __init__(self, limit: int = 6, window: float = 10.0, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        now = self.clock()
        while self._events and now - self._events[0] > self.window:
            self._events.popleft()
        if len(self._events) >= self.limit:
            return False
        self._events.append(now)
        return True
