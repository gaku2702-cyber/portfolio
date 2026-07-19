"""カラー補正ツール GUI（ドロップ → Photoshop → PSD 保存）。"""

from __future__ import annotations

import queue
import tempfile
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .analyze import analyze_image, save_json
from .apply_local import apply_correction_to_file
from .apply_psd import (
    detect_photoshop,
    ensure_photoshop_started,
    export_psds_with_adjustment_layers,
)

NAVY = "#1B3264"
BG = "#F3F4F6"
TEXT = "#232323"
SUB = "#6B7280"
DROP_BG = "#E8EDF5"
DROP_ACTIVE = "#D5E0F0"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
IMAGE_TYPES = [
    ("画像ファイル", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp"),
    ("すべて", "*.*"),
]


def _decode_drop_path(raw: Any) -> str:
    """windnd は bytes(cp932/mbcs) で渡すことが多い。"""
    if isinstance(raw, bytes):
        for enc in ("cp932", "mbcs", "utf-8"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _log_drop_error(exc: BaseException) -> Path | None:
    try:
        path = Path(tempfile.gettempdir()) / "ColorCorrect_drop_error.txt"
        path.write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
        return path
    except Exception:  # noqa: BLE001
        return None


class ColorCorrectApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("カラー補正ツール")
        self.geometry("640x560")
        self.minsize(480, 480)
        self.configure(bg=BG)

        self.image_paths: list[Path] = []
        self.image_path: Path | None = None
        self.result: dict[str, Any] | None = None
        self._busy = False
        self._drop_queue: queue.Queue[list[str]] = queue.Queue()
        self._ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.var_curves = tk.BooleanVar(value=True)
        self.var_levels = tk.BooleanVar(value=True)

        self._build_ui()
        self._hook_drag_drop()
        self._update_photoshop_status()
        # メインスレッドだけで Tk を更新する
        self.after(80, self._poll_queues)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=NAVY, height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header,
            text="カラー補正ツール",
            bg=NAVY,
            fg="white",
            font=("Yu Gothic UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=12)

        body = tk.Frame(self, bg=BG, padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        self.drop_frame = tk.Frame(
            body,
            bg=DROP_BG,
            highlightbackground=NAVY,
            highlightthickness=2,
            padx=16,
            pady=28,
        )
        self.drop_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.drop_title = tk.Label(
            self.drop_frame,
            text="ここに写真をドロップ",
            bg=DROP_BG,
            fg=NAVY,
            font=("Yu Gothic UI", 16, "bold"),
        )
        self.drop_title.pack(pady=(8, 4))

        self.drop_sub = tk.Label(
            self.drop_frame,
            text=(
                "ドロップすると自動で処理します\n"
                "① Photoshop 起動  →  ② 写真を開く  →  ③ 色補正  →  ④ PSD 保存"
            ),
            bg=DROP_BG,
            fg=TEXT,
            font=("Yu Gothic UI", 10),
            justify=tk.CENTER,
        )
        self.drop_sub.pack(pady=(0, 12))

        btn_row = tk.Frame(self.drop_frame, bg=DROP_BG)
        btn_row.pack()
        self.btn_browse = ttk.Button(
            btn_row, text="またはファイルを選ぶ…", command=self._pick_images
        )
        self.btn_browse.pack(side=tk.LEFT, padx=4)
        self.btn_clear = ttk.Button(btn_row, text="クリア", command=self._clear_files)
        self.btn_clear.pack(side=tk.LEFT, padx=4)

        list_frame = tk.Frame(body, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 8))
        self.file_list = tk.Listbox(
            list_frame,
            height=5,
            font=("Yu Gothic UI", 9),
            activestyle="dotbox",
        )
        scroll = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.file_list.yview
        )
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        opt = tk.Frame(body, bg=BG)
        opt.pack(fill=tk.X, pady=(0, 8))
        tk.Checkbutton(
            opt,
            text="レベル補正（HL/SH）",
            variable=self.var_levels,
            bg=BG,
            fg=TEXT,
            activebackground=BG,
            font=("Yu Gothic UI", 9),
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            opt,
            text="トーンカーブ（中間かぶり）",
            variable=self.var_curves,
            bg=BG,
            fg=TEXT,
            activebackground=BG,
            font=("Yu Gothic UI", 9),
        ).pack(side=tk.LEFT, padx=(16, 0))

        self.btn_start = tk.Button(
            body,
            text="選択中の写真を処理する",
            command=self._on_start,
            bg=NAVY,
            fg="white",
            activebackground="#152850",
            activeforeground="white",
            font=("Yu Gothic UI", 11, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            pady=10,
        )
        self.btn_start.pack(fill=tk.X, pady=(0, 8))

        self.summary_var = tk.StringVar(
            value="写真をドロップするか、ファイルを選んでください。"
        )
        tk.Label(
            body,
            textvariable=self.summary_var,
            bg=BG,
            fg=TEXT,
            font=("Yu Gothic UI", 9),
            justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X)

        self.status_var = tk.StringVar(value="準備完了 — 写真をドロップしてください")
        status = tk.Label(
            self,
            textvariable=self.status_var,
            bg="#F8F9FB",
            fg=SUB,
            anchor="w",
            font=("Yu Gothic UI", 9),
            padx=12,
            pady=6,
        )
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _update_photoshop_status(self) -> None:
        ok, msg = detect_photoshop()
        if ok:
            self._set_status(f"{msg} — 写真をドロップしてください")
        else:
            self._set_status(
                f"{msg} — 解析/JPEG は可能。PSD には Photoshop が必要です"
            )

    def _hook_drag_drop(self) -> None:
        """Windows ファイルドロップを有効化（コールバック内では Tk を触らない）。"""
        try:
            import windnd  # type: ignore[import-untyped]
        except ImportError:
            self.drop_sub.configure(
                text=(
                    "（ドロップ機能未導入: pip install windnd）\n"
                    "「ファイルを選ぶ…」から処理できます\n"
                    "① Photoshop 起動  →  ② 写真を開く  →  ③ 色補正  →  ④ PSD 保存"
                )
            )
            return

        def on_drop(files: Any) -> None:
            # ※ ここは別スレッド。Tk / after は絶対に呼ばない
            try:
                raw_list = list(files) if files is not None else []
                paths = [_decode_drop_path(f) for f in raw_list]
                self._drop_queue.put(paths)
            except Exception as exc:  # noqa: BLE001
                _log_drop_error(exc)

        try:
            # HWND を渡す方が安定する場合がある
            hwnd = int(self.winfo_id())
            windnd.hook_dropfiles(hwnd, func=on_drop)
        except Exception:
            windnd.hook_dropfiles(self, func=on_drop)

    def _poll_queues(self) -> None:
        # ドロップ
        try:
            while True:
                paths = self._drop_queue.get_nowait()
                try:
                    self._handle_dropped_paths(paths)
                except Exception as exc:  # noqa: BLE001
                    log = _log_drop_error(exc)
                    detail = f"\n\nログ: {log}" if log else ""
                    self._set_busy(False)
                    self._set_status("ドロップ処理でエラー")
                    messagebox.showerror("ドロップエラー", f"{exc}{detail}")
        except queue.Empty:
            pass

        # ワーカー → UI
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "status":
                    self._set_status(str(payload))
                elif kind == "finish":
                    done, errors, jsx_path = payload
                    self._finish_pipeline(done, errors, jsx_path)
                elif kind == "fail":
                    self._set_busy(False)
                    self._set_status(f"処理エラー: {payload}")
                    messagebox.showerror("処理エラー", str(payload))
        except queue.Empty:
            pass

        self.after(50, self._poll_queues)

    def _ui(self, kind: str, payload: Any = None) -> None:
        self._ui_queue.put((kind, payload))

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_start.configure(state=state)
        self.btn_browse.configure(state=state)
        self.btn_clear.configure(state=state)

    def _is_image(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in IMAGE_EXTS

    def _add_paths(self, paths: list[Path], *, replace: bool = False) -> int:
        added = 0
        if replace:
            self.image_paths = []
        existing = {p.resolve() for p in self.image_paths}
        for p in paths:
            try:
                rp = p.resolve()
            except Exception:  # noqa: BLE001
                continue
            if not self._is_image(rp):
                continue
            if rp in existing:
                continue
            self.image_paths.append(rp)
            existing.add(rp)
            added += 1
        self._refresh_file_list()
        return added

    def _refresh_file_list(self) -> None:
        self.file_list.delete(0, tk.END)
        for p in self.image_paths:
            self.file_list.insert(tk.END, p.name)
        n = len(self.image_paths)
        if n == 0:
            self.image_path = None
            self.summary_var.set("写真をドロップするか、ファイルを選んでください。")
        else:
            self.image_path = self.image_paths[0]
            self.summary_var.set(f"{n} 枚の写真がキューに入りました。")

    def _clear_files(self) -> None:
        if self._busy:
            return
        self.image_paths = []
        self.image_path = None
        self.result = None
        self._refresh_file_list()
        self._set_status("クリアしました — 写真をドロップしてください")

    def _pick_images(self) -> None:
        if self._busy:
            return
        paths = filedialog.askopenfilenames(
            title="処理する画像を選択（複数可）",
            filetypes=IMAGE_TYPES,
        )
        if not paths:
            return
        n = self._add_paths([Path(p) for p in paths], replace=True)
        self._set_status(f"{n} ファイルを選択しました")
        if n:
            self.after(100, self._on_start)

    def _handle_dropped_paths(self, path_strs: list[str]) -> None:
        if self._busy:
            self._set_status("処理中のためドロップを無視しました")
            return
        paths: list[Path] = []
        for s in path_strs:
            p = Path(s.strip().strip('"'))
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if self._is_image(child):
                        paths.append(child)
            else:
                paths.append(p)
        n = self._add_paths(paths, replace=True)
        if n == 0:
            messagebox.showwarning(
                "画像なし",
                "ドロップされたファイルに対応画像がありません。\n"
                "（jpg / png / tif / bmp / webp）",
            )
            return
        self.drop_frame.configure(bg=DROP_ACTIVE)
        self.after(300, lambda: self.drop_frame.configure(bg=DROP_BG))
        self._set_status(f"{n} 枚をドロップしました — 処理を開始します")
        # UI 更新後に開始（即時だと落ちやすい）
        self.after(150, self._on_start)

    def _correction_flags(self) -> tuple[bool, bool] | None:
        use_curves = bool(self.var_curves.get())
        use_levels = bool(self.var_levels.get())
        if not use_curves and not use_levels:
            messagebox.showwarning(
                "補正未選択",
                "「レベル補正」または「トーンカーブ」にチェックを入れてください。",
            )
            return None
        return use_curves, use_levels

    def _on_start(self) -> None:
        if self._busy:
            return
        if not self.image_paths:
            messagebox.showwarning(
                "画像未選択",
                "写真をドロップするか、「ファイルを選ぶ…」で選んでください。",
            )
            return
        flags = self._correction_flags()
        if flags is None:
            return
        self._run_pipeline_async(flags[0], flags[1])

    def _default_json_path(self, image_path: Path) -> Path:
        return image_path.with_name(image_path.stem + "_correction.json")

    def _run_pipeline_async(self, use_curves: bool, use_levels: bool) -> None:
        self._set_busy(True)
        paths = list(self.image_paths)
        self._set_status(f"処理開始（{len(paths)} 枚）…")
        thread = threading.Thread(
            target=self._pipeline_worker,
            kwargs={
                "paths": paths,
                "use_curves": use_curves,
                "use_levels": use_levels,
            },
            daemon=True,
        )
        thread.start()

    def _pipeline_worker(
        self,
        paths: list[Path],
        use_curves: bool,
        use_levels: bool,
    ) -> None:
        errors: list[str] = []
        analyzed: list[tuple[Path, dict[str, Any]]] = []
        try:
            self._ui("status", "① Photoshop を起動しています…")
            try:
                ensure_photoshop_started()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Photoshop 起動: {exc}")

            for i, path in enumerate(paths, start=1):
                self._ui("status", f"解析中… ({i}/{len(paths)}) {path.name}")
                try:
                    result = analyze_image(path)
                    save_json(result, self._default_json_path(path))
                    analyzed.append((path, result))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{path.name}: 解析失敗 — {exc}")

            if not analyzed:
                raise RuntimeError("解析に成功した画像がありません。")

            self._ui(
                "status",
                "②③④⑤ 写真を開き、色補正して PSD 保存しています…",
            )

            done, psd_errors, jsx_path = export_psds_with_adjustment_layers(
                analyzed,
                use_curves=use_curves,
                use_levels=use_levels,
                keep_open=True,
            )
            errors.extend(psd_errors)

            done_set = {p.resolve() for p in done}
            for path, data in analyzed:
                expected = path.with_name(f"{path.stem}_corrected.psd").resolve()
                if expected in done_set:
                    continue
                try:
                    jpg = apply_correction_to_file(
                        path, data, use_curves=use_curves, use_levels=use_levels
                    )
                    errors.append(
                        f"{path.name}: PSD 未作成のため JPEG を保存 → {jpg.name}"
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{path.name}: JPEG 保存も失敗 — {exc}")

            if analyzed:
                self.result = analyzed[0][1]
                self.image_path = analyzed[0][0]

            self._ui("finish", (done, errors, jsx_path))
        except Exception as exc:  # noqa: BLE001
            _log_drop_error(exc)
            self._ui("fail", str(exc))

    def _finish_pipeline(
        self,
        done: list[Path],
        errors: list[str],
        jsx_path: Path | None,
    ) -> None:
        self._set_busy(False)
        jpg_notes = [e for e in errors if "JPEG" in e]
        hard_errors = [e for e in errors if "JPEG" not in e]

        self._set_status(
            f"完了: PSD {len(done)} 件"
            + (f" / JPEG フォールバック {len(jpg_notes)} 件" if jpg_notes else "")
        )
        if done:
            self.summary_var.set(
                f"PSD 保存完了（{len(done)} 件）\n"
                + "\n".join(p.name for p in done[:5])
            )
        elif jpg_notes:
            self.summary_var.set(
                "PSD 未作成 — JPEG フォールバックを保存しました\n"
                + "\n".join(jpg_notes[:3])
            )

        msg = f"PSD 成功 {len(done)} 件\n"
        if done:
            msg += "\n【出力 PSD】\n" + "\n".join(f"・{p}" for p in done[:20])
            if len(done) > 20:
                msg += f"\n…他 {len(done) - 20} 件"
        if jpg_notes:
            msg += "\n\n【JPEG フォールバック】\n" + "\n".join(
                f"・{x}" for x in jpg_notes[:15]
            )
        if hard_errors:
            msg += "\n\n【詳細】\n" + "\n".join(f"・{x}" for x in hard_errors[:20])
        if jsx_path is not None and not done:
            msg += (
                f"\n\n手動実行用スクリプト:\n{jsx_path}\n"
                "Photoshop → ファイル → スクリプト → 参照…\n"
                "ログ: %TEMP%\\ColorCorrect_drop_error.txt"
            )
        if done:
            messagebox.showinfo("処理結果", msg)
        else:
            messagebox.showwarning("処理結果", msg)


def run() -> None:
    try:
        import pythoncom  # type: ignore[import-untyped]

        pythoncom.CoInitialize()
    except Exception:  # noqa: BLE001
        pass
    app = ColorCorrectApp()
    app.mainloop()


if __name__ == "__main__":
    run()
