// =========================================================
// PMAN Linker Backend (完全復旧 ＋ オンデマンド・部品コード対応版)
// =========================================================

const CHAT_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAQAjJWfCqs/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=UqVZW9Z7NBKxVJi2Uqf7ldnRLc6mgJshdamdLl2RAtM";

function normStr(str) {
  if (!str) return "";
  return String(str).replace(/[Ａ-Ｚａ-ｚ０-９]/g, function(s) { return String.fromCharCode(s.charCodeAt(0) - 0xFEE0); }).trim();
}

function doGet(e) { 
  if (e && e.parameter && e.parameter.page === 'dashboard') {
    return HtmlService.createTemplateFromFile('dashboard').evaluate().setTitle('進捗ダッシュボード').setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  }
  return HtmlService.createTemplateFromFile('index').evaluate().setTitle('PMAN Linker Workspace').setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); 
}

function getUserInfo() {
  const email = Session.getActiveUser().getEmail(); 
  const staffSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Staff_master');
  if (!staffSheet) return { email: email, name: "テスト", department: "制作部門", section: "制作課", staffId: "0000" };
  
  const data = staffSheet.getDataRange().getValues(); 
  const headers = data[0];
  let idxStaffId = headers.indexOf('StaffID'); 
  if (idxStaffId === -1) idxStaffId = headers.indexOf('担当者コード'); 
  if (idxStaffId === -1) idxStaffId = 4;
  
  for (let i = 1; i < data.length; i++) { 
    if (data[i][0] === email) return { email: email, name: data[i][1], department: data[i][2], section: data[i][3], staffId: String(data[i][idxStaffId]) || "0000" }; 
  }
  return { email: email, name: "未登録", department: "未分類部門", section: "未分類課", staffId: "0000" };
}

function checkTriggerStatus() { 
  return ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'importPMANCSVs'); 
}

function getInitData() {
  try {
    const userInfo = getUserInfo(); 
    const menuSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('M_Work_Menu'); 
    let menuItems = [];
    if (menuSheet) { 
      const data = menuSheet.getDataRange().getValues(); 
      for (let i = 1; i < data.length; i++) if (data[i][0] === userInfo.section) menuItems.push(data[i][1]); 
    }
    if (menuItems.length === 0) menuItems.push("※メニュー未登録");
    
    let noticeMsg = ""; 
    try { 
      const settingSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('設定'); 
      if (settingSheet) noticeMsg = String(settingSheet.getRange(1, 7).getValue()).trim(); 
    } catch(e) {}
    
    let lastCsvUpdate = PropertiesService.getScriptProperties().getProperty('LAST_CSV_UPDATE') || "";
    
    return { 
      userInfo: userInfo, 
      menuItems: menuItems, 
      triggerStatus: checkTriggerStatus(), 
      noticeMsg: noticeMsg, 
      devMessage: noticeMsg, 
      lastCsvUpdate: lastCsvUpdate 
    };
  } catch(e) {
    return { 
      userInfo: {name: "ゲスト", section: "不明"}, 
      menuItems: ["※エラー発生"], 
      triggerStatus: false, 
      noticeMsg: "初期化エラー",
      devMessage: "初期化エラー"
    };
  }
}

function getTargetLogSheetId(sectionName) { 
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('設定'); 
  if(!sheet) throw new Error("設定シートが存在しません");
  const data = sheet.getDataRange().getValues(); 
  for (let i = 1; i < data.length; i++) { if (data[i][1] === sectionName) return data[i][2]; } 
  throw new Error("設定シートに書き込み先IDが未登録です。部署名: " + sectionName); 
}

function getDeptSheetByName(targetDeptSs, userName) { 
  const sheets = targetDeptSs.getSheets(); 
  const normalized = normStr(userName); 
  for (let i = 0; i < sheets.length; i++) { 
    const sName = normStr(sheets[i].getName()); 
    if (normalized.includes(sName) || sName.includes(normalized)) return sheets[i]; 
  } 
  return sheets[0]; 
}

function sendGoogleChatMessage(textMsg) {
  if (!CHAT_WEBHOOK_URL) return;
  const payload = { "text": textMsg };
  const options = { "method": "post", "contentType": "application/json", "payload": JSON.stringify(payload) };
  try { UrlFetchApp.fetch(CHAT_WEBHOOK_URL, options); } catch (e) {}
}

function _normalizeStatus(rawStatus) {
  let s = String(rawStatus).trim();
  if (s.includes('削除')) return '削除';
  if (s.includes('完了') || s.includes('済')) return '完了';
  if (s.includes('エラー')) return 'エラー';
  if (s.includes('不要')) return '不要';
  if (s.includes('校正待ち')) return '校正待ち'; 
  if (s.includes('待機')) return 'RPA待機';
  if (s.includes('送信待')) return '送信待';
  if (s.includes('処理中')) return '処理中';
  return '作業中';
}

function _parseLogTimeWithDate(dateVal, timeVal) {
  if (!timeVal) return "未定";
  let dateObj = null; 
  if (dateVal instanceof Date) { dateObj = dateVal; } 
  else { let d = new Date(dateVal); dateObj = !isNaN(d.getTime()) ? d : new Date(); }
  const mmdd = Utilities.formatDate(dateObj, "Asia/Tokyo", "MM/dd"); 
  let hhmm = "";
  if (timeVal instanceof Date) { hhmm = Utilities.formatDate(timeVal, "Asia/Tokyo", "HH:mm"); } 
  else if (typeof timeVal === 'number') { let t = Math.round(timeVal * 24 * 3600); hhmm = `${String(Math.floor(t / 3600) % 24).padStart(2, '0')}:${String(Math.floor((t % 3600) / 60)).padStart(2, '0')}`; } 
  else { hhmm = String(timeVal).substring(0,5); }
  return `${mmdd} ${hhmm}`;
}

// 🌟 紛失していた重要関数（これがないとエラーになります！）
function _getAutoFillTasks(orderId, kouteiId) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const activeSheet = ss.getSheetByName('App_Daily_Report');
    const data = activeSheet.getDataRange().getValues();
    let result = [];
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][2]).trim() === String(orderId).trim() && String(data[i][9]) === String(kouteiId)) {
         result.push({
           orderId: String(data[i][2]), 
           clientName: data[i][3], 
           jobName: data[i][4], 
           partCode: data[i][5] !== undefined ? data[i][5] : "", // 部品コード
           partName: data[i][6],
           workCode: data[i][13], 
           kouteiId: data[i][9], 
           machineId: data[i][10]
         });
      }
    }
    return result;
  } catch(e) { return []; }
}

function finishTaskWithProgressBackend(centralRowNums, actionType, kouseiMsg = "", driveLink = "") { 
  if (typeof centralRowNums === 'string') { try { centralRowNums = JSON.parse(centralRowNums); } catch(e) {} }

  try {
    const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); 
    if (!centralLogSheet) return { status: 'エラー' };

    const today = new Date(); 
    const dateStrLog = Utilities.formatDate(today, "Asia/Tokyo", "yyyy/MM/dd");
    const endTimeStrLog = Utilities.formatDate(today, "Asia/Tokyo", "HH:mm:ss");
    const endTimeNumDept = Number(Utilities.formatDate(today, "Asia/Tokyo", "Hmm")); 
    
    let deptSsId = "", deptRowNum = ""; 
    let clientName = "", jobName = "", userName = getUserInfo().name, orderId = "";
    let finalLStatus = "送信待";

    if (!centralRowNums || !Array.isArray(centralRowNums)) return { status: 'エラー' };

    centralRowNums.forEach((rowNum, idx) => { 
      let row = Number(rowNum); 
      if (!row || isNaN(row)) return;

      centralLogSheet.getRange(row, 1).setValue(dateStrLog); 
      centralLogSheet.getRange(row, 11).setValue(endTimeStrLog); 

      if (idx === 0) { 
        deptSsId = centralLogSheet.getRange(row, 13).getValue(); 
        deptRowNum = centralLogSheet.getRange(row, 14).getValue(); 
        userName = centralLogSheet.getRange(row, 2).getValue();
        orderId = String(centralLogSheet.getRange(row, 3).getValue());
        clientName = String(centralLogSheet.getRange(row, 4).getValue());
        jobName = String(centralLogSheet.getRange(row, 5).getValue());
      } 
      
      let isBusinessTask = /\d{6}/.test(orderId);
      let lStatus = "送信待"; 
      let sStatus = "完了";

      if (!isBusinessTask) {
        lStatus = "不要"; sStatus = "業務外";
      } else {
        if (actionType === 'gehan') sStatus = "④ 工務手配(下版)";
        else if (actionType === 'kousei') sStatus = "③ DTP・校正中";
        else if (actionType === 'continue') sStatus = "② DTP・制作継続";
        else if (actionType === 'normal') sStatus = "完了";
      }
      
      centralLogSheet.getRange(row, 12).setValue(lStatus); 
      try { centralLogSheet.getRange(row, 19).setValue(sStatus); } catch(e) {} 
      if (idx === 0) finalLStatus = lStatus;
    }); 
    
    const timestamp = Utilities.formatDate(today, "Asia/Tokyo", "yyyy/MM/dd HH:mm");
    if (actionType === 'gehan') sendGoogleChatMessage(`【下版完了】${timestamp}\n${clientName} / ${jobName}\n担当／${userName}`);
    else if (actionType === 'kousei') sendGoogleChatMessage(`【校正提出】${timestamp}\n${clientName} / ${jobName}\n担当／${userName}${kouseiMsg?"\nコメント:\n"+kouseiMsg:""}${driveLink?"\nリンク:\n"+driveLink:""}`);
    
    return { endTimeStrLog: endTimeStrLog, status: finalLStatus, deptData: { ssId: deptSsId, row: deptRowNum, user: userName, endTime: endTimeNumDept } }; 
  } catch (e) { return { status: 'エラー' }; }
}

