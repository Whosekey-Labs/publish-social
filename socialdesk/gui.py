"""공유 서비스를 사용하는 macOS 개인용 게시 작업실."""

from pathlib import Path
from datetime import datetime
import sys

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl
from PySide6.QtGui import QFont, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QLineEdit, QTextEdit, QCheckBox,
    QFileDialog, QMessageBox, QDialog, QFormLayout, QComboBox, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout,
)

from .service import Service, PLATFORMS, VIDEO_SUFFIXES
from .store import AppError

STATUS = {"draft": "초안", "approved": "승인됨", "publishing": "게시 중", "published": "게시 완료", "partial": "일부 완료", "uncertain": "결과 확인 필요"}
FIELD_LABELS = {
    "INSTAGRAM_USER_ID": "Instagram 계정 ID", "THREADS_USER_ID": "Threads 계정 ID",
    "BLUESKY_HANDLE": "Bluesky 핸들", "MASTODON_INSTANCE_URL": "인스턴스 주소",
    "FACEBOOK_PAGE_ID": "Facebook 페이지 ID", "LINKEDIN_ORG_URN": "조직 URN",
    "YOUTUBE_CLIENT_ID": "Google 클라이언트 ID", "INSTAGRAM_ACCESS_TOKEN": "액세스 토큰",
    "THREADS_ACCESS_TOKEN": "액세스 토큰", "BLUESKY_APP_PASSWORD": "앱 비밀번호",
    "MASTODON_ACCESS_TOKEN": "액세스 토큰", "FACEBOOK_PAGE_ACCESS_TOKEN": "페이지 토큰",
    "LINKEDIN_ACCESS_TOKEN": "액세스 토큰", "YOUTUBE_CLIENT_SECRET": "클라이언트 시크릿",
    "YOUTUBE_REFRESH_TOKEN": "갱신 토큰", "X_API_KEY": "API 키", "X_API_SECRET": "API 시크릿",
    "X_ACCESS_TOKEN": "액세스 토큰", "X_ACCESS_TOKEN_SECRET": "토큰 시크릿",
}
STYLE = """
QWidget { color:#263630; font-family:'Apple SD Gothic Neo'; font-size:14px; }
QMainWindow, QWidget#canvas { background:#f4f3ed; }
QWidget#sidebar { background:#fcfcf8; border-right:1px solid #dfE3da; }
QLabel#brand { font-family:'Avenir Next'; font-size:24px; font-weight:700; letter-spacing:-1px; }
QLabel#heading { font-size:30px; font-weight:700; }
QLabel#muted { color:#7b877c; font-size:12px; }
QLabel#pill { background:#e5eddf; color:#546d4b; padding:7px 13px; border-radius:14px; font-size:12px; }
QLabel#status { color:#526d48; font-size:12px; font-weight:600; }
QLabel#preview { background:#eaece4; border:1px dashed #bfc9b8; border-radius:12px; color:#7a8975; }
QFrame#card { background:#fcfcf8; border:1px solid #e0e4da; border-radius:14px; }
QPushButton { background:#fcfcf8; border:1px solid #d7ddcf; border-radius:8px; padding:9px 16px; font-weight:500; }
QPushButton:hover { background:#e7eddf; border-color:#a8b898; }
QPushButton:disabled { color:#a0a99c; background:#eeeee8; }
QPushButton#primary { background:#3c5a39; color:white; border:1px solid #3c5a39; }
QPushButton#primary:hover { background:#2d462b; }
QPushButton#primary:disabled { background:#cbd3c5; border-color:#cbd3c5; color:#7b8874; }
QPushButton#nav { text-align:left; padding:13px 16px; border:none; background:transparent; border-radius:8px; }
QPushButton#nav:checked { background:#e7eddf; color:#304c2c; font-weight:700; }
QLineEdit, QTextEdit, QComboBox { background:#fffefb; border:1px solid #dce2d3; border-radius:8px; padding:9px; selection-background-color:#d5e4cc; }
QLineEdit:focus, QTextEdit:focus { border:1px solid #7f9d6b; }
QLineEdit#title { font-size:21px; font-weight:600; padding:11px; }
QListWidget { background:transparent; border:none; outline:none; }
QListWidget::item { background:#fcfcf8; border:1px solid #e1e4da; border-radius:10px; padding:12px; margin-bottom:8px; }
QListWidget::item:selected { background:#e8efdf; border:1px solid #9aae88; color:#263630; }
QTableWidget { background:#fcfcf8; border:1px solid #e0e4da; border-radius:10px; gridline-color:#edf0e7; }
QHeaderView::section { background:#eeF1e7; border:none; padding:11px; text-align:left; font-weight:600; }
QCheckBox { spacing:8px; padding:4px; }
QCheckBox::indicator { width:16px; height:16px; }
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { width:7px; background:transparent; }
QScrollBar::handle:vertical { background:#c7d1be; border-radius:3px; min-height:28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
QDialog { background:#f4f3ed; }
"""


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def message(parent, title, text, *, confirm=False):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No if confirm else QMessageBox.StandardButton.Ok)
    if confirm:
        box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


