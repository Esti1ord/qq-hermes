from collections import deque

import httpx
import pytest

from qq_hermes_bridge import outbound


def test_send_group_msg_succeeded_rejects_errors_bad_status_and_retcode():
    assert outbound.send_group_msg_succeeded({"status": "ok", "retcode": 0})
    assert outbound.send_group_msg_succeeded({"retcode": "0"})
    assert not outbound.send_group_msg_succeeded({"error": "ConnectError"})
    assert not outbound.send_group_msg_succeeded({"status": "failed", "retcode": 0})
    assert not outbound.send_group_msg_succeeded({"status": "ok", "retcode": 100})
    assert not outbound.send_group_msg_succeeded(None)




def test_cq_reply_helpers_escape_parameters_and_wrap_message():
    assert outbound.cq_escape_param("a&b[c],d") == "a&amp;b&#91;c&#93;&#44;d"
    assert outbound.cq_reply_segment("abc,123") == "[CQ:reply,id=abc&#44;123]"
    assert outbound.reply_to_message("你好", "42") == "[CQ:reply,id=42]你好"


def test_reply_to_message_keeps_plain_text_without_message_id():
    assert outbound.cq_reply_segment("") == ""
    assert outbound.reply_to_message("你好", "") == "你好"


def test_duplicate_outbound_ignores_whitespace_and_expires_by_window():
    buckets = {}

    assert not outbound.should_suppress_duplicate_outbound(1, "你好 世界", recent_by_group=buckets, now=100.0, window=30.0)
    outbound.remember_successful_outbound(1, "你好 世界", recent_by_group=buckets, now=100.0, window=30.0)
    assert outbound.should_suppress_duplicate_outbound(1, "你好世界", recent_by_group=buckets, now=101.0, window=30.0)
    assert not outbound.should_suppress_duplicate_outbound(1, "你好世界", recent_by_group=buckets, now=131.1, window=30.0)
    assert isinstance(buckets[1], deque)


def test_duplicate_check_does_not_record_failed_or_unattempted_send():
    buckets = {}

    assert not outbound.should_suppress_duplicate_outbound(1, "没发出去", recent_by_group=buckets, now=100.0, window=30.0)
    assert not outbound.should_suppress_duplicate_outbound(1, "没发 出去", recent_by_group=buckets, now=101.0, window=30.0)


@pytest.mark.anyio
async def test_send_group_msg_posts_json_and_auth_header():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "ok", "retcode": 0})

    data = await outbound.send_group_msg(
        123,
        "hello",
        onebot_http_url="http://onebot.local",
        access_token="token",
        transport=httpx.MockTransport(handler),
    )

    assert data == {"status": "ok", "retcode": 0}
    assert requests[0].url == "http://onebot.local/send_group_msg"
    assert requests[0].headers["authorization"] == "Bearer token"
    assert requests[0].read() == b'{"group_id":123,"message":"hello"}'


@pytest.mark.anyio
async def test_send_group_msg_returns_text_when_response_is_not_json():
    data = await outbound.send_group_msg(
        123,
        "hello",
        onebot_http_url="http://onebot.local",
        access_token="",
        transport=httpx.MockTransport(lambda request: httpx.Response(502, text="bad gateway")),
    )

    assert data == {"status_code": 502, "text": "bad gateway"}
