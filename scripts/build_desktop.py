"""개인용 macOS arm64 앱을 빌드한다. 실제 계정 데이터는 포함하지 않는다."""

from pathlib import Path
import argparse
import subprocess
import sys
from create_icon import create_icon


def main():
    parser = argparse.ArgumentParser(description="Publish Social macOS 앱 빌드")
    parser.add_argument("--output", default="dist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    create_icon(root / "build" / "app-icon.icns")
    subprocess.run([sys.executable, "-m", "PyInstaller", str(root / "desktop.spec"),
                    "--noconfirm", "--distpath", str(Path(args.output).resolve()),
                    "--workpath", str(root / "build"), "--log-level", "WARN"], cwd=root, check=True)
    print(f"앱 생성: {Path(args.output).resolve() / 'Publish Social.app'}")


if __name__ == "__main__":
    main()