function updateDeptSheetAsyncBackend(deptData) {
  try {
    if(deptData && deptData.ssId && deptData.row) {
      getDeptSheetByName(SpreadsheetApp.openById(deptData.ssId), deptData.user)
        .getRange(deptData.row, 5).setValue(deptData.endTime).setNumberFormat('0');
    }
  } catch(e) {} 
}

function loadMyTodayTasks() {
  try {
    const userInfo = getUserInfo(); const logSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); 
    if (!logSheet) return { active: [], action: [], waiting: [], doneToday: [] };
    const appSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('App_Daily_Report'); let noukiMap = {};
    if (appSheet) {
      const lastRow = appSheet.getLastRow();
      if (lastRow > 0) { const appData = appSheet.getRange(1, 1, lastRow, 3).getValues(); for (let i = 1; i < appData.length; i++) { let nVal = appData[i][1]; noukiMap[normStr(appData[i][2])] = (nVal instanceof Date) ? Utilities.formatDate(nVal, "Asia/Tokyo", "yyyy/MM/dd") : String(nVal); } }
    }
    const data = logSheet.getDataRange().getValues(); const todayStr = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy/MM/dd"); 
    let groupsMap = {}; let sessionKeys = {}; 
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i]; if (String(row[1]) !== userInfo.name) continue; 
      let rowDateStr = ""; if (row[0] instanceof Date) { rowDateStr = Utilities.formatDate(row[0], "Asia/Tokyo", "yyyy/MM/dd"); } else { let d = new Date(row[0]); rowDateStr = !isNaN(d.getTime()) ? Utilities.formatDate(d, "Asia/Tokyo", "yyyy/MM/dd") : String(row[0]).trim(); }
      let lStatus = _normalizeStatus(row[11]); if (lStatus === '削除') continue;
      let sStatus = String(row[18]).trim();
      let orderIdNorm = normStr(row[2]);
      let isBusinessTask = /\d{6}/.test(orderIdNorm);

      if (!isBusinessTask && rowDateStr !== todayStr) continue;

      const centralRowNum = String(i + 1); const deptRowNum = rowDateStr + "_" + String(row[13] || centralRowNum); 
      let sTimeStr = row[9] ? _parseLogTimeWithDate(row[0], row[9]) : ""; 
      if (sTimeStr) { sessionKeys[deptRowNum] = "session_" + centralRowNum; }
      const groupKey = sessionKeys[deptRowNum] || ("single_" + centralRowNum);
      
      if (!groupsMap[groupKey]) { 
        let eTimeStr = row[10] ? _parseLogTimeWithDate(row[0], row[10]) : "";
        groupsMap[groupKey] = { centralRowNums: [centralRowNum], dateStr: String(rowDateStr), orderId: String(row[2]), nouki: String(noukiMap[orderIdNorm] || "未定"), clientName: String(row[3]) + " / " + String(row[4]), jobName: String(row[4]), joinedWorkNames: String(row[6]), startTimeStrLog: String(sTimeStr), endTimeStrLog: String(eTimeStr), lStatus: String(lStatus), sStatus: String(sStatus), isBusinessTask: isBusinessTask }; 
      } else {
        let eTimeStr = row[10] ? _parseLogTimeWithDate(row[0], row[10]) : "";
        if (eTimeStr && !groupsMap[groupKey].endTimeStrLog) { groupsMap[groupKey].endTimeStrLog = String(eTimeStr); }
        groupsMap[groupKey].lStatus = String(lStatus);
        groupsMap[groupKey].sStatus = String(sStatus);
        groupsMap[groupKey].centralRowNums.push(centralRowNum);
      }
    }
    let active = [], action = [], waiting = [], doneToday = [];
    for (const key in groupsMap) { 
      const g = groupsMap[key];
      let isDoneToday = (g.dateStr === todayStr && g.endTimeStrLog !== "");
      if (g.dateStr !== todayStr && g.dateStr !== "") g.joinedWorkNames = "⚠️過去: " + g.joinedWorkNames; 

      if (isDoneToday) { doneToday.push(g); }
      if (g.lStatus === '送信待' || g.lStatus === 'エラー') { action.push(g); }

      if (g.dateStr === todayStr && g.endTimeStrLog === "") {
         active.push(g); 
      } else if (g.dateStr !== todayStr) {
         if (g.sStatus === '② DTP・制作継続' || g.sStatus === '③ DTP・校正中') {
             waiting.push(g); 
         }
      }
    }
    const sortNoukiAsc = (a, b) => { let na = a.nouki || "9999/99/99"; let nb = b.nouki || "9999/99/99"; if(na === "未定") na = "9999/99/99"; if(nb === "未定") nb = "9999/99/99"; return na.localeCompare(nb); };
    const sortTimeDesc = (a, b) => { let ta = a.endTimeStrLog || "00:00:00"; let tb = b.endTimeStrLog || "00:00:00"; return tb.localeCompare(ta); };
    active.sort(sortNoukiAsc); action.sort(sortNoukiAsc); waiting.sort(sortNoukiAsc); doneToday.sort(sortTimeDesc); 
    return { active: active, action: action, waiting: waiting, doneToday: doneToday };
  } catch(e) { return { active: [], action: [], waiting: [], doneToday: [] }; }
}

function loadHistoryTasks() {
  const userInfo = getUserInfo(); const logSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); if (!logSheet) return [];
  const appSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('App_Daily_Report'); let noukiMap = {};
  if (appSheet) {
    const lastRow = appSheet.getLastRow();
    if(lastRow > 0) { const appData = appSheet.getRange(1, 1, lastRow, 3).getValues(); for (let i = 1; i < appData.length; i++) { let nVal = appData[i][1]; noukiMap[normStr(appData[i][2])] = (nVal instanceof Date) ? Utilities.formatDate(nVal, "Asia/Tokyo", "yyyy/MM/dd") : String(nVal); } }
  }
  const data = logSheet.getDataRange().getValues(); const todayStr = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy/MM/dd"); const today = new Date(); today.setHours(0,0,0,0);
  let historyByOrder = {}; 
  for (let i = 1; i < data.length; i++) {
    const row = data[i]; if (String(row[1]) !== userInfo.name) continue; 
    let lStatus = _normalizeStatus(row[11]); if (lStatus === '削除') continue;
    let sStatus = String(row[18]).trim();

    if (sStatus !== '④ 工務手配(下版)' && sStatus !== '完了') continue;

    let rowDateStr = "", rowDateObj = null;
    if (row[0] instanceof Date) { rowDateObj = row[0]; rowDateStr = Utilities.formatDate(rowDateObj, "Asia/Tokyo", "yyyy/MM/dd"); } else { let d = new Date(row[0]); rowDateObj = !isNaN(d.getTime()) ? d : new Date(); rowDateStr = Utilities.formatDate(rowDateObj, "Asia/Tokyo", "yyyy/MM/dd"); }
    if (rowDateStr === todayStr) continue; 
    let diffDays = Math.floor((today - rowDateObj) / (1000 * 60 * 60 * 24));
    if (diffDays > 0 && diffDays <= 7) { 
      let orderId = String(row[2]).trim() || "番号なし"; let client = String(row[3]) || "不明"; let job = String(row[4]) || "";
      if (!historyByOrder[orderId]) { historyByOrder[orderId] = { orderId: orderId, clientName: client, jobName: job, nouki: noukiMap[orderId] || "未定", items: [], lastUpdate: "" }; }
      let sTimeStr = row[9] ? _parseLogTimeWithDate(row[0], row[9]) : ""; let eTimeStr = row[10] ? _parseLogTimeWithDate(row[0], row[10]) : "";
      historyByOrder[orderId].items.push({ date: rowDateStr, workName: row[6], startTime: sTimeStr, endTime: eTimeStr, lStatus: lStatus, sStatus: sStatus, centralRowNum: i + 1 });
      historyByOrder[orderId].lastUpdate = eTimeStr || sTimeStr; 
    }
  }
  let result = Object.values(historyByOrder); 
  result.sort((a, b) => { let na = a.nouki || "9999/99/99"; let nb = b.nouki || "9999/99/99"; if(na === "未定") na = "9999/99/99"; if(nb === "未定") nb = "9999/99/99"; return na.localeCompare(nb); });
  return result;
}

