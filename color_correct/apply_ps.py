"""Photoshop にトーンカーブ / レベル補正レイヤーを適用する（win32com）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .analyze import load_json

LAYER_NAME_CURVES = "Auto Color Curves"
LAYER_NAME_LEVELS = "Auto Color Levels"
LAYER_NAME_CURVES_CAST = "Auto Curves (Cast)"
LAYER_NAME_LEVELS_TONAL = "Auto Levels (HL/SH)"
DIALOG_MODE_NO = 3  # DialogModes.NO
DIALOG_MODE_ERROR = 2  # DialogModes.ERROR

# 後方互換
LAYER_NAME = LAYER_NAME_CURVES

# ハイライトは白飛びさせない（RGB≈245 ≒ CMYK 約5%）
HIGHLIGHT_OUTPUT_RGB = 245
# 理想シャドー: C95 M88 Y88 K70
SHADOW_TARGET_CMYK = (95, 88, 88, 70)


def _clamp(v: float, lo: float = 0.0, hi: float = 255.0) -> float:
    return max(lo, min(hi, v))


def _cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    """
    パーセント CMYK → おおよそ sRGB（プロファイル非依存の簡易換算）。
    R = 255*(1-C)*(1-K) など。
    """
    c_n, m_n, y_n, k_n = c / 100.0, m / 100.0, y / 100.0, k / 100.0
    r = int(round(255.0 * (1.0 - c_n) * (1.0 - k_n)))
    g = int(round(255.0 * (1.0 - m_n) * (1.0 - k_n)))
    b = int(round(255.0 * (1.0 - y_n) * (1.0 - k_n)))
    return (
        int(_clamp(r, 0, 255)),
        int(_clamp(g, 0, 255)),
        int(_clamp(b, 0, 255)),
    )


def _shadow_output_rgb() -> dict[str, int]:
    r, g, b = _cmyk_to_rgb(*SHADOW_TARGET_CMYK)
    return {"r": r, "g": g, "b": b}


# C95 M88 Y88 K70 → おおよそ R4 G9 B9
_SHADOW_OUT = _shadow_output_rgb()
SHADOW_OUTPUT_RGB = _SHADOW_OUT


def _mean3(r: float, g: float, b: float) -> float:
    return (float(r) + float(g) + float(b)) / 3.0


def _ensure_monotonic_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for inp, out in points:
        inp = _clamp(inp)
        out = _clamp(out)
        if cleaned and inp <= cleaned[-1][0]:
            inp = min(255.0, cleaned[-1][0] + 1.0)
        cleaned.append((inp, out))
    return cleaned


def _channel_points_mid_cast(gray: float, target: float) -> list[tuple[float, float]]:
    """
    トーンカーブは中間調のかぶり取りのみ。
    ライト／シャドーの明暗補正は行わない（端点は固定）。
    """
    g = _clamp(gray)
    t = _clamp(target)
    hout = float(HIGHLIGHT_OUTPUT_RGB)
    if g <= 0:
        g = 1.0
    if g >= hout:
        g = hout - 1.0
    return _ensure_monotonic_points([(0.0, 0.0), (g, t), (hout, hout)])


def _levels_hl_sh(
    shadow: float, highlight: float, out_black: int
) -> tuple[int, int, float, int, int]:
    """
    レベル補正用: (入力黒, 入力白, ガンマ, 出力黒, 出力白)
    出力黒 = 理想シャドー（CMYK換算RGB）、出力白 = 245
    """
    s = _clamp(shadow)
    h = _clamp(highlight)
    if h <= s + 1.0:
        h = min(255.0, s + 2.0)
    ob = int(_clamp(out_black, 0, 254))
    ow = int(HIGHLIGHT_OUTPUT_RGB)
    if ow <= ob:
        ow = min(255, ob + 1)
    return int(round(s)), int(round(h)), 1.0, ob, ow


def _require_rgb_keys(data: dict[str, Any]) -> tuple[dict, dict, dict]:
    for key in ("shadow", "highlight", "gray"):
        if key not in data:
            raise ValueError(f"JSON に '{key}' がありません。")
        for ch in ("r", "g", "b"):
            if ch not in data[key]:
                raise ValueError(f"JSON の '{key}' に '{ch}' がありません。")
    return data["shadow"], data["highlight"], data["gray"]


def normalize_curve_data(
    data: dict[str, Any],
    *,
    cast_only: bool = True,
) -> dict[str, list[tuple[float, float]]]:
    """
    トーンカーブ用データ。ライト／シャドー補正はせず、中間調のかぶりのみ。
    cast_only は互換のため残すが、常に中間かぶりのみを返す。
    """
    _sh, _hi, gy = _require_rgb_keys(data)
    target = _mean3(gy["r"], gy["g"], gy["b"])
    return {
        "Rd  ": _channel_points_mid_cast(gy["r"], target),
        "Grn ": _channel_points_mid_cast(gy["g"], target),
        "Bl  ": _channel_points_mid_cast(gy["b"], target),
    }


def normalize_levels_data(
    data: dict[str, Any],
    *,
    tonal_only: bool = True,
) -> dict[str, tuple[int, int, float, int, int]]:
    """
    レベル補正用データ。ハイライト／シャドーをチャンネルごとに調整する。
    出力シャドーは理想 CMYK（C95 M88 Y88 K70）の RGB 換算値。
    """
    sh, hi, _gy = _require_rgb_keys(data)
    out = _SHADOW_OUT
    return {
        "Rd  ": _levels_hl_sh(sh["r"], hi["r"], out["r"]),
        "Grn ": _levels_hl_sh(sh["g"], hi["g"], out["g"]),
        "Bl  ": _levels_hl_sh(sh["b"], hi["b"], out["b"]),
    }


def _dispatch_ps(prog_id: str) -> Any:
    import win32com.client  # type: ignore[import-untyped]

    return win32com.client.Dispatch(prog_id)


def _cid(app: Any, s: str) -> int:
    return app.CharIDToTypeID(s)


def _sid(app: Any, s: str) -> int:
    return app.StringIDToTypeID(s)


def _dispatch_ps_helper(base_name: str) -> Any:
    """ActionDescriptor 等。環境によってはバージョン付き ProgID のみ有効。"""
    errors: list[str] = []
    # 無印 → 新しい版から
    candidates = [base_name] + [
        f"{base_name}.{v}"
        for v in (
            "260",
            "250",
            "240",
            "230",
            "220",
            "210",
            "200",
            "190",
            "180",
            "170",
            "160",
            "150",
            "140",
            "130",
            "120",
            "110",
            "100",
            "90",
            "80",
            "70",
            "60",
        )
    ]
    for prog_id in candidates:
        try:
            return _dispatch_ps(prog_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{prog_id}:{exc}")
    detail = errors[-1] if errors else "不明"
    raise RuntimeError(
        f"{base_name} を作成できません（COM クラス未登録の可能性）。\n"
        f"（詳細: {detail}）"
    )


def _new_desc() -> Any:
    return _dispatch_ps_helper("Photoshop.ActionDescriptor")


def _new_ref() -> Any:
    return _dispatch_ps_helper("Photoshop.ActionReference")


def _new_list() -> Any:
    return _dispatch_ps_helper("Photoshop.ActionList")


def _put_curve_points(app: Any, point_list: Any, points: list[tuple[float, float]]) -> None:
    for inp, out in points:
        desc = _new_desc()
        desc.PutDouble(_cid(app, "Hrzn"), float(inp))
        desc.PutDouble(_cid(app, "Vrtc"), float(out))
        point_list.PutObject(_cid(app, "Pnt "), desc)


def _rename_active_layer(app: Any, layer_name: str) -> None:
    try:
        app.ActiveDocument.ActiveLayer.Name = layer_name
    except Exception:  # noqa: BLE001
        pass


def create_curves_adjustment_layer(
    app: Any,
    channel_curves: dict[str, list[tuple[float, float]]],
    layer_name: str = LAYER_NAME_CURVES,
) -> None:
    """Action Manager で Curves 調整レイヤーを新規作成する。"""
    desc_make = _new_desc()
    ref = _new_ref()
    ref.PutClass(_cid(app, "AdjL"))
    desc_make.PutReference(_cid(app, "null"), ref)

    desc_type = _new_desc()
    desc_curves = _new_desc()
    list_adj = _new_list()

    for ch_id, points in channel_curves.items():
        desc_ch = _new_desc()
        ref_ch = _new_ref()
        ref_ch.PutEnumerated(_cid(app, "Chnl"), _cid(app, "Chnl"), _cid(app, ch_id))
        desc_ch.PutReference(_cid(app, "Chnl"), ref_ch)

        list_pts = _new_list()
        _put_curve_points(app, list_pts, points)
        desc_ch.PutList(_cid(app, "Crv "), list_pts)
        list_adj.PutObject(_cid(app, "CrvA"), desc_ch)

    desc_curves.PutList(_cid(app, "Adjs"), list_adj)
    desc_type.PutObject(_cid(app, "Type"), _cid(app, "Crvs"), desc_curves)
    desc_make.PutObject(_cid(app, "Usng"), _cid(app, "AdjL"), desc_type)

    app.ExecuteAction(_cid(app, "Mk  "), desc_make, DIALOG_MODE_NO)
    _rename_active_layer(app, layer_name)


def _make_empty_levels_layer(app: Any) -> None:
    """デフォルトのレベル補正レイヤーを新規作成する。"""
    desc_make = _new_desc()
    ref = _new_ref()
    ref.PutClass(_cid(app, "AdjL"))
    desc_make.PutReference(_cid(app, "null"), ref)

    desc_type = _new_desc()
    desc_levels = _new_desc()
    desc_levels.PutEnumerated(
        _sid(app, "presetKind"),
        _sid(app, "presetKindType"),
        _sid(app, "presetKindDefault"),
    )
    desc_type.PutObject(_cid(app, "Type"), _cid(app, "Lvls"), desc_levels)
    desc_make.PutObject(_cid(app, "Usng"), _cid(app, "AdjL"), desc_type)
    app.ExecuteAction(_cid(app, "Mk  "), desc_make, DIALOG_MODE_NO)


def _set_levels_on_active_layer(
    app: Any,
    channel_levels: dict[str, tuple[int, int, float, int, int]],
) -> None:
    """
    アクティブなレベル補正レイヤーに黒点・白点・ガンマを書き込む。
    現代の stringID 形式（input / gamma / output）を使う。
    """
    channel_names = {
        "Rd  ": "red",
        "Grn ": "green",
        "Bl  ": "blue",
    }

    desc = _new_desc()
    ref = _new_ref()
    ref.PutEnumerated(
        _sid(app, "adjustmentLayer"),
        _sid(app, "ordinal"),
        _sid(app, "targetEnum"),
    )
    desc.PutReference(_cid(app, "null"), ref)

    desc_to = _new_desc()
    desc_to.PutEnumerated(
        _sid(app, "presetKind"),
        _sid(app, "presetKindType"),
        _sid(app, "presetKindCustom"),
    )

    adj_list = _new_list()
    for ch_id, (black, white, gamma, out_black, out_white) in channel_levels.items():
        black_i = int(max(0, min(254, black)))
        white_i = int(max(black_i + 1, min(255, white)))
        gamma_f = float(min(9.99, max(0.10, gamma)))
        out_b = int(max(0, min(254, out_black)))
        out_w = int(max(out_b + 1, min(255, out_white)))

        desc_ch = _new_desc()
        ref_ch = _new_ref()
        ch_name = channel_names.get(ch_id, "composite")
        ref_ch.PutEnumerated(
            _sid(app, "channel"),
            _sid(app, "channel"),
            _sid(app, ch_name),
        )
        desc_ch.PutReference(_sid(app, "channel"), ref_ch)

        input_list = _new_list()
        input_list.PutInteger(black_i)
        input_list.PutInteger(white_i)
        desc_ch.PutList(_sid(app, "input"), input_list)
        desc_ch.PutDouble(_sid(app, "gamma"), gamma_f)

        output_list = _new_list()
        output_list.PutInteger(out_b)
        output_list.PutInteger(out_w)
        desc_ch.PutList(_sid(app, "output"), output_list)

        adj_list.PutObject(_sid(app, "levelsAdjustment"), desc_ch)

    desc_to.PutList(_sid(app, "adjustment"), adj_list)
    desc.PutObject(_sid(app, "to"), _sid(app, "levels"), desc_to)
    app.ExecuteAction(_sid(app, "set"), desc, DIALOG_MODE_NO)


def create_levels_adjustment_layer(
    app: Any,
    channel_levels: dict[str, tuple[int, int, float, int, int]],
    layer_name: str = LAYER_NAME_LEVELS,
) -> None:
    """
    レベル補正レイヤーを作成し、続けて数値を set する。
    （作成時に Adjs を渡す古い形式は、環境によって無視されるため）
    """
    _make_empty_levels_layer(app)
    _rename_active_layer(app, layer_name)
    _set_levels_on_active_layer(app, channel_levels)


# Photoshop COM 接続用 ProgID（新しい版から順に試す）
_PHOTOSHOP_PROG_IDS = (
    "Photoshop.Application",
    "Photoshop.Application.260",  # 2025/2026 系
    "Photoshop.Application.250",
    "Photoshop.Application.240",
    "Photoshop.Application.230",
    "Photoshop.Application.220",
    "Photoshop.Application.210",
    "Photoshop.Application.200",
    "Photoshop.Application.190",
    "Photoshop.Application.180",
    "Photoshop.Application.170",
    "Photoshop.Application.160",
    "Photoshop.Application.150",
    "Photoshop.Application.140",
    "Photoshop.Application.130",
    "Photoshop.Application.120",
    "Photoshop.Application.110",
    "Photoshop.Application.100",
    "Photoshop.Application.90",
    "Photoshop.Application.80",
    "Photoshop.Application.70",
    "Photoshop.Application.60",
)


def _ensure_com_initialized() -> None:
    try:
        import pythoncom  # type: ignore[import-untyped]

        pythoncom.CoInitialize()
    except Exception:  # noqa: BLE001
        pass


def get_photoshop_app() -> Any:
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 がインストールされていません。\n"
            "開発実行時は pip install pywin32 を実行してください。"
        ) from exc

    _ensure_com_initialized()

    errors: list[str] = []
    app = None

    # 1) すでに起動中の Photoshop があれば優先して接続
    for prog_id in _PHOTOSHOP_PROG_IDS:
        try:
            app = win32com.client.GetActiveObject(prog_id)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GetActiveObject({prog_id}): {exc}")

    # 2) 起動していなければ新規に起動（Dispatch）
    if app is None:
        for prog_id in _PHOTOSHOP_PROG_IDS:
            try:
                app = win32com.client.Dispatch(prog_id)
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Dispatch({prog_id}): {exc}")

    # 3) dynamic Dispatch の最終手段
    if app is None:
        try:
            app = win32com.client.dynamic.Dispatch("Photoshop.Application")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dynamic.Dispatch: {exc}")

    if app is None:
        detail = errors[-1] if errors else "不明"
        raise RuntimeError(
            "Photoshop に接続できませんでした。\n"
            "インストール済みでも次で失敗することがあります。\n\n"
            "確認してください:\n"
            "・Photoshop を一度起動してログイン完了後、本ツールを再実行\n"
            "・64bit 版 Photoshop を使う（本ツールは 64bit）\n"
            "・本ツールと Photoshop を同じユーザーで実行\n"
            "・管理者権限の不一致（片方だけ管理者実行になっていないか）\n"
            "・Photoshop を修復インストール／再起動\n\n"
            f"（詳細: {detail}）"
        )

    try:
        app.Visible = True
        # Open 時に DisplayDialogs=NO だと「必要な値がありません」になる環境があるため、
        # 接続時は触らない（適用処理の中だけで制御する）
    except Exception:  # noqa: BLE001
        pass

    # 接続確認（名前が取れれば OK）
    try:
        _ = str(app.Name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Photoshop オブジェクトには接続できましたが、操作できませんでした。\n"
            "Photoshop を再起動してからもう一度試してください。\n"
            f"（詳細: {exc}）"
        ) from exc

    return app


def _js_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _path_for_extendscript(path: Path) -> str:
    """ExtendScript File() 用パス（/ 区切り）。"""
    return _js_escape(str(path.resolve()).replace("\\", "/"))


def _open_format_id(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".tif": "TIFF",
        ".tiff": "TIFF",
        ".bmp": "BMP",
        ".gif": "GIFf",
    }.get(ext, "JPEG")


def _is_ascii_path(path: Path) -> bool:
    try:
        str(path.resolve()).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _copy_to_ascii_temp(path: Path) -> Path:
    import shutil
    import tempfile
    import uuid

    suffix = path.suffix if path.suffix else ".jpg"
    tmp_dir = Path(tempfile.gettempdir()) / "ColorCorrectOpen"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"open_{uuid.uuid4().hex}{suffix}"
    shutil.copy2(path, tmp_path)
    return tmp_path


def _jsx_dir() -> Path:
    import tempfile

    d = Path(tempfile.gettempdir()) / "ColorCorrectJSX"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_jsx(app: Any, script: str) -> Any:
    """
    ExtendScript を一時 .jsx（UTF-8 BOM）として実行する。
    この PC では ActionDescriptor の COM ProgID が無効なことがあり、
    開く／調整レイヤー作成は JSX 内の new ActionDescriptor() に寄せる。
    """
    import uuid

    jsx_path = _jsx_dir() / f"run_{uuid.uuid4().hex}.jsx"
    jsx_path.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))
    jsx_fs = str(jsx_path.resolve())
    last_exc: Exception | None = None
    result: Any = None
    try:
        for caller in (
            lambda: app.DoJavaScriptFile(jsx_fs),
            lambda: app.DoJavaScript(script),
        ):
            try:
                result = caller()
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                result = None
        else:
            assert last_exc is not None
            raise last_exc

        if isinstance(result, str):
            low = result.strip().lower()
            if low.startswith("error") or "exception" in low[:80]:
                raise RuntimeError(result)
        return result
    finally:
        try:
            jsx_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


def _jsx_open_function() -> str:
    """Camera Raw 経由の JPEG Open を避けるための open ヘルパー。"""
    return r"""
