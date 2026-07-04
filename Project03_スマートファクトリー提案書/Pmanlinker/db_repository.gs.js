// =========================================================
// db_repository.gs
// 役割：スプレッドシートへの高速な読み書き（通信を最小限にする）
// =========================================================

/**
 * 複数のデータを一括でシートの末尾に追加する（超高速化）
 * @param {string} sheetName - 書き込み先のシート名
 * @param {Array<Array>} data2D - 追加する2次元配列のデータ（段ボール箱）
 */
function appendRowsFast(sheetName, data2D) {
  if (!data2D || data2D.length === 0) return;
  
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(sheetName);
    
    if (!sheet) throw new Error("シートが見つかりません: " + sheetName);
    
    // データを入れる範囲を指定し、1回の通信でまとめてドカンと書き込む
    const startRow = sheet.getLastRow() + 1;
    const numRows = data2D.length;
    const numCols = data2D[0].length;
    
    sheet.getRange(startRow, 1, numRows, numCols).setValues(data2D);
    
  } catch (e) {
    // utils.gs のエラー通知を呼び出す
    logSystemError('appendRowsFast', e);
    throw e;
  }
}

/**
 * シートの全データを取得する（読み込み用）
 * @param {string} sheetName - 対象のシート名
 * @return {Array<Array>} シートの全データ
 */
function getAllData(sheetName) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) return [];
    
    return sheet.getDataRange().getValues();
  } catch (e) {
    logSystemError('getAllData', e);
    return [];
  }
}