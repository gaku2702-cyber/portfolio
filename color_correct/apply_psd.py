"""調整レイヤー付き PSD を書き出す（Photoshop JSX / exe 起動）。"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from .apply_ps import (
    LAYER_NAME_CURVES_CAST,
    LAYER_NAME_LEVELS_TONAL,
    _copy_to_ascii_temp,
    _is_ascii_path,
    _js_escape,
    _jsx_curves_function,
    _jsx_dir,
    _jsx_levels_functions,
    _jsx_open_function,
    _open_format_id,
    _path_for_extendscript,
    _photoshop_exe,
    get_photoshop_app,
    normalize_curve_data,
    normalize_levels_data,
)


def _default_psd_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.stem}_corrected.psd")


def _find_photoshop_exe_only() -> Path | None:
    """COM なしで Photoshop.exe を探す。"""
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
            matches = sorted(
                adobe.glob("Adobe Photoshop */Photoshop.exe"), reverse=True
            )
        except Exception:  # noqa: BLE001
            matches = []
        if matches:
            return matches[0]
    return None


def _find_photoshop_exe() -> Path | None:
    try:
        app = get_photoshop_app()
        exe = _photoshop_exe(app)
        if exe is not None:
            return exe
    except Exception:  # noqa: BLE001
        pass
    return _find_photoshop_exe_only()


def detect_photoshop() -> tuple[bool, str]:
    """
    起動時チェック用。Photoshop.exe の有無を返す。
    Returns: (検出できたか, 表示用メッセージ)
    """
    exe = _find_photoshop_exe_only()
    if exe is None:
        return False, "Photoshop: 未検出（PSD 本線は不可・JPEG フォールバック可）"
    # フォルダ名だけ短く出す
    try:
        label = exe.parent.name
    except Exception:  # noqa: BLE001
        label = "Photoshop"
    return True, f"Photoshop: 検出済み（{label}）"


def ensure_photoshop_started(*, wait_sec: float = 45.0) -> None:
    """
    Photoshop を起動し、操作可能になるまで待つ。
    すでに起動済みならそのまま接続する。
    """
    # まず COM で既存／起動を試す
    try:
        get_photoshop_app()
        return
    except Exception:  # noqa: BLE001
        pass

    exe = _find_photoshop_exe_only()
    if exe is None:
        raise RuntimeError(
            "Photoshop.exe が見つかりません。\n"
            "Adobe Photoshop（デスクトップ版）をインストールしてください。"
        )

    subprocess.Popen([str(exe)], cwd=str(exe.parent), close_fds=True)
    deadline = time.time() + wait_sec
    last_err: Exception | None = None
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            get_photoshop_app()
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    detail = f"（詳細: {last_err}）" if last_err else ""
    raise RuntimeError(
        "Photoshop の起動待機がタイムアウトしました。\n"
        "Photoshop を手動で起動・ログインしてから再実行してください。\n"
        f"{detail}"
    )


def _jsx_save_psd_function() -> str:
    return r"""
function ccSavePsd(path) {
  var f = new File(path);
  var parent = f.parent;
  if (parent && !parent.exists) {
    parent.create();
  }
  var opt = new PhotoshopSaveOptions();
  opt.layers = true;
  opt.embedColorProfile = true;
  opt.alphaChannels = true;
  opt.annotations = false;
  opt.spotColors = false;
  app.activeDocument.saveAs(f, opt, true, Extension.LOWERCASE);
}

