from qq_hermes_bridge import matching


def test_normalize_spaces_collapses_whitespace():
    assert matching.normalize_spaces("  a\n b\t c  ") == "a b c"


def test_phrase_matching_preserves_case_option_and_first_match_order():
    assert matching.contains_phrase("Esti 在吗", "esti", case_sensitive=False)
    assert not matching.contains_phrase("Esti 在吗", "esti", case_sensitive=True)
    assert matching.first_phrase_match("今天精神状态笑死", ["笑死", "精神状态"]) == "笑死"
    assert matching.contains_any_phrase("今天精神状态笑死", ["困", "精神状态"])


def test_exact_normalized_match_is_whitespace_and_case_insensitive_by_default():
    assert matching.exact_normalized_match("  JRRP  ", "jrrp")
    assert not matching.exact_normalized_match("jrrp 一下", "jrrp")


def test_strip_text_mentions_handles_plain_and_cq_mentions():
    text = "@Esti1ord [CQ:at,qq=3975680980] 武汉怎么样"
    assert matching.strip_text_mentions(text) == "武汉怎么样"


def test_extract_keyword_candidates_expands_cjk_ngrams():
    keywords = matching.extract_keyword_candidates("@Esti 武汉读研体验怎么样", min_len=2)

    assert "武汉读研体验怎么样" in keywords
    assert "武汉" in keywords
    assert "读研" in keywords
    assert "体验" in keywords
    assert "@Esti" not in keywords


def test_compact_text_key_removes_punctuation_and_spaces():
    assert matching.compact_text_key("笑死，这个 说法！") == "笑死这个说法"
    assert matching.compact_text_key("A B", remove_punctuation=False) == "ab"
