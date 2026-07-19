/**
 * Portfolio contact form backend.
 *
 * Deploy: Deploy > New deployment > Web app
 *   Execute as: Me
 *   Who has access: Anyone
 * Paste the Web app URL into index.html (GAS_URL).
 */

const RECIPIENT_EMAIL = 'smartdtp.studio.works@gmail.com';

function doPost(e) {
  try {
    const data = parsePayload_(e);
    const name = sanitize_(data.name);
    const company = sanitize_(data.company);
    const email = sanitize_(data.email);
    const type = sanitize_(data.type);
    const message = sanitize_(data.message);

    if (!name || !email || !message) {
      return htmlResponse_('missing fields', false);
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

    return htmlResponse_('success', true);
  } catch (err) {
    return htmlResponse_(String(err), false);
  }
}

function doGet() {
  return htmlResponse_('ok', true);
}

function parsePayload_(e) {
  if (e.parameter && (e.parameter.name || e.parameter.email || e.parameter.message)) {
    return {
      name: e.parameter.name,
      company: e.parameter.company,
      email: e.parameter.email,
      type: e.parameter.type,
      message: e.parameter.message,
    };
  }

  if (e.postData && e.postData.contents) {
    const type = (e.postData.type || '').toLowerCase();
    if (type.indexOf('application/json') >= 0) {
      return JSON.parse(e.postData.contents);
    }
  }

  return {};
}

function sanitize_(value) {
  return String(value || '').trim();
}

function htmlResponse_(message, ok) {
  const safe = String(message)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const html = '<!DOCTYPE html><html><body data-status="' + (ok ? 'success' : 'error') + '">' +
    safe + '</body></html>';
  return HtmlService.createHtmlOutput(html).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
