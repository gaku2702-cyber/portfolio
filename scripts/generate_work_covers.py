"""Generate unified Works gallery cover images (960x540 JPEG)."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "covers"
W, H = 960, 540

NAVY = "#1B3264"
NAVY_PALE = "#E8EDF5"
TEXT_SUB = "#6B7280"
BORDER = "#E2E4E9"

COVERS = [
    {
        "file": "imposition-demo.jpg",
        "category": "DTP Automation",
        "title": ["JFX200", "面付シミュレーター"],
        "motif": "imposition",
    },
    {
        "file": "word-tag-extractor.jpg",
        "category": "Data Conversion",
        "title": ["Word → InDesign", "組版パイプライン"],
        "motif": "word",
    },
    {
        "file": "photo-cut-demo.jpg",
        "category": "Image Processing",
        "title": ["写真切り出しツール", "Photo Extractor"],
        "motif": "photo",
    },
    {
        "file": "pman-task-demo.jpg",
        "category": "Production Workflow",
        "title": ["MIS 部署別", "タスク管理"],
        "motif": "task",
    },
    {
        "file": "dx-consulting.jpg",
        "category": "DX Support",
        "title": ["DX化ヒアリング", "ロードマップ策定"],
        "motif": "consulting",
    },
]


def load_fonts():
    meiryo = "C:/Windows/Fonts/meiryo.ttc"
    try:
        return {
            "pill": ImageFont.truetype(meiryo, 13),
            "title_lg": ImageFont.truetype(meiryo, 40),
            "title_md": ImageFont.truetype(meiryo, 32),
            "title_sm": ImageFont.truetype(meiryo, 26),
        }
    except OSError:
        default = ImageFont.load_default()
        return {"pill": default, "title_lg": default, "title_md": default, "title_sm": default}


def draw_background(d: ImageDraw.ImageDraw) -> None:
    d.rectangle([0, 0, W, H], fill="#FAFBFC")
    for i in range(120):
        alpha = int(18 * (1 - i / 120))
        color = (27, 50, 100, alpha)
        d.ellipse([W - 280 + i, -80 + i, W + 80 - i, 200 - i], fill=color)
    for i in range(80):
        alpha = int(10 * (1 - i / 80))
        d.ellipse([-60 + i, H - 160 + i, 180 - i, H + 40 - i], fill=(232, 237, 245, alpha))


def draw_pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font) -> None:
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 14, 6
    d.rounded_rectangle(
        [x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
        radius=14,
        fill=NAVY_PALE,
        outline=BORDER,
    )
    d.text((x + pad_x, y + pad_y - 1), text, fill=NAVY, font=font)


def draw_title(d: ImageDraw.ImageDraw, lines: list[str], fonts) -> None:
    x, y = 48, 118
    for i, line in enumerate(lines):
        font = fonts["title_lg"] if i == 0 and len(line) <= 12 else fonts["title_md"]
        if len(line) > 14:
            font = fonts["title_sm"]
        d.text((x, y), line, fill=NAVY, font=font)
        bbox = d.textbbox((x, y), line, font=font)
        y = bbox[3] + 8


def draw_motif_imposition(d: ImageDraw.ImageDraw) -> None:
    ox, oy = 520, 200
    d.rounded_rectangle([ox, oy, ox + 380, oy + 280], radius=8, fill="#FFFFFF", outline=BORDER, width=2)
    d.rectangle([ox, oy, ox + 100, oy + 280], fill=NAVY_PALE)
    for i in range(4):
        d.rectangle([ox + 14, oy + 20 + i * 58, ox + 86, oy + 58 + i * 58], fill="#FFFFFF", outline=BORDER)
    gx, gy = ox + 118, oy + 18
    for row in range(3):
        for col in range(4):
            d.rectangle(
                [gx + col * 62, gy + row * 82, gx + col * 62 + 52, gy + row * 82 + 72],
                fill="#F0F4FA" if (row + col) % 2 == 0 else "#FFFFFF",
                outline="#C8D4E8",
            )


def draw_motif_word(d: ImageDraw.ImageDraw) -> None:
    ox, oy = 500, 210
    d.rounded_rectangle([ox, oy, ox + 170, oy + 260], radius=8, fill="#FFFFFF", outline=BORDER, width=2)
    d.rectangle([ox, oy, ox + 170, oy + 36], fill=NAVY)
    for i in range(5):
        d.rectangle([ox + 16, oy + 52 + i * 38, ox + 154, oy + 78 + i * 38], fill="#ECEFF1", outline=BORDER)

    bx = ox + 190
    d.rounded_rectangle([bx, oy, bx + 170, oy + 260], radius=8, fill="#FFFFFF", outline="#A5C4E8", width=2)
    d.rectangle([bx, oy, bx + 170, oy + 36], fill="#1565C0")
    for i in range(5):
        w = 120 if i % 2 == 0 else 90
        d.rectangle([bx + 16, oy + 52 + i * 38, bx + 16 + w, oy + 78 + i * 38], fill=NAVY_PALE, outline="#B0C4DE")


def draw_motif_photo(d: ImageDraw.ImageDraw) -> None:
    ox, oy = 510, 195
    d.rounded_rectangle([ox, oy, ox + 390, oy + 295], radius=8, fill="#0F2347", outline="#37474F", width=2)
    boxes = [(30, 30, 150, 110), (200, 25, 340, 130), (40, 150, 170, 260), (210, 155, 360, 265)]
    for x1, y1, x2, y2 in boxes:
        d.rectangle([ox + x1, oy + y1, ox + x2, oy + y2], outline="#28A745", width=3)
        d.rectangle([ox + x1 + 4, oy + y1 + 4, ox + x2 - 4, oy + y2 - 4], fill="#1A3050")


def draw_motif_task(d: ImageDraw.ImageDraw) -> None:
    ox, oy = 500, 205
    d.rounded_rectangle([ox, oy, ox + 380, oy + 285], radius=8, fill="#FFFFFF", outline=BORDER, width=2)
    d.rectangle([ox, oy, ox + 380, oy + 44], fill="#1565C0")
    cards = [
        ("#C62828", "#FFF8F8"),
        ("#E65100", "#FFFAF5"),
        ("#2E7D32", "#F5FFF5"),
    ]
    for i, (bar, bg) in enumerate(cards):
        cy = oy + 58 + i * 72
        d.rounded_rectangle([ox + 16, cy, ox + 364, cy + 58], radius=4, fill=bg, outline=BORDER)
        d.rectangle([ox + 16, cy, ox + 22, cy + 58], fill=bar)
        d.rectangle([ox + 36, cy + 12, ox + 200, cy + 26], fill="#1565C0")
        d.rounded_rectangle([ox + 290, cy + 10, ox + 348, cy + 28], radius=8, fill="#1565C0" if i < 2 else "#546E7A")


def draw_motif_consulting(d: ImageDraw.ImageDraw) -> None:
    ox, oy = 510, 200
    d.rounded_rectangle([ox, oy, ox + 370, oy + 290], radius=8, fill="#FFFFFF", outline=BORDER, width=2)
    d.rectangle([ox, oy, ox + 370, oy + 48], fill=NAVY)
    fields = [220, 180, 240, 100]
    y = oy + 68
    for w in fields:
        d.rectangle([ox + 24, y, ox + 24 + w, y + 28], fill="#F3F4F6", outline=BORDER)
        y += 46
    d.rounded_rectangle([ox + 24, y + 8, ox + 160, y + 44], radius=4, fill=NAVY)


MOTIF_DRAWERS = {
    "imposition": draw_motif_imposition,
    "word": draw_motif_word,
    "photo": draw_motif_photo,
    "task": draw_motif_task,
    "consulting": draw_motif_consulting,
}


def render_cover(spec: dict, fonts) -> Image.Image:
    img = Image.new("RGBA", (W, H), "#FAFBFC")
    d = ImageDraw.Draw(img, "RGBA")
    draw_background(d)
    draw_pill(d, 48, 48, spec["category"], fonts["pill"])
    draw_title(d, spec["title"], fonts)
    MOTIF_DRAWERS[spec["motif"]](d)
    return img.convert("RGB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    for spec in COVERS:
        img = render_cover(spec, fonts)
        out = OUT_DIR / spec["file"]
        img.save(out, "JPEG", quality=90)
        print(f"saved {out}")


if __name__ == "__main__":
    main()