function loadMyInboxTasks_V2() {
  try {
    const userInfo = getUserInfo(); const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('DB_Progress');
    if (!sheet) return { success: false, msg: "DB_Progressシートなし" };
    const data = sheet.getDataRange().getValues(); if (data.length <= 1) return { success: false, msg: "データ0件" };
    const headers = data[0];
    const idxMainOp = headers.indexOf('主OP') !== -1 ? headers.indexOf('主OP') : 1; const idxSubOp = headers.indexOf('準OP') !== -1 ? headers.indexOf('準OP') : 2; const idxStatus = headers.indexOf('現在のステータス') !== -1 ? headers.indexOf('現在のステータス') : 12; const idxNouki = headers.indexOf('納期') !== -1 ? headers.indexOf('納期') : 5;
    let inbox = []; let myName = normStr(userInfo.name);
    for(let i=1; i<data.length; i++) {
      let row = data[i]; if (!row[0]) continue;
      let mainOp = normStr(row[idxMainOp]); let subOp = normStr(row[idxSubOp]); let status = normStr(row[idxStatus]);
      let isMyTask = false;
      if (myName !== "") { if (mainOp.includes(myName) || myName.includes(mainOp) || subOp.includes(myName) || myName.includes(subOp)) { isMyTask = true; } }
      if (isMyTask && (status === '制作待ち' || status === '校正戻り')) {
        let noukiVal = row[idxNouki]; let noukiStr = (noukiVal instanceof Date) ? Utilities.formatDate(noukiVal, "Asia/Tokyo", "yyyy/MM/dd") : String(noukiVal);
        inbox.push({ orderId: row[0], clientName: row[3], jobName: row[4], nouki: noukiStr, memo: row[10], status: status });
      }
    }
    return { success: true, tasks: inbox };
  } catch (e) { return { success: false, msg: e.message }; }
}

function searchActiveData(keyword) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const activeSheet = ss.getSheetByName('App_Daily_Report');
    const targetKeyword = normStr(keyword).toLowerCase().trim();
    if (!targetKeyword) return { found: false };

    const activeRows = activeSheet.getDataRange().getValues().slice(1);
    let exactRows = activeRows.filter(r => normStr(r[2]).toLowerCase() === targetKeyword);

    if (exactRows.length === 0) {
      const hSheet = ss.getSheetByName('History_Completed');
      if (hSheet) {
        const hFound = hSheet.getDataRange().getValues().slice(1).find(r => normStr(r[2]).toLowerCase() === targetKeyword);
        if (hFound) {
          return { found: true, isMultiple: false, isArchive: true, data: { groups: [{ items: [{ orderId: normStr(hFound[2]) }] }] } };
        }
      }
      const bSheet = ss.getSheetByName('Backup_CSV');
      if (bSheet) {
        const bData = bSheet.getDataRange().getValues();
        const headers = bData[0] || [];
        const idxId = headers.indexOf('受注番号') !== -1 ? headers.indexOf('受注番号') : 1;
        const bFound = bData.slice(1).find(r => normStr(r[idxId]).toLowerCase() === targetKeyword);
        if (bFound) {
          return { found: true, isMultiple: false, isArchive: true, data: { groups: [{ items: [{ orderId: normStr(bFound[idxId]) }] }] } };
        }
      }
    }

    if (exactRows.length > 0) {
      let groupsMap = {};
      exactRows.forEach(row => {
        const gKey = `${row[12]}_${row[11]}_${row[7]}`;
        if (!groupsMap[gKey]) groupsMap[gKey] = { bumon: row[12], section: row[11], kouteiMei: row[7], items: [] };
        const noukiStr = (row[1] instanceof Date) ? Utilities.formatDate(row[1], "Asia/Tokyo", "yyyy/MM/dd") : String(row[1]);
        
        groupsMap[gKey].items.push({
          orderId: String(row[2]), 
          clientName: row[3], 
          jobName: row[4], 
          partCode: row[5] !== undefined ? row[5] : "", // 🌟部品コードを完全取得！🌟
          partName: row[6],
          nouki: noukiStr, 
          workName: row[8], 
          kouteiId: row[9], 
          machineId: row[10], 
          workCode: row[13] || "0000"
        });
      });

      let sortedGroups = [];
      let myDept = "";
      try { myDept = getUserInfo().department; } catch(e) {}
      for (const key in groupsMap) {
        if (groupsMap[key].bumon === myDept) { sortedGroups.push({ ...groupsMap[key], isOwnBumon: true }); delete groupsMap[key]; }
      }
      for (const key in groupsMap) { sortedGroups.push({ ...groupsMap[key], isOwnBumon: false }); }

      return { found: true, isMultiple: false, isArchive: false, data: { groups: sortedGroups, schedule: null } };
    }
    
    let summaryMap = {};
    for (let i = 0; i < activeRows.length; i++) {
      const r = activeRows[i];
      if (`${r[2]} ${r[3]} ${r[4]}`.toLowerCase().includes(targetKeyword)) {
        const oid = String(r[2]);
        if (!summaryMap[oid]) summaryMap[oid] = { orderId: oid, clientName: r[3], jobName: r[4] };
      }
    }
    const summaryList = Object.values(summaryMap);
    if (summaryList.length > 0) return { found: true, isMultiple: true, summaryList: summaryList };

    return { found: false };

  } catch (e) {
    return { found: false, error: e.message }; 
  }
}

function getMachineAlias(m) {
  if (!m || m === "" || m === "未定") return "刷機未";
  let name = String(m).trim();
  if (name.includes("81") || name.includes("71")) return "刷機未";
  if (name.includes("4UVﾌﾟ")) return "JFX200";
  if (name.includes("1Ver")) return "Versa";
  if (name.includes("2BIZ")) return "BIZHUB";
  if (name.includes("泉")) return "外注";
  name = name.replace(/^[0-9\s]+/, '');
  return name || "刷機未";
}

function editTaskBackend(centralRowNums, newStartNum, newEndNum, newWorkName, newDateStr, newStatus) { 
  const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); 
  let deptSsId = "", deptRowNum = ""; 
  const formatTime = (num) => { if (!num) return ""; let s = String(num).replace(/[^0-9]/g, '').padStart(4, '0'); return `${s.substring(0,2)}:${s.substring(2,4)}:00`; }; 
  const startStr = formatTime(newStartNum), endStr = formatTime(newEndNum); 
  
  let dateObj = newDateStr ? new Date(newDateStr) : new Date();
  let dateStrLog = Utilities.formatDate(dateObj, "Asia/Tokyo", "yyyy/MM/dd");
  let dateStrDept = Utilities.formatDate(dateObj, "Asia/Tokyo", "M月d日");

  if (!centralRowNums || !Array.isArray(centralRowNums)) return true;

  centralRowNums.forEach((rowNum, idx) => { 
    let row = Number(rowNum);
    if (!row || isNaN(row)) return;

    centralLogSheet.getRange(row, 1).setValue(dateStrLog); 
    centralLogSheet.getRange(row, 7).setValue(newWorkName); 
    
    centralLogSheet.getRange(row, 10).setValue(startStr); 
    if (endStr) {
      centralLogSheet.getRange(row, 11).setValue(endStr); 
    } else {
      centralLogSheet.getRange(row, 11).setValue(""); 
    }
    
    if (newStatus) {
      centralLogSheet.getRange(row, 19).setValue(newStatus); 
    }
    
    if (idx === 0) { 
      deptSsId = centralLogSheet.getRange(row, 13).getValue(); 
      deptRowNum = centralLogSheet.getRange(row, 14).getValue(); 
    } 
  }); 
  
  try { 
    if(deptSsId && deptRowNum) {
      const deptSheet = getDeptSheetByName(SpreadsheetApp.openById(deptSsId), getUserInfo().name); 
      deptSheet.getRange(deptRowNum, 1).setValue(dateStrDept); 
      deptSheet.getRange(deptRowNum, 4).setValue(newStartNum).setNumberFormat('0'); 
      if (newEndNum) deptSheet.getRange(deptRowNum, 5).setValue(newEndNum).setNumberFormat('0'); 
      deptSheet.getRange(deptRowNum, 7).setValue(newWorkName); 
    }
  } catch (e) {} 
  return true;
}

