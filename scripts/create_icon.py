"""개인용 앱 아이콘을 코드로 그려 ICNS 파일로 저장한다."""

from pathlib import Path
from PIL import Image, ImageDraw


def create_icon(target):
    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((52, 52, 972, 972), radius=210, fill="#3c5a39")
    draw.rounded_rectangle((292, 208, 732, 816), radius=42, fill="#fcfcf8")
    draw.polygon(((570, 208), (732, 370), (570, 370)), fill="#c7d7b9")
    draw.line((374, 454, 626, 454), fill="#a2b797", width=28)
    draw.line((374, 538, 566, 538), fill="#a2b797", width=28)
    draw.line((374, 622, 608, 622), fill="#a2b797", width=28)
    draw.ellipse((622, 646, 850, 874), fill="#e1ecd7")
    draw.line((736, 821, 736, 705), fill="#3c5a39", width=27)
    draw.line((686, 753, 736, 703, 788, 753), fill="#3c5a39", width=27)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="ICNS")
    return target


if __name__ == "__main__":
    print(create_icon(Path(__file__).resolve().parents[1] / "build" / "app-icon.icns"))
