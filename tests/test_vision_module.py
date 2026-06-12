import base64
import json
import subprocess
from pathlib import Path

import httpx
import pytest

from qq_hermes_bridge import media, media_fetch, vision


def make_fetch_result(content=b"image-bytes"):
    return media_fetch.MediaFetchResult(
        ref=media.MediaRef(index=0, type="image", file_id="a.png"),
        status="ok",
        content=content,
        content_type="image/png",
        source_host="example.test",
        status_code=200,
    )


def test_noop_vision_provider_returns_skipped():
    result = vision.NoopVisionProvider().recognize_image(make_fetch_result())

    assert result.status == "skipped"
    assert result.provider == "none"
    assert result.error == "ocr_disabled"


def test_mock_vision_provider_returns_configured_text():
    result = vision.MockVisionProvider(text="文字", description="描述").recognize_image(make_fetch_result())

    assert result.status == "ok"
    assert result.text == "文字"
    assert result.description == "描述"
    assert result.provider == "mock"


def test_model_vision_provider_sends_openai_compatible_image_request(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "test-api-key")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "图片里有文字"}}]})

    provider = vision.ModelVisionProvider(
        base_url="https://api.example.test/v1",
        model="vision-model",
        api_key_env="VISION_API_KEY",
        timeout=5,
        max_result_chars=100,
        transport=httpx.MockTransport(handler),
    )

    result = provider.recognize_image(make_fetch_result(b"fixture-bytes"), prompt="看图")

    assert result.status == "ok"
    assert result.text == "图片里有文字"
    assert result.provider == "model"
    request = requests[0]
    assert str(request.url) == "https://api.example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-api-key"
    body = json.loads(request.content.decode("utf-8"))
    assert body["model"] == "vision-model"
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看图"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64.b64encode(b'fixture-bytes').decode('ascii')}"},
                },
            ],
        }
    ]
    assert 64 <= body["max_tokens"] <= 4096


def test_model_vision_provider_normalizes_root_and_endpoint_urls():
    assert vision.normalize_chat_completions_url("https://api.example.test/v1") == "https://api.example.test/v1/chat/completions"
    assert vision.normalize_chat_completions_url("https://api.example.test/v1/") == "https://api.example.test/v1/chat/completions"
    assert (
        vision.normalize_chat_completions_url("https://api.example.test/v1/chat/completions")
        == "https://api.example.test/v1/chat/completions"
    )
    assert (
        vision.normalize_chat_completions_url("https://api.example.test/v1/chat/completions/")
        == "https://api.example.test/v1/chat/completions"
    )


def test_model_vision_provider_parses_content_list_response(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "test-api-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "第一段"},
                                {"type": "text", "text": "第二段"},
                            ]
                        }
                    }
                ]
            },
        )

    provider = vision.ModelVisionProvider(
        base_url="https://api.example.test/v1/chat/completions",
        model="vision-model",
        api_key_env="VISION_API_KEY",
        transport=httpx.MockTransport(handler),
    )

    result = provider.recognize_image(make_fetch_result())

    assert result.status == "ok"
    assert result.text == "第一段\n第二段"


def test_model_vision_provider_missing_config_errors_are_safe(monkeypatch):
    monkeypatch.delenv("MISSING_VISION_KEY", raising=False)
    monkeypatch.setenv("VISION_API_KEY", "test-api-key")
    image = make_fetch_result()

    cases = [
        (vision.ModelVisionProvider(base_url="", model="vision-model", api_key_env="VISION_API_KEY"), "missing_base_url"),
        (vision.ModelVisionProvider(base_url="https://api.example.test/v1", model="", api_key_env="VISION_API_KEY"), "missing_model"),
        (vision.ModelVisionProvider(base_url="https://api.example.test/v1", model="vision-model", api_key_env=""), "missing_api_key_env"),
        (vision.ModelVisionProvider(base_url="https://api.example.test/v1", model="vision-model", api_key_env="MISSING_VISION_KEY"), "missing_api_key"),
    ]

    for provider, expected_error in cases:
        result = provider.recognize_image(image)
        assert result.status == "error"
        assert result.error == expected_error
        assert result.text == ""
        assert result.description == ""


