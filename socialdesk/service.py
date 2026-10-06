"""모든 데이터 변경과 게시 규칙은 GUI·CLI 공통 서비스에서 실행한다."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import sqlite3
from urllib.parse import urlparse

from .store import Store, AppError, new_id, now
from .vault import KeychainVault

PLATFORMS = {
    "instagram": ("Instagram", ("INSTAGRAM_USER_ID",), ("INSTAGRAM_ACCESS_TOKEN",)),
    "threads": ("Threads", ("THREADS_USER_ID",), ("THREADS_ACCESS_TOKEN",)),
    "bluesky": ("Bluesky", ("BLUESKY_HANDLE",), ("BLUESKY_APP_PASSWORD",)),
    "mastodon": ("Mastodon", ("MASTODON_INSTANCE_URL",), ("MASTODON_ACCESS_TOKEN",)),
    "facebook": ("Facebook", ("FACEBOOK_PAGE_ID",), ("FACEBOOK_PAGE_ACCESS_TOKEN",)),
    "linkedin": ("LinkedIn", ("LINKEDIN_ORG_URN",), ("LINKEDIN_ACCESS_TOKEN",)),
    "youtube": ("YouTube", ("YOUTUBE_CLIENT_ID",), ("YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")),
    "x": ("X", (), ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")),
}
LIMITS = {"instagram": 2200, "threads": 500, "bluesky": 300, "mastodon": 500,
          "facebook": 63206, "linkedin": 3000, "youtube": 5000, "x": 280}
SETTING_KEYS = {"IMAGE_HOST_BASE_URL", "IMAGE_HOST_SSH", "IMAGE_HOST_PATH"}
SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".m4v", ".webm"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


class Service:
    def __init__(self, directory=None, *, vault=None, publisher=None):
        self.store = Store(directory)
        self.vault = vault or KeychainVault()
        self.publisher = publisher

    def create_account(self, platform, label, username="", config=None):
        if platform not in PLATFORMS or not label.strip():
            raise AppError("지원하는 플랫폼과 계정 이름을 지정하세요.")
        config = self.validate_config(platform, config or {})
        id = new_id()
        with self.store.write() as db:
            db.execute("INSERT INTO accounts(id,platform,label,username,config,created_at) VALUES(?,?,?,?,?,?)",
                       (id, platform, label.strip(), username.strip(), json.dumps(config), now()))
        return self.store.account(id)

    def validate_config(self, platform, config):
        if not isinstance(config, dict) or set(config) - set(PLATFORMS[platform][1]):
            raise AppError("공개 설정에는 플랫폼 식별 정보만 넣으세요. 토큰은 인증 정보로 저장합니다.")
        if any(not isinstance(value, str) for value in config.values()):
            raise AppError("계정 설정값은 문자열이어야 합니다.")
        return config

    def configure_account(self, id, config):
        account = self.store.account(id)
        config = self.validate_config(account["platform"], config)
        if config == account["config"]:
            return account
        with self.store.write() as db:
            self.guard_account_change(db, id)
            db.execute("UPDATE accounts SET config=? WHERE id=?", (json.dumps(config), id))
            self.invalidate_account_posts(db, id)
        return self.store.account(id)

    def credentials(self, id, secrets):
        account = self.store.account(id)
        allowed = set(PLATFORMS[account["platform"]][2])
        if not isinstance(secrets, dict) or set(secrets) != allowed or any(not isinstance(v, str) or not v for v in secrets.values()):
            raise AppError("플랫폼에 필요한 인증 항목을 모두 입력하세요.")
        with self.store.write() as db:
            self.guard_account_change(db, id)
            self.vault.set(id, secrets)
            db.execute("UPDATE accounts SET has_credentials=1 WHERE id=?", (id,))
            self.invalidate_account_posts(db, id)
        return {"id": id, "has_credentials": True}

    def guard_account_change(self, db, id):
        if db.execute("SELECT 1 FROM jobs WHERE account_id=? AND status='publishing'", (id,)).fetchone():
            raise AppError("게시 중인 계정은 설정을 변경할 수 없습니다.")

    def invalidate_account_posts(self, db, id):
        for row in db.execute("SELECT id,targets FROM posts WHERE status IN ('draft','approved','partial')").fetchall():
            if id in json.loads(row["targets"]):
                sent = db.execute("SELECT 1 FROM jobs WHERE post_id=? AND status='published'", (row["id"],)).fetchone()
                if sent:
                    db.execute("UPDATE posts SET approved_version=NULL,status='partial',updated_at=? WHERE id=?", (now(), row["id"]))
                else:
                    db.execute("UPDATE posts SET version=version+1,approved_version=NULL,status='draft',updated_at=? WHERE id=?", (now(), row["id"]))

    def save_settings(self, values, *, expected=None):
        if not isinstance(values, dict) or set(values) - SETTING_KEYS or any(not isinstance(v, str) for v in values.values()):
            raise AppError("지원하는 이미지 호스트 설정만 저장할 수 있습니다.")
        if values.get("IMAGE_HOST_BASE_URL") and urlparse(values["IMAGE_HOST_BASE_URL"]).scheme != "https":
            raise AppError("이미지 호스트는 HTTPS 주소를 사용하세요.")
        with self.store.write() as db:
            if expected is not None:
                for key in values:
                    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                    if (row[0] if row else "") != expected.get(key, ""):
                        raise AppError("다른 화면이나 CLI에서 같은 설정을 변경했습니다. 최신 값을 다시 불러오세요.")
            for key, value in values.items():
                db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        return self.store.settings()

    def import_media(self, path):
        if not path:
            return None
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in SUFFIXES:
            raise AppError("지원하는 이미지 또는 영상 파일을 선택하세요.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        folder = self.store.root / "media"
        folder.mkdir(mode=0o700, exist_ok=True)
        target = folder / f"{digest}{source.suffix.lower()}"
        if not target.exists():
            # 첨부한 파일만 관리 저장소로 복사하며 원본은 변경하지 않는다.
            temporary = folder / f".{new_id()}"
            try:
                shutil.copyfile(source, temporary)
                temporary.chmod(0o600)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                    raise AppError("첨부 중 원본 파일이 변경되었습니다. 다시 선택하세요.")
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return str(target)

    def validate_targets(self, db, targets):
        if not isinstance(targets, list) or len(set(targets)) != len(targets):
            raise AppError("대상 계정 목록을 확인하세요.")
        for id in targets:
            if db.execute("SELECT 1 FROM accounts WHERE id=?", (id,)).fetchone() is None:
                raise AppError("선택한 대상 계정이 존재하지 않습니다.")

    def create_post(self, title, caption="", targets=None, media=None, captions=None):
        if not title.strip():
            raise AppError("게시물 제목을 입력하세요.")
        if not isinstance(captions or {}, dict):
            raise AppError("플랫폼별 문구는 JSON 객체로 지정하세요.")
        id, timestamp = new_id(), now()
        attachment = self.import_media(media)
        with self.store.write() as db:
            self.validate_targets(db, targets or [])
            db.execute("""INSERT INTO posts(id,title,caption,captions,targets,media,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                       (id, title.strip(), caption, json.dumps(captions or {}), json.dumps(targets or []), attachment, timestamp, timestamp))
        return self.store.post(id)

    def update_post(self, id, *, expected_version, title=None, caption=None, targets=None, media=None, captions=None, remove_media=False):
        attachment = self.import_media(media) if media else None
        with self.store.write() as db:
            post = self.store.post_row(db.execute("SELECT * FROM posts WHERE id=?", (id,)).fetchone())
            if post["version"] != expected_version:
                raise AppError("다른 화면이나 CLI에서 수정한 게시물입니다. 최신 내용을 다시 불러오세요.")
            if db.execute("SELECT 1 FROM jobs WHERE post_id=? AND status IN ('publishing','uncertain')", (id,)).fetchone():
                raise AppError("게시 중이거나 결과 확인이 필요한 작업입니다. 먼저 게시 기록을 확인하세요.")
            if db.execute("SELECT 1 FROM jobs WHERE post_id=? AND status='published'", (id,)).fetchone():
                raise AppError("이미 게시한 내용은 이 화면에서 바꾸지 않습니다. 수정한 내용을 다시 게시하려면 새 게시물로 만드세요.")
            title = post["title"] if title is None else title.strip()
            if not title:
                raise AppError("게시물 제목을 입력하세요.")
            targets = post["targets"] if targets is None else targets
            self.validate_targets(db, targets)
            db.execute("""UPDATE posts SET title=?,caption=?,captions=?,targets=?,media=?,version=version+1,
                       approved_version=NULL,status='draft',updated_at=? WHERE id=?""",
                       (title, post["caption"] if caption is None else caption,
                        json.dumps(post["captions"] if captions is None else captions), json.dumps(targets),
                        None if remove_media else attachment or post["media"], now(), id))
        return self.store.post(id)

    def preview(self, id):
        post = self.store.post(id)
        accounts = [self.store.account(target) for target in post["targets"]]
        warnings = []
        if not accounts:
            warnings.append("게시할 계정을 선택하세요.")
        if post["media"] and not Path(post["media"]).is_file():
            warnings.append("첨부 파일이 없습니다.")
        if post["media"] and any(a["platform"] in {"instagram", "threads", "facebook"} for a in accounts):
            settings = self.store.settings()
            if any(not settings.get(key) for key in SETTING_KEYS):
                warnings.append("미디어 전송에 필요한 이미지 호스트 설정을 입력하세요.")
        targets = []
        for account in accounts:
            platform = account["platform"]
            caption = post["captions"].get(platform, post["caption"])
            if not isinstance(caption, str):
                raise AppError("게시 문구는 문자열이어야 합니다.")
            if len(caption) > LIMITS[platform]:
                warnings.append(f"{account['label']}: 문구가 {LIMITS[platform]}자를 넘습니다.")
            if not account["has_credentials"]:
                warnings.append(f"{account['label']}: 인증 정보가 필요합니다.")
            if any(not account["config"].get(field) for field in PLATFORMS[platform][1]):
                warnings.append(f"{account['label']}: 계정 식별 정보를 입력하세요.")
            if platform == "instagram" and not post["media"]:
                warnings.append("Instagram 게시에는 사진 또는 영상이 필요합니다.")
            if platform == "youtube" and (not post["media"] or Path(post["media"]).suffix.lower() not in VIDEO_SUFFIXES):
                warnings.append("YouTube 게시에는 영상이 필요합니다.")
            targets.append({"account_id": account["id"], "platform": platform, "label": account["label"], "caption": caption, "characters": len(caption)})
        return {"post": post, "targets": targets, "warnings": warnings, "network_used": False}

    def approve(self, id, expected_version):
        preview = self.preview(id)
        if not preview["targets"]:
            raise AppError("게시할 계정을 먼저 선택하세요.")
        with self.store.write() as db:
            result = db.execute("""UPDATE posts SET approved_version=version,status='approved',updated_at=?
                                  WHERE id=? AND version=? AND status IN ('draft','approved','partial')""", (now(), id, expected_version))
            if result.rowcount != 1:
                raise AppError("게시물 상태가 바뀌었습니다. 최신 내용을 다시 확인하세요.")
        return self.store.post(id)

    def claim(self, id, account_id, *, allow_paid_x=False):
        with self.store.write() as db:
            post = self.store.post_row(db.execute("SELECT * FROM posts WHERE id=?", (id,)).fetchone())
            if post["approved_version"] != post["version"]:
                raise AppError("현재 게시물 버전의 게시 승인이 필요합니다.")
            if account_id not in post["targets"]:
                raise AppError("게시물에 지정되지 않은 계정입니다.")
            account = self.store.account_row(db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())
            existing = db.execute("SELECT * FROM jobs WHERE post_id=? AND account_id=? AND version=?", (id, account_id, post["version"])).fetchone()
            if existing:
                if existing["status"] == "published":
                    return {"already_published": True, "id": existing["id"], "url": existing["url"]}
                raise AppError("이미 시도한 게시입니다. 중복 게시를 막기 위해 기록에서 결과를 먼저 확인하세요.")
            if account["platform"] == "x" and not allow_paid_x:
                raise AppError("X 유료 API 게시에는 별도 승인과 --allow-paid-x가 필요합니다.")
            if not account["has_credentials"] or any(not account["config"].get(k) for k in PLATFORMS[account["platform"]][1]):
                raise AppError("계정의 인증 정보와 식별 정보를 먼저 설정하세요.")
            job_id = new_id()
            payload = {"post": post, "account": account, "settings": {k: v for k, v in db.execute("SELECT key,value FROM settings")}}
            db.execute("INSERT INTO jobs(id,post_id,account_id,version,status,payload,url,error,created_at,updated_at) VALUES(?,?,?,?,?,?,NULL,NULL,?,?)",
                       (job_id, id, account_id, post["version"], "publishing", json.dumps(payload), now(), now()))
            db.execute("UPDATE posts SET status='publishing',updated_at=? WHERE id=?", (now(), id))
        return self.store.job(job_id)

    def finish(self, job_id, result):
        with self.store.write() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None or job["status"] != "publishing":
                raise AppError("진행 중인 게시 작업이 아닙니다.")
            status = "published" if result.get("ok") else "uncertain"
            db.execute("UPDATE jobs SET status=?,url=?,error=?,updated_at=? WHERE id=?",
                       (status, result.get("url"), result.get("error"), now(), job_id))
            post = self.store.post_row(db.execute("SELECT * FROM posts WHERE id=?", (job["post_id"],)).fetchone())
            statuses = [row[0] for row in db.execute("SELECT status FROM jobs WHERE post_id=? AND version=?", (post["id"], post["version"]))]
            overall = "published" if len(statuses) == len(post["targets"]) and all(s == "published" for s in statuses) else "partial"
            if "publishing" in statuses:
                overall = "publishing"
            if "uncertain" in statuses:
                overall = "uncertain"
            db.execute("UPDATE posts SET status=?,updated_at=? WHERE id=?", (overall, now(), post["id"]))
        return self.store.job(job_id)

    def publish(self, id, *, allow_paid_x=False):
        post = self.store.post(id)
        preview = self.preview(id)
        if preview["warnings"]:
            raise AppError("게시 준비를 확인하세요: " + " / ".join(preview["warnings"]))
        if not post["targets"]:
            raise AppError("게시할 계정이 없습니다.")
        if any(target["platform"] == "x" for target in preview["targets"]) and not allow_paid_x:
            raise AppError("X 유료 API 게시에는 별도 승인과 --allow-paid-x가 필요합니다.")
        results = []
        for target in post["targets"]:
            job = self.claim(id, target, allow_paid_x=allow_paid_x)
            if job.get("already_published"):
                results.append(job)
                continue
            try:
                if self.publisher:
                    result = self.publisher(job)
                else:
                    from .worker import execute
                    result = execute(self.store.root, job["id"])
            except Exception:
                result = {"ok": False, "error": "게시 결과를 확정하지 못했습니다. 재시도 전에 실제 계정을 확인하세요."}
            completed = self.finish(job["id"], result)
            results.append({key: completed.get(key) for key in ("id", "status", "url", "error")})
            if not result.get("ok"):
                break
        return {"post": self.store.post(id), "results": results}

    def resolve_job(self, id, *, url=None, not_published=False):
        if bool(url) == bool(not_published):
            raise AppError("게시 URL 또는 미게시 확인 중 하나를 지정하세요.")
        if url and urlparse(url).scheme != "https":
            raise AppError("확인한 게시 URL은 HTTPS 주소여야 합니다.")
        with self.store.write() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (id,)).fetchone()
            if job is None or job["status"] not in {"uncertain", "publishing"}:
                raise AppError("결과 확인이 필요한 작업이 아닙니다.")
            if not_published:
                db.execute("DELETE FROM jobs WHERE id=?", (id,))
                db.execute("UPDATE posts SET status='draft',approved_version=NULL,updated_at=? WHERE id=?", (now(), job["post_id"]))
            else:
                db.execute("UPDATE jobs SET status='published',url=?,error=NULL,updated_at=? WHERE id=?", (url, now(), id))
                post = self.store.post_row(db.execute("SELECT * FROM posts WHERE id=?", (job["post_id"],)).fetchone())
                published = db.execute("SELECT count(*) FROM jobs WHERE post_id=? AND version=? AND status='published'", (post["id"], post["version"])).fetchone()[0]
                status = "published" if published == len(post["targets"]) else "partial"
                db.execute("UPDATE posts SET status=?,updated_at=? WHERE id=?", (status, now(), job["post_id"]))
        return {"resolved": True, "post": self.store.post(job["post_id"])}
