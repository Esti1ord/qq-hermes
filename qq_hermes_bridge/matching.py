"""Shared text matching primitives for QQ/Hermes bridge helpers.

The helpers here intentionally stay small and stateless. Callers own policy
(deciding which phrases matter, scoring, throttling, routing) while this module
keeps normalization and simple phrase matching consistent.
"""
from __future__ import annotations

import re
from collections.abc import Iterable


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def strip_text_mentions(text: str) -> str:
    clean = re.sub(r"\[CQ:at,qq=\d+(?:,[^\]]*)?\]", " ", str(text or ""))
    clean = re.sub(r"@\S+", " ", clean)
    return normalize_spaces(clean)


def contains_phrase(text: str, phrase: str, *, case_sensitive: bool = True) -> bool:
    if not phrase:
        return False
    haystack = str(text or "")
    needle = str(phrase)
    if not case_sensitive:
        haystack = haystack.lower()
        needle = needle.lower()
    return needle in haystack


def first_phrase_match(text: str, phrases: Iterable[str], *, case_sensitive: bool = True) -> str:
    for phrase in phrases:
        if contains_phrase(text, str(phrase or ""), case_sensitive=case_sensitive):
            return str(phrase)
    return ""


def contains_any_phrase(text: str, phrases: Iterable[str], *, case_sensitive: bool = True) -> bool:
    return bool(first_phrase_match(text, phrases, case_sensitive=case_sensitive))


def exact_normalized_match(text: str, phrase: str, *, case_sensitive: bool = False) -> bool:
    left = normalize_spaces(text)
    right = normalize_spaces(phrase)
    if not case_sensitive:
        left = left.lower()
        right = right.lower()
    return left == right


def extract_keyword_candidates(
    text: str,
    *,
    min_len: int,
    expand_cjk: bool = True,
    max_cjk_ngram: int = 4,
) -> set[str]:
    clean = strip_text_mentions(text)
    raw_keywords = [kw for kw in re.findall(r"[一-鿿A-Za-z0-9_]{%d,}" % min_len, clean) if kw]
    keywords: set[str] = set(raw_keywords)
    if not expand_cjk:
        return keywords
    for kw in raw_keywords:
        if re.fullmatch(r"[一-鿿]+", kw) and len(kw) > min_len:
            max_n = min(max_cjk_ngram, len(kw))
            for n in range(min_len, max_n + 1):
                for i in range(0, len(kw) - n + 1):
                    keywords.add(kw[i:i + n])
    return keywords


def compact_text_key(text: str, *, remove_punctuation: bool = True, lower: bool = True) -> str:
    clean = str(text or "")
    if lower:
        clean = clean.lower()
    if remove_punctuation:
        clean = re.sub(r"[\s，,。.!！?？；;：:、（）()\[\]【】\"'“”‘’]+", "", clean)
    else:
        clean = re.sub(r"\s+", "", clean)
    return clean