def test_model_vision_provider_http_and_malformed_errors_do_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "secret-api-key")

    def http_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"secret response body with secret-api-key")

    http_error_provider = vision.ModelVisionProvider(
        base_url="https://api.example.test/v1",
        model="vision-model",
        api_key_env="VISION_API_KEY",
        transport=httpx.MockTransport(http_error_handler),
    )
    http_error = http_error_provider.recognize_image(make_fetch_result())

    assert http_error.status == "error"
    assert http_error.error == "http_status"
    assert "secret-api-key" not in repr(http_error)
    assert "secret response body" not in repr(http_error)

    def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json secret-api-key")

    malformed_provider = vision.ModelVisionProvider(
        base_url="https://api.example.test/v1",
        model="vision-model",
        api_key_env="VISION_API_KEY",
        transport=httpx.MockTransport(malformed_handler),
    )
    malformed = malformed_provider.recognize_image(make_fetch_result())

    assert malformed.status == "error"
    assert malformed.error == "invalid_json"
    assert "secret-api-key" not in repr(malformed)
    assert "not json" not in repr(malformed)

    def no_text_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": []}}]})

    no_text_provider = vision.ModelVisionProvider(
        base_url="https://api.example.test/v1",
        model="vision-model",
        api_key_env="VISION_API_KEY",
        transport=httpx.MockTransport(no_text_handler),
    )
    no_text = no_text_provider.recognize_image(make_fetch_result())

    assert no_text.status == "error"
    assert no_text.error == "malformed_response"
    assert "secret-api-key" not in repr(no_text)


def test_hermes_vision_provider_invokes_hermes_with_temp_image_and_cleans_output(tmp_path):
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs, Path(cmd[cmd.index("--image") + 1]).read_bytes()))
        return subprocess.CompletedProcess(cmd, 0, stdout="session_id: abc\n识别文字", stderr="")

    provider = vision.HermesVisionProvider(
        hermes_bin="/bin/hermes",
        model="gpt-5.5",
        provider="openai-gpt",
        timeout=12,
        max_result_chars=100,
        cwd=tmp_path,
        runner=fake_runner,
    )

    result = provider.recognize_image(make_fetch_result(b"fixture-bytes"), prompt="识别")

    assert result.status == "ok"
    assert result.text == "识别文字"
    assert result.provider == "hermes"
    cmd, kwargs, image_bytes = calls[0]
    assert cmd[:4] == ["/bin/hermes", "chat", "-q", "识别"]
    assert "--image" in cmd
    assert cmd[-4:] == ["--model", "gpt-5.5", "--provider", "openai-gpt"]
    assert kwargs["timeout"] == 12
    assert kwargs["cwd"] == str(tmp_path)
    assert image_bytes == b"fixture-bytes"
    assert not Path(cmd[cmd.index("--image") + 1]).exists()


def test_hermes_vision_provider_reports_fetch_and_process_errors():
    bad_fetch = media_fetch.MediaFetchResult(ref=media.MediaRef(index=1, type="image"), status="error", error="timeout")
    assert vision.HermesVisionProvider(hermes_bin="hermes").recognize_image(bad_fetch).error == "timeout"

    def failing_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="bad")

    result = vision.HermesVisionProvider(hermes_bin="hermes", runner=failing_runner).recognize_image(make_fetch_result())
    assert result.status == "error"
    assert result.error == "returncode:2"
    assert result.description == "bad"


def test_build_vision_provider_selects_hermes_model_or_noop(tmp_path):
    assert isinstance(vision.build_vision_provider("none", hermes_bin="hermes"), vision.NoopVisionProvider)
    provider = vision.build_vision_provider("hermes", hermes_bin="hermes", model="m", hermes_provider="p", cwd=tmp_path)
    assert isinstance(provider, vision.HermesVisionProvider)
    assert provider.model == "m"
    assert provider.provider == "p"
    assert provider.cwd == tmp_path

    model_provider = vision.build_vision_provider(
        "openai_compatible",
        hermes_bin="hermes",
        model="vision-model",
        base_url="https://api.example.test/v1",
        api_key_env="VISION_API_KEY",
        timeout=9,
        max_result_chars=321,
    )
    assert isinstance(model_provider, vision.ModelVisionProvider)
    assert model_provider.name == "model"
    assert model_provider.model == "vision-model"
    assert model_provider.base_url == "https://api.example.test/v1"
    assert model_provider.api_key_env == "VISION_API_KEY"
    assert model_provider.timeout == 9
    assert model_provider.max_result_chars == 321


def test_build_vision_provider_keeps_builtin_provider_names_out_of_model_aliases(tmp_path):
    common = {
        "hermes_bin": "hermes",
        "model": "vision-model",
        "base_url": "https://api.example.test/v1",
        "api_key_env": "VISION_API_KEY",
        "cwd": tmp_path,
    }

    assert isinstance(vision.build_vision_provider("none", **common), vision.NoopVisionProvider)
    assert isinstance(vision.build_vision_provider("mock", **common), vision.MockVisionProvider)
    assert isinstance(vision.build_vision_provider("hermes", **common), vision.HermesVisionProvider)


@pytest.mark.parametrize("alias", ["model", "model_vision", "openai", "openai_compatible", "custom", "axonhub", "SiliconFlow"])
def test_build_vision_provider_supports_model_aliases(alias):
    provider = vision.build_vision_provider(
        alias,
        hermes_bin="hermes",
        model="vision-model",
        base_url="https://api.example.test/v1",
        api_key_env="VISION_API_KEY",
    )

    assert isinstance(provider, vision.ModelVisionProvider)
    assert provider.name == "model"
