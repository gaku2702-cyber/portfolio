"""Generate content-matched Works gallery covers (960x540 JPEG).

Uses real demo samples / promo art where available, and richer
product-specific illustrations for the rest.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "covers"
W, H = 960, 540

NAVY = (27, 50, 100)
NAVY_DEEP = (15, 35, 71)
AMBER = (200, 134, 58)
WHITE = (255, 255, 255)
MUTED = (107, 114, 128)
LIGHT = (248, 250, 252)
BORDER = (226, 228, 233)


def load_fonts():
    meiryo = "C:/Windows/Fonts/meiryo.ttc"
    meiryo_b = "C:/Windows/Fonts/meiryob.ttc"
    try:
        return {
            "pill": ImageFont.truetype(meiryo, 13),
            "title": ImageFont.truetype(meiryo_b if Path(meiryo_b).exists() else meiryo, 34),
            "title_sm": ImageFont.truetype(meiryo, 22),
            "body": ImageFont.truetype(meiryo, 15),
            "tiny": ImageFont.truetype(meiryo, 12),
            "mono": ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13),
        }
    except OSError:
        d = ImageFont.load_default()
        return {k: d for k in ("pill", "title", "title_sm", "body", "tiny", "mono")}


def fit_cover(img: Image.Image) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (W, H), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))


def darken(img: Image.Image, alpha: float = 0.35) -> Image.Image:
    overlay = Image.new("RGB", img.size, NAVY_DEEP)
    return Image.blend(img.convert("RGB"), overlay, alpha)


def draw_pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill=(232, 237, 245), color=NAVY):
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 12, 5
    d.rounded_rectangle([x, y, x + tw + pad_x * 2, y + th + pad_y * 2], radius=12, fill=fill)
    d.text((x + pad_x, y + pad_y - 1), text, fill=color, font=font)


def draw_title_block(d: ImageDraw.ImageDraw, lines: list[str], fonts, x=40, y=70, color=WHITE):
    for i, line in enumerate(lines):
        font = fonts["title"] if i == 0 else fonts["title_sm"]
        # soft shadow
        d.text((x + 1, y + 1), line, fill=(0, 0, 0, 120), font=font)
        d.text((x, y), line, fill=color, font=font)
        bbox = d.textbbox((x, y), line, font=font)
        y = bbox[3] + 6
    return y


def frosted_panel(base: Image.Image, box, radius=16, opacity=210):
    """Semi-transparent navy panel."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(box, radius=radius, fill=(*NAVY_DEEP, opacity))
    out = base.convert("RGBA")
    out = Image.alpha_composite(out, overlay)
    return out.convert("RGB")


SRC_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "cursor" / "screenshots"


def from_screenshot(candidates: list[str], crop_right_ratio: float = 0.0) -> Image.Image | None:
    """Load latest matching screenshot and fit to cover size."""
    for name in candidates:
        path = SRC_DIR / name
        if not path.exists():
            continue
        img = Image.open(path).convert("RGB")
        if crop_right_ratio > 0:
            w, h = img.size
            left = int(w * crop_right_ratio)
            img = img.crop((left, 0, w, h))
        return fit_cover(img)
    return None


# ── Photo cut: real sample scan + detection frames ───────────────
def cover_photo_cut(fonts) -> Image.Image:
    shot = from_screenshot(["cover-src-photo-cut.png"], crop_right_ratio=0.28)
    if shot:
        shot = darken(shot, 0.18)
        shot = frosted_panel(shot, [28, 28, 430, 160], opacity=200)
        d = ImageDraw.Draw(shot)
        draw_pill(d, 48, 44, "Image Processing", fonts["pill"], fill=(255, 255, 255), color=NAVY)
        draw_title_block(d, ["写真切り出しツール", "黒台紙スキャン → 自動検出"], fonts, x=48, y=78)
        return shot

    src = ROOT / "assets" / "demo" / "sample-scan.jpg"
    if not src.exists():
        src = ROOT / "photoshop_sab" / "cut_sample.jpg"
    base = fit_cover(Image.open(src))
    base = darken(base, 0.22)

    # Detection overlays (approximate 2x4 grid like the product)
    d = ImageDraw.Draw(base)
    frames = [
        (70, 55, 430, 160),
        (500, 50, 880, 165),
        (80, 180, 440, 290),
        (510, 185, 890, 300),
        (75, 310, 435, 420),
        (505, 315, 885, 430),
        (90, 440, 420, 520),
        (520, 445, 860, 525),
    ]
    for i, (x1, y1, x2, y2) in enumerate(frames, 1):
        # red detect
        d.rectangle([x1 - 4, y1 - 4, x2 + 4, y2 + 4], outline=(220, 60, 60), width=2)
        # green cut
        d.rectangle([x1, y1, x2, y2], outline=(40, 180, 80), width=3)
        d.ellipse([x1 + 6, y1 + 6, x1 + 28, y1 + 28], fill=(40, 180, 80))
        d.text((x1 + 11, y1 + 7), str(i), fill=WHITE, font=fonts["tiny"])

    base = frosted_panel(base, [28, 28, 430, 160], opacity=200)
    d = ImageDraw.Draw(base)
    draw_pill(d, 48, 44, "Image Processing", fonts["pill"], fill=(255, 255, 255), color=NAVY)
    draw_title_block(d, ["写真切り出しツール", "黒台紙スキャン → 自動検出"], fonts, x=48, y=78)
    return base


