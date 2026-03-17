"""
SmartSafe V27 - Content Safety & Variation Policy (Phase B)

This module provides:
- Template variant parsing + rotation
- Lightweight spintax ([[a|b|c]]) for controlled variation
- Bounded text jitter (very conservative, meaning-preserving)
- Similarity + entropy heuristics to reduce "bot-like" repetition
"""

from __future__ import annotations

import math
import random
import re
import zlib
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple


_RE_WS = re.compile(r"\s+")
_RE_NUM = re.compile(r"\d+")
_RE_WORD = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_RE_SPINTAX = re.compile(r"\[\[([^\[\]]+?)\]\]")


def split_template_variants(raw: str) -> List[str]:
    """
    Split a user-provided template string into multiple variants.

    Supported separators (picked to be human-friendly in a textbox):
    - A line containing only: ---  (common markdown separator)
    - A line containing only: ===
    - The token: |||
    """
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        return []

    # First: explicit token separator
    if "|||" in text:
        parts = [p.strip() for p in text.split("|||")]
        return [p for p in parts if p]

    # Then: line separator blocks
    lines = text.split("\n")
    parts: List[str] = []
    buf: List[str] = []

    def flush():
        s = "\n".join(buf).strip()
        if s:
            parts.append(s)
        buf.clear()

    for line in lines:
        t = line.strip()
        if t in {"---", "==="}:
            flush()
            continue
        buf.append(line)

    flush()
    return parts or [text.strip()]


def apply_spintax(text: str, rng: random.Random) -> str:
    """
    Replace occurrences of [[a|b|c]] by picking one option.

    Notes:
    - Non-nested by design (keeps it predictable for operators).
    - Does not touch {placeholders} used by contact variables.
    """

    def _repl(m: re.Match) -> str:
        body = m.group(1) or ""
        opts = [o.strip() for o in body.split("|") if o.strip()]
        if not opts:
            return ""
        return rng.choice(opts)

    # Apply a small bounded number of replacements to avoid pathological cases.
    out = text or ""
    for _ in range(12):
        if not _RE_SPINTAX.search(out):
            break
        out = _RE_SPINTAX.sub(_repl, out)
    return out


def normalize_for_similarity(text: str) -> str:
    """
    Normalize message text so superficial differences (numbers, whitespace, casing)
    don't defeat similarity checks.
    """
    s = (text or "").strip().lower()
    if not s:
        return ""

    s = _RE_NUM.sub("0", s)  # phone numbers, OTP codes, amounts
    s = s.replace("\u200b", "")  # zero-width space
    s = _RE_WS.sub(" ", s)
    return s.strip()


def token_entropy_bits(text: str) -> float:
    """
    Shannon entropy (bits) of word tokens.

    Lower values imply repetitive wording. For very short messages this is noisy,
    so callers should treat it as a heuristic signal only.
    """
    s = normalize_for_similarity(text)
    if not s:
        return 0.0
    tokens = _RE_WORD.findall(s)
    if not tokens:
        return 0.0
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = float(len(tokens))
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(max(p, 1e-12))
    return float(h)


def max_similarity_ratio(text: str, history: Iterable[str]) -> float:
    """
    Return the maximum similarity ratio between `text` and any entry in `history`.
    Uses a cheap, stable n-gram hashing approach (Jaccard over 3-grams).
    """
    base = normalize_for_similarity(text)
    if not base:
        return 0.0

    def grams(s: str, n: int = 3) -> set[int]:
        s2 = f" {s} "
        if len(s2) < n:
            return set()
        out: set[int] = set()
        for i in range(len(s2) - n + 1):
            g = s2[i : i + n].encode("utf-8", errors="ignore")
            out.add(int(zlib.crc32(g) & 0xFFFFFFFF))
        return out

    g_base = grams(base)
    if not g_base:
        return 0.0

    best = 0.0
    for prev in history:
        p = normalize_for_similarity(prev)
        if not p:
            continue
        g_prev = grams(p)
        if not g_prev:
            continue
        inter = len(g_base & g_prev)
        union = len(g_base | g_prev)
        ratio = (inter / union) if union else 0.0
        if ratio > best:
            best = ratio
            if best >= 0.999:
                return 1.0
    return float(best)


def bounded_jitter(text: str, rng: random.Random) -> str:
    """
    Apply a *very conservative* jitter that keeps meaning intact.

    Jitter operations are intentionally limited:
    - normalize whitespace
    - optional trailing punctuation toggle
    - optional greeting prefix tweak (only if message starts with common greeting)
    """
    s = (text or "").strip()
    if not s:
        return ""

    s = _RE_WS.sub(" ", s).strip()

    # Trailing punctuation toggle
    if len(s) >= 6:
        tail = s[-1]
        if tail in {".", "!", "?"}:
            if rng.random() < 0.35:
                s = s[:-1]
        else:
            if rng.random() < 0.35:
                s = s + rng.choice([".", "!", ""])

    # Gentle greeting variations
    low = s.lower()
    greetings = [("hi ", ["hi ", "hey ", "hello "]), ("hello ", ["hello ", "hi ", "hey "]), ("hey ", ["hey ", "hi ", "hello "])]
    for prefix, opts in greetings:
        if low.startswith(prefix):
            # Replace prefix only, preserve the rest.
            rest = s[len(prefix) :]
            s = rng.choice(opts) + rest
            break

    return s


@dataclass(frozen=True)
class ContentGateDecision:
    gate: str  # PASS | ROTATE | JITTER | SLOWDOWN | BLOCK
    similarity: float
    entropy_bits: float
    risk_points: int
    delay_multiplier: float
    reason: str


class TemplateRotator:
    """
    Per-account template variant rotation.

    Rotation is memory-only and resets between jobs (intended).
    """

    def __init__(self, variants: List[str], *, seed: Optional[int] = None) -> None:
        self.variants = [v.strip() for v in (variants or []) if (v or "").strip()]
        self._rng = random.Random(seed if seed is not None else random.randint(1, 2**31 - 1))
        self._last_idx_by_account: Dict[str, int] = {}

    @classmethod
    def from_raw_template(cls, raw: str, *, seed: Optional[int] = None) -> "TemplateRotator":
        variants = split_template_variants(raw)
        if not variants:
            variants = [""]
        return cls(variants, seed=seed)

    def count(self) -> int:
        return len(self.variants)

    def pick(self, account_key: str, *, avoid_idx: Optional[int] = None) -> Tuple[int, str]:
        n = len(self.variants)
        if n <= 1:
            return 0, self.variants[0] if self.variants else ""

        last = self._last_idx_by_account.get(account_key)
        candidates = list(range(n))
        if avoid_idx is not None and avoid_idx in candidates and len(candidates) > 1:
            candidates.remove(int(avoid_idx))
        if last is not None and last in candidates and len(candidates) > 1:
            candidates.remove(int(last))

        idx = self._rng.choice(candidates) if candidates else int((last or 0) + 1) % n
        self._last_idx_by_account[account_key] = int(idx)
        return int(idx), self.variants[int(idx)]

