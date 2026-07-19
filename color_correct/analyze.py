"""画像からハイライト / シャドー / ニュートラルグレーの RGB を算出する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

CLIP_PERCENT = 0.1  # シャドー側（後方互換・単独指定時）
CLIP_SHADOW_PERCENT = 0.1
CLIP_HIGHLIGHT_PERCENT = 0.25  # ハイライト計測（白飛びしない程度）
LAB_L_RANGE = (35.0, 65.0)
AB_THRESHOLDS = (5.0, 8.0, 12.0, 18.0, 25.0)
NEAR_BAND = 2  # クリップ閾値近傍の輝度幅（フォールバック用）
MIN_NEUTRAL_PIXELS = 50
MIN_REGION_AREA_RATIO = 0.0002  # 画像面積に対する最小領域比
MORPH_KERNEL = 3


def load_image_bgr(path: str | Path) -> np.ndarray:
    """日本語パス対応で画像を BGR で読み込む。"""
    path = Path(path)
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"画像を読み込めませんでした: {path}")
    return image


def _luminance_rec709(bgr: np.ndarray) -> np.ndarray:
    """Rec.709 近似の輝度 (0–255 float)。"""
    b = bgr[:, :, 0].astype(np.float64)
    g = bgr[:, :, 1].astype(np.float64)
    r = bgr[:, :, 2].astype(np.float64)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _percentile_thresholds(
    luma: np.ndarray,
    clip_percent: float | None = None,
    *,
    shadow_percent: float = CLIP_SHADOW_PERCENT,
    highlight_percent: float = CLIP_HIGHLIGHT_PERCENT,
) -> tuple[float, float]:
    """上下クリップ閾値。ハイライト側は強めのパーセントを使う。"""
    flat = luma.ravel()
    if clip_percent is not None:
        shadow_percent = clip_percent
        highlight_percent = clip_percent
    low = float(np.percentile(flat, shadow_percent))
    high = float(np.percentile(flat, 100.0 - highlight_percent))
    if high <= low:
        high = min(255.0, low + 1.0)
    return low, high


def _mean_rgb_from_mask(bgr: np.ndarray, mask: np.ndarray) -> dict[str, int]:
    pixels = bgr[mask]
    if pixels.size == 0:
        raise ValueError("測色マスクが空です。")
    mean_bgr = pixels.mean(axis=0)
    return {
        "r": int(round(mean_bgr[2])),
        "g": int(round(mean_bgr[1])),
        "b": int(round(mean_bgr[0])),
    }


def _mean_rgb_near_luma(
    bgr: np.ndarray, luma: np.ndarray, target: float, band: float
) -> dict[str, int]:
    mask = (luma >= target - band) & (luma <= target + band)
    if not np.any(mask):
        idx = int(np.argmin(np.abs(luma - target)))
        y, x = divmod(idx, luma.shape[1])
        b, g, r = bgr[y, x]
        return {"r": int(r), "g": int(g), "b": int(b)}
    return _mean_rgb_from_mask(bgr, mask)


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    """小さな点ノイズを除き、領域を少しつなげる。"""
    u8 = (mask.astype(np.uint8) * 255)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL, MORPH_KERNEL))
    u8 = cv2.morphologyEx(u8, cv2.MORPH_OPEN, k)
    u8 = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, k)
    return u8 > 0


def _largest_component_region(
    mask: np.ndarray,
    *,
    min_area: int,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    """
    最大連結成分のマスクと場所情報を返す。
    見つからなければ None。
    """
    u8 = (mask.astype(np.uint8) * 255)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(u8, connectivity=8)
    if n <= 1:
        return None

    # label 0 は背景
    areas = stats[1:, cv2.CC_STAT_AREA]
    best_i = int(np.argmax(areas)) + 1
    area = int(stats[best_i, cv2.CC_STAT_AREA])
    if area < min_area:
        return None

    x = int(stats[best_i, cv2.CC_STAT_LEFT])
    y = int(stats[best_i, cv2.CC_STAT_TOP])
    w = int(stats[best_i, cv2.CC_STAT_WIDTH])
    h = int(stats[best_i, cv2.CC_STAT_HEIGHT])
    cx = float(centroids[best_i, 0])
    cy = float(centroids[best_i, 1])
    comp = labels == best_i
    info = {
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "cx": round(cx, 1),
        "cy": round(cy, 1),
        "count": area,
    }
    return comp, info


def detect_tone_regions(
    bgr: np.ndarray,
    luma: np.ndarray,
    low: float,
    high: float,
) -> tuple[dict[str, int], dict[str, int], dict[str, Any], dict[str, Any]]:
    """
    ハイライト／シャドーの場所（最大連結領域）を判定し、領域内平均 RGB を返す。
    領域が取れない場合は輝度近傍の全画像平均へフォールバックする。
    """
    h_img, w_img = luma.shape[:2]
    min_area = max(16, int(h_img * w_img * MIN_REGION_AREA_RATIO))

    # 閾値近傍バンドで候補マスクを作る（広すぎず狭すぎず）
    band = max(NEAR_BAND, (high - low) * 0.02)
    shadow_mask = _clean_mask(luma <= (low + band))
    highlight_mask = _clean_mask(luma >= (high - band))

    shadow_region: dict[str, Any]
    highlight_region: dict[str, Any]

    sh_comp = _largest_component_region(shadow_mask, min_area=min_area)
    if sh_comp is not None:
        sh_mask, shadow_region = sh_comp
        shadow = _mean_rgb_from_mask(bgr, sh_mask)
        shadow_region["method"] = "connected_component"
    else:
        shadow = _mean_rgb_near_luma(bgr, luma, low, NEAR_BAND)
        shadow_region = {
            "x": 0,
            "y": 0,
            "w": w_img,
            "h": h_img,
            "cx": round(w_img / 2, 1),
            "cy": round(h_img / 2, 1),
            "count": int(np.count_nonzero(shadow_mask)) or 0,
            "method": "fallback_global",
        }

    hi_comp = _largest_component_region(highlight_mask, min_area=min_area)
    if hi_comp is not None:
        hi_mask, highlight_region = hi_comp
        highlight = _mean_rgb_from_mask(bgr, hi_mask)
        highlight_region["method"] = "connected_component"
    else:
        highlight = _mean_rgb_near_luma(bgr, luma, high, NEAR_BAND)
        highlight_region = {
            "x": 0,
            "y": 0,
            "w": w_img,
            "h": h_img,
            "cx": round(w_img / 2, 1),
            "cy": round(h_img / 2, 1),
            "count": int(np.count_nonzero(highlight_mask)) or 0,
            "method": "fallback_global",
        }

    return shadow, highlight, shadow_region, highlight_region


def _find_neutral_gray(
    bgr: np.ndarray,
    lab_l_range: tuple[float, float] = LAB_L_RANGE,
    ab_thresholds: tuple[float, ...] = AB_THRESHOLDS,
    min_pixels: int = MIN_NEUTRAL_PIXELS,
) -> tuple[dict[str, int], float, int]:
    """Lab 中間明度かつ a*/b* が小さい領域の平均 RGB を求める。"""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float64)
    # OpenCV Lab: L=0–255, a/b=0–255 (128=中立)
    L = lab[:, :, 0] * (100.0 / 255.0)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0

    l_lo, l_hi = lab_l_range
    mid_mask = (L >= l_lo) & (L <= l_hi)

    used_threshold = ab_thresholds[-1]
    selected = np.zeros(L.shape, dtype=bool)

    for thr in ab_thresholds:
        cand = mid_mask & (np.abs(a) <= thr) & (np.abs(b) <= thr)
        if int(np.count_nonzero(cand)) >= min_pixels:
            selected = cand
            used_threshold = thr
            break
    else:
        # 最終フォールバック: 中間明度内で |a|+|b| が小さい上位ピクセル
        if np.any(mid_mask):
            chroma = np.abs(a) + np.abs(b)
            chroma_mid = np.where(mid_mask, chroma, np.inf)
            flat = chroma_mid.ravel()
            n = min(max(min_pixels, 100), int(np.count_nonzero(mid_mask)))
            idx = np.argpartition(flat, n - 1)[:n]
            selected = np.zeros(flat.shape, dtype=bool)
            selected[idx] = True
            selected = selected.reshape(L.shape)
            used_threshold = float(np.max(chroma[selected])) if np.any(selected) else used_threshold
        else:
            # 中間明度が空なら画像全体の chroma 最小
            chroma = np.abs(a) + np.abs(b)
            flat = chroma.ravel()
            n = min(max(min_pixels, 100), flat.size)
            idx = np.argpartition(flat, n - 1)[:n]
            selected = np.zeros(flat.shape, dtype=bool)
            selected[idx] = True
            selected = selected.reshape(L.shape)
            used_threshold = float(np.max(chroma[selected]))

    count = int(np.count_nonzero(selected))
    if count == 0:
        raise ValueError("ニュートラルグレー領域を検出できませんでした。")

    mean_bgr = bgr[selected].mean(axis=0)
    gray = {
        "r": int(round(mean_bgr[2])),
        "g": int(round(mean_bgr[1])),
        "b": int(round(mean_bgr[0])),
    }
    return gray, used_threshold, count


def analyze_image(
    path: str | Path,
    clip_percent: float | None = None,
    lab_l_range: tuple[float, float] = LAB_L_RANGE,
    *,
    shadow_clip_percent: float = CLIP_SHADOW_PERCENT,
    highlight_clip_percent: float = CLIP_HIGHLIGHT_PERCENT,
) -> dict[str, Any]:
    """画像を解析し、補正値 dict を返す。"""
    path = Path(path)
    bgr = load_image_bgr(path)
    luma = _luminance_rec709(bgr)
    low, high = _percentile_thresholds(
        luma,
        clip_percent,
        shadow_percent=shadow_clip_percent,
        highlight_percent=highlight_clip_percent,
    )

    shadow, highlight, shadow_region, highlight_region = detect_tone_regions(
        bgr, luma, low, high
    )
    gray, ab_thr, neutral_count = _find_neutral_gray(bgr, lab_l_range=lab_l_range)

    return {
        "version": 1,
        "source": path.name,
        "shadow": shadow,
        "highlight": highlight,
        "gray": gray,
        "params": {
            "clip_shadow_percent": shadow_clip_percent if clip_percent is None else clip_percent,
            "clip_highlight_percent": (
                highlight_clip_percent if clip_percent is None else clip_percent
            ),
            "lab_l_range": [lab_l_range[0], lab_l_range[1]],
            "ab_threshold": ab_thr,
            "neutral_pixel_count": neutral_count,
            "shadow_luma": round(low, 2),
            "highlight_luma": round(high, 2),
            "shadow_region": shadow_region,
            "highlight_region": highlight_region,
            "detection": "local_opencv_regions",
        },
    }


def save_json(result: dict[str, Any], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out_path


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="カラー補正値を画像から算出して JSON 出力")
    parser.add_argument("image", help="入力画像パス")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="出力 JSON パス（省略時は画像と同じ場所に correction.json）",
    )
    args = parser.parse_args(argv)

    image_path = Path(args.image)
    out = Path(args.output) if args.output else image_path.with_name("correction.json")

    try:
        result = analyze_image(image_path)
        save_json(result, out)
    except Exception as exc:  # noqa: BLE001 — CLI 入口
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    print(f"書き出しました: {out}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