class AccountDialog(QDialog):
    def __init__(self, service, account=None, parent=None):
        super().__init__(parent)
        self.service, self.account = service, account
        self.setWindowTitle("계정 설정" if account else "SNS 계정 추가")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.addWidget(label("내 SNS 계정", "heading"))
        hint = label("식별 정보는 공유 데이터에, 인증 정보는 Mac 키체인에 저장합니다.", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.platform = QComboBox()
        for key, value in PLATFORMS.items():
            self.platform.addItem(value[0], key)
        if account:
            self.platform.setCurrentIndex(list(PLATFORMS).index(account["platform"]))
            self.platform.setEnabled(False)
        self.name = QLineEdit(account["label"] if account else "")
        self.username = QLineEdit(account["username"] if account else "")
        if account:
            self.name.setReadOnly(True)
            self.username.setReadOnly(True)
        form.addRow("플랫폼", self.platform)
        form.addRow("계정 이름", self.name)
        form.addRow("표시 핸들", self.username)
        layout.addLayout(form)
        self.fields_host = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_host)
        self.fields_layout.setContentsMargins(0, 6, 0, 6)
        layout.addWidget(self.fields_host)
        self.platform.currentIndexChanged.connect(self.build_fields)
        self.build_fields()
        layout.addWidget(button("저장", self.save, True))

    def build_fields(self):
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(0, 0, 0, 0)
        self.public, self.secrets = {}, {}
        platform = self.platform.currentData()
        for field in PLATFORMS[platform][1]:
            edit = QLineEdit(self.account["config"].get(field, "") if self.account else "")
            edit.setToolTip(field)
            self.public[field] = edit
            form.addRow(FIELD_LABELS.get(field, field), edit)
        for field in PLATFORMS[platform][2]:
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setPlaceholderText("새 인증 정보를 입력하세요" if self.account else "아직 없다면 비워 두세요")
            edit.setToolTip(field)
            self.secrets[field] = edit
            form.addRow(FIELD_LABELS.get(field, field), edit)
        self.fields_layout.addWidget(content)

    def save(self):
        try:
            config = {key: edit.text().strip() for key, edit in self.public.items()}
            if self.account:
                record = self.service.configure_account(self.account["id"], config)
            else:
                record = self.service.create_account(self.platform.currentData(), self.name.text(), self.username.text(), config)
                self.account = record
            values = {key: edit.text().strip() for key, edit in self.secrets.items()}
            if any(values.values()):
                self.service.credentials(record["id"], values)
            self.accept()
        except AppError as exc:
            message(self, "저장할 수 없습니다", str(exc))


class PublishThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service, id, allow_paid_x=False):
        super().__init__()
        self.service, self.id, self.allow_paid_x = service, id, allow_paid_x

    def run(self):
        try:
            self.completed.emit(self.service.publish(self.id, allow_paid_x=self.allow_paid_x))
        except AppError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("게시 처리를 완료하지 못했습니다. 게시 기록을 확인하세요.")