function ccOpenFile(path, fmt) {
  var f = File(path);
  if (!f.exists) {
    throw new Error("File not found: " + path);
  }
  var errors = [];

  function tryForceFormat(dialogMode) {
    var d = new ActionDescriptor();
    d.putPath(charIDToTypeID("null"), f);
    try { d.putBoolean(stringIDToTypeID("overrideOpen"), true); } catch (e0) {}
    var asDesc = new ActionDescriptor();
    d.putObject(stringIDToTypeID("as"), stringIDToTypeID(fmt), asDesc);
    executeAction(charIDToTypeID("Opn "), d, dialogMode);
  }

  function tryOverride(dialogMode) {
    var d = new ActionDescriptor();
    d.putPath(charIDToTypeID("null"), f);
    try { d.putBoolean(stringIDToTypeID("overrideOpen"), true); } catch (e0) {}
    executeAction(charIDToTypeID("Opn "), d, dialogMode);
  }

  var modes = [DialogModes.NO, DialogModes.ERROR];
  var i;
  for (i = 0; i < modes.length; i++) {
    try {
      app.displayDialogs = modes[i];
      tryForceFormat(modes[i]);
      return;
    } catch (e1) { errors.push("force:" + e1); }
  }
  for (i = 0; i < modes.length; i++) {
    try {
      app.displayDialogs = modes[i];
      tryOverride(modes[i]);
      return;
    } catch (e2) { errors.push("override:" + e2); }
  }
  for (i = 0; i < modes.length; i++) {
    try {
      app.displayDialogs = modes[i];
      app.open(f);
      return;
    } catch (e3) { errors.push("dom:" + e3); }
  }
  throw new Error("open failed: " + errors.join(" | "));
}
"""


def _jsx_curves_function() -> str:
    return r"""
