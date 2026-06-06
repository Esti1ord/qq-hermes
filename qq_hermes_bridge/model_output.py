"""Model output filters for reply generation."""
from __future__ import annotations

import re
from collections.abc import Iterable

from . import matching

FALLBACK_PHRASES = [
    "我看到了不过暂时没想好怎么回",
    "我还没组织好",
    "这条我先不硬接",
    "我有点卡住了等会再说",
    "我这边卡了一下等会再试",
    "刚才没跑顺稍后再问我一次",
    "这下没处理好先缓一下",
    "我这边断了一下等会再来",
    "暂时没想好",
    "没想好怎么回",
    "还没组织好",
    "有点卡住",
    "没处理好",
]

SILENT_MARKERS = {"空字符串", "empty string", "empty", "无", "none", "不回复", "不插话", "沉默"}


def model_wants_silent(output: str) -> bool:
    """Whether the model explicitly indicated silence, including quoted variants."""
    clean = re.sub(r"[（()）「」『』\"\"'']", "", output or "").strip().lower()
    if not clean:
        return True
    return any(matching.exact_normalized_match(clean, marker) for marker in SILENT_MARKERS)


def output_is_fallback(output: str) -> bool:
    clean = matching.compact_text_key(output, remove_punctuation=False, lower=False)
    if not clean:
        return True
    return matching.contains_any_phrase(clean, FALLBACK_PHRASES)


def proactive_output_is_fallback(output: str) -> bool:
    return output_is_fallback(output)


def normalize_repetition_text(text: str) -> str:
    """Normalize generated text for conservative repeated-wording checks."""
    return matching.compact_text_key(text)


def text_ngrams(text: str, n: int = 3) -> set[str]:
    clean = normalize_repetition_text(text)
    if not clean:
        return set()
    if len(clean) <= n:
        return {clean}
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


def proactive_output_repeats_recent_bot_wording(
    output: str,
    recent_bot_outputs: Iterable[str],
    *,
    min_key_chars: int = 8,
    min_ngram_chars: int = 12,
    ngram: int = 3,
    overlap_threshold: float = 0.82,
) -> bool:
    """Return True when a proactive reply substantially repeats recent bot wording."""
    clean = normalize_repetition_text(output)
    if len(clean) < min_key_chars:
        return False

    output_ngrams = text_ngrams(clean, n=ngram) if len(clean) >= min_ngram_chars else set()
    for recent in recent_bot_outputs:
        old = normalize_repetition_text(recent)
        if len(old) < min_key_chars:
            continue
        if clean == old:
            return True
        shorter, longer = sorted((clean, old), key=len)
        if len(shorter) >= min_key_chars and shorter in longer:
            return True
        if len(clean) < min_ngram_chars or len(old) < min_ngram_chars:
            continue
        old_ngrams = text_ngrams(old, n=ngram)
        if not output_ngrams or not old_ngrams:
            continue
        overlap = len(output_ngrams & old_ngrams) / max(1, min(len(output_ngrams), len(old_ngrams)))
        if overlap >= overlap_threshold:
            return True
    return False