function deleteTaskBackend(centralRowNums) {
  try {
    const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log');
    let deptSsId = "", deptRowNum = "";
    
    if (!centralRowNums || !Array.isArray(centralRowNums)) return true;

    centralRowNums.forEach((rowNum, idx) => {
      let row = Number(rowNum);
      if(!row) return;
      centralLogSheet.getRange(row, 12).setValue("❌削除");
      if (idx === 0) { deptSsId = centralLogSheet.getRange(row, 13).getValue(); deptRowNum = centralLogSheet.getRange(row, 14).getValue(); }
    });
    
    try {
      if (deptSsId && deptRowNum) {
        const deptSheet = getDeptSheetByName(SpreadsheetApp.openById(deptSsId), getUserInfo().name);
        deptSheet.getRange(deptRowNum, 1, 1, 7).clearContent();
        let checkCell = deptSheet.getRange(deptRowNum, 8);
        if (checkCell.getDataValidation() !== null) { checkCell.uncheck(); } else { checkCell.clearContent(); }
      }
    } catch (e) {}
    return true;
  } catch (e) { return true; }
}

function sendToRPABackend(centralRowNums) { try { const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); if (!centralRowNums || !Array.isArray(centralRowNums)) return 'RPA待機中'; centralRowNums.forEach(r => { if(Number(r)) centralLogSheet.getRange(Number(r), 12).setValue("RPA待機中"); }); return 'RPA待機中'; } catch(e) { return 'RPA待機中'; } }
function sendToRPABulkBackend(centralRowNumsArray) { try { const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); if (!centralRowNumsArray || !Array.isArray(centralRowNumsArray)) return 'RPA待機中'; centralRowNumsArray.forEach(rowNums => { if(Array.isArray(rowNums)) { rowNums.forEach(r => { if(Number(r)) centralLogSheet.getRange(Number(r), 12).setValue("RPA待機中"); }); } }); return 'RPA待機中'; } catch(e) { return 'RPA待機中'; } }

function addManualTaskBackend(manualData) {
  try {
    const userInfo = getUserInfo(); 
    const userSection = normStr(userInfo.section); 
    const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); 
    const today = new Date(); 
    const dateStrLog = Utilities.formatDate(today, "Asia/Tokyo", "yyyy/MM/dd"); 
    const dateStrDept = Utilities.formatDate(today, "Asia/Tokyo", "M月d日"); 
    let orderId = "業務外タスク"; 
    let workName = normStr(manualData.workName); 
    let hinmei = normStr(manualData.hinmei) || "要件なし"; 
    
    const formatTimeLog = (tStr) => { if (!tStr) return ""; if (tStr.includes(":")) return tStr + ":00"; return tStr; }; 
    const tStartLog = formatTimeLog(manualData.startTime); 
    const tEndLog = formatTimeLog(manualData.endTime); 
    const getNumTime = (tStr) => { if (!tStr) return ""; return Number(tStr.replace(":", "")); }; 
    const tStartNum = getNumTime(manualData.startTime); 
    const tEndNum = getNumTime(manualData.endTime);
    
    let targetDeptSsId = ""; let targetRow = ""; let deptSheetName = "";

    try {
      targetDeptSsId = getTargetLogSheetId(userSection); 
      const deptSs = SpreadsheetApp.openById(targetDeptSsId); 
      const deptSheet = getDeptSheetByName(deptSs, userInfo.name); 
      deptSheetName = deptSheet.getName();

      const abcValues = deptSheet.getRange("A1:C" + (deptSheet.getMaxRows() || 100)).getValues(); 
      let tempRow = -1; 
      for (let i = 4; i < abcValues.length; i++) { 
        if (String(abcValues[i][0]).trim() === "" && String(abcValues[i][1]).trim() === "" && String(abcValues[i][2]).trim() === "") { tempRow = i + 1; break; } 
      }
      if (tempRow === -1) tempRow = deptSheet.getLastRow() + 1; 
      targetRow = tempRow;
      
      const formulaStr = `=IF(AND(D${targetRow}="",E${targetRow}=""),"", CEILING((TEXT(E${targetRow},"00:00")-TEXT(D${targetRow},"00:00"))*1440, 5))`;
      deptSheet.getRange(targetRow, 1).setValue(dateStrDept); 
      deptSheet.getRange(targetRow, 2).setValue(""); 
      deptSheet.getRange(targetRow, 3).setValue(`業務外 / ${hinmei}`); 
      deptSheet.getRange(targetRow, 4).setValue(tStartNum).setNumberFormat('0'); 
      if (tEndNum) deptSheet.getRange(targetRow, 5).setValue(tEndNum).setNumberFormat('0'); 
      deptSheet.getRange(targetRow, 6).setFormula(formulaStr); 
      deptSheet.getRange(targetRow, 7).setValue(workName); 
      let checkCell = deptSheet.getRange(targetRow, 8); 
      if (checkCell.getDataValidation() === null) { checkCell.insertCheckboxes(); } 
      checkCell.uncheck(); 
    } catch (e) {}
    
    let lStatus = tEndLog ? "不要" : "作業中"; 
    let sStatus = tEndLog ? "業務外" : "作業中"; 
    
    let manualMachineId = ""; 
    if (userSection.includes("制作")) { manualMachineId = "81"; } 
    else if (userSection.includes("オンデマンド")) { manualMachineId = "79"; } 
    else if (userSection.includes("デジタルメディア")) { manualMachineId = "80"; }
    
    centralLogSheet.appendRow([ 
      dateStrLog, userInfo.name, orderId, "手動追加", hinmei, "", workName, "", 
      manualMachineId, tStartLog, tEndLog, lStatus, targetDeptSsId, targetRow, 
      "", "", userInfo.staffId, deptSheetName, sStatus 
    ]); 
    return true;
  } catch(e) { throw new Error(e.message); }
}

// 🌟 作業開始のコア処理（O列の部品コード等も完全対応）
function startTasksBackend(tasks, keywordId, selectedWorkName) {
  try {
    const userInfo = getUserInfo(); const userSection = normStr(userInfo.section); const centralLogSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log'); 
    let orderId = (tasks && tasks.length > 0 && tasks[0].orderId) ? normStr(tasks[0].orderId) : normStr(keywordId); 
    const today = new Date(); const dateStrLog = Utilities.formatDate(today, "Asia/Tokyo", "yyyy/MM/dd"); const startTimeStrLog = Utilities.formatDate(today, "Asia/Tokyo", "HH:mm:ss"); const dateStrDept = Utilities.formatDate(today, "Asia/Tokyo", "M月d日"); const startTimeNumDept = Number(Utilities.formatDate(today, "Asia/Tokyo", "Hmm")); 
    
    const machineMapSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('M_Machine_Map'); const machineTypeDict = {}; 
    if (machineMapSheet) { 
      const mData = machineMapSheet.getDataRange().getValues(); const mHeaders = mData[0]; const idxSagyoCode = mHeaders.indexOf('作業コード'); const idxType = mHeaders.indexOf('稼働タイプ'); 
      if (idxSagyoCode !== -1 && idxType !== -1) { for (let i = 1; i < mData.length; i++) { let code = normStr(mData[i][idxSagyoCode]); let type = normStr(mData[i][idxType]); if (code) machineTypeDict[code] = type; } } 
    }
    
    let targetDeptSsId = ""; let targetRow = ""; let deptSheetName = "";
    try {
      targetDeptSsId = getTargetLogSheetId(userSection); const deptSs = SpreadsheetApp.openById(targetDeptSsId); const deptSheet = getDeptSheetByName(deptSs, userInfo.name); deptSheetName = deptSheet.getName();
      const abcValues = deptSheet.getRange("A1:C" + (deptSheet.getMaxRows() || 100)).getValues(); let tempRow = -1; 
      for (let i = 4; i < abcValues.length; i++) { if (String(abcValues[i][0]).trim() === "" && String(abcValues[i][1]).trim() === "" && String(abcValues[i][2]).trim() === "") { tempRow = i + 1; break; } }
      if (tempRow === -1) tempRow = deptSheet.getLastRow() + 1; targetRow = tempRow;
      const formulaStr = `=IF(AND(D${targetRow}="",E${targetRow}=""),"", CEILING((TEXT(E${targetRow},"00:00")-TEXT(D${targetRow},"00:00"))*1440, 5))`;
      deptSheet.getRange(targetRow, 1).setValue(dateStrDept); deptSheet.getRange(targetRow, 2).setValue(orderId); deptSheet.getRange(targetRow, 3).setValue(`${tasks[0].clientName} / ${tasks[0].jobName}`); deptSheet.getRange(targetRow, 4).setValue(startTimeNumDept).setNumberFormat('0'); deptSheet.getRange(targetRow, 6).setFormula(formulaStr); deptSheet.getRange(targetRow, 7).setValue(selectedWorkName); deptSheet.getRange(targetRow, 8).insertCheckboxes().uncheck(); 
    } catch (e) {}
    
    let isGehan = selectedWorkName.includes("下版"); let mainTask = tasks[0]; let kouteiId = mainTask ? normStr(mainTask.kouteiId) : ""; let machineId = mainTask ? normStr(mainTask.machineId) : "";
    let isOwnDept = (kouteiId === "6"); let isOtherDeptTarget = (kouteiId !== "6" && ["81", "82", "56"].includes(machineId));
    let autoFilledTasks = []; 
    if (!isGehan) { tasks = [mainTask]; } else {
      if (isOwnDept) {
        for (let i = 1; i < tasks.length; i++) autoFilledTasks.push(tasks[i]); let allDeptTasks = _getAutoFillTasks(orderId, "6"); let checkedWorkCodes = tasks.map(t => normStr(t.workCode));
        allDeptTasks.forEach(t => { if (!checkedWorkCodes.includes(normStr(t.workCode))) { autoFilledTasks.push(t); } }); tasks = [mainTask]; 
      } else if (isOtherDeptTarget) { } else { tasks = [mainTask]; }
    }
    
    let centralRowNums = []; 
    tasks.forEach((task, idx) => { 
      let currentKouteiId = normStr(task.kouteiId); let currentMachineId = normStr(task.machineId); let wCode = normStr(task.workCode); let workType = machineTypeDict[wCode] || "人間"; 
      if (workType !== "機械") { if (userSection.includes("制作")) { currentMachineId = "81"; } else if (userSection.includes("オンデマンド")) { currentMachineId = "79"; } else if (userSection.includes("デジタルメディア")) { currentMachineId = "80"; } } 
      if (currentMachineId) currentMachineId = parseInt(currentMachineId, 10).toString(); 
      let tStart = (idx === 0) ? startTimeStrLog : ""; 
      
      // 🌟 O列(Index 14) に task.partCode（部品コード）が確実に入ります！
      centralLogSheet.appendRow([ dateStrLog, userInfo.name, orderId, task.clientName, task.jobName, task.partName, selectedWorkName, currentKouteiId, currentMachineId, tStart, "", "作業中", targetDeptSsId, targetRow, task.partCode, task.workCode, userInfo.staffId, deptSheetName, "② 入稿・作業中" ]); 
      centralRowNums.push(String(centralLogSheet.getLastRow())); 
    });
    
    autoFilledTasks.forEach((task) => {
      let currentKouteiId = normStr(task.kouteiId); let currentMachineId = normStr(task.machineId); let wCode = normStr(task.workCode); let workType = machineTypeDict[wCode] || "人間"; 
      if (workType !== "機械") { if (userSection.includes("制作")) { currentMachineId = "81"; } else if (userSection.includes("オンデマンド")) { currentMachineId = "79"; } else if (userSection.includes("デジタルメディア")) { currentMachineId = "80"; } } 
      if (currentMachineId) currentMachineId = parseInt(currentMachineId, 10).toString(); 
      
      centralLogSheet.appendRow([ dateStrLog, userInfo.name, orderId, task.clientName, task.jobName, task.partName, "自動補完(0分)", currentKouteiId, currentMachineId, startTimeStrLog, startTimeStrLog, "送信待", "", "", task.partCode, task.workCode, userInfo.staffId, deptSheetName, "④ 工務手配(下版)" ]);
    });
    
    return { orderId: String(orderId), clientName: String(tasks[0].clientName), jobName: String(tasks[0].jobName), joinedWorkNames: String(selectedWorkName), startTimeStrLog: String(startTimeStrLog), centralRowNums: centralRowNums, status: '作業中' };
  } catch(e) { throw new Error(e.message); }
}