function ccCreateCurves(channelMap, layerName) {
  var descMake = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putClass(charIDToTypeID("AdjL"));
  descMake.putReference(charIDToTypeID("null"), ref);

  var descType = new ActionDescriptor();
  var descCurves = new ActionDescriptor();
  var listAdj = new ActionList();
  var chIds = ["Rd  ", "Grn ", "Bl  "];
  var ci, pi;
  for (ci = 0; ci < chIds.length; ci++) {
    var ch = chIds[ci];
    var pts = channelMap[ch];
    if (!pts) continue;
    var descCh = new ActionDescriptor();
    var refCh = new ActionReference();
    refCh.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID(ch));
    descCh.putReference(charIDToTypeID("Chnl"), refCh);
    var listPts = new ActionList();
    for (pi = 0; pi < pts.length; pi++) {
      var pdesc = new ActionDescriptor();
      pdesc.putDouble(charIDToTypeID("Hrzn"), pts[pi][0]);
      pdesc.putDouble(charIDToTypeID("Vrtc"), pts[pi][1]);
      listPts.putObject(charIDToTypeID("Pnt "), pdesc);
    }
    descCh.putList(charIDToTypeID("Crv "), listPts);
    listAdj.putObject(charIDToTypeID("CrvA"), descCh);
  }
  descCurves.putList(charIDToTypeID("Adjs"), listAdj);
  descType.putObject(charIDToTypeID("Type"), charIDToTypeID("Crvs"), descCurves);
  descMake.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), descType);
  executeAction(charIDToTypeID("Mk  "), descMake, DialogModes.NO);
  try { app.activeDocument.activeLayer.name = layerName; } catch (e) {}
}
"""


def _jsx_levels_functions() -> str:
    return r"""
