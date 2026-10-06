# macOS 앱 안에 동일한 GUI·CLI 실행 파일을 넣는다.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "social.py")], pathex=[str(root)],
    datas=[(str(root / "LICENSE"), ".")],
    hiddenimports=["keyring.backends.macOS", "socialdesk.gui", "publish", "images", "atproto", "mastodon", "tweepy"],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick", "pytest", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="publish-social", console=True,
          strip=False, upx=False, target_arch="arm64")
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="publish-social")
app = BUNDLE(coll, name="Publish Social.app", icon=str(root / "build" / "app-icon.icns"), bundle_identifier="com.whosekeylabs.publishsocial", version="0.2.0",
             info_plist={"NSPrincipalClass": "NSApplication", "NSHighResolutionCapable": True,
                         "LSMinimumSystemVersion": "13.0", "CFBundleDisplayName": "Publish Social"})
