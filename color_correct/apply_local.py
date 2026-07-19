"""Photoshop を使わず、解析結果と同じ Levels / Curves を OpenCV で適用する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .analyze import load_image_bgr
from .apply_ps import normalize_curve_data, normalize_levels_data


def _levels_lut(
    black: int, white: int, gamma: float, out_black: int, out_white: int
) -> np.ndarray:
    """1 チャンネル分のレベル補正 LUT (uint8, 256)。"""
    b = int(max(0, min(254, black)))
    w = int(max(b + 1, min(255, white)))
    g = float(min(9.99, max(0.10, gamma)))
    ob = int(max(0, min(254, out_black)))
    ow = int(max(ob + 1, min(255, out_white)))

    x = np.arange(256, dtype=np.float64)
    # 入力レンジへ正規化
    t = (x - b) / (w - b)
    t = np.clip(t, 0.0, 1.0)
    if abs(g - 1.0) > 1e-9:
        t = np.power(t, 1.0 / g)
    y = ob + t * (ow - ob)
    return np.clip(np.rint(y), 0, 255).astype(np.uint8)


def _curve_lut(points: list[tuple[float, float]]) -> np.ndarray:
    """折れ線トーンカーブ LUT。"""
    if len(points) < 2:
        return np.arange(256, dtype=np.uint8)
    xs = np.array([p[0] for p in points], dtype=np.float64)
    ys = np.array([p[1] for p in points], dtype=np.float64)
    # 単調増加を保証
    for i in range(1, len(xs)):
        if xs[i] <= xs[i - 1]:
            xs[i] = min(255.0, xs[i - 1] + 1.0)
    grid = np.arange(256, dtype=np.float64)
    y = np.interp(grid, xs, ys)
    return np.clip(np.rint(y), 0, 255).astype(np.uint8)


def apply_correction_bgr(
    bgr: np.ndarray,
    data: dict[str, Any],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
) -> np.ndarray:
    """BGR 画像に Levels（HL/SH）→ Curves（中間かぶり）を適用する。"""
    if not use_curves and not use_levels:
        raise ValueError("レベル補正またはトーンカーブを有効にしてください。")

    out = bgr.copy()
    # OpenCV は B,G,R
    ch_map = ("Bl  ", "Grn ", "Rd  ")

    if use_levels:
        levels = normalize_levels_data(data)
        luts = [_levels_lut(*levels[ch]) for ch in ch_map]
        planes = cv2.split(out)
        planes = [cv2.LUT(p, lut) for p, lut in zip(planes, luts)]
        out = cv2.merge(planes)

    if use_curves:
        curves = normalize_curve_data(data)
        luts = [_curve_lut(curves[ch]) for ch in ch_map]
        planes = cv2.split(out)
        planes = [cv2.LUT(p, lut) for p, lut in zip(planes, luts)]
        out = cv2.merge(planes)

    return out


def _default_out_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.stem}_corrected{image_path.suffix}")


def save_bgr_image(bgr: np.ndarray, path: Path) -> None:
    """日本語パス対応で保存。"""
    path = Path(path)
    ext = path.suffix.lower() or ".jpg"
    if ext in (".jpg", ".jpeg"):
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    elif ext == ".png":
        ok, buf = cv2.imencode(".png", bgr)
    elif ext in (".tif", ".tiff"):
        ok, buf = cv2.imencode(".tif", bgr)
    elif ext == ".bmp":
        ok, buf = cv2.imencode(".bmp", bgr)
    elif ext == ".webp":
        ok, buf = cv2.imencode(".webp", bgr, [int(cv2.IMWRITE_WEBP_QUALITY), 95])
    else:
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        path = path.with_suffix(".jpg")
    if not ok:
        raise RuntimeError(f"画像のエンコードに失敗しました: {path}")
    buf.tofile(str(path))


def apply_correction_to_file(
    image_path: str | Path,
    data: dict[str, Any],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
    output_path: str | Path | None = None,
) -> Path:
    """
    画像を読み込み、補正して保存する。
    戻り値: 保存先パス
    """
    src = Path(image_path).resolve()
    if not src.is_file():
        raise RuntimeError(f"ファイルが見つかりません: {src}")

    bgr = load_image_bgr(src)
    corrected = apply_correction_bgr(
        bgr, data, use_curves=use_curves, use_levels=use_levels
    )
    out = Path(output_path).resolve() if output_path else _default_out_path(src)
    save_bgr_image(corrected, out)
    return out