function ccMakeEmptyLevels(layerName) {
  var descMake = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putClass(charIDToTypeID("AdjL"));
  descMake.putReference(charIDToTypeID("null"), ref);
  var descType = new ActionDescriptor();
  var descLevels = new ActionDescriptor();
  descLevels.putEnumerated(
    stringIDToTypeID("presetKind"),
    stringIDToTypeID("presetKindType"),
    stringIDToTypeID("presetKindDefault")
  );
  descType.putObject(charIDToTypeID("Type"), charIDToTypeID("Lvls"), descLevels);
  descMake.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), descType);
  executeAction(charIDToTypeID("Mk  "), descMake, DialogModes.NO);
  try { app.activeDocument.activeLayer.name = layerName; } catch (e) {}
}

function ccSetLevels(channelMap) {
  var chNames = { "Rd  ": "red", "Grn ": "green", "Bl  ": "blue" };
  var desc = new ActionDescriptor();
  var ref = new ActionReference();
  ref.putEnumerated(
    stringIDToTypeID("adjustmentLayer"),
    stringIDToTypeID("ordinal"),
    stringIDToTypeID("targetEnum")
  );
  desc.putReference(charIDToTypeID("null"), ref);

  var descTo = new ActionDescriptor();
  descTo.putEnumerated(
    stringIDToTypeID("presetKind"),
    stringIDToTypeID("presetKindType"),
    stringIDToTypeID("presetKindCustom")
  );
  var adjList = new ActionList();
  var chIds = ["Rd  ", "Grn ", "Bl  "];
  var i;
  for (i = 0; i < chIds.length; i++) {
    var ch = chIds[i];
    var vals = channelMap[ch];
    if (!vals) continue;
    var descCh = new ActionDescriptor();
    var refCh = new ActionReference();
    refCh.putEnumerated(
      stringIDToTypeID("channel"),
      stringIDToTypeID("channel"),
      stringIDToTypeID(chNames[ch])
    );
    descCh.putReference(stringIDToTypeID("channel"), refCh);
    var inputList = new ActionList();
    inputList.putInteger(vals[0]);
    inputList.putInteger(vals[1]);
    descCh.putList(stringIDToTypeID("input"), inputList);
    descCh.putDouble(stringIDToTypeID("gamma"), vals[2]);
    var outputList = new ActionList();
    outputList.putInteger(vals[3]);
    outputList.putInteger(vals[4]);
    descCh.putList(stringIDToTypeID("output"), outputList);
    adjList.putObject(stringIDToTypeID("levelsAdjustment"), descCh);
  }
  descTo.putList(stringIDToTypeID("adjustment"), adjList);
  desc.putObject(stringIDToTypeID("to"), stringIDToTypeID("levels"), descTo);
  executeAction(stringIDToTypeID("set"), desc, DialogModes.NO);
}

