/**
 * Portfolio contact form backend.
 * Deploy: Deploy > New deployment > Web app
 *   Execute as: Me
 *   Who has access: Anyone
 * Paste the Web app URL into index.html (gasUrl).
 */

const RECIPIENT_EMAIL = 'smartdtp.studio.works@gmail.com';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const name = sanitize_(data.name);
    const company = sanitize_(data.company);
    const email = sanitize_(data.email);
    const type = sanitize_(data.type);
    const message = sanitize_(data.message);

    if (!name || !email || !message) {
      return jsonResponse_({ status: 'error', message: 'missing fields' });
    }

    const subject = '[Portfolio] ' + (type || 'お問い合わせ') + ' — ' + name;
    const body = [
      'ポートフォリオサイトからお問い合わせがありました。',
      '',
      'お名前: ' + name,
      '会社名: ' + (company || '（未入力）'),
      'メール: ' + email,
      '種別: ' + (type || '（未選択）'),
      '',
      '--- ご相談内容 ---',
      message,
    ].join('\n');

    GmailApp.sendEmail(RECIPIENT_EMAIL, subject, body, {
      replyTo: email,
      name: 'Portfolio Contact Form',
    });

    return jsonResponse_({ status: 'success' });
  } catch (err) {
    return jsonResponse_({ status: 'error', message: String(err) });
  }
}

function doGet() {
  return jsonResponse_({ status: 'ok' });
}

function sanitize_(value) {
  return String(value || '').trim();
}

function jsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