function restoreFromBackupBackend(orderId, newNouki) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const activeSheet = ss.getSheetByName('App_Daily_Report');
    const targetId = String(orderId).trim();

    const machineMapSheet = ss.getSheetByName('M_Machine_Map');
    const deptMapSheet = ss.getSheetByName('M_Department_Map');

    const machineDict = {};
    if (machineMapSheet) {
      const mData = machineMapSheet.getDataRange().getValues();
      const mHeaders = mData[0];
      const idxMapSagyoCode = mHeaders.indexOf('作業コード');
      const idxMapKouteiId  = mHeaders.indexOf('進捗工程ID');
      const idxMapMachineId = mHeaders.indexOf('機械ID');
      if (idxMapSagyoCode !== -1) {
        for (let i = 1; i < mData.length; i++) {
          const code = (typeof normStr === 'function') ? normStr(mData[i][idxMapSagyoCode]) : String(mData[i][idxMapSagyoCode]).trim();
          if (code) machineDict[code] = { kouteiId: mData[i][idxMapKouteiId], machineId: mData[i][idxMapMachineId] };
        }
      }
    }

    const deptDict = {};
    if (deptMapSheet) {
      const dData = deptMapSheet.getDataRange().getValues();
      if (dData.length > 0) {
        const dHeaders = dData[0];
        let idxMapBushoId = dHeaders.indexOf('部署名ID') !== -1 ? dHeaders.indexOf('部署名ID') : (dHeaders.indexOf('部署名') !== -1 ? dHeaders.indexOf('部署名') : 0);
        let idxMapBumon = dHeaders.indexOf('部門') !== -1 ? dHeaders.indexOf('部門') : 1;
        for (let i = 1; i < dData.length; i++) {
          const bushoStr = (typeof normStr === 'function') ? normStr(dData[i][idxMapBushoId]) : String(dData[i][idxMapBushoId]).trim();
          if (bushoStr) deptDict[bushoStr] = (typeof normStr === 'function') ? normStr(dData[i][idxMapBumon]) : String(dData[i][idxMapBumon]).trim();
        }
      }
    }

    let rowsToAppend = [];

    const hSheet = ss.getSheetByName('History_Completed');
    if (hSheet) {
      const hData = hSheet.getDataRange().getValues();
      let rowsToDelete = [];
      for (let i = 1; i < hData.length; i++) {
        if (String(hData[i][2]).trim() === targetId) { 
          let rowData = hData[i].slice(0, 16); 
          while(rowData.length < 16) rowData.push(""); 
          if (newNouki) rowData[1] = newNouki; 
          rowsToAppend.push(rowData);
          rowsToDelete.push(i + 1);
        }
      }
      
      if (rowsToAppend.length > 0) {
        activeSheet.getRange(activeSheet.getLastRow() + 1, 1, rowsToAppend.length, 16).setValues(rowsToAppend);
        for (let j = rowsToDelete.length - 1; j >= 0; j--) hSheet.deleteRow(rowsToDelete[j]);
        return `✅ 履歴から ${rowsToAppend.length} 件の工程を現役に復元しました！\n再検索してください。`;
      }
    }

    const bSheet = ss.getSheetByName('Backup_CSV');
    if (bSheet) {
      const bData = bSheet.getDataRange().getValues();
      const headers = bData[0] || [];

      const getIdx = (names) => {
        for (let n of names) {
          let idx = headers.findIndex(h => String(h).replace(/[\s\u3000]/g, '').includes(n.replace(/[\s\u3000]/g, '')));
          if (idx !== -1) return idx;
        }
        return -1;
      };

      const idxJuchuNo = getIdx(['受注番号']);
      if (idxJuchuNo === -1) throw new Error("Backup_CSVに「受注番号」列がありません。");

      for (let i = 1; i < bData.length; i++) {
        if (String(bData[i][idxJuchuNo]).trim() === targetId) {
          let r = bData[i];
          let newRow = new Array(16).fill(""); 
          const safeGet = (names) => { let id = getIdx(names); return id !== -1 ? String(r[id]).trim() : ""; };

          let rawSagyoCode = safeGet(['作業ｺｰﾄﾞ', '作業コード', '作業ｺｰﾄﾞﾞ']);
          let currentSagyoCode = (typeof normStr === 'function') ? normStr(rawSagyoCode) : rawSagyoCode;
          const mappedData = machineDict[currentSagyoCode] || { kouteiId: "", machineId: "" }; 
          
          let csvShozokuKa = (typeof normStr === 'function') ? normStr(safeGet(['部署名'])) : safeGet(['部署名']); 
          let kouteiMeiStr = (typeof normStr === 'function') ? normStr(safeGet(['工程名'])) : safeGet(['工程名']);
          let kouteiIdStr = mappedData.kouteiId; 
          let machineIdStr = mappedData.machineId;

          if (csvShozokuKa === "生産管理室" && kouteiMeiStr === "制作") { 
            csvShozokuKa = "制作課"; kouteiIdStr = "6"; machineIdStr = "81"; 
          }

          newRow[0] = safeGet(['受注日']);
          newRow[1] = newNouki ? newNouki : safeGet(['納期']);
          newRow[2] = targetId;
          newRow[3] = safeGet(['得意先名', '得意先']);
          newRow[4] = safeGet(['品名', '品　名']);
          newRow[5] = safeGet(['部品ｺｰﾄﾞ', '部品コード']);
          newRow[6] = safeGet(['部品名']);
          newRow[7] = kouteiMeiStr;             
          newRow[8] = safeGet(['作業名']);       
          newRow[9] = kouteiIdStr;              
          newRow[10] = machineIdStr;            
          newRow[11] = csvShozokuKa;            
          newRow[12] = deptDict[csvShozokuKa] || "未分類部門"; 
          newRow[13] = currentSagyoCode;        
          
          newRow[14] = safeGet(['数量', '数　量']) + safeGet(['単位', '単　位']);
          let pStr = safeGet(['頁数']) ? safeGet(['頁数']) + "P" : "";
          let omote = safeGet(['表色数']), ura = safeGet(['裏色数']);
          let cStr = (omote || ura) ? `${omote}C/${ura}C` : "";
          let paper = (safeGet(['用紙名']) + " " + safeGet(['用紙規格'])).trim();
          newRow[15] = [pStr, cStr, paper].filter(Boolean).join(' | ');

          if (newRow[0] && new Date(newRow[0]).toString() !== "Invalid Date") newRow[0] = Utilities.formatDate(new Date(newRow[0]), "Asia/Tokyo", "yyyy/MM/dd");
          if (newRow[1] && new Date(newRow[1]).toString() !== "Invalid Date") newRow[1] = Utilities.formatDate(new Date(newRow[1]), "Asia/Tokyo", "yyyy/MM/dd");

          rowsToAppend.push(newRow);
        }
      }

      if (rowsToAppend.length > 0) {
        activeSheet.getRange(activeSheet.getLastRow() + 1, 1, rowsToAppend.length, 16).setValues(rowsToAppend);
        return `✅ Backup_CSV から ${rowsToAppend.length} 件の工程を完璧に復元しました！\n再検索してください。`;
      }
    }
    return "⚠️ データベースのどこにも見つかりませんでした。";
  } catch (err) { return "❌ エラー発生：" + err.message; }
}

