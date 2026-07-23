"""Erzeugt build/CrashAnalyzer.ico (Puls-Linie auf blauem Kachel-Grund,
gleiches Motiv wie das Web-Favicon)."""
from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (42, 120, 214, 255)
WHITE = (255, 255, 255, 255)


def draw_tile(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 7 // 32
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BLUE)
    s = size / 32.0
    pts = [(5 * s, 17 * s), (11 * s, 17 * s), (13.5 * s, 10 * s),
           (17.5 * s, 23 * s), (20.5 * s, 17 * s), (27 * s, 17 * s)]
    d.line(pts, fill=WHITE, width=max(2, int(2.6 * s)), joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - 1.2 * s, p[1] - 1.2 * s, p[0] + 1.2 * s, p[1] + 1.2 * s], fill=WHITE)
    return img


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = draw_tile(256)
    out = Path(__file__).parent / "CrashAnalyzer.ico"
    base.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Icon geschrieben: {out}")


if __name__ == "__main__":
    main()
