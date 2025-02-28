var SHEET_NAMES = ["2015", "2016", "2017", "2018", "2019"];

function combineSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var combinedSheetName = SHEET_NAMES[0] + " ~ " + SHEET_NAMES[SHEET_NAMES.length - 1];
  var combinedSheet = ss.getSheetByName(combinedSheetName) || ss.insertSheet(combinedSheetName);

  // 先頭のシートのヘッダーを取得
  var headerRange = ss.getSheetByName(SHEET_NAMES[0]).getRange(1, 1, 1, ss.getSheetByName(SHEET_NAMES[0]).getLastColumn());
  var headers = headerRange.getValues()[0];
  
  // ヘッダーを新しいシートに設定
  combinedSheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  
  var combinedData = [];
  
  // 各シートのデータを取得
  for (var i = 0; i < SHEET_NAMES.length; i++) {
    var sheet = ss.getSheetByName(SHEET_NAMES[i]);
    var range = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn());
    var data = range.getValues();
    combinedData = combinedData.concat(data);
  }
  
  // データを新しいシートに設定
  combinedSheet.getRange(2, 1, combinedData.length, combinedData[0].length).setValues(combinedData);
}