// ==========================================
// その他の自動化処理・トリガー
// ==========================================
function getDashboardData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const appSheet = ss.getSheetByName('App_Daily_Report');
  const logSheet = ss.getSheetByName('Log');
  const scheduleSheet = ss.getSheetByName('App_Print_Schedule');
  
  if (!appSheet || !logSheet) return [];
  const appData = appSheet.getDataRange().getValues();
  let orders = {};

  for (let i = 1; i < appData.length; i++) {
    let r = appData[i];
    let orderId = String(r[2]).trim();
    if (!orderId) continue;
    let noukiVal = r[1];
    let noukiStr = (noukiVal instanceof Date) ? Utilities.formatDate(noukiVal, "Asia/Tokyo", "yyyy/MM/dd") : String(noukiVal);

    if (!orders[orderId]) {
      orders[orderId] = {
        orderId: orderId, clientName: String(r[3]), jobName: String(r[4]), 
        nouki: noukiStr, qty: String(r[14] || ""), spec: String(r[15] || ""),
        departments: new Set(), history: [], latestStatus: "① 受注・未着手", 
        machine: "", printDate: "-", deadline: "-", pages: "-", printMachine: "未定"
      };
    }
    let dept = String(r[11]); let bumon = String(r[12]);
    if (dept) orders[orderId].departments.add(dept);
    if (bumon) orders[orderId].departments.add(bumon);
  }

  try {
    const cache = CacheService.getScriptCache();
    let cachedSchedule = cache.get('scheduleData');
    let scheduleData = cachedSchedule ? JSON.parse(cachedSchedule) : null;
    
    if (!scheduleData && scheduleSheet) {
      scheduleData = scheduleSheet.getDataRange().getValues();
      cache.put('scheduleData', JSON.stringify(scheduleData), 3600);
    }

    if (scheduleData) {
      for (let i = 1; i < scheduleData.length; i++) {
        let sId = String(scheduleData[i][0]).trim();
        if (orders[sId]) {
          const formatDateSafe = (d) => {
            if (!d) return "-"; let dObj = new Date(d);
            return (!isNaN(dObj.getTime())) ? Utilities.formatDate(dObj, "Asia/Tokyo", "yyyy/MM/dd") : String(d);
          };
          orders[sId].printDate = formatDateSafe(scheduleData[i][1]);
          orders[sId].deadline = formatDateSafe(scheduleData[i][2]);
          orders[sId].pages = String(scheduleData[i][3] || "-");
          orders[sId].printMachine = String(scheduleData[i][4] || "未定");
        }
      }
    }
  } catch (e) { }

  const logData = logSheet.getDataRange().getValues();
  for (let i = 1; i < logData.length; i++) {
    let r = logData[i]; let oId = String(r[2]).trim();
    if (!orders[oId]) continue; 

    let logUser = String(r[1]);
    let logDate = (r[0] instanceof Date) ? Utilities.formatDate(r[0], "Asia/Tokyo", "MM/dd") : String(r[0]);
    let logTime = String(r[9] || "").substring(0,5);
    let logMachine = String(r[8] || "").trim(); 
    let logStatus = String(r[11]).trim(); 
    let sStatus = String(r[18] || "").trim(); 

    orders[oId].history.push({ date: logDate + " " + logTime, title: String(r[6]), user: logUser, status: logStatus + (sStatus ? ` [${sStatus}]` : "") });
    if (logMachine) orders[oId].machine = logMachine;

    if (logStatus.includes("印刷済") || logStatus.includes("製本済") || logStatus.includes("出荷済")) {
      delete orders[oId]; continue; 
    }

    const isGehan = logStatus.includes("完了") || logStatus.includes("済") || sStatus.includes("完了") || sStatus.includes("下版") || sStatus.includes("済");
    const isSapanDone = logStatus.includes("刷版") && (logStatus.includes("済") || logStatus.includes("完了"));
    const machineName = getMachineAlias(orders[oId].printMachine || logMachine);

    let dashStatus = "① 受注・未着手";
    
    if (sStatus.startsWith("①") || sStatus.startsWith("②") || sStatus.startsWith("③") || sStatus.startsWith("④")) dashStatus = sStatus;
    else if (logStatus.includes("処理中") || logStatus.includes("校正") || sStatus.includes("校正")) dashStatus = "③ DTP・校正中";
    else if (logStatus.includes("待機") || logStatus.includes("作業中") || sStatus.includes("作業中") || sStatus.includes("継続")) dashStatus = "② 入稿・作業中";

    if (logUser === "🤖EQUIOS(自動)" || isSapanDone) {
      if (["UV4", "UV5", "K2", "Versa", "BIZHUB", "JFX200"].includes(machineName)) dashStatus = machineName;
      else dashStatus = "⑤ 刷版";
    } else if (isGehan || dashStatus.startsWith("④")) {
      if (["Versa", "BIZHUB", "JFX200"].includes(machineName)) dashStatus = machineName; 
      else if (["UV4", "UV5", "K2"].includes(machineName)) dashStatus = "⑤ 刷版";
      else dashStatus = "④ 工務手配(未確定)";
    }
    
    orders[oId].latestStatus = dashStatus;
  }

  try {
    const extSsId = '1IRT3imz1fWbIYewHfk4rGRT8lsZWdMMAI-Bz0KXWAnE';
    const extSs = SpreadsheetApp.openById(extSsId);
    const extSheet = extSs.getSheetByName('220405インポート');
    if (extSheet) {
      const extData = extSheet.getDataRange().getValues();
      for (let i = 1; i < extData.length; i++) {
        let rawId = String(extData[i][2] || "").trim();
        let extOrderId = rawId.split('\n')[0].trim();
        if (!extOrderId || !orders[extOrderId]) continue; 
        
        let l_seisaku = String(extData[i][11] || "").trim();
        let m_kousei  = String(extData[i][12] || "").trim();
        let n_gehan   = String(extData[i][13] || "").trim();
        let o_nyuko   = String(extData[i][14] || "").trim();

        let realStatus = "";
        
        if (n_gehan !== "") {
           let mName = getMachineAlias(orders[extOrderId].printMachine);
           if (["Versa", "BIZHUB", "JFX200"].includes(mName)) realStatus = mName;
           else if (["UV4", "UV5", "K2"].includes(mName)) realStatus = "⑤ 刷版";
           else realStatus = "④ 工務手配(未確定)";
        }
        else if (m_kousei !== "") realStatus = "③ DTP・校正中";
        else if (l_seisaku !== "" || o_nyuko !== "") realStatus = "② 入稿・作業中";
        
        if (realStatus !== "") {
          let currentStatus = orders[extOrderId].latestStatus;
          if (currentStatus.startsWith("①") || currentStatus.startsWith("②") || currentStatus.startsWith("③") || currentStatus.startsWith("④")) {
            orders[extOrderId].latestStatus = realStatus;
          }
        }
      }
    }
  } catch (e) { }

  let result = [];
  for (let key in orders) {
    let o = orders[key]; o.departments = Array.from(o.departments); o.history.reverse(); result.push(o);
  }
  return result;
}

