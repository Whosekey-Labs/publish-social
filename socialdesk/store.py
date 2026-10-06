"""단일 SQLite 저장소와 여러 프로세스의 쓰기 조정을 담당한다."""

from contextlib import contextmanager
from pathlib import Path
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone


class AppError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def data_dir(explicit=None):
    if explicit or os.environ.get("PUBLISH_SOCIAL_DATA_DIR"):
        return Path(explicit or os.environ["PUBLISH_SOCIAL_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Publish Social"
    return Path.home() / ".local" / "share" / "publish-social"


class Store:
    def __init__(self, directory=None):
        self.root = data_dir(directory)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.path = self.root / "state.sqlite3"
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise AppError("더 최신 앱에서 만든 데이터입니다. 앱을 업데이트하세요.")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            INSERT OR IGNORE INTO meta VALUES ('revision', 0);
            CREATE TABLE IF NOT EXISTS accounts (
              id TEXT PRIMARY KEY, platform TEXT NOT NULL, label TEXT NOT NULL,
              username TEXT NOT NULL DEFAULT '', config TEXT NOT NULL DEFAULT '{}',
              has_credentials INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, caption TEXT NOT NULL,
              captions TEXT NOT NULL DEFAULT '{}', targets TEXT NOT NULL DEFAULT '[]',
              media TEXT, version INTEGER NOT NULL DEFAULT 1,
              approved_version INTEGER, status TEXT NOT NULL DEFAULT 'draft',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES posts(id),
              account_id TEXT NOT NULL REFERENCES accounts(id), version INTEGER NOT NULL,
              status TEXT NOT NULL, payload TEXT NOT NULL, url TEXT, error TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, worker_started INTEGER NOT NULL DEFAULT 0,
              UNIQUE(post_id, account_id, version)
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            PRAGMA user_version=1;
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def write(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("UPDATE meta SET value=value+1 WHERE key='revision'")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def revision(self):
        with self.connection() as db:
            return db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]

    @staticmethod
    def post_row(row):
        if row is None:
            raise AppError("게시물을 찾을 수 없습니다.")
        result = dict(row)
        result["captions"] = json.loads(result["captions"])
        result["targets"] = json.loads(result["targets"])
        return result

    @staticmethod
    def account_row(row):
        if row is None:
            raise AppError("계정을 찾을 수 없습니다.")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        result["has_credentials"] = bool(result["has_credentials"])
        return result

    def accounts(self):
        with self.connection() as db:
            return [self.account_row(row) for row in db.execute("SELECT * FROM accounts ORDER BY created_at")]

    def account(self, id):
        with self.connection() as db:
            return self.account_row(db.execute("SELECT * FROM accounts WHERE id=?", (id,)).fetchone())

    def posts(self):
        with self.connection() as db:
            return [self.post_row(row) for row in db.execute("SELECT * FROM posts ORDER BY updated_at DESC")]

    def post(self, id):
        with self.connection() as db:
            return self.post_row(db.execute("SELECT * FROM posts WHERE id=?", (id,)).fetchone())

    def history(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT j.id,j.post_id,j.account_id,j.version,j.status,
                j.url,j.error,j.created_at,j.updated_at,p.title,a.label,a.platform
                FROM jobs j JOIN posts p ON p.id=j.post_id JOIN accounts a ON a.id=j.account_id
                ORDER BY j.created_at DESC""")]

    def settings(self):
        with self.connection() as db:
            return {row["key"]: row["value"] for row in db.execute("SELECT * FROM settings")}

    def job(self, id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
            if row is None:
                raise AppError("게시 작업을 찾을 수 없습니다.")
            result = dict(row)
            result["payload"] = json.loads(result["payload"])
            return result

    def backup(self, target):
        target = Path(target).expanduser().resolve()
        if target == self.path or target.exists():
            raise AppError("백업은 존재하지 않는 새 파일 경로를 지정하세요.")
        with self.connection() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        target.chmod(0o600)
        return str(target)


def new_id():
    return uuid.uuid4().hex
