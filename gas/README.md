# お問い合わせフォーム（Google Apps Script）

フォーム送信先: **smartdtp.studio.works@gmail.com**

## 初回セットアップ / 宛先変更時

1. [Google Apps Script](https://script.google.com/) で新規プロジェクトを作成
2. `contact-form.gs` の内容を貼り付け（`RECIPIENT_EMAIL` を確認）
3. **デプロイ** → **新しいデプロイ** → 種類: **ウェブアプリ**
   - 実行ユーザー: **自分**
   - アクセス: **全員**
4. 表示された **ウェブアプリ URL** を `index.html` の `gasUrl` に貼り付け
5. 既存デプロイの更新時は **デプロイを管理** → 鉛筆アイコン → **バージョン: 新規** → **デプロイ**

## 動作確認

ブラウザでフォームからテスト送信し、`smartdtp.studio.works@gmail.com` に届くことを確認してください。