function importPMANCSVs() {
  const FOLDER_ID = '1Hh4SdMTldQnoK8rLwAwfZzxwMxO3OVTU'; 
  const folder = DriveApp.getFolderById(FOLDER_ID);
  const files = folder.getFilesByType(MimeType.CSV);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const backupSheet = ss.getSheetByName('Backup_CSV');
  const activeSheet = ss.getSheetByName('App_Daily_Report');
  const machineMapSheet = ss.getSheetByName('M_Machine_Map');
  const deptMapSheet = ss.getSheetByName('M_Department_Map');

  function generateUniqueKey(juchu, buhin, sagyo, busho) {
    function clean(val) { let s = normStr(val); if (/^[0-9]+$/.test(s)) return String(Number(s)); return s; }
    return clean(juchu) + "_" + clean(buhin) + "_" + clean(sagyo) + "_" + normStr(busho);
  }
  
  const machineData = machineMapSheet.getDataRange().getValues();
  const machineHeaders = machineData[0];
  const idxMapSagyoCode = machineHeaders.indexOf('作業コード');
  const idxMapKouteiId  = machineHeaders.indexOf('進捗工程ID');
  const idxMapMachineId = machineHeaders.indexOf('機械ID');
  const machineDict = {};
  for (let i = 1; i < machineData.length; i++) {
    const sagyoCode = normStr(machineData[i][idxMapSagyoCode]);
    if (sagyoCode) machineDict[sagyoCode] = { kouteiId: machineData[i][idxMapKouteiId], machineId: machineData[i][idxMapMachineId] };
  }
  
  const deptDict = {};
  if (deptMapSheet) {
    const deptData = deptMapSheet.getDataRange().getValues();
    if (deptData.length > 0) {
      const deptHeaders = deptData[0];
      let idxMapBushoId = deptHeaders.indexOf('部署名ID') !== -1 ? deptHeaders.indexOf('部署名ID') : (deptHeaders.indexOf('部署名') !== -1 ? deptHeaders.indexOf('部署名') : 0);
      let idxMapBumon = deptHeaders.indexOf('部門') !== -1 ? deptHeaders.indexOf('部門') : 1;
      for (let i = 1; i < deptData.length; i++) {
        const bushoIdStr = normStr(deptData[i][idxMapBushoId]);
        if (bushoIdStr) deptDict[bushoIdStr] = normStr(deptData[i][idxMapBumon]);
      }
    }
  }
  
  let activeData = activeSheet.getDataRange().getValues();
  if (activeData.length === 0 || (activeData.length === 1 && String(activeData[0][0]) === "")) {
    activeData = [["受注日", "納期", "受注番号", "得意先名", "品名", "部品コード", "部品名", "工程名", "作業名", "進捗工程ID", "機械ID", "部署名", "部門", "作業コード", "数量", "仕様詳細"]];
  } else {
    for(let i=0; i<activeData.length; i++){ while(activeData[i].length < 16){ activeData[i].push(""); } }
    activeData[0][14] = "数量"; activeData[0][15] = "仕様詳細";
  }

  const existingActiveMap = new Map(); 
  for (let i = 1; i < activeData.length; i++) {
    const r = activeData[i];
    if (r[2]) { existingActiveMap.set(generateUniqueKey(r[2], r[5], r[13], r[11]), i); }
  }
  
  const backupData = backupSheet.getDataRange().getValues();
  const existingBackupKeys = new Set();
  if (backupData.length > 0) {
    let bHead = backupData[0];
    let bJuchu = bHead.indexOf('受注番号'), bBuhin = bHead.indexOf('部品ｺｰﾄﾞ'), bBusho = bHead.indexOf('部署名');
    let bSagyo = bHead.indexOf('作業ｺｰﾄﾞﾞ') !== -1 ? bHead.indexOf('作業ｺｰﾄﾞﾞ') : (bHead.indexOf('作業ｺｰﾄﾞ') !== -1 ? bHead.indexOf('作業ｺｰﾄﾞ') : bHead.indexOf('作業コード'));
    if (bJuchu !== -1 && bBuhin !== -1 && bSagyo !== -1 && bBusho !== -1) {
      for (let i = 1; i < backupData.length; i++) {
        existingBackupKeys.add(generateUniqueKey(backupData[i][bJuchu], backupData[i][bBuhin], backupData[i][bSagyo], backupData[i][bBusho]));
      }
    }
  }
  
  const today = new Date(); const limitDate = new Date(); limitDate.setMonth(today.getMonth() - 6);
  let isUpdated = false; let isAppSheetModified = false; let backupDataToAppend = [];
  const EXCLUDE_WORK_CODES = ["7251", "7252"];
  
  while (files.hasNext()) {
    const file = files.next();
    if (!file.getName().startsWith('受注データ出力')) continue;
    const csvData = Utilities.parseCsv(file.getBlob().getDataAsString('MS932'));
    if (csvData.length <= 1) { file.setTrashed(true); continue; }
    
    const headers = csvData[0]; const dataRows = csvData.slice(1);
    if (backupSheet.getLastRow() === 0) backupSheet.appendRow(headers);
    
    function getColIdx(name) { return headers.findIndex(h => String(h).replace(/[\s\u3000]/g, '') === name); }
    const idxJuchuBi = getColIdx('受注日'); const idxNouki = getColIdx('納期'); const idxJuchuNo = getColIdx('受注番号'); const idxTokuisaki = getColIdx('得意先名');
    const idxHinmei = getColIdx('品名'); const idxBuhinCode = getColIdx('部品ｺｰﾄﾞ'); const idxBuhinMei = getColIdx('部品名'); const idxKouteiMei = getColIdx('工程名');
    const idxSagyoMei = getColIdx('作業名'); const idxBushoMei = getColIdx('部署名');
    let idxSagyoCode = headers.indexOf('作業ｺｰﾄﾞﾞ') !== -1 ? headers.indexOf('作業ｺｰﾄﾞﾞ') : (headers.indexOf('作業ｺｰﾄﾞ') !== -1 ? headers.indexOf('作業ｺｰﾄﾞ') : headers.indexOf('作業コード'));
    const idxSuryo = getColIdx('数量'); const idxTani = getColIdx('単位'); const idxPages = getColIdx('頁数');
    const idxOmoteC = getColIdx('表色数'); const idxUraC = getColIdx('裏色数'); const idxPaperName = getColIdx('用紙名'); const idxPaperKikaku = getColIdx('用紙規格');
    
    for (let i = 0; i < dataRows.length; i++) {
      const row = dataRows[i]; 
      const backupUniqueKey = generateUniqueKey(row[idxJuchuNo], row[idxBuhinCode], row[idxSagyoCode], row[idxBushoMei]);
      if (!existingBackupKeys.has(backupUniqueKey)) { backupDataToAppend.push(row); existingBackupKeys.add(backupUniqueKey); }
      
      let noukiDate = new Date(row[idxNouki]);
      if (!row[idxNouki] || isNaN(noukiDate.getTime()) || noukiDate >= limitDate) {
        let currentSagyoCode = normStr(row[idxSagyoCode]);
        if (EXCLUDE_WORK_CODES.includes(currentSagyoCode)) { continue; }
        
        const mappedData = machineDict[currentSagyoCode] || { kouteiId: "", machineId: "" }; 
        let csvShozokuKa = normStr(row[idxBushoMei]); let kouteiMeiStr = normStr(row[idxKouteiMei]);
        let kouteiIdStr = mappedData.kouteiId; let machineIdStr = mappedData.machineId;
        
        if (csvShozokuKa === "生産管理室" && kouteiMeiStr === "制作") { csvShozokuKa = "制作課"; kouteiIdStr = "6"; machineIdStr = "81"; }
        
        let valSuryo = (idxSuryo !== -1 && row[idxSuryo]) ? row[idxSuryo] : ""; let valTani = (idxTani !== -1 && row[idxTani]) ? row[idxTani] : "";
        let qtyStr = valSuryo + valTani; let pageStr = (idxPages !== -1 && row[idxPages]) ? row[idxPages] + "P" : "";
        let omoteC = (idxOmoteC !== -1 && row[idxOmoteC]) ? row[idxOmoteC] : 0; let uraC = (idxUraC !== -1 && row[idxUraC]) ? row[idxUraC] : 0;
        let colorStr = (omoteC || uraC) ? `${omoteC}C/${uraC}C` : ""; let pName = (idxPaperName !== -1 && row[idxPaperName]) ? row[idxPaperName] : "";
        let pKikaku = (idxPaperKikaku !== -1 && row[idxPaperKikaku]) ? row[idxPaperKikaku] : ""; let paperStr = (pName + " " + pKikaku).trim();
        let specStr = [pageStr, colorStr, paperStr].filter(Boolean).join(' | ');

        const activeUniqueKey = generateUniqueKey(row[idxJuchuNo], row[idxBuhinCode], row[idxSagyoCode], csvShozokuKa);
        let newRowData = [ row[idxJuchuBi], row[idxNouki], row[idxJuchuNo], row[idxTokuisaki], row[idxHinmei], row[idxBuhinCode], row[idxBuhinMei], kouteiMeiStr, row[idxSagyoMei], kouteiIdStr, machineIdStr, csvShozokuKa, (deptDict[csvShozokuKa] || "未分類部門"), currentSagyoCode, qtyStr, specStr ];

        if (existingActiveMap.has(activeUniqueKey)) {
          let rowIndex = existingActiveMap.get(activeUniqueKey); let existingRow = activeData[rowIndex];
          let oldNouki = (existingRow[1] instanceof Date) ? Utilities.formatDate(existingRow[1], "Asia/Tokyo", "yyyy/MM/dd") : String(existingRow[1]);
          let newNouki = (newRowData[1] instanceof Date) ? Utilities.formatDate(newRowData[1], "Asia/Tokyo", "yyyy/MM/dd") : String(newRowData[1]);
          if (oldNouki !== newNouki || String(existingRow[14]) !== String(qtyStr) || String(existingRow[15]) !== String(specStr)) {
            activeData[rowIndex][1] = newRowData[1]; activeData[rowIndex][14] = newRowData[14]; activeData[rowIndex][15] = newRowData[15]; isAppSheetModified = true;
          }
        } else {
          activeData.push(newRowData); existingActiveMap.set(activeUniqueKey, activeData.length - 1); isAppSheetModified = true;
        }
      }
    }
    file.setTrashed(true); isUpdated = true;
  }
  if (backupDataToAppend.length > 0) { backupSheet.getRange(backupSheet.getLastRow() + 1, 1, backupDataToAppend.length, backupDataToAppend[0].length).setValues(backupDataToAppend); }
  if (isAppSheetModified) { activeSheet.getRange(1, 1, activeData.length, 16).setValues(activeData); }
  if (isUpdated) { PropertiesService.getScriptProperties().setProperty('LAST_CSV_UPDATE', Utilities.formatDate(new Date(), "Asia/Tokyo", "M月d日 HH:mm")); }
}

