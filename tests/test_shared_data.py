"""GUI·CLI 공유 데이터와 여러 프로세스의 게시 잠금을 검증한다."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from socialdesk.service import Service
from socialdesk.store import AppError, Store

ROOT = Path(__file__).resolve().parents[1]


class MemoryVault:
    def __init__(self):
        self.values = {}
    def set(self, id, values):
        self.values[id] = values
    def get(self, id):
        return self.values.get(id, {})


def account(service):
    record = service.create_account("bluesky", "내 Bluesky", "example.bsky.social", {"BLUESKY_HANDLE": "example.bsky.social"})
    service.credentials(record["id"], {"BLUESKY_APP_PASSWORD": "FAKE_APP_PASSWORD"})
    return record


def cli(directory, *args):
    process = subprocess.run([sys.executable, str(ROOT / "social.py"), "--data-dir", str(directory), *args], capture_output=True, text=True)
    return process.returncode, json.loads(process.stdout)


def test_서로다른_서비스인스턴스가_같은_게시물을_읽고_수정(tmp_path):
    first, second = Service(tmp_path), Service(tmp_path)
    post = first.create_post("첫 인사", "안녕하세요")
    assert second.store.post(post["id"])["caption"] == "안녕하세요"
    updated = second.update_post(post["id"], expected_version=1, caption="수정한 문구")
    assert first.store.post(post["id"]) == updated
    assert first.store.revision() == second.store.revision()


def test_CLI프로세스_생성후_공유서비스에서_읽음(tmp_path):
    service = Service(tmp_path)
    code, output = cli(tmp_path, "posts", "create", "--title", "CLI 초안", "--text", "공유합니다")
    assert code == 0
    id = output["data"]["id"]
    assert service.store.post(id)["caption"] == "공유합니다"
    service.update_post(id, expected_version=1, caption="화면에서 수정")
    code, output = cli(tmp_path, "posts", "show", id)
    assert code == 0 and output["data"]["caption"] == "화면에서 수정"


def test_CLI는_Qt를_가져오거나_GUI를_실행하지_않음(tmp_path):
    command = "import sys; from socialdesk.cli import run; run(['--data-dir',sys.argv[1],'status']); assert not any(k.startswith('PySide6') for k in sys.modules)"
    result = subprocess.run([sys.executable, "-c", command, str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"]["gui_required"] is False


def test_동시수정은_기존변경을_덮어쓰지_않음(tmp_path):
    service = Service(tmp_path)
    post = service.create_post("제목", "원래 문구")
    service.update_post(post["id"], expected_version=1, caption="먼저 저장")
    with pytest.raises(AppError, match="다른 화면"):
        service.update_post(post["id"], expected_version=1, caption="나중 저장")
    assert service.store.post(post["id"])["caption"] == "먼저 저장"


def test_수정하면_기존승인이_무효화됨(tmp_path):
    service = Service(tmp_path, vault=MemoryVault())
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    changed = service.update_post(post["id"], expected_version=1, caption="새 문구")
    assert changed["approved_version"] is None
    with pytest.raises(AppError, match="승인"):
        service.claim(post["id"], target["id"])


def test_계정식별정보_변경도_게시승인을_무효화(tmp_path):
    service = Service(tmp_path, vault=MemoryVault())
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    service.configure_account(target["id"], {"BLUESKY_HANDLE": "other.bsky.social"})
    assert service.store.post(post["id"])["approved_version"] is None
    assert service.store.post(post["id"])["version"] == 2


def test_인증값은_SQLite에_저장하지_않음(tmp_path):
    vault = MemoryVault()
    service = Service(tmp_path, vault=vault)
    target = account(service)
    with service.store.connection() as db:
        dump = "\n".join(db.iterdump())
    assert "FAKE_APP_PASSWORD" not in dump
    assert vault.get(target["id"])["BLUESKY_APP_PASSWORD"] == "FAKE_APP_PASSWORD"
    with pytest.raises(AppError, match="토큰"):
        service.configure_account(target["id"], {"BLUESKY_APP_PASSWORD": "secret"})


def test_동시에_같은_게시를_시작해도_한쪽만_작업을_획득(tmp_path):
    service = Service(tmp_path, vault=MemoryVault())
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    def claim(_):
        try:
            return Service(tmp_path).claim(post["id"], target["id"])["id"]
        except AppError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert len([result for result in results if result]) == 1
    assert len(service.store.history()) == 1


def test_완료한_버전은_다시_API를_호출하지_않음(tmp_path):
    calls = []
    service = Service(tmp_path, vault=MemoryVault(), publisher=lambda job: calls.append(job["id"]) or {"ok": True, "url": "https://example.invalid/post"})
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    assert service.publish(post["id"])["post"]["status"] == "published"
    assert service.publish(post["id"])["results"][0]["already_published"] is True
    assert len(calls) == 1


def test_불확실한_게시는_자동재시도하지_않음(tmp_path):
    calls = []
    service = Service(tmp_path, vault=MemoryVault(), publisher=lambda job: calls.append(job["id"]) or {"ok": False, "error": "연결 종료"})
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    result = service.publish(post["id"])
    assert result["post"]["status"] == "uncertain"
    with pytest.raises(AppError, match="이미 시도"):
        service.publish(post["id"])
    with pytest.raises(AppError, match="결과 확인"):
        service.update_post(post["id"], expected_version=1, caption="수정")
    assert len(calls) == 1
    service.resolve_job(result["results"][0]["id"], not_published=True)
    assert service.store.post(post["id"])["approved_version"] is None


def test_여러_CLI프로세스가_동시에_초안을_저장(tmp_path):
    Store(tmp_path)
    processes = [subprocess.Popen([sys.executable, str(ROOT / "social.py"), "--data-dir", str(tmp_path), "posts", "create", "--title", f"초안 {i}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(4)]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["ok"]
    assert len(Store(tmp_path).posts()) == 4


def test_백업은_WAL내용까지_일관된_상태로_복사(tmp_path):
    service = Service(tmp_path / "data")
    service.create_post("백업 대상")
    backup = tmp_path / "backup.sqlite3"
    service.store.backup(backup)
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT title FROM posts").fetchone()[0] == "백업 대상"


def test_게시작업을_별도프로세스들이_동시에_획득할_수_없음(tmp_path):
    service = Service(tmp_path, vault=MemoryVault())
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    script = """import sys
from socialdesk.service import Service
from socialdesk.store import AppError
try:
    print(Service(sys.argv[1]).claim(sys.argv[2], sys.argv[3])['id'])
