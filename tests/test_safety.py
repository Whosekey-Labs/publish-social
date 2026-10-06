"""실제 인증 정보나 외부 게시 없이 안전 조건을 검증한다."""

import hashlib
import os
import sys
from pathlib import Path

import pytest
import requests
from PIL import Image

import images
import publish
import x_playwright
from security import redact, safe_error


@pytest.fixture(autouse=True)
def 외부_통신_차단(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("검증 중 외부 API 호출이 발생했습니다.")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


def 게시파일(tmp_path, *, approved=False, image=None):
    path = tmp_path / "post.md"
    media = f"image: {image.name}\n" if image else ""
    path.write_text(
        f"---\nstatus: {'ready' if approved else 'draft'}\napproved: {str(approved).lower()}\n"
        f"platforms: [instagram]\n{media}image-alt: 사진 설명\n---\n"
        "## Instagram\n```\n첫 게시글입니다.\n```\n", encoding="utf-8",
    )
    return path


def 실행환경(monkeypatch, tmp_path, path, *flags):
    monkeypatch.setattr(publish, "ENV_PATH", tmp_path / "unused.env")
    monkeypatch.setattr(sys, "argv", ["publish.py", "--file", str(path), *flags])


@pytest.mark.parametrize("flags", [[], ["--dry-run"]])
def test_기본실행과_미리보기는_원본과_외부서버를_변경하지_않음(tmp_path, monkeypatch, flags):
    source = tmp_path / "portrait.png"
    Image.frombytes("RGB", (768, 768), os.urandom(768 * 768 * 3)).save(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    path = 게시파일(tmp_path, image=source)
    실행환경(monkeypatch, tmp_path, path, *flags)
    monkeypatch.setattr(images, "prepare_image", lambda *a: pytest.fail("미리보기에서 이미지 변환"))
    monkeypatch.setattr(images, "upload_to_image_host", lambda *a, **k: pytest.fail("미리보기에서 업로드"))
    monkeypatch.setattr(publish, "instagram_access_token", lambda: pytest.fail("미리보기에서 토큰 사용"))
    assert publish.main() == 0
    assert hashlib.sha256(source.read_bytes()).digest() == before
    assert path.read_text().startswith("---\nstatus: draft")


def test_승인없는_실제게시는_업로드전에_차단(tmp_path, monkeypatch):
    path = 게시파일(tmp_path)
    실행환경(monkeypatch, tmp_path, path, "--publish", "--yes")
    monkeypatch.setattr(publish, "resolve_media", lambda *a, **k: pytest.fail("승인 전 미디어 처리"))
    with pytest.raises(publish.PublishError, match="status"):
        publish.main()


def test_게시취소시_이미지_업로드하지_않음(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    Image.new("RGB", (8, 8)).save(source)
    path = 게시파일(tmp_path, approved=True, image=source)
    실행환경(monkeypatch, tmp_path, path, "--publish")
    monkeypatch.setattr(publish, "confirm", lambda _: False)
    monkeypatch.setattr(images, "upload_to_image_host", lambda *a, **k: pytest.fail("게시 취소 후 업로드"))
    assert publish.main() == 1


def test_큰이미지_변환은_원본과_기존파일을_보존(tmp_path):
    source = tmp_path / "source.png"
    Image.frombytes("RGB", (768, 768), os.urandom(768 * 768 * 3)).save(source)
    sibling = source.with_suffix(".jpg")
    sibling.write_bytes(b"existing-file")
    before = source.read_bytes()
    assert len(before) > images.SAFE_MAX_BYTES
    prepared = images.prepare_image(source)
    assert prepared != source and prepared.parent != source.parent
    assert prepared.stat().st_size <= images.SAFE_MAX_BYTES
    assert source.read_bytes() == before
    assert sibling.read_bytes() == b"existing-file"


def test_HTTP오류에_토큰과_URL을_출력하지_않음():
    response = requests.Response()
    response.status_code = 400
    response.reason = "Bad Request"
    response.url = "https://graph.instagram.com/media?access_token=FAKE_TOKEN"
    with pytest.raises(requests.HTTPError) as captured:
        response.raise_for_status()
    message = safe_error(captured.value)
    assert "400" in message
    assert "FAKE_TOKEN" not in message
    assert "https://" not in message


def test_통신오류와_본문에서_인증값을_숨김(monkeypatch):
    monkeypatch.setenv("TEST_ACCESS_TOKEN", "fake-secret/one")
    for message in ("token fake-secret/one", "token fake-secret%2Fone", "access_token=unknown-value&x=1"):
        assert "fake-secret" not in redact(message)
        assert "unknown-value" not in redact(message)


def test_인증갱신실패_응답본문을_출력하지_않음(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "FAKE_TOKEN")
    response = requests.Response()
    response.status_code = 403
    response._content = b"secret response body FAKE_TOKEN"
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    with pytest.raises(publish.PublishError) as captured:
        publish.refresh_instagram_token()
    assert "403" in str(captured.value)
    assert "FAKE_TOKEN" not in str(captured.value)
    assert "secret response" not in str(captured.value)


def test_유료X는_별도승인플래그_없이_차단(tmp_path, monkeypatch):
    path = tmp_path / "x.md"
    path.write_text("---\nstatus: ready\napproved: true\nplatforms: [x]\n---\n## X\n```\n테스트\n```\n")
    실행환경(monkeypatch, tmp_path, path, "--publish", "--yes", "--x-transport", "api")
    with pytest.raises(publish.PublishError, match="allow-paid-x"):
        publish.main()


def test_실제게시는_승인뒤에만_업로드(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    Image.new("RGB", (8, 8)).save(source)
    path = 게시파일(tmp_path, approved=True, image=source)
    실행환경(monkeypatch, tmp_path, path, "--publish")
    events = []
    monkeypatch.setattr(publish, "confirm", lambda _: events.append("승인") or True)
    monkeypatch.setenv("IMAGE_HOST_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("IMAGE_HOST_SSH", "unused")
    monkeypatch.setenv("IMAGE_HOST_PATH", "/unused")
    monkeypatch.setattr(images, "upload_to_image_host", lambda *a, **k: events.append("업로드") or "https://example.invalid/photo.png")
    monkeypatch.setitem(publish.POSTERS, "instagram", lambda *a: events.append("게시") or "https://example.invalid/post")
    assert publish.main() == 0
    assert events == ["승인", "업로드", "게시"]
    assert "status: posted" in path.read_text()


def test_게시실패_터미널에_토큰을_노출하지_않음(tmp_path, monkeypatch, capsys):
    path = 게시파일(tmp_path, approved=True)
    실행환경(monkeypatch, tmp_path, path, "--publish", "--yes")
    response = requests.Response()
    response.status_code = 401
    response.reason = "Unauthorized"
    response.url = "https://graph.instagram.com/media?access_token=FAKE_TOKEN"
    def failure(*args):
        response.raise_for_status()
    monkeypatch.setitem(publish.POSTERS, "instagram", failure)
    assert publish.main() == 1
    output = capsys.readouterr().out
    assert "FAKE_TOKEN" not in output
    assert "401" in output


def test_비대화_게시는_자동승인하지_않음(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert publish.confirm(["instagram"]) is False


def test_X단독실행도_기본은_브라우저없는_미리보기(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("X_PLAYWRIGHT_STATE", str(tmp_path / "unused-state.json"))
    monkeypatch.setattr(sys, "argv", ["x_playwright.py", "post", "--text", "테스트"])
    assert x_playwright.main() == 0
    assert "dry-run" in capsys.readouterr().out