# ── Color correct: note thumbnail promo art ──────────────────────
def cover_color_correct(fonts) -> Image.Image:
    src = ROOT / "color_correct" / "note_thumbnail.png"
    if src.exists():
        return fit_cover(Image.open(src))

    # Fallback: before/after with sample photo
    photo = ROOT / "photoshop_sab" / "sample" / "photo_0001.jpg"
    img = Image.new("RGB", (W, H), NAVY_DEEP)
    if photo.exists():
        p = ImageOps.fit(Image.open(photo), (420, 420), Image.Resampling.LANCZOS)
        warm = ImageOps.colorize(ImageOps.grayscale(p), black="#1a1020", white="#ffe8c8")
        cool = p
        img.paste(warm, (40, 60))
        img.paste(cool, (500, 60))
    d = ImageDraw.Draw(img)
    draw_pill(d, 40, 24, "Color Correction", fonts["pill"])
    draw_title_block(d, ["カラー補正ツール", "Photoshop 連携"], fonts, x=40, y=470, color=WHITE)
    return img


# ── Imposition: sheet preview matching JFX200 demo ───────────────
def cover_imposition(fonts) -> Image.Image:
    shot = from_screenshot(["cover-src-imposition.png"], crop_right_ratio=0.32)
    if shot:
        shot = darken(shot, 0.12)
        shot = frosted_panel(shot, [28, 28, 420, 160], opacity=210)
        d = ImageDraw.Draw(shot)
        draw_pill(d, 48, 44, "DTP Automation", fonts["pill"], fill=WHITE, color=NAVY)
        draw_title_block(d, ["JFX200", "面付シミュレーター"], fonts, x=48, y=78)
        return shot

    img = Image.new("RGB", (W, H), NAVY_DEEP)
    d = ImageDraw.Draw(img)

    # left accent
    d.rectangle([0, 0, 8, H], fill=AMBER)

    # machine label
    draw_pill(d, 36, 28, "DTP Automation", fonts["pill"], fill=(40, 60, 110), color=(220, 230, 245))
    draw_title_block(d, ["JFX200", "面付シミュレーター"], fonts, x=36, y=70)

    # Sheet preview panel
    sx, sy, sw, sh = 380, 70, 540, 420
    d.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=10, fill=(30, 48, 78), outline=(80, 100, 140), width=2)
    d.text((sx + 16, sy + 12), "面付プレビュー — 原反 600×2500mm", fill=(180, 195, 220), font=fonts["tiny"])

    # white sheet
    sheet = [sx + 40, sy + 48, sx + sw - 40, sy + sh - 36]
    d.rectangle(sheet, fill=WHITE, outline=(200, 205, 215), width=2)

    # A4-ish parts grid (2 cols x 5 rows look)
    margin = 18
    gap = 10
    cols, rows = 2, 5
    inner_w = sheet[2] - sheet[0] - margin * 2
    inner_h = sheet[3] - sheet[1] - margin * 2
    pw = (inner_w - gap * (cols - 1)) // cols
    ph = (inner_h - gap * (rows - 1)) // rows
    colors = [(70, 130, 200), (90, 150, 210), (60, 120, 190), (100, 160, 220)]
    for r in range(rows):
        for c in range(cols):
            x1 = sheet[0] + margin + c * (pw + gap)
            y1 = sheet[1] + margin + r * (ph + gap)
            d.rounded_rectangle([x1, y1, x1 + pw, y1 + ph], radius=3, fill=colors[(r + c) % 4], outline=NAVY)
            d.text((x1 + 8, y1 + 6), f"A4-{r * cols + c + 1}", fill=WHITE, font=fonts["tiny"])

    # result chip
    d.rounded_rectangle([36, 420, 330, 490], radius=8, fill=(40, 60, 110))
    d.text((52, 435), "単品面付  /  トンボ付き", fill=(220, 230, 245), font=fonts["body"])
    d.text((52, 460), "収率・ドブ・原反を可視化", fill=AMBER, font=fonts["tiny"])
    return img


