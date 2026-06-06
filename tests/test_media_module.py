from qq_hermes_bridge import media, onebot


def test_extract_media_refs_from_segment_array_preserves_image_metadata_and_order():
    message = [
        {"type": "text", "data": {"text": "看图"}},
        {
            "type": "image",
            "data": {
                "file": "abc.image",
                "url": "https://example.test/a.png",
                "summary": "[动画表情]",
                "sub_type": "normal",
            },
        },
        {"type": "face", "data": {"id": "14"}},
        {
            "type": "image",
            "data": {
                "file_id": "second-file-id",
                "url": "https://example.test/b.webp",
                "title": "第二张",
            },
        },
    ]

    refs = media.extract_media_refs(message)

    assert refs == [
        media.MediaRef(
            index=0,
            type="image",
            file_id="abc.image",
            url="https://example.test/a.png",
            summary="[动画表情]",
            sub_type="normal",
            raw_keys=("file", "sub_type", "summary", "url"),
        ),
        media.MediaRef(
            index=1,
            type="image",
            file_id="second-file-id",
            url="https://example.test/b.webp",
            summary="第二张",
            raw_keys=("file_id", "title", "url"),
        ),
    ]


def test_extract_media_refs_from_cq_image_string_unescapes_params():
    message = "看看[CQ:image,file=abc&#44;def.jpg,url=https://example.test/a.png?x=1&amp;y=2,summary=图&#91;一&#93;]"

    refs = media.extract_media_refs(message)

    assert refs == [
        media.MediaRef(
            index=0,
            type="image",
            file_id="abc,def.jpg",
            url="https://example.test/a.png?x=1&y=2",
            summary="图[一]",
            raw_keys=("file", "summary", "url"),
        )
    ]


def test_extract_media_refs_respects_max_refs_and_ignores_non_images():
    message = [
        {"type": "record", "data": {"file": "voice.amr"}},
        {"type": "image", "data": {"file": "1.jpg"}},
        {"type": "video", "data": {"file": "v.mp4"}},
        {"type": "image", "data": {"file": "2.jpg"}},
    ]

    refs = media.extract_media_refs(message, max_refs=1)

    assert refs == [media.MediaRef(index=0, type="image", file_id="1.jpg", raw_keys=("file",))]
    assert media.has_processable_media(message)
    assert not media.has_processable_media([{"type": "text", "data": {"text": "无图"}}])


def test_message_to_text_keeps_existing_image_placeholder_behavior():
    message = [
        {"type": "text", "data": {"text": "看"}},
        {"type": "image", "data": {"file": "abc.image", "url": "https://example.test/a.png"}},
        {"type": "text", "data": {"text": "这个"}},
    ]

    assert onebot.message_to_text(message) == "看[图片]这个"


def test_format_media_context_and_merge_text_for_future_prompt_use():
    results = [
        media.MediaRecognition(index=0, type="image", status="ok", text="招牌写着营业中", description="一张店门口照片", provider="mock"),
        media.MediaRecognition(index=1, type="image", status="error", error="TimeoutExpired"),
    ]

    context = media.format_media_context(results, max_chars=200)

    assert "图片1" in context
    assert "文字：招牌写着营业中" in context
    assert "描述：一张店门口照片" in context
    assert "图片2：识别失败" in context
    assert media.merge_text_and_media_context("帮我看图", context).startswith("帮我看图\n- 图片1")


def test_format_media_context_can_skip_failures_for_group_context():
    results = [
        media.MediaRecognition(index=0, type="image", status="ok", text="看得清的字", provider="mock"),
        media.MediaRecognition(index=1, type="image", status="error", error="timeout"),
    ]

    context = media.format_media_context(results, max_chars=200, include_failures=False)

    assert "图片1" in context
    assert "看得清的字" in context
    assert "图片2" not in context
    assert "识别失败" not in context