function ccCreateLevels(channelMap, layerName) {
  ccMakeEmptyLevels(layerName);
  ccSetLevels(channelMap);
}
"""


def _curves_to_js_object(curves: dict[str, list[tuple[float, float]]]) -> str:
    parts: list[str] = []
    for ch, pts in curves.items():
        pts_js = ",".join(f"[{float(a)},{float(b)}]" for a, b in pts)
        parts.append(f'"{ch}":[{pts_js}]')
    return "{" + ",".join(parts) + "}"


def _levels_to_js_object(
    levels: dict[str, tuple[int, int, float, int, int]],
) -> str:
    parts: list[str] = []
    for ch, vals in levels.items():
        b, w, g, ob, ow = vals
        parts.append(f'"{ch}":[{int(b)},{int(w)},{float(g)},{int(ob)},{int(ow)}]')
    return "{" + ",".join(parts) + "}"


def _build_apply_jsx(
    *,
    open_path: Path | None,
    use_levels: bool,
    use_curves: bool,
    levels: dict[str, tuple[int, int, float, int, int]] | None,
    curves: dict[str, list[tuple[float, float]]] | None,
) -> str:
    chunks: list[str] = [
        "#target photoshop\n",
        "app.displayDialogs = DialogModes.NO;\n",
        _jsx_open_function(),
        _jsx_levels_functions(),
        _jsx_curves_function(),
        "var ccCreated = [];\n",
    ]
    if open_path is not None:
        jp = _path_for_extendscript(open_path)
        fmt = _open_format_id(open_path)
        chunks.append(f'ccOpenFile("{jp}", "{fmt}");\n')

    chunks.append(
        "if (!app.documents.length) { throw new Error('No active document'); }\n"
        "if (app.activeDocument.mode != DocumentMode.RGB) {\n"
        "  throw new Error('Document is not RGB mode');\n"
        "}\n"
    )

    if use_levels and levels is not None:
        chunks.append(
            f"ccCreateLevels({_levels_to_js_object(levels)}, "
            f'"{_js_escape(LAYER_NAME_LEVELS_TONAL)}");\n'
            f'ccCreated.push("{_js_escape(LAYER_NAME_LEVELS_TONAL)}");\n'
        )
    if use_curves and curves is not None:
        chunks.append(
            f"ccCreateCurves({_curves_to_js_object(curves)}, "
            f'"{_js_escape(LAYER_NAME_CURVES_CAST)}");\n'
            f'ccCreated.push("{_js_escape(LAYER_NAME_CURVES_CAST)}");\n'
        )

    chunks.append(
        'app.activeDocument.name + "|||" + ccCreated.join(",");\n'
    )
    return "".join(chunks)


def _parse_jsx_apply_result(result: Any) -> tuple[str, list[str]]:
    text = str(result or "").strip()
    if "|||" in text:
        name, layers = text.split("|||", 1)
        created = [x for x in layers.split(",") if x]
        return name, created
    # ドキュメント名だけ返った場合
    try:
        return text, []
    except Exception:  # noqa: BLE001
        return text, []


def apply_via_jsx(
    app: Any,
    data: dict[str, Any],
    *,
    image_path: str | Path | None = None,
    use_curves: bool = True,
    use_levels: bool = True,
) -> tuple[str, list[str]]:
    """
    開く＋Levels/Curves をすべて ExtendScript で実行する。
    COM の ActionDescriptor が使えない環境向けの本命ルート。
    """
    if not use_curves and not use_levels:
        raise RuntimeError(
            "適用する補正が選ばれていません。\n"
            "レベル補正またはトーンカーブを有効にしてください。"
        )

    open_path: Path | None = None
    temp_copy: Path | None = None
    if image_path is not None:
        src = Path(image_path).resolve()
        if not src.is_file():
            raise RuntimeError(f"ファイルが見つかりません: {src}")
        # 日本語パスは常に ASCII 一時ファイルへ（Open 安定化）
        if _is_ascii_path(src):
            open_path = src
        else:
            temp_copy = _copy_to_ascii_temp(src)
            open_path = temp_copy

    levels = normalize_levels_data(data) if use_levels else None
    curves = normalize_curve_data(data) if use_curves else None

    errors: list[str] = []
    paths_to_try: list[Path | None]
    if open_path is None:
        paths_to_try = [None]
    else:
        paths_to_try = [open_path]
        # 元パスが ASCII でも失敗したら一時コピーでも試す
        if temp_copy is None:
            paths_to_try.append(_copy_to_ascii_temp(Path(image_path).resolve()))  # type: ignore[arg-type]

    last_exc: Exception | None = None
    for candidate in paths_to_try:
        try:
            script = _build_apply_jsx(
                open_path=candidate,
                use_levels=use_levels,
                use_curves=use_curves,
                levels=levels,
                curves=curves,
            )
            result = _run_jsx(app, script)
            doc_name, created = _parse_jsx_apply_result(result)
            if not created:
                # 戻り値が変でも、レイヤー作成は成功している可能性がある
                created = []
                if use_levels:
                    created.append(LAYER_NAME_LEVELS_TONAL)
                if use_curves:
                    created.append(LAYER_NAME_CURVES_CAST)
            try:
                app.DisplayDialogs = DIALOG_MODE_NO
            except Exception:  # noqa: BLE001
                pass
            return doc_name or str(app.ActiveDocument.Name), created
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            errors.append(str(exc))

    detail = " | ".join(errors[-2:]) if errors else str(last_exc)
    raise RuntimeError(
        "Photoshop への適用に失敗しました。\n"
        f"{Path(image_path) if image_path else '(アクティブドキュメント)'}\n\n"
        "確認してください:\n"
        "・Photoshop を起動し、ログイン完了後に再実行\n"
        "・環境設定 → ファイル処理 → 「JPEG ファイルを Camera Raw で開く」をオフ\n"
        "・手動で画像を開いてから「再適用（アクティブ）」\n"
        f"（詳細: {detail}）"
    )


def _photoshop_exe(app: Any) -> Path | None:
    """起動中 Photoshop の exe パスを推定する。"""
    try:
        base = Path(str(app.Path))
        cand = base / "Photoshop.exe"
        if cand.is_file():
            return cand
    except Exception:  # noqa: BLE001
        pass

    import os

    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    for root in roots:
        adobe = Path(root) / "Adobe"
        if not adobe.is_dir():
            continue
        try:
            matches = sorted(adobe.glob("Adobe Photoshop */Photoshop.exe"), reverse=True)
        except Exception:  # noqa: BLE001
            matches = []
        if matches:
            return matches[0]
    return None


def _doc_names(app: Any) -> set[str]:
    names: set[str] = set()
    try:
        count = int(app.Documents.Count)
        for i in range(count):
            try:
                # Photoshop COM は 0 始まりのことが多い
                names.add(str(app.Documents[i].Name))
            except Exception:  # noqa: BLE001
                try:
                    names.add(str(app.Documents[i + 1].Name))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return names


def open_via_shell(app: Any, image_path: str | Path, *, timeout_sec: float = 90.0) -> str:
    """
    Photoshop.exe / OS 関連付けでファイルを開く（スクリプト Open を使わない）。
    日本語パスは ASCII 一時コピーへ逃がす。
    """
    import os
    import subprocess
    import time

    src = Path(image_path).resolve()
    if not src.is_file():
        raise RuntimeError(f"ファイルが見つかりません: {src}")

    open_path = src if _is_ascii_path(src) else _copy_to_ascii_temp(src)
    before_names = _doc_names(app)
    before_count = -1
    try:
        before_count = int(app.Documents.Count)
    except Exception:  # noqa: BLE001
        pass

    exe = _photoshop_exe(app)
    launched = False
    if exe is not None:
        try:
            subprocess.Popen(
                [str(exe), str(open_path)],
                cwd=str(exe.parent),
                close_fds=True,
            )
            launched = True
        except Exception:  # noqa: BLE001
            launched = False
    if not launched:
        try:
            os.startfile(str(open_path))  # type: ignore[attr-defined]
            launched = True
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"ファイルを Photoshop で起動できませんでした: {open_path}\n（詳細: {exc}）"
            ) from exc

    expect = open_path.name
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(0.45)
        try:
            count = int(app.Documents.Count)
        except Exception:  # noqa: BLE001
            continue
        try:
            active = str(app.ActiveDocument.Name)
        except Exception:  # noqa: BLE001
            active = ""

        names = _doc_names(app)
        opened = False
        if before_count >= 0 and count > before_count:
            opened = True
        elif expect.lower() in {n.lower() for n in names - before_names}:
            opened = True
        elif active.lower() == expect.lower():
            opened = True
        elif Path(expect).stem.lower() in active.lower():
            opened = True

        if opened and active:
            return active

    raise RuntimeError(
        "Photoshop でファイルが開きませんでした（タイムアウト）。\n"
        f"対象: {open_path}\n"
        "Photoshop を前面にして、手動で同じファイルを開いてから\n"
        "「再適用（アクティブ）」を使ってください。"
    )


def _set_active_channel(doc: Any, channel_name: str) -> None:
    """RGB / Red / Green / Blue を ActiveChannels に設定する。"""
    ch = None
    # 名前参照
    try:
        ch = doc.Channels[channel_name]
    except Exception:  # noqa: BLE001
        ch = None
    if ch is None:
        # インデックス参照（0:RGB, 1:Red, 2:Green, 3:Blue）
        index_map = {"RGB": 0, "Red": 1, "Green": 2, "Blue": 3}
        idx = index_map.get(channel_name)
        if idx is not None:
            try:
                ch = doc.Channels[idx]
            except Exception:  # noqa: BLE001
                try:
                    ch = doc.Channels[idx + 1]
                except Exception:  # noqa: BLE001
                    ch = None
    if ch is None:
        raise RuntimeError(f"チャンネルを取得できません: {channel_name}")

    # 代入形式が環境で異なるため複数試行
    last_exc: Exception | None = None
    for setter in (
        lambda: setattr(doc, "ActiveChannels", [ch]),
        lambda: setattr(doc, "ActiveChannels", (ch,)),
        lambda: setattr(doc, "ActiveChannels", ch),
    ):
        try:
            setter()
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _points_for_com(points: list[tuple[float, float]]) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    for a, b in points:
        out.append((int(round(a)), int(round(b))))
    return tuple(out)


def apply_via_dom(
    app: Any,
    data: dict[str, Any],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
) -> tuple[str, list[str]]:
    """
    ActionDescriptor / DoJavaScript を使わず、DOM の AdjustLevels / AdjustCurves で適用。
    調整レイヤーではなく、複製ピクセルレイヤーへ破壊的適用する（互換性優先）。
    """
    if not use_curves and not use_levels:
        raise RuntimeError(
            "適用する補正が選ばれていません。\n"
            "レベル補正またはトーンカーブを有効にしてください。"
        )

    try:
        if int(app.Documents.Count) < 1:
            raise RuntimeError("開いているドキュメントがありません。")
        doc = app.ActiveDocument
        doc_name = str(doc.Name)
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "アクティブドキュメントを取得できませんでした。\n"
            f"（詳細: {exc}）"
        ) from exc

    try:
        mode = int(doc.Mode)
        if mode != 2:
            raise RuntimeError(
                f"ドキュメント「{doc_name}」は RGB モードではありません。\n"
                "イメージ → モード → RGB カラー に変換してから適用してください。"
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    # 背景のロック解除 → 複製レイヤーへ適用
    try:
        layer = doc.ActiveLayer
        try:
            if bool(layer.IsBackgroundLayer):
                layer.IsBackgroundLayer = False
        except Exception:  # noqa: BLE001
            pass
        dup = layer.Duplicate()
        try:
            dup.Name = "Auto Color Correct (DOM)"
        except Exception:  # noqa: BLE001
            pass
        try:
            doc.ActiveLayer = dup
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "レイヤーの複製に失敗しました。\n"
            f"（詳細: {exc}）"
        ) from exc

    created: list[str] = []
    channel_ids = (
        ("Rd  ", "Red"),
        ("Grn ", "Green"),
        ("Bl  ", "Blue"),
    )

    try:
        if use_levels:
            levels = normalize_levels_data(data)
            for ch_id, ch_name in channel_ids:
                black, white, gamma, out_b, out_w = levels[ch_id]
                _set_active_channel(doc, ch_name)
                doc.ActiveLayer.AdjustLevels(
                    int(black),
                    int(white),
                    float(gamma),
                    int(out_b),
                    int(out_w),
                )
            created.append("Auto Color Correct (Levels DOM)")

        if use_curves:
            curves = normalize_curve_data(data)
            for ch_id, ch_name in channel_ids:
                pts = _points_for_com(curves[ch_id])
                _set_active_channel(doc, ch_name)
                doc.ActiveLayer.AdjustCurves(pts)
            created.append("Auto Color Correct (Curves DOM)")

        # RGB に戻す
        try:
            _set_active_channel(doc, "RGB")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "DOM 補正の適用に失敗しました。\n"
            f"（詳細: {exc}）"
        ) from exc

    return doc_name, created


def open_document(app: Any, image_path: str | Path) -> str:
    """画像を Photoshop で開く（シェル起動優先、失敗時 JSX）。"""
    errors: list[str] = []
    try:
        return open_via_shell(app, image_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Shell: {exc}")

    path = Path(image_path).resolve()
    if not path.is_file():
        raise RuntimeError(f"ファイルが見つかりません: {path}")

    open_path = path if _is_ascii_path(path) else _copy_to_ascii_temp(path)
    fmt = _open_format_id(open_path)
    jp = _path_for_extendscript(open_path)
    script = (
        "#target photoshop\n"
        + _jsx_open_function()
        + f'ccOpenFile("{jp}", "{fmt}");\n'
        + "app.activeDocument.name;\n"
    )
    try:
        result = _run_jsx(app, script)
        return str(result or app.ActiveDocument.Name)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"JSX: {exc}")
        raise RuntimeError(
            "Photoshop でファイルを開けませんでした:\n"
            f"{path}\n\n"
            "回避策:\n"
            "① Photoshop で画像を手動で開く\n"
            "② 本ツールで「再適用（アクティブ）」を押す\n"
            f"（詳細: {' | '.join(errors)}）"
        ) from exc


def _friendly_com_error(exc: BaseException) -> RuntimeError:
    raw = str(exc).strip() or type(exc).__name__
    lower = raw.lower()
    if (
        "actiondescriptor" in lower
        or "actionreference" in lower
        or "actionlist" in lower
        or "クラス文字列" in raw
    ):
        return RuntimeError(
            "調整レイヤーの作成に失敗しました（COM クラス未登録）。\n"
            "・ドキュメントが RGB モードか確認してください\n"
            "・Photoshop を再起動して再試行してください"
        )
    if "rpc" in lower or "拒否" in raw or "rejected" in lower:
        return RuntimeError(
            "Photoshop との通信に失敗しました。\n"
            "Photoshop を前面にしてから、もう一度試してください。"
        )
    return RuntimeError(
        "調整レイヤーの作成に失敗しました。\n"
        "・Photoshop で RGB ドキュメントを開いているか確認してください\n"
        f"（詳細: {raw}）"
    )


def apply_correction_to_active_document(
    data: dict[str, Any],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
    curves_layer_name: str = LAYER_NAME_CURVES,
    levels_layer_name: str = LAYER_NAME_LEVELS,
) -> tuple[str, list[str]]:
    """
    アクティブドキュメントに補正を適用する。
    優先順: DOM → JSX → Action Manager COM
    """
    if not use_curves and not use_levels:
        raise RuntimeError(
            "適用する補正が選ばれていません。\n"
            "レベル補正またはトーンカーブを有効にしてください。"
        )

    app = get_photoshop_app()
    errors: list[str] = []

    # 1) DOM（この環境向け本命: ActionDescriptor / JSX 不要）
    try:
        return apply_via_dom(
            app, data, use_curves=use_curves, use_levels=use_levels
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"DOM: {exc}")

    # 2) JSX
    try:
        return apply_via_jsx(
            app,
            data,
            image_path=None,
            use_curves=use_curves,
            use_levels=use_levels,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"JSX: {exc}")

    try:
        doc_count = int(app.Documents.Count)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Photoshop のドキュメント情報を取得できませんでした。\n"
            "Photoshop を起動し直してから再試行してください。"
        ) from exc

    if doc_count < 1:
        raise RuntimeError(
            "Photoshop に開いているドキュメントがありません。\n"
            "補正したいファイルを開いてアクティブにしてから再実行してください。"
        )

    try:
        doc = app.ActiveDocument
        doc_name = str(doc.Name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "アクティブドキュメントを取得できませんでした。\n"
            "Photoshop で対象ファイルをクリックしてから再試行してください。"
        ) from exc

    try:
        mode = int(doc.Mode)
        if mode != 2:
            raise RuntimeError(
                f"ドキュメント「{doc_name}」は RGB モードではありません。\n"
                "イメージ → モード → RGB カラー に変換してから適用してください。"
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    created: list[str] = []
    try:
        if use_levels:
            levels = normalize_levels_data(data)
            create_levels_adjustment_layer(
                app, levels, layer_name=LAYER_NAME_LEVELS_TONAL
            )
            created.append(LAYER_NAME_LEVELS_TONAL)
        if use_curves:
            curves = normalize_curve_data(data)
            create_curves_adjustment_layer(
                app, curves, layer_name=LAYER_NAME_CURVES_CAST
            )
            created.append(LAYER_NAME_CURVES_CAST)
        return doc_name, created
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"{_friendly_com_error(exc)}\n"
            f"（試行: {' | '.join(errors)}）"
        ) from exc


def apply_correction_to_image_file(
    image_path: str | Path,
    data: dict[str, Any],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
) -> tuple[str, list[str]]:
    """
    画像を開いてから補正を適用する。
    優先: シェルで開く → DOM 適用（スクリプト Open を避ける）
    """
    app = get_photoshop_app()
    errors: list[str] = []

    # 1) シェル Open + DOM 適用
    try:
        open_via_shell(app, image_path)
        return apply_via_dom(
            app, data, use_curves=use_curves, use_levels=use_levels
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Shell+DOM: {exc}")

    # 2) シェル Open + JSX 適用（open なし）
    try:
        open_via_shell(app, image_path)
        return apply_via_jsx(
            app,
            data,
            image_path=None,
            use_curves=use_curves,
            use_levels=use_levels,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Shell+JSX: {exc}")

    # 3) JSX で open+apply
    try:
        return apply_via_jsx(
            app,
            data,
            image_path=image_path,
            use_curves=use_curves,
            use_levels=use_levels,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"JSX: {exc}")

    raise RuntimeError(
        "Photoshop への適用に失敗しました。\n"
        f"{Path(image_path)}\n\n"
        "回避策（確実）:\n"
        "① 本ツールで「解析のみ」を実行\n"
        "② Photoshop で画像を手動で開く\n"
        "③ 「再適用（アクティブ）」を押す\n\n"
        f"（詳細: {' | '.join(errors[-2:])}）"
    )


def apply_from_json(
    json_path: str | Path,
    *,
    use_curves: bool = True,
    use_levels: bool = True,
) -> tuple[str, list[str]]:
    data = load_json(json_path)
    return apply_correction_to_active_document(
        data, use_curves=use_curves, use_levels=use_levels
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="JSON の補正値で Photoshop に Levels / Curves 調整レイヤーを作成"
    )
    parser.add_argument("json", help="correction.json のパス")
    parser.add_argument(
        "--levels-only",
        action="store_true",
        help="レベル補正のみ適用",
    )
    parser.add_argument(
        "--curves-only",
        action="store_true",
        help="トーンカーブ（中間かぶり）のみ適用",
    )
    args = parser.parse_args(argv)

    use_curves = True
    use_levels = True
    if args.levels_only and args.curves_only:
        print("エラー: --levels-only と --curves-only は同時に指定できません。", file=sys.stderr)
        return 1
    if args.levels_only:
        use_curves = False
    if args.curves_only:
        use_levels = False

    try:
        doc_name, created = apply_from_json(
            args.json, use_curves=use_curves, use_levels=use_levels
        )
    except Exception as exc:  # noqa: BLE001
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    print(f"適用しました: {doc_name} ← {args.json}")
    print("作成レイヤー: " + ", ".join(created))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
