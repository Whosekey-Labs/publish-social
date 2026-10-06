"""실제 Qt 위젯과 별도 CLI 프로세스 사이의 데이터 동기화를 검증한다."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import json
import subprocess
import sys

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from socialdesk.gui import Window
from socialdesk.service import Service

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_GUI저장후_CLI조회와_CLI수정후_GUI자동갱신(app, tmp_path):
    window = Window(Service(tmp_path))
    window.title.setText("화면에서 만든 게시물")
    window.caption.setPlainText("GUI 문구")
    post = window.save_post()
    assert post is not None
    result = subprocess.run([sys.executable, str(ROOT / "social.py"), "--data-dir", str(tmp_path), "posts", "show", post["id"]], capture_output=True, text=True)
    assert json.loads(result.stdout)["data"]["caption"] == "GUI 문구"
    result = subprocess.run([sys.executable, str(ROOT / "social.py"), "--data-dir", str(tmp_path), "posts", "update", post["id"], "--version", "1", "--text", "CLI에서 바꾼 문구"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
    QTest.qWait(1000)
    assert window.caption.toPlainText() == "CLI에서 바꾼 문구"
    assert window.current["version"] == 2
    window.timer.stop()
    window.close()


def test_저장하지_않은_GUI편집은_CLI변경으로_덮어쓰지_않음(app, tmp_path):
    service = Service(tmp_path)
    post = service.create_post("제목", "처음")
    window = Window(service)
    window.load_post(post)
    window.caption.setPlainText("아직 저장하지 않은 문구")
    assert window.dirty
    Service(tmp_path).update_post(post["id"], expected_version=1, caption="CLI 변경")
    window.poll()
    assert window.caption.toPlainText() == "아직 저장하지 않은 문구"
    assert "최신" in window.notice.text()
    window.dirty = False
    window.timer.stop()
    window.close()


def test_접근성_메뉴선택도_화면을_전환하고_선택은_하나만_유지(app, tmp_path):
    window = Window(Service(tmp_path))
    window.navigation[3].setChecked(True)
    assert window.stack.currentIndex() == 3
    assert sum(action.isChecked() for action in window.navigation) == 1
    window.navigation[1].click()
    assert window.stack.currentIndex() == 1
    assert sum(action.isChecked() for action in window.navigation) == 1
    window.timer.stop()
    window.close()


def test_접근성_제목수정도_저장하지_않은_편집으로_보존(app, tmp_path):
    service = Service(tmp_path)
    post = service.create_post("처음 제목")
    window = Window(service)
    window.load_post(post)
    window.title.setText("접근성으로 수정한 제목")
    assert window.dirty
    Service(tmp_path).update_post(post["id"], expected_version=1, title="CLI 제목")
    window.poll()
    assert window.title.text() == "접근성으로 수정한 제목"
    window.dirty = False
    window.timer.stop()
    window.close()