function ccCloseNoSave() {
  try {
    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
  } catch (e) {}
}
"""


def _build_one_job_body(
    *,
    open_path: Path,
    save_path: Path,
    use_levels: bool,
    use_curves: bool,
    levels: dict[str, tuple[int, int, float, int, int]] | None,
    curves: dict[str, list[tuple[float, float]]] | None,
    keep_open: bool = True,
) -> str:
    jp_open = _path_for_extendscript(open_path)
    jp_save = _path_for_extendscript(save_path)
    fmt = _open_format_id(open_path)
    parts = [
        f'ccOpenFile("{jp_open}", "{fmt}");\n',
        "if (!app.documents.length) { throw new Error('No document after open'); }\n",
        "if (app.activeDocument.mode != DocumentMode.RGB) {\n"
        "  throw new Error('Document is not RGB');\n"
        "}\n",
    ]
    if use_levels and levels is not None:
        from .apply_ps import _levels_to_js_object

        parts.append(
            f"ccCreateLevels({_levels_to_js_object(levels)}, "
            f'"{_js_escape(LAYER_NAME_LEVELS_TONAL)}");\n'
        )
    if use_curves and curves is not None:
        from .apply_ps import _curves_to_js_object

        parts.append(
            f"ccCreateCurves({_curves_to_js_object(curves)}, "
            f'"{_js_escape(LAYER_NAME_CURVES_CAST)}");\n'
        )
    parts.append(f'ccSavePsd("{jp_save}");\n')
    if not keep_open:
        parts.append("ccCloseNoSave();\n")
    return "".join(parts)


def build_batch_psd_jsx(
    jobs: list[tuple[Path, Path, dict[str, Any]]],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
    keep_open: bool = True,
) -> Path:
    """
    複数画像を開き、調整レイヤーを付けて PSD 保存する JSX を書く。
    jobs: (open用パス, 保存PSDパス, 解析data)
    """
    import uuid

    if not jobs:
        raise ValueError("jobs が空です")

    chunks: list[str] = [
        "#target photoshop\n",
        "app.bringToFront();\n",
        "app.displayDialogs = DialogModes.NO;\n",
        _jsx_open_function(),
        _jsx_levels_functions(),
        _jsx_curves_function(),
        _jsx_save_psd_function(),
        "var ccErrors = [];\n",
        "var ccOk = 0;\n",
    ]

    for i, (open_path, save_path, data) in enumerate(jobs):
        levels = normalize_levels_data(data) if use_levels else None
        curves = normalize_curve_data(data) if use_curves else None
        body = _build_one_job_body(
            open_path=open_path,
            save_path=save_path,
            use_levels=use_levels,
            use_curves=use_curves,
            levels=levels,
            curves=curves,
            keep_open=keep_open,
        )
        chunks.append(
            "try {\n"
            f"{body}"
            "  ccOk++;\n"
            "} catch (e) {\n"
            f'  ccErrors.push("job{i}: " + e);\n'
            "  try { ccCloseNoSave(); } catch (e2) {}\n"
            "}\n"
        )

    chunks.append(
        'if (ccErrors.length) {\n'
        '  alert("ColorCorrect PSD: 成功 " + ccOk + " / 失敗 " + ccErrors.length'
        ' + "\\n" + ccErrors.join("\\n"));\n'
        "} else {\n"
        '  alert("ColorCorrect PSD: 完了 " + ccOk + " 件\\n'
        '調整レイヤー付き PSD を保存しました");\n'
        "}\n"
        "ccOk;\n"
    )

    jsx_path = _jsx_dir() / f"batch_psd_{uuid.uuid4().hex}.jsx"
    script = "".join(chunks)
    jsx_path.write_bytes(b"\xef\xbb\xbf" + script.encode("utf-8"))
    return jsx_path


def run_jsx_via_photoshop_exe(jsx_path: Path) -> None:
    """Photoshop.exe に JSX を渡して実行（COM DoJavaScript を使わない）。"""
    exe = _find_photoshop_exe()
    if exe is None:
        raise RuntimeError(
            "Photoshop.exe が見つかりません。\n"
            "Photoshop をインストールするか、手動で次のスクリプトを実行してください:\n"
            f"{jsx_path}"
        )
    subprocess.Popen(
        [str(exe), str(jsx_path.resolve())],
        cwd=str(exe.parent),
        close_fds=True,
    )


def wait_for_files(
    paths: list[Path],
    *,
    timeout_sec: float,
    poll_sec: float = 0.8,
) -> tuple[list[Path], list[Path]]:
    """存在する／しないファイルを分けて返す。"""
    pending = {p.resolve() for p in paths}
    done: set[Path] = set()
    deadline = time.time() + timeout_sec
    while pending and time.time() < deadline:
        for p in list(pending):
            if p.is_file() and p.stat().st_size > 0:
                pending.remove(p)
                done.add(p)
        if pending:
            time.sleep(poll_sec)
    return sorted(done), sorted(pending)


def prepare_open_path(image_path: Path) -> Path:
    """日本語パスは ASCII 一時コピーして開く。"""
    src = image_path.resolve()
    if _is_ascii_path(src):
        return src
    return _copy_to_ascii_temp(src)


def export_psds_with_adjustment_layers(
    items: list[tuple[Path, dict[str, Any]]],
    *,
    use_curves: bool = True,
    use_levels: bool = True,
    timeout_per_file_sec: float = 90.0,
    keep_open: bool = True,
) -> tuple[list[Path], list[str], Path]:
    """
    解析済み画像リストから調整レイヤー付き PSD を書き出す。

    Returns:
        (成功したPSDパス, エラーメッセージ, 実行したJSXパス)
    """
    if not use_curves and not use_levels:
        raise RuntimeError("レベル補正またはトーンカーブを有効にしてください。")

    jobs: list[tuple[Path, Path, dict[str, Any]]] = []
    expected: list[Path] = []
    for image_path, data in items:
        src = Path(image_path).resolve()
        if not src.is_file():
            raise RuntimeError(f"ファイルが見つかりません: {src}")
        open_path = prepare_open_path(src)
        psd_path = _default_psd_path(src)
        # 既存があると wait が即座に成功してしまうので消す
        try:
            if psd_path.is_file():
                psd_path.unlink()
        except Exception:  # noqa: BLE001
            pass
        jobs.append((open_path, psd_path, data))
        expected.append(psd_path)

    jsx_path = build_batch_psd_jsx(
        jobs,
        use_curves=use_curves,
        use_levels=use_levels,
        keep_open=keep_open,
    )

    # COM は環境によって無言失敗するため、短時間待ってから exe 起動へフォールバック
    try:
        ensure_photoshop_started()
        app = get_photoshop_app()
        app.DoJavaScriptFile(str(jsx_path.resolve()))
        done_quick, missing_quick = wait_for_files(
            expected, timeout_sec=8.0, poll_sec=0.5
        )
        if not missing_quick:
            return done_quick, [], jsx_path
    except Exception:  # noqa: BLE001
        pass

    run_jsx_via_photoshop_exe(jsx_path)

    timeout = max(90.0, timeout_per_file_sec * max(1, len(expected)))
    done, missing = wait_for_files(expected, timeout_sec=timeout)

    errors: list[str] = []
    for p in missing:
        errors.append(f"{p.name}: PSD が作成されませんでした")

    if not done and missing:
        errors.append(
            "Photoshop でスクリプトが実行されていない可能性があります。\n"
            "次のファイルを Photoshop の\n"
            "ファイル → スクリプト → 参照… で実行してください:\n"
            f"{jsx_path}"
        )

    return done, errors, jsx_path


def export_active_document_psd(
    data: dict[str, Any],
    save_path: str | Path,
    *,
    use_curves: bool = True,
    use_levels: bool = True,
) -> Path:
    """アクティブドキュメントに調整レイヤーを付けて PSD 保存。"""
    import uuid

    from .apply_ps import _curves_to_js_object, _levels_to_js_object

    save_path = Path(save_path).resolve()
    levels = normalize_levels_data(data) if use_levels else None
    curves = normalize_curve_data(data) if use_curves else None

    chunks = [
        "#target photoshop\n",
        "app.displayDialogs = DialogModes.NO;\n",
        _jsx_levels_functions(),
        _jsx_curves_function(),
        _jsx_save_psd_function(),
        "if (!app.documents.length) { throw new Error('No active document'); }\n",
    ]
    if use_levels and levels is not None:
        chunks.append(
            f"ccCreateLevels({_levels_to_js_object(levels)}, "
            f'"{_js_escape(LAYER_NAME_LEVELS_TONAL)}");\n'
        )
    if use_curves and curves is not None:
        chunks.append(
            f"ccCreateCurves({_curves_to_js_object(curves)}, "
            f'"{_js_escape(LAYER_NAME_CURVES_CAST)}");\n'
        )
    chunks.append(f'ccSavePsd("{_path_for_extendscript(save_path)}");\n')
    chunks.append("app.activeDocument.name;\n")

    jsx_path = _jsx_dir() / f"active_psd_{uuid.uuid4().hex}.jsx"
    jsx_path.write_bytes(b"\xef\xbb\xbf" + "".join(chunks).encode("utf-8"))

    try:
        if save_path.is_file():
            save_path.unlink()
    except Exception:  # noqa: BLE001
        pass

    try:
        app = get_photoshop_app()
        app.DoJavaScriptFile(str(jsx_path.resolve()))
    except Exception:
        run_jsx_via_photoshop_exe(jsx_path)

    done, _missing = wait_for_files([save_path], timeout_sec=120.0)
    if not done:
        raise RuntimeError(
            "アクティブドキュメントの PSD 保存に失敗しました。\n"
            "Photoshop で次を実行してください:\n"
            f"{jsx_path}"
        )
    return save_path