# ── PMAN task: manager panel look ────────────────────────────────
def cover_pman(fonts) -> Image.Image:
    img = Image.new("RGB", (W, H), (245, 247, 250))
    d = ImageDraw.Draw(img)

    draw_pill(d, 36, 28, "Production Workflow", fonts["pill"])
    d.text((36, 70), "MIS 部署別", fill=NAVY, font=fonts["title"])
    d.text((36, 112), "タスク管理", fill=NAVY, font=fonts["title_sm"])

    # Phone / panel mock matching demo colors
    px, py = 420, 40
    d.rounded_rectangle([px, py, px + 500, py + 470], radius=18, fill=WHITE, outline=BORDER, width=2)
    d.rectangle([px, py, px + 500, py + 56], fill=(21, 101, 192))
    d.text((px + 20, py + 16), "管理者パネル", fill=WHITE, font=fonts["body"])
    d.rounded_rectangle([px + 360, py + 14, px + 470, py + 40], radius=10, fill=(46, 125, 50))
    d.text((px + 378, py + 18), "オペレーター", fill=WHITE, font=fonts["tiny"])

    tasks = [
        ("B2024-0055", "至急", (198, 40, 40), (255, 245, 245), "印刷課｜表紙 1C+1C", "750", "割当済"),
        ("B2024-0061", "飛び込み", (230, 81, 0), (255, 248, 240), "制作課｜レイアウト調整", "620", "未着手"),
        ("B2024-0048", "通常", (46, 125, 50), (245, 255, 245), "製本課｜無線綴じ", "450", "作業中"),
        ("B2024-0070", "通常", (84, 110, 122), (248, 250, 252), "印刷課｜色校正再出力", "310", "完了"),
    ]
    y = py + 72
    for tid, tag, bar, bg, title, score, status in tasks:
        d.rounded_rectangle([px + 16, y, px + 484, y + 78], radius=8, fill=bg, outline=BORDER)
        d.rectangle([px + 16, y, px + 22, y + 78], fill=bar)
        d.text((px + 36, y + 10), tid, fill=MUTED, font=fonts["tiny"])
        tag_w = 12 * len(tag) + 20
        d.rounded_rectangle([px + 130, y + 8, px + 130 + tag_w, y + 28], radius=8, fill=bar)
        d.text((px + 138, y + 10), tag, fill=WHITE, font=fonts["tiny"])
        d.text((px + 36, y + 34), title, fill=NAVY, font=fonts["body"])
        d.ellipse([px + 400, y + 18, px + 460, y + 58], fill=(21, 101, 192) if tag != "至急" else (198, 40, 40))
        sw = d.textbbox((0, 0), f"P:{score}", font=fonts["tiny"])
        d.text((px + 430 - (sw[2] - sw[0]) // 2, y + 30), f"P:{score}", fill=WHITE, font=fonts["tiny"])
        d.text((px + 36, y + 56), status, fill=MUTED, font=fonts["tiny"])
        y += 90

    return img


# ── Word → InDesign pipeline ─────────────────────────────────────
def cover_word(fonts) -> Image.Image:
    desk = ROOT / "assets" / "hero" / "desk.png"
    if desk.exists():
        base = darken(fit_cover(Image.open(desk)), 0.45)
    else:
        base = Image.new("RGB", (W, H), LIGHT)

    base = frosted_panel(base, [28, 28, 520, 200], opacity=215)
    d = ImageDraw.Draw(base)
    draw_pill(d, 48, 44, "Data Conversion", fonts["pill"], fill=WHITE, color=NAVY)
    draw_title_block(d, ["Word → InDesign", "組版パイプライン"], fonts, x=48, y=82)

    # Tagged text card
    d.rounded_rectangle([48, 240, 470, 500], radius=10, fill=(18, 28, 48), outline=(70, 90, 130))
    d.text((64, 256), "tagged.txt", fill=AMBER, font=fonts["tiny"])
    lines = [
        "<h1>特集タイトル</h1>",
        "<biu>見出し</biu>",
        "本文…<ruby>漢字|かんじ</ruby>",
        "<table>セルA|セルB</table>",
        "→ InDesign Place + タグ処理",
    ]
    y = 290
    for line in lines:
        d.text((64, y), line, fill=(200, 215, 235), font=fonts["body"])
        y += 28

    # Arrow + InDesign card
    d.polygon([(500, 360), (540, 340), (540, 350), (580, 350), (580, 370), (540, 370), (540, 380)], fill=AMBER)
    d.rounded_rectangle([600, 240, 920, 500], radius=10, fill=WHITE, outline=BORDER)
    d.rectangle([600, 240, 920, 280], fill=(156, 39, 176))
    d.text((620, 252), "InDesign ページ", fill=WHITE, font=fonts["body"])
    for i, w in enumerate([260, 220, 280, 180, 240]):
        d.rectangle([620, 300 + i * 32, 620 + w, 318 + i * 32], fill=(232, 237, 245))
    d.rounded_rectangle([620, 460, 760, 486], radius=4, fill=NAVY)
    d.text((640, 464), "スタイル適用済", fill=WHITE, font=fonts["tiny"])
    return base


# ── MIS × Google Workspace DX ────────────────────────────────────
def cover_mis_dx(fonts) -> Image.Image:
    img = Image.new("RGB", (W, H), (250, 251, 253))
    d = ImageDraw.Draw(img)

    # subtle grid
    for x in range(0, W, 40):
        d.line([(x, 0), (x, H)], fill=(238, 241, 246))
    for y in range(0, H, 40):
        d.line([(0, y), (W, y)], fill=(238, 241, 246))

    draw_pill(d, 40, 28, "DX Proposal", fonts["pill"])
    d.text((40, 72), "MIS × Google Workspace", fill=NAVY, font=fonts["title"])
    d.text((40, 118), "連結 DX 提案", fill=NAVY, font=fonts["title_sm"])

    # Architecture nodes
    nodes = [
        (80, 220, 260, 320, "MIS / 生産管理", (21, 101, 192)),
        (360, 200, 600, 340, "GAS + Sheets\nリアルタイム連携", (46, 125, 50)),
        (700, 220, 900, 320, "現場パネル\nタスク可視化", AMBER),
    ]
    # connectors
    d.line([(260, 270), (360, 270)], fill=NAVY, width=3)
    d.line([(600, 270), (700, 270)], fill=NAVY, width=3)
    for x1, y1, x2, y2, label, color in nodes:
        d.rounded_rectangle([x1, y1, x2, y2], radius=12, fill=WHITE, outline=color, width=3)
        d.rectangle([x1, y1, x2, y1 + 10], fill=color)
        lines = label.split("\n")
        ty = y1 + 40
        for line in lines:
            bbox = d.textbbox((0, 0), line, font=fonts["body"])
            tw = bbox[2] - bbox[0]
            d.text(((x1 + x2 - tw) // 2, ty), line, fill=NAVY, font=fonts["body"])
            ty += 28

    d.rounded_rectangle([40, 400, 520, 500], radius=10, fill=NAVY)
    d.text((60, 425), "Smart Factory ロードマップ", fill=WHITE, font=fonts["body"])
    d.text((60, 458), "入稿〜印刷工程を Workspace でつなぐ提案書", fill=(200, 210, 230), font=fonts["tiny"])
    return img


# ── DX consulting roadmap ────────────────────────────────────────
def cover_consulting(fonts) -> Image.Image:
    desk = ROOT / "assets" / "hero" / "desk.png"
    if desk.exists():
        base = darken(fit_cover(Image.open(desk)), 0.5)
    else:
        base = Image.new("RGB", (W, H), NAVY_DEEP)

    base = frosted_panel(base, [28, 28, 520, 170], opacity=210)
    d = ImageDraw.Draw(base)
    draw_pill(d, 48, 44, "DX Support", fonts["pill"], fill=WHITE, color=NAVY)
    draw_title_block(d, ["DX化ヒアリング", "ロードマップ策定"], fonts, x=48, y=82)

    steps = [
        ("01", "Discovery", "現場課題の可視化"),
        ("02", "Design", "安全・可逆な設計"),
        ("03", "Build", "Python / GAS 実装"),
        ("04", "Operate", "定着と改善"),
    ]
    x = 48
    for num, en, ja in steps:
        d.rounded_rectangle([x, 280, x + 200, 480], radius=12, fill=(22, 40, 72), outline=(80, 100, 140))
        d.text((x + 20, 300), num, fill=AMBER, font=fonts["title"])
        d.text((x + 20, 360), en, fill=WHITE, font=fonts["body"])
        d.text((x + 20, 400), ja, fill=(180, 195, 220), font=fonts["tiny"])
        if x < 700:
            d.polygon([(x + 208, 370), (x + 228, 360), (x + 228, 380)], fill=AMBER)
        x += 230
    return base


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    jobs = [
        ("photo-cut-demo.jpg", cover_photo_cut),
        ("color-correct-demo.jpg", cover_color_correct),
        ("imposition-demo.jpg", cover_imposition),
        ("pman-task-demo.jpg", cover_pman),
        ("word-tag-extractor.jpg", cover_word),
        ("MISGoogle WorkspaceDX.jpg", cover_mis_dx),
        ("dx-consulting.jpg", cover_consulting),
    ]
    for name, fn in jobs:
        img = fn(fonts)
        out = OUT_DIR / name
        img.save(out, "JPEG", quality=92, optimize=True)
        print(f"saved {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