function syncPrintSchedule() {
  const sourceSsId = '12Gs-sraboekSu0ylvb6D7_4o59sZTEPOwPW7YvkG-1g';
  const sourceSheetName = '★入力★';
  try {
    const sourceSs = SpreadsheetApp.openById(sourceSsId);
    const sourceSheet = sourceSs.getSheetByName(sourceSheetName);
    if (!sourceSheet) return;

    const lastRow = sourceSheet.getLastRow();
    if (lastRow < 3) return; 
    const data = sourceSheet.getRange(3, 1, lastRow - 2, 30).getValues();

    const targetSs = SpreadsheetApp.getActiveSpreadsheet();
    let targetSheet = targetSs.getSheetByName('App_Print_Schedule');
    
    let outputData = [["伝票番号", "印刷予定日", "下版予定日(自動計算)", "頁数", "印刷機種", "済ステータス"]];

    for (let i = 0; i < data.length; i++) {
      const row = data[i];
      const isDone = String(row[0]).trim();     
      const orderId = String(row[1]).trim();    
      const printDateVal = row[8];              
      const pagesVal = row[13];                 
      const machine = String(row[21]).trim();   

      if (!orderId || isDone !== "") continue; 

      let printDateStr = "";
      let deadlineStr = "";

      if (printDateVal instanceof Date) {
        printDateStr = Utilities.formatDate(printDateVal, "Asia/Tokyo", "yyyy/MM/dd");
        let pages = Number(pagesVal) || 0;
        let daysToSubtract = (pages >= 50) ? 2 : 1; 
        let deadlineDate = new Date(printDateVal.getTime());
        deadlineDate.setDate(deadlineDate.getDate() - daysToSubtract);
        deadlineStr = Utilities.formatDate(deadlineDate, "Asia/Tokyo", "yyyy/MM/dd");
      } 
      else if (printDateVal) {
         printDateStr = String(printDateVal); 
         deadlineStr = "確認要"; 
      }
      outputData.push([orderId, printDateStr, deadlineStr, pagesVal, machine, isDone]);
    }
    targetSheet.clearContents();
    if (outputData.length > 0) targetSheet.getRange(1, 1, outputData.length, outputData[0].length).setValues(outputData);
  } catch (e) { }
}

function importEquiosLog() {
  const FOLDER_ID = '1aiemDc8xI5IB_hgm7doPt94AA0Dszfow'; 
  const folder = DriveApp.getFolderById(FOLDER_ID);
  const files = folder.getFilesByType(MimeType.CSV);
  const logSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Log');
  if (!logSheet) return;

  const logData = logSheet.getDataRange().getValues();
  const existingEquiosOrders = new Set();
  for (let i = 1; i < logData.length; i++) {
    let userName = String(logData[i][1]);
    let orderId = String(logData[i][2]);
    if (userName === "🤖EQUIOS(自動)") { existingEquiosOrders.add(orderId); }
  }
  
  let logDataToAppend = [];
  let isUpdated = false;
  
  while (files.hasNext()) {
    const file = files.next();
    const csvStr = file.getBlob().getDataAsString("UTF-8"); 
    const csvData = Utilities.parseCsv(csvStr);
    if (csvData.length < 2) { file.setTrashed(true); continue; }
    
    let headerRow = csvData[0];
    let dataStartIndex = 1;
    if (String(headerRow[0]).includes("日付:")) { headerRow = csvData[1]; dataStartIndex = 2; }
    
    const idxJobName = headerRow.indexOf("ジョブ名"); const idxEndTime = headerRow.indexOf("終了日時");
    if (idxJobName === -1 || idxEndTime === -1) { file.setTrashed(true); continue; }
    
    for (let i = dataStartIndex; i < csvData.length; i++) {
      let row = csvData[i];
      let jobName = String(row[idxJobName]).trim();
      let endTime = row[idxEndTime];
      
      if (!endTime || String(endTime).trim() === "") continue;
      
      let match = jobName.match(/\d{5,7}/);
      if (!match) continue;
      let orderId = match[0];
      
      if (!existingEquiosOrders.has(orderId)) {
        let targetMachine = "印刷機(判定不能)";
        if (jobName.startsWith("H_UV_")) { targetMachine = "UV5色機"; } 
        else if (jobName.startsWith("UV_")) { targetMachine = "UV4色機"; } 
        else if (jobName.startsWith("K2_")) { targetMachine = "菊判4色機"; }

        let endDateStr = endTime.split(" ")[0] || Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy/MM/dd");
        let endTimeStr = endTime.split(" ")[1] || "12:00:00";
        
        let newLog = [
          endDateStr, "🤖EQUIOS(自動)", orderId, "", jobName, "刷版（CTP出力）", 
          `刷版出力完了 (${targetMachine}用)`, "", targetMachine, endTimeStr, endTimeStr, 
          "✅完了", "", "", "", "", "", "編集・校正製版課" 
        ]; 
        logDataToAppend.push(newLog);
        existingEquiosOrders.add(orderId); 
      }
    }
    file.setTrashed(true);
    isUpdated = true;
  }
  if (logDataToAppend.length > 0) { logSheet.getRange(logSheet.getLastRow() + 1, 1, logDataToAppend.length, logDataToAppend[0].length).setValues(logDataToAppend); }
}

function archiveAndCleanupJobs() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const mainSheet = ss.getSheetByName('App_Daily_Report');
  const historySheet = ss.getSheetByName('History_Completed') || ss.insertSheet('History_Completed');
  
  const data = mainSheet.getDataRange().getValues();
  const headers = data[0];
  const now = new Date();
  const oneMonthAgo = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());

  let activeData = [headers];
  let archiveData = [];

  for (let i = 1; i < data.length; i++) {
    const status = String(data[i][11]); // L列
    if (status.includes("済") || status.includes("完了")) {
      archiveData.push([...data[i], now]); 
    } else {
      activeData.push(data[i]);
    }
  }

  mainSheet.clearContents().getRange(1, 1, activeData.length, activeData[0].length).setValues(activeData);
  if (archiveData.length > 0) {
    historySheet.getRange(historySheet.getLastRow() + 1, 1, archiveData.length, archiveData[0].length).setValues(archiveData);
  }

  const histData = historySheet.getDataRange().getValues();
  const cleanHist = [histData[0]];
  for (let j = 1; j < histData.length; j++) {
    const archivedDate = new Date(histData[j][histData[j].length - 1]);
    if (archivedDate > oneMonthAgo) cleanHist.push(histData[j]);
  }
  historySheet.clearContents().getRange(1, 1, cleanHist.length, cleanHist[0].length).setValues(cleanHist);
}

function setupAllTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('importPMANCSVs').timeBased().everyHours(1).create();     
  ScriptApp.newTrigger('syncPrintSchedule').timeBased().everyMinutes(15).create(); 
  ScriptApp.newTrigger('importEquiosLog').timeBased().everyMinutes(15).create();   
  ScriptApp.newTrigger('archiveAndCleanupJobs').timeBased().everyDays(1).atHour(2).create(); 

  return "✅ 自動化トリガーの設定が完了しました！これでもう自動で巡回します。";
}