class Window(QMainWindow):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.current = None
        self.dirty = False
        self.loading = False
        self.attachment = None
        self.remove_attachment = False
        self.thread = None
        self.seen_revision = -1
        self.settings_dirty = False
        self.settings_baseline = {}
        self.setWindowTitle("Publish Social")
        self.resize(1240, 840)
        self.setMinimumSize(1040, 720)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName("canvas")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(24, 32, 24, 26)
        nav.setSpacing(9)
        nav.addWidget(label("Publish\nSocial", "brand"))
        nav.addWidget(label("나의 SNS 작업실", "muted"))
        nav.addSpacing(38)
        self.navigation = []
        for index, title in enumerate(("게시물", "내 계정", "게시 기록", "설정")):
            action = QPushButton(title)
            action.setObjectName("nav")
            action.setCheckable(True)
            action.setAutoExclusive(True)
            action.toggled.connect(lambda checked, i=index: self.navigate(i) if checked else None)
            self.navigation.append(action)
            nav.addWidget(action)
        nav.addStretch()
        nav.addWidget(label("PERSONAL WORKSPACE", "muted"))
        foot = label("이 Mac에 저장됩니다.\n앱을 닫아도 CLI로 사용할 수 있어요.", "muted")
        foot.setWordWrap(True)
        nav.addWidget(foot)
        outer.addWidget(sidebar)
        body = QVBoxLayout()
        body.setContentsMargins(30, 28, 30, 22)
        body.setSpacing(20)
        header = QHBoxLayout()
        self.heading = label("게시물", "heading")
        self.sync = label("CLI 변경 자동 반영", "pill")
        header.addWidget(self.heading)
        header.addStretch()
        header.addWidget(self.sync)
        body.addLayout(header)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.make_posts()
        self.make_accounts()
        self.make_history()
        self.make_settings()
        self.refresh()
        self.navigate(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(750)

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        self.heading.setText(("게시물 작업실", "내 SNS 계정", "게시 기록", "설정")[index])
        for number, action in enumerate(self.navigation):
            action.setChecked(number == index)

    def make_posts(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(22)
        left = QVBoxLayout()
        left.addWidget(button("＋ 새 게시물", self.new_post, True))
        self.post_list = QListWidget()
        self.post_list.setObjectName("post-list")
        self.post_list.setFixedWidth(270)
        self.post_list.currentItemChanged.connect(self.select_post)
        left.addWidget(self.post_list, 1)
        self.count = label("", "muted")
        left.addWidget(self.count)
        layout.addLayout(left)
        card = QFrame()
        card.setObjectName("card")
        editor = QVBoxLayout(card)
        editor.setContentsMargins(23, 22, 23, 22)
        editor.setSpacing(13)
        self.state = label("새로운 이야기", "status")
        status_row = QHBoxLayout()
        status_row.addWidget(self.state)
        status_row.addStretch()
        status_row.addWidget(button("다시 불러오기", self.reload_post))
        editor.addLayout(status_row)
        self.title = QLineEdit()
        self.title.setObjectName("title")
        self.title.setPlaceholderText("게시물 제목")
        self.title.textChanged.connect(self.changed)
        editor.addWidget(self.title)
        media = QHBoxLayout()
        self.preview_image = label("사진 또는 영상\n\n첨부한 원본은 그대로 보존합니다.", "preview")
        self.preview_image.setFixedSize(194, 162)
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        media.addWidget(self.preview_image)
        actions = QVBoxLayout()
        actions.addWidget(label("첨부 파일", "status"))
        self.media_name = label("아직 첨부하지 않았습니다.", "muted")
        self.media_name.setWordWrap(True)
        actions.addWidget(self.media_name)
        actions.addWidget(button("파일 선택", self.pick_media))
        actions.addWidget(button("첨부 해제", self.clear_media))
        actions.addStretch()
        media.addLayout(actions)
        editor.addLayout(media)
        editor.addWidget(label("게시할 문구", "status"))
        self.caption = QTextEdit()
        self.caption.setObjectName("caption")
        self.caption.setAcceptRichText(False)
        self.caption.setPlaceholderText("사진에 담긴 이야기와 해시태그를 적어 주세요.")
        self.caption.setMinimumHeight(135)
        self.caption.textChanged.connect(self.changed)
        editor.addWidget(self.caption, 1)
        self.characters = label("0자", "muted")
        editor.addWidget(self.characters)
        editor.addWidget(label("게시할 계정", "status"))
        self.targets_widget = QWidget()
        self.targets_layout = QGridLayout(self.targets_widget)
        self.targets_layout.setContentsMargins(0, 0, 0, 0)
        self.targets_layout.setSpacing(8)
        editor.addWidget(self.targets_widget)
        self.notice = label("초안부터 저장해 보세요.", "muted")
        self.notice.setWordWrap(True)
        editor.addWidget(self.notice)
        buttons = QHBoxLayout()
        buttons.addWidget(button("저장", self.save_post))
        buttons.addWidget(button("미리보기", self.preview_post))
        buttons.addWidget(button("게시 승인", self.approve_post))
        self.publish_button = button("지금 게시", self.publish_post, True)
        buttons.addWidget(self.publish_button)
        editor.addLayout(buttons)
        layout.addWidget(card, 1)
        self.stack.addWidget(page)

    def make_accounts(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        intro = label("한 번 설정한 계정은 앱과 CLI에서 함께 사용합니다.", "muted")
        layout.addWidget(intro)
        toolbar = QHBoxLayout()
        toolbar.addWidget(button("＋ 계정 추가", self.add_account, True))
        toolbar.addWidget(button("선택 계정 설정", self.edit_account))
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.account_list = QListWidget()
        layout.addWidget(self.account_list, 1)
        layout.addWidget(label("앱에 계정을 추가해도 SNS 가입이나 개발자 앱 인증이 자동으로 완료되지는 않습니다.", "muted"))
        self.stack.addWidget(page)

    def make_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("앱과 CLI가 실행한 게시 결과가 여기에 함께 남습니다.", "muted"))
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(["게시물", "계정", "상태", "실행 시간", "결과"])
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.cellDoubleClicked.connect(self.open_receipt)
        layout.addWidget(self.history, 1)
        layout.addWidget(button("선택 작업의 실제 결과 확인", self.resolve_history))
        self.stack.addWidget(page)

    def make_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(24, 24, 24, 24)
        self.setting_fields = {}
        for key, title in (("IMAGE_HOST_BASE_URL", "이미지 HTTPS 주소"), ("IMAGE_HOST_SSH", "SSH 호스트"), ("IMAGE_HOST_PATH", "서버의 이미지 폴더")):
            field = QLineEdit()
            field.setPlaceholderText({"IMAGE_HOST_BASE_URL": "https://images.example.com", "IMAGE_HOST_SSH": "my-image-host", "IMAGE_HOST_PATH": "/var/www/images"}[key])
            self.setting_fields[key] = field
            field.textChanged.connect(lambda text: setattr(self, "settings_dirty", True))
            form.addRow(title, field)
        form.addRow(button("호스트 설정 저장", self.save_settings, True))
        layout.addWidget(label("Instagram·Threads·Facebook 사진 게시에 필요한 이미지 호스트입니다.", "muted"))
        layout.addWidget(card)
        layout.addSpacing(20)
        layout.addWidget(label("저장 위치", "status"))
        path = label(str(self.service.store.root), "muted")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path.setWordWrap(True)
        layout.addWidget(path)
        layout.addWidget(button("저장 폴더 열기", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.service.store.root)))))
        layout.addWidget(button("상태 데이터 백업", self.backup))
        note = label("백업은 게시물·계정 식별 정보·게시 기록입니다. 첨부 파일과 Mac 키체인 인증 정보는 별도 보관됩니다.", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.stack.addWidget(page)

    def changed(self, *args):
        if not self.loading:
            self.dirty = True
            self.notice.setText("저장하지 않은 변경이 있습니다.")
            self.publish_button.setEnabled(False)
        self.characters.setText(f"{len(self.caption.toPlainText()):,}자")

    def target_ids(self):
        return [id for id, checkbox in self.target_checks.items() if checkbox.isChecked()]

    def refresh(self):
        revision = self.service.store.revision()
        selected = self.current["id"] if self.current else None
        old_targets = self.target_ids() if hasattr(self, "target_checks") and self.dirty else None
        self.post_list.blockSignals(True)
        self.post_list.clear()
        posts, accounts = self.service.store.posts(), self.service.store.accounts()
        for post in posts:
            item = QListWidgetItem(f"{post['title'][:24]}\n{STATUS.get(post['status'], post['status'])}  ·  {len(post['targets'])}개 계정")
            item.setData(Qt.ItemDataRole.UserRole, post["id"])
            self.post_list.addItem(item)
            if selected == post["id"]:
                self.post_list.setCurrentItem(item)
        if not posts:
            empty = QListWidgetItem("아직 게시물이 없습니다.\n새 게시물로 시작하세요.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.post_list.addItem(empty)
        self.post_list.blockSignals(False)
        self.count.setText(f"게시물 {len(posts)}개  ·  계정 {len(accounts)}개")
        self.account_list.clear()
        for account in accounts:
            item = QListWidgetItem(f"{PLATFORMS[account['platform']][0]}   {account['label']}\n{account['username'] or '핸들 미입력'}  ·  {'인증 정보 저장됨' if account['has_credentials'] else '인증 정보 필요'}")
            item.setData(Qt.ItemDataRole.UserRole, account["id"])
            self.account_list.addItem(item)
        self.loading = True
        while self.targets_layout.count():
            item = self.targets_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.target_checks = {}
        targets = old_targets if old_targets is not None else (self.current["targets"] if self.current else [])
        for index, account in enumerate(accounts):
            checkbox = QCheckBox(account["label"][:22])
            checkbox.setToolTip(account["label"])
            checkbox.setChecked(account["id"] in targets)
            checkbox.toggled.connect(self.changed)
            self.target_checks[account["id"]] = checkbox
            self.targets_layout.addWidget(checkbox, index // 3, index % 3)
        if not accounts:
            self.targets_layout.addWidget(label("내 계정에서 SNS 계정을 추가하세요.", "muted"), 0, 0, 1, 3)
        self.targets_layout.setColumnStretch(2, 1)
        self.loading = False
        self.history_rows = self.service.store.history()
        self.history.setRowCount(len(self.history_rows))
        for index, row in enumerate(self.history_rows):
            timestamp = datetime.fromisoformat(row["created_at"]).astimezone().strftime("%m/%d %H:%M")
            for column, value in enumerate((row["title"], row["label"], STATUS.get(row["status"], row["status"]), timestamp, row["url"] or row["error"] or "진행 중")):
                self.history.setItem(index, column, QTableWidgetItem(value))
        values = self.service.store.settings()
        if not self.settings_dirty:
            self.settings_baseline = values
            for key, field in self.setting_fields.items():
                field.blockSignals(True)
                field.setText(values.get(key, ""))
                field.blockSignals(False)
        self.seen_revision = revision
        self.publish_button.setEnabled(bool(self.current and not self.dirty and self.current["status"] in {"approved", "partial"}) and not (self.thread and self.thread.isRunning()))

    def poll(self):
        revision = self.service.store.revision()
        if revision == self.seen_revision:
            return
        if self.current and not self.dirty:
            self.load_post(self.service.store.post(self.current["id"]))
        elif self.current and self.dirty:
            fresh = self.service.store.post(self.current["id"])
            if fresh["version"] != self.current["version"]:
                self.notice.setText("CLI 또는 다른 화면에서 수정했습니다. 저장 전에 최신 내용을 다시 불러오세요.")
        self.refresh()
        self.sync.setText("같은 데이터 · 방금 갱신")

    def load_post(self, post):
        self.loading = True
        self.current = post
        self.title.setText(post["title"])
        self.caption.setPlainText(post["caption"])
        self.attachment = post["media"]
        self.remove_attachment = False
        self.state.setText(f"{STATUS.get(post['status'], post['status'])}  ·  버전 {post['version']}")
        self.notice.setText("앱과 CLI가 같은 게시물을 사용합니다.")
        for id, checkbox in getattr(self, "target_checks", {}).items():
            checkbox.setChecked(id in post["targets"])
        self.loading = False
        self.dirty = False
        self.update_attachment()
        self.characters.setText(f"{len(post['caption']):,}자")

    def select_post(self, item, previous):
        if item is None or not item.data(Qt.ItemDataRole.UserRole):
            return
        if self.dirty and not message(self, "변경 내용", "저장하지 않은 내용을 버리고 다른 게시물을 여시겠습니까?", confirm=True):
            self.post_list.blockSignals(True)
            self.post_list.setCurrentItem(previous)
            self.post_list.blockSignals(False)
            return
        self.load_post(self.service.store.post(item.data(Qt.ItemDataRole.UserRole)))
        self.refresh()

    def new_post(self):
        if self.dirty and not message(self, "변경 내용", "저장하지 않은 내용을 버리고 새 게시물을 만드시겠습니까?", confirm=True):
            return
        self.loading = True
        self.current = None
        self.title.clear()
        self.caption.clear()
        self.attachment = None
        self.remove_attachment = False
        self.state.setText("새로운 이야기")
        self.loading = False
        self.dirty = False
        self.notice.setText("초안부터 저장해 보세요.")
        self.update_attachment()
        self.refresh()
        self.title.setFocus()

    def reload_post(self):
        if not self.current:
            return
        if self.dirty and not message(self, "최신 내용 불러오기", "저장하지 않은 내용을 버리고 최신 버전을 불러오시겠습니까?", confirm=True):
            return
        self.load_post(self.service.store.post(self.current["id"]))
        self.refresh()

    def pick_media(self):
        path, _ = QFileDialog.getOpenFileName(self, "사진 또는 영상 선택", "", "미디어 (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.m4v *.webm)")
        if path:
            self.attachment = path
            self.remove_attachment = False
            self.update_attachment()
            self.changed()

    def clear_media(self):
        self.attachment = None
        self.remove_attachment = True
        self.update_attachment()
        self.changed()

    def update_attachment(self):
        self.preview_image.clear()
        if self.attachment:
            self.media_name.setText(Path(self.attachment).name)
            pixmap = QPixmap(self.attachment)
            if not pixmap.isNull():
                self.preview_image.setPixmap(pixmap.scaled(188, 156, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.preview_image.setText("영상 첨부")
        else:
            self.media_name.setText("아직 첨부하지 않았습니다.")
            self.preview_image.setText("사진 또는 영상\n\n첨부한 원본은 그대로 보존합니다.")

    def save_post(self):
        try:
            if self.current:
                post = self.service.update_post(self.current["id"], expected_version=self.current["version"], title=self.title.text(),
                    caption=self.caption.toPlainText(), targets=self.target_ids(), media=self.attachment,
                    remove_media=self.remove_attachment)
            else:
                post = self.service.create_post(self.title.text(), self.caption.toPlainText(), self.target_ids(), self.attachment)
            self.load_post(post)
            self.refresh()
            self.notice.setText("저장했습니다. CLI에서도 바로 볼 수 있습니다.")
            return post
        except AppError as exc:
            message(self, "저장할 수 없습니다", str(exc))
            return None

    def saved_id(self):
        if self.dirty or self.current is None:
            message(self, "저장 필요", "변경 내용을 먼저 저장하세요.")
            return None
        return self.current["id"]

    def preview_post(self):
        id = self.saved_id()
        if not id:
            return
        preview = self.service.preview(id)
        text = "\n\n".join(f"{target['label']} · {target['characters']}자\n{target['caption']}" for target in preview["targets"])
        if preview["warnings"]:
            text += "\n\n확인할 내용\n" + "\n".join(preview["warnings"])
        message(self, "게시 미리보기 · 외부 전송 없음", text or "게시할 계정을 선택하세요.")

    def approve_post(self):
        id = self.saved_id()
        if not id:
            return
        if not message(self, "게시 승인", "현재 저장한 문구·첨부·대상 계정을 게시할 버전으로 승인하시겠습니까?\n지금은 외부에 게시하지 않습니다.", confirm=True):
            return
        try:
            self.load_post(self.service.approve(id, self.current["version"]))
            self.refresh()
        except AppError as exc:
            message(self, "승인할 수 없습니다", str(exc))

    def publish_post(self):
        id = self.saved_id()
        if not id:
            return
        preview = self.service.preview(id)
        if preview["warnings"]:
            message(self, "게시 준비", "\n".join(preview["warnings"]))
            return
        names = ", ".join(target["label"] for target in preview["targets"])
        if not message(self, "실제 게시", f"{names}에 지금 게시하시겠습니까?\n첨부가 필요한 경우 공개 이미지 호스트로 전송됩니다.", confirm=True):
            return
        allow_x = any(target["platform"] == "x" for target in preview["targets"])
        if allow_x and not message(self, "X 유료 API", "X API 게시에는 비용이 발생합니다. 이 게시의 API 사용을 별도로 승인하시겠습니까?", confirm=True):
            return
        self.publish_button.setEnabled(False)
        self.notice.setText("게시 중입니다. 결과는 게시 기록에 남습니다.")
        self.thread = PublishThread(self.service, id, allow_x)
        self.thread.completed.connect(self.publish_finished)
        self.thread.failed.connect(self.publish_failed)
        self.thread.start()

    def publish_finished(self, result):
        self.load_post(result["post"])
        self.refresh()
        self.notice.setText("게시를 완료했습니다." if result["post"]["status"] == "published" else "게시 결과를 확인해야 합니다. 게시 기록을 확인하세요.")

    def publish_failed(self, text):
        message(self, "게시 결과", text)
        self.refresh()

    def add_account(self):
        if AccountDialog(self.service, parent=self).exec():
            self.refresh()

    def edit_account(self):
        item = self.account_list.currentItem()
        if not item:
            return
        if AccountDialog(self.service, self.service.store.account(item.data(Qt.ItemDataRole.UserRole)), self).exec():
            self.refresh()

    def save_settings(self):
        try:
            changes = {key: field.text().strip() for key, field in self.setting_fields.items()
                       if field.text().strip() != self.settings_baseline.get(key, "")}
            self.service.save_settings(changes, expected=self.settings_baseline)
            self.settings_dirty = False
            self.refresh()
            message(self, "설정", "저장했습니다. CLI에서도 같은 설정을 사용합니다.")
        except AppError as exc:
            message(self, "설정 오류", str(exc))

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "상태 데이터 백업", "publish-social-backup.sqlite3", "SQLite 상태 (*.sqlite3)")
        if path:
            try:
                self.service.store.backup(path)
                message(self, "백업", "상태 데이터를 백업했습니다. 첨부 파일과 키체인 인증 정보는 포함하지 않습니다.")
            except AppError as exc:
                message(self, "백업 오류", str(exc))

    def open_receipt(self, row, column):
        url = self.history_rows[row].get("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def resolve_history(self):
        row = self.history.currentRow()
        if row < 0:
            return
        record = self.history_rows[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("실제 게시 결과 확인")
        form = QFormLayout(dialog)
        hint = label("SNS에서 실제 게시 여부를 확인한 뒤 입력하세요.\n확인 없이 다시 게시하면 중복 게시될 수 있습니다.")
        form.addRow(hint)
        url = QLineEdit()
        url.setPlaceholderText("게시된 글의 HTTPS 주소")
        form.addRow("게시 URL", url)
        absent = QCheckBox("실제로 게시되지 않았음을 확인했습니다")
        form.addRow(absent)
        def resolve():
            try:
                self.service.resolve_job(record["id"], url=url.text().strip() or None, not_published=absent.isChecked())
                dialog.accept()
                self.refresh()
            except AppError as exc:
                message(dialog, "결과 확인", str(exc))
        form.addRow(button("확인한 결과 저장", resolve, True))
        dialog.exec()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            message(self, "게시 진행 중", "게시 결과를 기록할 때까지 잠시 기다려 주세요.")
            event.ignore()
        elif self.dirty and not message(self, "변경 내용", "저장하지 않은 내용을 버리고 닫으시겠습니까?", confirm=True):
            event.ignore()
        else:
            event.accept()


def launch(directory=None, screenshot=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Publish Social")
    app.setOrganizationName("WhosekeyLabs")
    app.setFont(QFont("Apple SD Gothic Neo", 13))
    window = Window(Service(directory))
    window.show()
    if screenshot:
        def capture():
            window.grab().save(str(Path(screenshot).expanduser()), "PNG")
            app.quit()
        QTimer.singleShot(600, capture)
    return app.exec()
