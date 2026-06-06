import subprocess
from pathlib import Path

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


def test_build_vision_provider_selects_hermes_or_noop(tmp_path):
    assert isinstance(vision.build_vision_provider("none", hermes_bin="hermes"), vision.NoopVisionProvider)
    provider = vision.build_vision_provider("hermes", hermes_bin="hermes", model="m", hermes_provider="p", cwd=tmp_path)
    assert isinstance(provider, vision.HermesVisionProvider)
    assert provider.model == "m"
    assert provider.provider == "p"
    assert provider.cwd == tmp_path
