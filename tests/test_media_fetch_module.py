import httpx
import pytest

from qq_hermes_bridge import media, media_fetch


@pytest.mark.anyio
async def test_fetch_onebot_image_downloads_url_with_same_origin_auth_header():
    requests = []
    ref = media.MediaRef(index=0, type="image", file_id="abc.image", url="http://onebot.local/media/abc.png")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png-bytes")

    result = await media_fetch.fetch_onebot_image(
        ref,
        onebot_http_url="http://onebot.local",
        access_token="secret-token",
        timeout=1,
        max_bytes=1024,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert result.content == b"png-bytes"
    assert result.content_type == "image/png"
    assert result.source_host == "onebot.local"
    assert requests[0].headers["authorization"] == "Bearer secret-token"


@pytest.mark.anyio
async def test_fetch_onebot_image_does_not_send_token_to_different_origin():
    requests = []
    ref = media.MediaRef(index=0, type="image", url="https://cdn.example.test/a.jpg")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"jpg")

    result = await media_fetch.fetch_onebot_image(
        ref,
        onebot_http_url="http://onebot.local",
        access_token="secret-token",
        timeout=1,
        max_bytes=1024,
        allowed_content_types={"image/jpeg"},
        transport=httpx.MockTransport(handler),
    )

    assert result.status == "ok"
    assert "authorization" not in requests[0].headers


@pytest.mark.anyio
async def test_fetch_onebot_image_rejects_unsupported_scheme_before_request():
    ref = media.MediaRef(index=0, type="image", url="file:///tmp/a.png")

    result = await media_fetch.fetch_onebot_image(
        ref,
        onebot_http_url="http://onebot.local",
        timeout=1,
        max_bytes=1024,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(lambda request: pytest.fail("request should not be sent")),
    )

    assert result.status == "error"
    assert result.error == "unsupported_url_scheme"
    assert result.content == b""


@pytest.mark.anyio
async def test_fetch_onebot_image_rejects_non_image_content_type():
    ref = media.MediaRef(index=0, type="image", url="https://cdn.example.test/not-image")

    result = await media_fetch.fetch_onebot_image(
        ref,
        onebot_http_url="http://onebot.local",
        timeout=1,
        max_bytes=1024,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<html>")),
    )

    assert result.status == "error"
    assert result.error == "unsupported_content_type"
    assert result.content_type == "text/html"
    assert result.content == b""


@pytest.mark.anyio
async def test_fetch_onebot_image_enforces_declared_and_streamed_byte_limits():
    declared_ref = media.MediaRef(index=0, type="image", url="https://cdn.example.test/declared.png")
    declared = await media_fetch.fetch_onebot_image(
        declared_ref,
        onebot_http_url="http://onebot.local",
        timeout=1,
        max_bytes=4,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "image/png", "content-length": "5"}, content=b"")),
    )
    assert declared.status == "error"
    assert declared.error == "max_bytes_exceeded"

    streamed_ref = media.MediaRef(index=0, type="image", url="https://cdn.example.test/streamed.png")
    streamed = await media_fetch.fetch_onebot_image(
        streamed_ref,
        onebot_http_url="http://onebot.local",
        timeout=1,
        max_bytes=4,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "image/png"}, content=b"12345")),
    )
    assert streamed.status == "error"
    assert streamed.error == "max_bytes_exceeded"
    assert streamed.content == b""


@pytest.mark.anyio
async def test_fetch_onebot_image_refuses_redirects():
    ref = media.MediaRef(index=0, type="image", url="https://cdn.example.test/a.png")

    result = await media_fetch.fetch_onebot_image(
        ref,
        onebot_http_url="http://onebot.local",
        timeout=1,
        max_bytes=1024,
        allowed_content_types={"image/png"},
        transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://other.example/a.png"})),
    )

    assert result.status == "error"
    assert result.error == "redirect_not_followed"
    assert result.status_code == 302


def test_media_ref_log_summary_redacts_file_id_and_url_by_default():
    ref = media.MediaRef(index=2, type="image", file_id="very-sensitive-file-id", url="https://cdn.example.test/path/a.png?token=secret")

    summary = media_fetch.media_ref_log_summary(ref)

    assert summary == {
        "type": "image",
        "index": 2,
        "has_file_id": True,
        "has_url": True,
        "file_id_hash": media_fetch.short_hash("very-sensitive-file-id"),
        "url_host": "cdn.example.test",
    }
    assert "very-sensitive-file-id" not in str(summary)
    assert "token=secret" not in str(summary)
