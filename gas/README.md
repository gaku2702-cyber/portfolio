# お問い合わせフォーム（Google Apps Script）

送信先: **smartdtp.studio.works@gmail.com**

## 重要: GAS を必ず再デプロイしてください

フォームが「通信エラー」「送信失敗」になる主な原因は、**Google 側のスクリプトが未設定・古いまま**であることです。

1. [Google Apps Script](https://script.google.com/) を開く
2. ポートフォリオ用プロジェクトを開く（または新規作成）
3. エディタのコードを **`contact-form.gs` の内容すべて** に置き換える
4. **デプロイ** → **新しいデプロイ**（初回）または **デプロイを管理** → 鉛筆 → **バージョン: 新規**（更新時）
   - 種類: **ウェブアプリ**
   - 実行ユーザー: **自分**
   - アクセスできるユーザー: **全員**
5. 表示された **ウェブアプリ URL** を `index.html` の `GAS_URL` に貼り付けて push

### 動作確認

ブラウザで次の URL を開き、`success` または `ok` と表示されればデプロイ成功です。

```
（あなたの GAS URL）?test=1
```

`スクリプト関数が見つかりません: doGet` と出る場合は、コード未反映またはデプロイ未更新です。

## サイト側の仕組み

`index.html` は **hidden iframe への form POST** で GAS に送信します（fetch + JSON は CORS で失敗しやすいため）。
