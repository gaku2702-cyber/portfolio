// =========================================================
// config.gs
// 役割：システム全体の設定値。秘匿情報はプロパティストアから取得
// =========================================================

const CONFIG = (function() {
  // スクリプトプロパティ（金庫）を開ける
  const props = PropertiesService.getScriptProperties();
  
  return {
    // 金庫から値を取り出す（設定されていなければ空文字）
    CHAT_WEBHOOK_URL: props.getProperty('CHAT_WEBHOOK_URL') || "",
    FOLDER_ID_PMAN: props.getProperty('FOLDER_ID_PMAN') || "",
    FOLDER_ID_EQUIOS: props.getProperty('FOLDER_ID_EQUIOS') || "1aiemDc8xI5IB_hgm7doPt94AA0Dszfow", // 必要に応じてプロパティへ

    // シート名は構成が漏れても直接的な危険はないためそのまま
    SHEET: {
      LOG: 'Log',
      STAFF: 'Staff_master',
      DAILY_REPORT: 'App_Daily_Report',
      MACHINE_MAP: 'M_Machine_Map',
      DEPT_MAP: 'M_Department_Map',
      BACKUP_CSV: 'Backup_CSV',
      HISTORY: 'History_Completed'
    },

    DEFAULT_USER: { name: "未登録", department: "未分類", section: "未分類", staffId: "0000" }
  };
})();