except AppError:
    print('blocked')
"""
    processes = [subprocess.Popen([sys.executable, "-c", script, str(tmp_path), post["id"], target["id"]], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    outputs = [process.communicate(timeout=30)[0].strip() for process in processes]
    assert outputs.count("blocked") == 1
    assert len(service.store.history()) == 1


def test_게시어댑터는_작업당_한번만_실행하고_인증을_DB에_남기지_않음(tmp_path, monkeypatch, capsys):
    import publish
    from socialdesk import worker
    vault = MemoryVault()
    service = Service(tmp_path, vault=vault)
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    job = service.claim(post["id"], target["id"])
    calls = []
    monkeypatch.setattr(worker.os, "environ", {})
    monkeypatch.setattr(publish, "ENV_PATH", tmp_path / "unused.env")
    def send(text, media):
        calls.append(text)
        print("FAKE_APP_PASSWORD")
        publish.update_env_values({"BLUESKY_APP_PASSWORD": "FAKE_REFRESHED_PASSWORD"})
        return "https://example.invalid/receipt"
    monkeypatch.setitem(publish.POSTERS, "bluesky", send)
    result = worker.run(tmp_path, job["id"], vault=vault)
    assert result == {"ok": True, "url": "https://example.invalid/receipt"}
    assert vault.get(target["id"])["BLUESKY_APP_PASSWORD"] == "FAKE_REFRESHED_PASSWORD"
    assert worker.run(tmp_path, job["id"], vault=vault)["ok"] is False
    assert len(calls) == 1
    assert "FAKE_APP_PASSWORD" not in capsys.readouterr().out
    with service.store.connection() as db:
        assert "FAKE_REFRESHED_PASSWORD" not in "\n".join(db.iterdump())


def test_공유설정_충돌을_감지하고_다른설정을_덮어쓰지_않음(tmp_path):
    service = Service(tmp_path)
    service.save_settings({"IMAGE_HOST_SSH": "first"})
    baseline = service.store.settings()
    other = Service(tmp_path)
    other.save_settings({"IMAGE_HOST_SSH": "cli-updated"})
    with pytest.raises(AppError, match="같은 설정"):
        service.save_settings({"IMAGE_HOST_SSH": "gui-updated"}, expected=baseline)
    service.save_settings({"IMAGE_HOST_PATH": "/images"}, expected=baseline)
    assert service.store.settings()["IMAGE_HOST_SSH"] == "cli-updated"


def test_실제_URL로_결과확인하면_완료상태도_갱신됨(tmp_path):
    service = Service(tmp_path, vault=MemoryVault())
    target = account(service)
    post = service.create_post("제목", "문구", [target["id"]])
    service.approve(post["id"], 1)
    job = service.claim(post["id"], target["id"])
    service.finish(job["id"], {"ok": False, "error": "응답 없음"})
    resolved = service.resolve_job(job["id"], url="https://example.invalid/post")
    assert resolved["post"]["status"] == "published"
    with pytest.raises(AppError, match="이미 게시"):
        service.update_post(post["id"], expected_version=1, caption="새 문구")
