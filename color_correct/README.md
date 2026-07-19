# カラー補正ツール

写真をドロップすると Photoshop を起動し、レベル補正・中間かぶりトーンカーブ（調整レイヤー）を追加して **PSD 保存**する Windows 向けアプリです。

解析はすべてローカル（OpenCV）で完結します。クラウド AI / API キーは不要です。

## ポートフォリオ掲載

- 体験デモ（ブラウザ）: リポジトリ直下の [`color-correct-demo.html`](../color-correct-demo.html)
- トップの「提案・開発実績」から同デモへリンクしています

## 動作環境

| 項目 | 要件 |
|------|------|
| OS | Windows 10 / 11 |
| Photoshop | Adobe Photoshop（デスクトップ版） |
| 開発実行時 | Python 3.10 以上推奨 |

## 使い方（GUI）

1. 写真をアプリへ **ドロップ**（複数可）
2. 自動で次を実行
   1. Photoshop 起動
   2. 写真を開く
   3. 色補正（調整レイヤー）
   4. 同じフォルダに `*_corrected.psd` を保存
3. 「ファイルを選ぶ…」でも同じ処理が始まります

### 起動方法（開発）

```powershell
cd color_correct
python -m pip install -r requirements.txt
cd ..
python -m color_correct
```

### CLI（任意）

```powershell
# 解析のみ
python -m color_correct.analyze path\to\photo.jpg -o correction.json

# Photoshop 適用のみ（要: アクティブドキュメント）
python -m color_correct.apply_ps correction.json
```

## 解析・補正の概要

1. 輝度ヒストグラムでシャドー／ハイライト帯を決め、領域の平均 RGB を測色
2. Lab で中間明度のニュートラルグレーを推定
3. Photoshop に調整レイヤーを追加して PSD 保存

**役割分担**

- レベル補正 `Auto Levels (HL/SH)`: ハイライト／シャドー
  - 出力黒 ≈ C95 M88 Y88 K70（簡易換算で R4 G9 B9）
  - 出力白 = 245
- トーンカーブ `Auto Curves (Cast)`: 中間調のかぶり取りのみ（端点固定）

## 配布用ビルド

```powershell
cd color_correct
.\build.ps1
```

出力:

- `color_correct/dist/ColorCorrect/` … 実行フォルダ
- `color_correct/dist/ColorCorrect_dist.zip` … 配布 ZIP

利用先では ZIP を展開し `ColorCorrect.exe` を起動します（Python 不要、Photoshop は必要）。  
詳細は同梱の `haifu_tebiki.txt` / `haifu_guide.txt` を参照してください。
