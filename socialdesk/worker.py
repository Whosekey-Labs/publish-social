"""게시 프로세스를 분리해 계정별 인증 환경이 섞이지 않도록 한다."""

from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time

from .store import Store, AppError
from .vault import KeychainVault
from .service import PLATFORMS, VIDEO_SUFFIXES


def execute(directory, job_id):
    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / "social.py")]
    command += ["--data-dir", str(directory), "internal-worker", "--job", job_id]
    result = subprocess.run(command, capture_output=True, text=True, timeout=900)
    try:
        return json.loads(result.stdout.strip())
    except (ValueError, TypeError):
        return {"ok": False, "error": "게시 프로세스가 결과를 반환하지 못했습니다. 실제 계정을 확인하세요."}


def run(directory, job_id, *, vault=None):
    store = Store(directory)
    # 같은 작업을 두 프로세스가 실행하더라도 API 호출은 한 번만 시작한다.
    with store.write() as db:
        row = db.execute("UPDATE jobs SET worker_started=1 WHERE id=? AND status='publishing' AND worker_started=0", (job_id,))
        if row.rowcount != 1:
            return {"ok": False, "error": "이미 실행했거나 종료한 게시 작업입니다."}
    job = store.job(job_id)
    payload = job["payload"]
    account, post = payload["account"], payload["post"]
    vault = vault or KeychainVault()
    try:
        secrets = vault.get(account["id"])
        if any(not secrets.get(key) for key in PLATFORMS[account["platform"]][2]):
            raise AppError("키체인에 필요한 인증 정보가 없습니다.")
        # 게시 어댑터는 이 프로세스의 계정 정보만 읽는다.
        for key in list(os.environ):
            if any(key.startswith(prefix) for prefix in ("INSTAGRAM_", "THREADS_", "BLUESKY_", "MASTODON_", "FACEBOOK_", "LINKEDIN_", "YOUTUBE_", "X_", "IMAGE_HOST_")):
                del os.environ[key]
        os.environ.update(account["config"])
        os.environ.update(secrets)
        os.environ.update(payload["settings"])
        os.environ["X_TRANSPORT"] = "api"
        import publish as legacy
        import images
        from security import safe_error
        with tempfile.TemporaryDirectory(prefix="publish-social-worker-") as directory:
            folder = Path(directory)
            folder.chmod(0o700)
            legacy.ENV_PATH = folder / "refresh.env"
            platform = account["platform"]
            caption = post["captions"].get(platform, post["caption"])
            media = None
            try:
                # 라이브 API 어댑터의 출력은 JSON 프로토콜에 섞지 않는다.
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    if post["media"]:
                        field = "video" if Path(post["media"]).suffix.lower() in VIDEO_SUFFIXES else "image"
                        record = legacy.Post(path=folder / "post.md", frontmatter={field: post["media"], f"{field}-alt": post["title"]}, body="")
                        media = legacy.resolve_media(record, [platform])
                    if platform == "youtube":
                        if not media or media.kind != "video":
                            raise AppError("YouTube에는 영상 첨부가 필요합니다.")
                        url = legacy.post_youtube(caption, media, title=post["title"], privacy="public")
                    else:
                        url = legacy.POSTERS[platform](caption, media)
                result = {"ok": True, "url": url}
            except Exception as exc:
                result = {"ok": False, "error": safe_error(exc)}
            finally:
                # 갱신된 토큰은 임시 파일에서 키체인으로 옮기고 임시 파일은 삭제한다.
                if legacy.ENV_PATH.exists():
                    from dotenv import dotenv_values
                    changes = dict(dotenv_values(legacy.ENV_PATH))
                    if changes:
                        secrets.update({key: value for key, value in changes.items() if value is not None})
                        vault.set(account["id"], secrets)
        return result
    except AppError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "게시 처리 중 오류가 발생했습니다. 실제 게시 결과를 확인하세요."}
