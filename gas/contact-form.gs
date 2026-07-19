/**
 * Portfolio contact form backend.
 *
 * Deploy: Deploy > New deployment > Web app
 *   Execute as: Me
 *   Who has access: Anyone
 *
 * First-time setup (run once from GAS editor):
 *   1. Run setupContactSheet() — creates inbox spreadsheet
 *   2. Run testSendEmail() — verifies mail delivery
 */

const RECIPIENT_EMAIL = 'smartdtp.studio.works@gmail.com';

function doPost(e) {
  var data;
  try {
    data = parsePayload_(e);
    var name = sanitize_(data.name);
    var company = sanitize_(data.company);
    var email = sanitize_(data.email);
    var type = sanitize_(data.type);
    var message = sanitize_(data.message);

    if (!name || !email || !message) {
      return htmlResponse_('missing fields', false);
    }

    data = { name: name, company: company, email: email, type: type, message: message };

    // Always log to spreadsheet first (backup if mail fails)
    appendSubmission_(data);

    var subject = '[Portfolio] ' + (type || 'お問い合わせ') + ' — ' + name;
    var body = [
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

    MailApp.sendEmail({
      to: RECIPIENT_EMAIL,
      subject: subject,
      body: body,
      replyTo: email,
    });

    return htmlResponse_('success', true);
  } catch (err) {
    var errMsg = String(err && err.message ? err.message : err);
    try {
      if (data) appendSubmission_(data, 'MAIL_ERROR: ' + errMsg);
    } catch (_) {}
    return htmlResponse_(errMsg, false);
  }
}

function doGet() {
  return htmlResponse_('ok', true);
}

/** Run once: creates spreadsheet to store all submissions */
function setupContactSheet() {
  var ss = SpreadsheetApp.create('Portfolio Contact Inbox');
  var sheet = ss.getActiveSheet();
  sheet.setName('inbox');
  sheet.appendRow(['日時', '名前', '会社', 'メール', '種別', '内容', '備考']);
  PropertiesService.getScriptProperties().setProperty('CONTACT_SHEET_ID', ss.getId());
  Logger.log('Created sheet: ' + ss.getUrl());
  return ss.getUrl();
}

/** Run once: verify email can be sent */
function testSendEmail() {
  MailApp.sendEmail({
    to: RECIPIENT_EMAIL,
    subject: '[Portfolio] GAS メール送信テスト',
    body: 'このメールが届けば GAS からの送信は正常です。',
  });
  Logger.log('Test mail sent to ' + RECIPIENT_EMAIL);
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
    var contentType = (e.postData.type || '').toLowerCase();
    if (contentType.indexOf('application/json') >= 0) {
      return JSON.parse(e.postData.contents);
    }
  }

  return {};
}

function appendSubmission_(data, note) {
  var sheetId = PropertiesService.getScriptProperties().getProperty('CONTACT_SHEET_ID');
  if (!sheetId) return;
  var sheet = SpreadsheetApp.openById(sheetId).getSheets()[0];
  sheet.appendRow([
    new Date(),
    data.name || '',
    data.company || '',
    data.email || '',
    data.type || '',
    data.message || '',
    note || '',
  ]);
}

function sanitize_(value) {
  return String(value || '').trim();
}

function htmlResponse_(message, ok) {
  var status = ok ? 'success' : 'error';
  var payload = JSON.stringify({
    source: 'portfolio-contact',
    status: status,
    message: String(message),
  });
  var html = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>' +
    '<script>window.parent.postMessage(' + payload + ',"*");<\/script>' +
    '</body></html>';
  return HtmlService.createHtmlOutput(html)
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .setSandboxMode(HtmlService.SandboxMode.IFRAME);
}
