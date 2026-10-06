"""Qt와 GUI 프로세스 없이 같은 데이터를 사용하는 JSON CLI."""

import argparse
import json
from pathlib import Path
import sys
import sqlite3

from . import __version__
from .service import Service, PLATFORMS
from .store import AppError


def parser():
    root = argparse.ArgumentParser(prog="publish-social", description="개인용 SNS 작업실 — GUI와 CLI가 하나의 데이터를 사용합니다.")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--data-dir", help="저장 위치를 명시적으로 바꿉니다. 기본값은 모든 화면과 CLI에서 같습니다.")
    root.add_argument("--json", action="store_true", help="JSON 출력 (CLI 기본값).")
    commands = root.add_subparsers(dest="command")
    commands.add_parser("status", help="저장 위치와 상태 확인")
    gui = commands.add_parser("gui", help="데스크톱 화면 실행")
    gui.add_argument("--screenshot", help=argparse.SUPPRESS)
    accounts = commands.add_parser("accounts", help="SNS 계정 관리").add_subparsers(dest="action", required=True)
    accounts.add_parser("list", help="계정 목록")
    add = accounts.add_parser("add", help="계정 추가")
    add.add_argument("--platform", choices=PLATFORMS, required=True)
    add.add_argument("--label", required=True)
    add.add_argument("--username", default="")
    add.add_argument("--config", default="{}", help="토큰을 제외한 플랫폼 식별 정보 JSON")
    config = accounts.add_parser("configure", help="플랫폼 식별 정보 수정")
    config.add_argument("id")
    config.add_argument("--config", required=True)
    secret = accounts.add_parser("credentials", help="표준 입력 JSON을 macOS 키체인에 저장")
    secret.add_argument("id")
    secret.add_argument("--from-stdin", action="store_true", required=True)
    posts = commands.add_parser("posts", help="게시물 관리").add_subparsers(dest="action", required=True)
    posts.add_parser("list", help="게시물 목록")
    create = posts.add_parser("create", help="초안 생성")
    create.add_argument("--title", required=True)
    create.add_argument("--text", default="")
    create.add_argument("--text-file")
    create.add_argument("--account", action="append", default=[])
    create.add_argument("--media")
    create.add_argument("--captions", default="{}", help="플랫폼별 문구 JSON")
    update = posts.add_parser("update", help="버전을 확인하고 초안 수정")
    update.add_argument("id")
    update.add_argument("--version", required=True, type=int)
    update.add_argument("--title")
    update.add_argument("--text")
    update.add_argument("--text-file")
    update.add_argument("--account", action="append")
    update.add_argument("--media")
    update.add_argument("--remove-media", action="store_true")
    update.add_argument("--captions")
    for name in ("show", "preview", "approve", "publish"):
        item = posts.add_parser(name, help={"show": "게시물 보기", "preview": "외부 호출 없는 미리보기", "approve": "현재 버전 게시 승인", "publish": "승인된 게시물 실제 게시"}[name])
        item.add_argument("id")
        if name == "approve":
            item.add_argument("--version", type=int, required=True)
        if name == "publish":
            item.add_argument("--confirm", action="store_true", required=True, help="이 명령의 실제 게시를 승인합니다.")
            item.add_argument("--allow-paid-x", action="store_true")
    history = commands.add_parser("history", help="게시 결과 관리").add_subparsers(dest="action", required=True)
    history.add_parser("list", help="게시 기록")
    resolve = history.add_parser("resolve", help="불확실한 작업의 실제 결과 확인")
    resolve.add_argument("id")
    choice = resolve.add_mutually_exclusive_group(required=True)
    choice.add_argument("--url")
    choice.add_argument("--not-published", action="store_true")
    settings = commands.add_parser("settings", help="공유 설정").add_subparsers(dest="action", required=True)
    settings.add_parser("show", help="설정 조회")
    edit = settings.add_parser("set", help="이미지 호스트 설정 저장")
    edit.add_argument("--name", required=True)
    edit.add_argument("--value", required=True)
    backup = commands.add_parser("backup", help="SQLite 상태 백업 (미디어·키체인 제외)")
    backup.add_argument("--output", required=True)
    worker = commands.add_parser("internal-worker", help=argparse.SUPPRESS)
    worker.add_argument("--job", required=True)
    return root


def run(argv=None):
    args = parser().parse_args(argv)
    if args.command is None or args.command == "gui":
        # CLI의 다른 명령에서는 Qt를 import하거나 앱을 실행하지 않는다.
        from .gui import launch
        return launch(args.data_dir, getattr(args, "screenshot", None))
    if args.command == "internal-worker":
        from .worker import run as worker
        print(json.dumps(worker(args.data_dir, args.job), ensure_ascii=False))
        return 0
    try:
        service = Service(args.data_dir)
        store = service.store
        if args.command == "status":
            data = {"data_dir": str(store.root), "database": str(store.path), "revision": store.revision(),
                    "accounts": len(store.accounts()), "posts": len(store.posts()), "gui_required": False}
        elif args.command == "accounts":
            if args.action == "list":
                data = store.accounts()
            elif args.action == "add":
                data = service.create_account(args.platform, args.label, args.username, json.loads(args.config))
            elif args.action == "configure":
                data = service.configure_account(args.id, json.loads(args.config))
            else:
                if sys.stdin.isatty():
                    raise AppError("인증 JSON은 안전한 표준 입력으로 전달하세요. 명령 인자에 토큰을 넣지 마세요.")
                data = service.credentials(args.id, json.load(sys.stdin))
        elif args.command == "posts":
            text = Path(args.text_file).read_text(encoding="utf-8") if getattr(args, "text_file", None) else getattr(args, "text", None)
            if args.action == "list":
                data = store.posts()
            elif args.action == "create":
                data = service.create_post(args.title, text or "", args.account, args.media, json.loads(args.captions))
            elif args.action == "update":
                data = service.update_post(args.id, expected_version=args.version, title=args.title, caption=text,
                                           targets=args.account, media=args.media, remove_media=args.remove_media,
                                           captions=json.loads(args.captions) if args.captions else None)
            elif args.action == "show":
                data = store.post(args.id)
            elif args.action == "preview":
                data = service.preview(args.id)
            elif args.action == "approve":
                data = service.approve(args.id, args.version)
            else:
                data = service.publish(args.id, allow_paid_x=args.allow_paid_x)
        elif args.command == "history":
            data = store.history() if args.action == "list" else service.resolve_job(args.id, url=args.url, not_published=args.not_published)
        elif args.command == "settings":
            data = store.settings() if args.action == "show" else service.save_settings({args.name: args.value})
        else:
            data = {"database_backup": store.backup(args.output), "includes_media": False, "includes_credentials": False}
        success = not (args.command == "posts" and args.action == "publish" and data["post"]["status"] != "published")
        print(json.dumps({"ok": success, "data": data, "revision": store.revision()}, ensure_ascii=False))
        return 0 if success else 1
    except (AppError, ValueError, OSError, sqlite3.Error) as exc:
        from security import safe_error
        print(json.dumps({"ok": False, "error": safe_error(exc)}, ensure_ascii=False))
        return 2


def main():
    raise SystemExit(run())
