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

SILENT_MARKERS = {
    "<silent>",
    "[silent]",
    "silent",
    "空字符串",
    "empty string",
    "empty",
    "无",
    "none",
    "不回复",
    "不发言",
    "不插话",
    "不需要输出",
    "不需要再输出",
    "不再输出",
    "不需要回复",
    "不需要发言",
    "不需要插话",
    "无需回复",
    "无需发言",
    "无需插话",
    "不适合插话",
    "没有新的接话点",
    "没有自然接话点",
    "没话接",
    "沉默",
    "保持沉默",
}

# Short meta outputs that describe the output contract rather than a sendable
# group message. These are kept separate from longer rationale detection so
# casual sentences containing words like "不需要回复" are not suppressed by length.
PROACTIVE_SHORT_SILENCE_DECISIONS = [
    "空的输出",
    "输出为空",
    "空输出",
    "输出空字符串",
    "只输出空字符串",
    "输出 <silent>",
    "输出<silent>",
    "只输出 <silent>",
    "只输出<silent>",
]

PROACTIVE_STANDALONE_SILENCE_DECISIONS = [
    *PROACTIVE_SHORT_SILENCE_DECISIONS,
    "保持沉默",
    "不需要插话",
    "无需插话",
    "不适合插话",
    "没有新的接话点",
    "没有自然接话点",
]

PROACTIVE_CONNECTION_POINT_PHRASES = [
    "没有新的接话点",
    "没有自然接话点",
]

PROACTIVE_INSERTION_DECISION_PHRASES = [
    "不需要插话",
    "无需插话",
    "不适合插话",
]


# Phrases that can indicate a proactive silence rationale when paired with
# internal/meta context wording.
PROACTIVE_SILENCE_DECISION_PHRASES = [
    *PROACTIVE_SHORT_SILENCE_DECISIONS,
    "不需要输出",
    "不需要再输出",
    "不再输出",
    "不需要回复",
    "无需回复",
    "不需要插话",
    "无需插话",
    "不适合插话",
    "没有新的接话点",
    "没有自然接话点",
    "没话接",
]

PROACTIVE_INTERNAL_CONTEXT_PHRASES = [
    "主动发言",
    "主动接话",
    "判断结果",
    "触发原因",
    "群友之间",
    "持续讨论",
]


def _compact_phrases(phrases: Iterable[str]) -> list[str]:
    return [matching.compact_text_key(phrase) for phrase in phrases if phrase]


_COMPACT_SILENT_MARKERS = set(_compact_phrases(SILENT_MARKERS))
_COMPACT_PROACTIVE_SHORT_SILENCE_DECISIONS = set(_compact_phrases(PROACTIVE_SHORT_SILENCE_DECISIONS))
_COMPACT_PROACTIVE_STANDALONE_SILENCE_DECISIONS = _compact_phrases(PROACTIVE_STANDALONE_SILENCE_DECISIONS)
_COMPACT_PROACTIVE_CONNECTION_POINT_PHRASES = _compact_phrases(PROACTIVE_CONNECTION_POINT_PHRASES)
_COMPACT_PROACTIVE_INSERTION_DECISION_PHRASES = _compact_phrases(PROACTIVE_INSERTION_DECISION_PHRASES)
_COMPACT_PROACTIVE_SILENCE_DECISION_PHRASES = _compact_phrases(PROACTIVE_SILENCE_DECISION_PHRASES)
_COMPACT_PROACTIVE_INTERNAL_CONTEXT_PHRASES = _compact_phrases(PROACTIVE_INTERNAL_CONTEXT_PHRASES)


def model_wants_silent(output: str) -> bool:
    """Whether the model explicitly indicated silence, including quoted variants."""
    clean = re.sub(r"[（()）「」『』\"\"''`]", "", output or "").strip().lower()
    if not clean:
        return True
    compact = matching.compact_text_key(clean)
    return compact in _COMPACT_SILENT_MARKERS or any(
        matching.exact_normalized_match(clean, marker)
        for marker in SILENT_MARKERS
    )


def proactive_output_is_silence_decision(output: str) -> bool:
    """Detect proactive silence decisions or rationale text, not group messages."""
    compact = matching.compact_text_key(output)
    if not compact:
        return True
    if model_wants_silent(output):
        return True
    if "<silent>" in compact:
        return True
    if compact in _COMPACT_PROACTIVE_SHORT_SILENCE_DECISIONS:
        return True
    has_standalone_decision = matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_STANDALONE_SILENCE_DECISIONS,
        case_sensitive=False,
    )
    if has_standalone_decision and len(compact) <= 24:
        return True
    has_short_contract_phrase = matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_SHORT_SILENCE_DECISIONS,
        case_sensitive=False,
    )
    if has_short_contract_phrase and len(compact) <= 20:
        return True
    has_connection_point = matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_CONNECTION_POINT_PHRASES,
        case_sensitive=False,
    )
    has_insertion_decision = matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_INSERTION_DECISION_PHRASES,
        case_sensitive=False,
    )
    if has_connection_point and has_insertion_decision:
        return True
    has_silence_decision = matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_SILENCE_DECISION_PHRASES,
        case_sensitive=False,
    )
    if not has_silence_decision:
        return False
    return matching.contains_any_phrase(
        compact,
        _COMPACT_PROACTIVE_INTERNAL_CONTEXT_PHRASES,
        case_sensitive=False,
    )


def proactive_output_is_silence_rationale(output: str) -> bool:
    """Backward-compatible name for proactive silence-decision suppression."""
    return proactive_output_is_silence_decision(output)


def output_is_fallback(output: str) -> bool:
    clean = matching.compact_text_key(output, remove_punctuation=False, lower=False)
    if not clean:
        return True
    return matching.contains_any_phrase(clean, FALLBACK_PHRASES)


def proactive_output_should_suppress(output: str) -> bool:
    return output_is_fallback(output) or proactive_output_is_silence_decision(output)


def proactive_output_is_fallback(output: str) -> bool:
    """Backward-compatible wrapper for proactive output suppression."""
    return proactive_output_should_suppress(output)


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
