"""개인 Applications 폴더와 CLI 심볼릭 링크를 함께 설치한다."""

from pathlib import Path
import argparse
import os
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description="개인용 앱과 CLI 설치")
    parser.add_argument("--app", required=True)
    parser.add_argument("--replace", action="store_true", help="기존 이 앱만 교체합니다. 데이터는 앱 밖에 보존됩니다.")
    args = parser.parse_args()
    source = Path(args.app).expanduser().resolve()
    if not (source / "Contents" / "MacOS" / "publish-social").is_file():
        raise SystemExit("빌드한 Publish Social.app을 지정하세요.")
    destination = Path.home() / "Applications" / "Publish Social.app"
    destination.parent.mkdir(exist_ok=True)
    if destination.exists() and not args.replace:
        raise SystemExit("기존 앱이 있습니다. 종료한 뒤 --replace로 교체하세요.")
    executable = destination / "Contents" / "MacOS" / "publish-social"
    link = Path.home() / ".local" / "bin" / "publish-social"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        if not link.is_symlink() or link.resolve() != executable:
            raise SystemExit("다른 publish-social 명령이 있어 자동 덮어쓰지 않습니다.")
    staging = destination.with_name(".Publish Social.installing.app")
    if staging.exists():
        raise SystemExit("이전 설치 작업 폴더가 남아 있습니다. 먼저 확인하세요.")
    shutil.copytree(source, staging, symlinks=True)
    try:
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(staging)], check=True)
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    if not link.is_symlink():
        link.symlink_to(executable)
    print(f"앱 설치: {destination}\nCLI 설치: {link}")


if __name__ == "__main__":
    main()
