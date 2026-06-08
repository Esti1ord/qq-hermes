from qq_hermes_bridge import model_output


def test_model_wants_silent_handles_empty_and_declared_silence_variants():
    for text in ["", "  ", "（空字符串）", "'empty string'", "<SILENT>", "不回复", "沉默"]:
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
        assert model_output.proactive_output_should_suppress(output)
        assert model_output.proactive_output_is_fallback(output)

    assert not model_output.output_is_fallback("笑死 这个说法太河南服务器了")
    assert not model_output.proactive_output_should_suppress("笑死 这个说法太河南服务器了")
    assert not model_output.proactive_output_is_fallback("笑死 这个说法太河南服务器了")


def test_proactive_silence_decision_suppresses_markers_and_meta_outputs():
    suppressed = [
        "<SILENT>",
        "输出 <SILENT> 即可",
        "<SILENT>（保持沉默）",
        "只输出要发到群里的内容；如果不发言，只输出 <SILENT> 这个标记。",
        "保持沉默",
        "不合适就保持沉默",
        "只输出空字符串就行",
        "不适合插话了",
        "当前话题没有自然接话点了 不需要插话",
        "大家聊得挺顺 没有新的接话点 不需要插话",
        "当前话题已经在自然延续了 没有新的接话点 所以不需要插话",
    ]

    for output in suppressed:
        assert model_output.proactive_output_should_suppress(output), output
        assert model_output.proactive_output_is_silence_decision(output), output


def test_proactive_silence_decision_allows_natural_phrase_overlap():
    allowed = [
        "他这个你不需要回复太认真 笑死",
        "这个我也没话接了 但可以换个话题",
        "这上下文不需要回复太认真 笑死",
        "当前话题不需要回复太认真",
        "这波不需要输出太高 先保命",
    ]

    for output in allowed:
        assert not model_output.proactive_output_should_suppress(output), output
        assert not model_output.proactive_output_is_silence_decision(output), output


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


def test_proactive_silence_rationale_is_suppressed():
    leaked = "空的输出是正确的——这个主动发言判断的结果就是当前话题已经是持续讨论 群友之间在不断回应，所以没有新的接话点不需要再输出什么了"

    assert model_output.proactive_output_should_suppress(leaked)
    assert model_output.proactive_output_is_silence_rationale(leaked)
    assert not model_output.output_is_fallback(leaked)
