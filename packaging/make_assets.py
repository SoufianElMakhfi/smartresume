"""Erzeugt App-Symbol und Store-Bilder aus einer Vorlage (Petrol-Kachel mit Dokument und „SR“).

    python packaging/make_assets.py

Ergebnis: packaging/icon.ico (für die .exe) und packaging/msix/Assets/*.png (für das Store-Paket).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = ROOT.parent / "fonts" / "Lexend-SemiBold.ttf"
PETROL = (15, 95, 110, 255)
WHITE = (255, 255, 255, 255)

# Dateiname → (Breite, Höhe); Namen wie im AppxManifest
STORE = {
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150),
    "Square310x310Logo.png": (310, 310),
    "StoreLogo.png": (50, 50),
    "SplashScreen.png": (620, 300),
}


def symbol(size: int) -> Image.Image:
    """Quadratisches Symbol: abgerundete Petrol-Kachel, weißes Blatt mit Eselsohr, „SR“ in Petrol."""
    s = size * 4                                   # groß zeichnen, dann glatt verkleinern
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.22, fill=PETROL)
    w, h = s * 0.50, s * 0.64                      # Blatt
    x0, y0 = (s - w) / 2, (s - h) / 2
    fold = w * 0.30
    d.polygon([(x0, y0), (x0 + w - fold, y0), (x0 + w, y0 + fold), (x0 + w, y0 + h), (x0, y0 + h)],
              fill=WHITE)
    d.polygon([(x0 + w - fold, y0), (x0 + w - fold, y0 + fold), (x0 + w, y0 + fold)],
              fill=(183, 214, 219, 255))
    font = ImageFont.truetype(str(FONT), int(w * 0.42))
    box = d.textbbox((0, 0), "SR", font=font)
    tx = x0 + (w - (box[2] - box[0])) / 2 - box[0]
    ty = y0 + h * 0.58 - (box[3] - box[1]) / 2 - box[1]
    d.text((tx, ty), "SR", font=font, fill=PETROL)
    return img.resize((size, size), Image.LANCZOS)


def tile(width: int, height: int) -> Image.Image:
    """Store-Bild im gewünschten Format: Symbol mittig auf Petrol (Breitformate) bzw. das Symbol selbst."""
    if width == height:
        return symbol(width)
    img = Image.new("RGBA", (width, height), PETROL)
    side = int(min(width, height) * 0.8)
    img.alpha_composite(symbol(side), ((width - side) // 2, (height - side) // 2))
    return img


def main() -> None:
    out = ROOT / "msix" / "Assets"
    out.mkdir(parents=True, exist_ok=True)
    for name, (w, h) in STORE.items():
        tile(w, h).save(out / name)
    big = symbol(256)
    big.save(ROOT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    symbol(300).save(ROOT / "store-logo-300.png")       # für den Store-Eintrag (1:1-Logo)
    print(f"Bilder geschrieben nach {out} und {ROOT / 'icon.ico'}")


if __name__ == "__main__":
    main()
