"""Generate Works gallery covers in the color-correct promo style (960x540).

Dark navy product-promo look: soft spotlight, centered JP title with amber
accent, floating UI mockups — matching color_correct/note_thumbnail.png.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "covers"
W, H = 960, 540

NAVY = (12, 28, 58)
NAVY_MID = (22, 42, 82)
NAVY_LIGHT = (40, 70, 120)
CYAN = (90, 170, 255)
AMBER = (232, 170, 60)
WHITE = (255, 255, 255)
MUTED = (160, 180, 210)


def load_fonts():
    meiryo = "C:/Windows/Fonts/meiryo.ttc"
    meiryo_b = "C:/Windows/Fonts/meiryob.ttc"
    bold = meiryo_b if Path(meiryo_b).exists() else meiryo
    try:
        return {
            "title": ImageFont.truetype(bold, 48),
            "title_sm": ImageFont.truetype(bold, 36),
            "sub": ImageFont.truetype(meiryo, 18),
            "ui": ImageFont.truetype(meiryo, 13),
            "tiny": ImageFont.truetype(meiryo, 11),
            "label": ImageFont.truetype(meiryo, 12),
        }
    except OSError:
        d = ImageFont.load_default()
        return {k: d for k in ("title", "title_sm", "sub", "ui", "tiny", "label")}


def make_bg() -> Image.Image:
    """Dark navy with soft diagonal spotlight (like note_thumbnail)."""
    img = Image.new("RGB", (W, H), NAVY)
    # radial-ish spotlight via blurred ellipse
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-120, -180, 620, 420], fill=(40, 80, 150, 70))
    gd.ellipse([480, 200, 1100, 700], fill=(30, 60, 110, 50))
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    base = img.convert("RGBA")
    base = Image.alpha_composite(base, glow)
    return base.convert("RGB")


def panel(d: ImageDraw.ImageDraw, box, radius=12, fill=(18, 36, 68), outline=(60, 100, 160), width=2):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_centered_title(d, fonts, line1: str, line2: str | None, accent_word: str | None = None, y=210):
    """Big centered title; optional amber accent on accent_word inside line1."""
    font = fonts["title"] if len(line1) <= 12 else fonts["title_sm"]

    def text_w(s, f):
        b = d.textbbox((0, 0), s, font=f)
        return b[2] - b[0]

    if accent_word and accent_word in line1:
        before, _, after = line1.partition(accent_word)
        total = text_w(before, font) + text_w(accent_word, font) + text_w(after, font)
        x = (W - total) // 2
        # shadow
        d.text((x + 2, y + 2), line1, fill=(0, 0, 0), font=font)
        d.text((x, y), before, fill=WHITE, font=font)
        x += text_w(before, font)
        d.text((x, y), accent_word, fill=AMBER, font=font)
        x += text_w(accent_word, font)
        d.text((x, y), after, fill=WHITE, font=font)
        title_bottom = y + 58
    else:
        tw = text_w(line1, font)
        x = (W - tw) // 2
        d.text((x + 2, y + 2), line1, fill=(0, 0, 0), font=font)
        d.text((x, y), line1, fill=WHITE, font=font)
        title_bottom = y + 58

    # amber underline
    uw = min(220, text_w(line1, font) // 2)
    d.rectangle([(W - uw) // 2, title_bottom - 4, (W + uw) // 2, title_bottom - 1], fill=AMBER)

    if line2:
        sw = text_w(line2, fonts["sub"])
        d.text(((W - sw) // 2, title_bottom + 10), line2, fill=MUTED, font=fonts["sub"])


def cover_color_correct(fonts) -> Image.Image:
    src = ROOT / "color_correct" / "note_thumbnail.png"
    if src.exists():
        return ImageOps.fit(Image.open(src).convert("RGB"), (W, H), Image.Resampling.LANCZOS)
    # fallback minimal
    img = make_bg()
    d = ImageDraw.Draw(img)
    draw_centered_title(d, fonts, "カラー補正ツール", "Photoshop連携 / 有料配布", "ツール")
    return img


def cover_imposition(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    # Left: settings card
    panel(d, [40, 80, 280, 460], fill=(16, 32, 62), outline=(70, 120, 190))
    d.text((58, 98), "原反 / 仕上がり", fill=CYAN, font=fonts["label"])
    fields = ["面付モード: 単品", "原反 600×2500", "A4 297×210", "数量 30 / ドブ 3mm"]
    y = 140
    for f in fields:
        d.rounded_rectangle([58, y, 262, y + 36], radius=6, fill=(28, 50, 90), outline=(55, 90, 140))
        d.text((70, y + 9), f, fill=MUTED, font=fonts["tiny"])
        y += 48
    d.rounded_rectangle([58, 400, 262, 436], radius=6, fill=(40, 100, 200))
    d.text((88, 410), "▶ 面付計算", fill=WHITE, font=fonts["ui"])

    # Right: sheet preview
    panel(d, [680, 70, 920, 470], fill=(20, 38, 72), outline=(80, 130, 200))
    d.text((700, 86), "面付プレビュー", fill=CYAN, font=fonts["label"])
    d.rectangle([710, 120, 890, 440], fill=(35, 55, 95), outline=(100, 140, 190))
    # mini sheet parts
    for r in range(4):
        for c in range(2):
            x1 = 725 + c * 80
            y1 = 140 + r * 70
            d.rounded_rectangle([x1, y1, x1 + 68, y1 + 58], radius=3, fill=(70, 130, 210), outline=(140, 180, 230))
            d.text((x1 + 14, y1 + 20), "A4", fill=WHITE, font=fonts["tiny"])

    draw_centered_title(d, fonts, "面付シミュレーター", "JFX200 / 収率・トンボ可視化", "シミュレーター", y=200)
    return img


def cover_photo_cut(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    # Sample thumb on left
    sample = ROOT / "assets" / "demo" / "sample-scan.jpg"
    if not sample.exists():
        sample = ROOT / "photoshop_sab" / "cut_sample.jpg"
    if sample.exists():
        thumb = ImageOps.fit(Image.open(sample).convert("RGB"), (220, 280), Image.Resampling.LANCZOS)
        # dark frame
        d.rounded_rectangle([36, 100, 276, 420], radius=10, fill=(18, 34, 64), outline=(70, 120, 190), width=2)
        img.paste(thumb, (46, 120))
        # green/red frame overlays on thumb
        od = ImageDraw.Draw(img)
        od.rectangle([56, 140, 150, 210], outline=(220, 70, 70), width=2)
        od.rectangle([60, 144, 146, 206], outline=(50, 200, 90), width=2)
        od.ellipse([64, 148, 82, 166], fill=(50, 200, 90))
        od.text((68, 150), "1", fill=WHITE, font=fonts["tiny"])
    else:
        panel(d, [40, 100, 280, 420])

    # Right: detection list
    panel(d, [680, 100, 920, 420], fill=(16, 32, 62), outline=(70, 120, 190))
    d.text((700, 118), "検出結果", fill=CYAN, font=fonts["label"])
    for i in range(1, 7):
        y = 150 + (i - 1) * 40
        d.ellipse([710, y + 4, 730, y + 24], fill=(50, 180, 90))
        d.text((714, y + 6), str(i), fill=WHITE, font=fonts["tiny"])
        d.text((742, y + 6), f"写真_{i:04d}.jpg", fill=MUTED, font=fonts["ui"])

    draw_centered_title(d, fonts, "写真切り出しツール", "黒台紙スキャン → 自動検出・切出し", "ツール", y=200)
    return img


def cover_word(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    # Left: tagged.txt
    panel(d, [40, 90, 300, 430], fill=(14, 28, 54), outline=(70, 120, 190))
    d.rectangle([40, 90, 300, 122], fill=(30, 55, 100))
    d.text((56, 98), "tagged.txt", fill=AMBER, font=fonts["ui"])
    lines = [
        "<h1>特集タイトル</h1>",
        "<biu>見出し</biu>",
        "<ruby>漢字|かんじ</ruby>",
        "<table>A|B</table>",
        "本文テキスト…",
    ]
    y = 145
    for line in lines:
        d.text((56, y), line, fill=MUTED, font=fonts["tiny"])
        y += 36

    # Arrow
    d.polygon([(340, 250), (390, 230), (390, 242), (430, 242), (430, 258), (390, 258), (390, 270)], fill=AMBER)

    # Right: InDesign page
    panel(d, [660, 90, 920, 430], fill=(245, 246, 250), outline=(160, 100, 200), width=2)
    d.rectangle([660, 90, 920, 122], fill=(140, 50, 180))
    d.text((678, 98), "InDesign ページ", fill=WHITE, font=fonts["ui"])
    for i, wlen in enumerate([200, 170, 220, 140, 190, 160]):
        d.rectangle([680, 150 + i * 38, 680 + wlen, 168 + i * 38], fill=(220, 225, 235))
    d.rounded_rectangle([680, 380, 820, 408], radius=4, fill=(27, 50, 100))
    d.text((700, 386), "スタイル適用済", fill=WHITE, font=fonts["tiny"])

    draw_centered_title(d, fonts, "組版パイプライン", "Word → タグTXT → InDesign", "パイプライン", y=200)
    # smaller top label via subtitle only — add Word→InDesign above
    tw = d.textbbox((0, 0), "Word → InDesign", font=fonts["sub"])
    d.text(((W - (tw[2] - tw[0])) // 2, 168), "Word → InDesign", fill=CYAN, font=fonts["sub"])
    return img


def cover_pman(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    # Phone-like panel center-right
    panel(d, [620, 50, 920, 490], fill=(248, 249, 252), outline=(100, 140, 200), width=2)
    d.rectangle([620, 50, 920, 100], fill=(21, 101, 192))
    d.text((640, 66), "管理者パネル", fill=WHITE, font=fonts["ui"])
    d.rounded_rectangle([800, 62, 900, 88], radius=10, fill=(46, 125, 50))
    d.text((812, 66), "オペレーター", fill=WHITE, font=fonts["tiny"])

    tasks = [
        ((198, 40, 40), "至急", "印刷課｜表紙", "P:750"),
        ((230, 81, 0), "飛び込み", "制作課｜レイアウト", "P:620"),
        ((46, 125, 50), "通常", "製本課｜無線綴じ", "P:450"),
        ((84, 110, 122), "通常", "印刷課｜色校正", "P:310"),
    ]
    y = 118
    for bar, tag, title, pts in tasks:
        d.rounded_rectangle([638, y, 902, y + 78], radius=8, fill=(255, 255, 255), outline=(220, 225, 230))
        d.rectangle([638, y, 646, y + 78], fill=bar)
        d.rounded_rectangle([656, y + 10, 656 + 12 * len(tag) + 16, y + 30], radius=8, fill=bar)
        d.text((664, y + 12), tag, fill=WHITE, font=fonts["tiny"])
        d.text((656, y + 38), title, fill=(30, 50, 90), font=fonts["ui"])
        d.ellipse([840, y + 18, 890, y + 68], fill=bar if tag == "至急" else (21, 101, 192))
        bw = d.textbbox((0, 0), pts, font=fonts["tiny"])
        d.text((865 - (bw[2] - bw[0]) // 2, y + 34), pts, fill=WHITE, font=fonts["tiny"])
        y += 90

    # Left accent icon panel
    panel(d, [40, 140, 260, 400], fill=(16, 32, 62), outline=(70, 120, 190))
    d.text((70, 170), "MIS", fill=CYAN, font=fonts["title_sm"])
    d.text((70, 230), "部署別タスク", fill=WHITE, font=fonts["ui"])
    d.text((70, 260), "リアルタイム進捗", fill=MUTED, font=fonts["tiny"])
    d.rounded_rectangle([70, 320, 230, 360], radius=6, fill=AMBER)
    d.text((88, 332), "至急 / 飛び込み対応", fill=NAVY, font=fonts["tiny"])

    draw_centered_title(d, fonts, "タスク管理", "MIS 部署別 / 管理者・オペレーター", None, y=40)
    return img


def cover_mis_dx(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    nodes = [
        (60, 160, 260, 300, "MIS", "生産管理", (40, 120, 220)),
        (350, 140, 610, 320, "GAS + Sheets", "リアルタイム連携", (50, 160, 100)),
        (700, 160, 900, 300, "現場パネル", "タスク可視化", AMBER),
    ]
    d.line([(260, 230), (350, 230)], fill=CYAN, width=3)
    d.line([(610, 230), (700, 230)], fill=CYAN, width=3)
    for x1, y1, x2, y2, t1, t2, color in nodes:
        panel(d, [x1, y1, x2, y2], fill=(16, 32, 62), outline=color, width=3)
        d.rectangle([x1, y1, x2, y1 + 8], fill=color)
        tw = d.textbbox((0, 0), t1, font=fonts["ui"])
        d.text(((x1 + x2 - (tw[2] - tw[0])) // 2, y1 + 50), t1, fill=WHITE, font=fonts["ui"])
        tw2 = d.textbbox((0, 0), t2, font=fonts["tiny"])
        d.text(((x1 + x2 - (tw2[2] - tw2[0])) // 2, y1 + 85), t2, fill=MUTED, font=fonts["tiny"])

    draw_centered_title(d, fonts, "連結 DX 提案", "MIS × Google Workspace / Smart Factory", "DX", y=360)
    return img


def cover_consulting(fonts) -> Image.Image:
    img = make_bg()
    d = ImageDraw.Draw(img)

    steps = [
        ("01", "Discovery", "現場課題の可視化"),
        ("02", "Design", "安全・可逆な設計"),
        ("03", "Build", "Python / GAS"),
        ("04", "Operate", "定着と改善"),
    ]
    x = 50
    for i, (num, en, ja) in enumerate(steps):
        panel(d, [x, 120, x + 190, 340], fill=(16, 32, 62), outline=(70, 120, 190))
        d.text((x + 24, 145), num, fill=AMBER, font=fonts["title_sm"])
        d.text((x + 24, 220), en, fill=WHITE, font=fonts["ui"])
        d.text((x + 24, 260), ja, fill=MUTED, font=fonts["tiny"])
        if i < 3:
            d.polygon([(x + 198, 220), (x + 218, 210), (x + 218, 230)], fill=AMBER)
        x += 230

    draw_centered_title(d, fonts, "DX化ヒアリング", "ロードマップ策定 / 無料相談", "ヒアリング", y=380)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    jobs = [
        ("color-correct-demo.jpg", cover_color_correct),
        ("imposition-demo.jpg", cover_imposition),
        ("photo-cut-demo.jpg", cover_photo_cut),
        ("word-tag-extractor.jpg", cover_word),
        ("pman-task-demo.jpg", cover_pman),
        ("MISGoogle WorkspaceDX.jpg", cover_mis_dx),
        ("dx-consulting.jpg", cover_consulting),
    ]
    for name, fn in jobs:
        img = fn(fonts)
        out = OUT_DIR / name
        img.save(out, "JPEG", quality=92, optimize=True)
        print(f"saved {out.name} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
