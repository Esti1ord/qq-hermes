from qq_hermes_bridge import model_output


def test_model_wants_silent_handles_empty_and_declared_silence_variants():
    for text in ["", "  ", "（空字符串）", "'empty string'", "不回复", "沉默"]:
        assert model_output.model_wants_silent(text)

    assert not model_output.model_wants_silent("这句可以发")


def test_output_is_fallback_matches_common_bad_fallbacks():
    fallback_outputs = [
        "我看到了 不过暂时没想好怎么回",
        "先略过 我还没组织好",
        "这条我先不硬接",
        "我有点卡住了 等会再说",
        "我这边卡了一下 等会再试",
        "刚才没跑顺 稍后再问我一次",
        "这下没处理好 先缓一下",
        "我这边断了一下 等会再来",
        "",
    ]
    for output in fallback_outputs:
        assert model_output.output_is_fallback(output)
        assert model_output.proactive_output_is_fallback(output)

    assert not model_output.output_is_fallback("笑死 这个说法太河南服务器了")
    assert not model_output.proactive_output_is_fallback("笑死 这个说法太河南服务器了")


def test_proactive_repeated_bot_wording_suppresses_exact_normalized_repeat():
    assert model_output.proactive_output_repeats_recent_bot_wording(
        "笑死 这个说法太河南服务器了",
        ["笑死，这个说法太河南服务器了。"],
    )


def test_proactive_repeated_bot_wording_suppresses_strong_containment():
    assert model_output.proactive_output_repeats_recent_bot_wording(
        "这群今天像集体低电量",
        ["这群今天像集体低电量 先充会儿再说"],
    )


def test_proactive_repeated_bot_wording_allows_short_common_overlap():
    for output in ["笑死", "确实", "我在", "离谱"]:
        assert not model_output.proactive_output_repeats_recent_bot_wording(
            output,
            [f"{output} 这个说法太河南服务器了"],
        )


def test_proactive_repeated_bot_wording_allows_distinct_reply():
    assert not model_output.proactive_output_repeats_recent_bot_wording(
        "那还是先看晚上吃什么",
        ["这群今天像集体低电量"],
    )
