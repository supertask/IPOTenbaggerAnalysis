function getFinancialStatements(idToken, code) {
  try {
    var url = "https://api.jquants.com/v1/fins/statements?code=" + code;
    var options = {
      method: "get",
      headers: {
        Authorization: "Bearer " + idToken
      },
      muteHttpExceptions: true
    };
    var response = UrlFetchApp.fetch(url, options);
    var json = JSON.parse(response.getContentText());
    return json.statements;
  } catch (error) {
    Logger.log("Error getting financial statements for code " + code + ": " + error.message);
    return null;
  }
}

function getMinStockPrice(idToken, code) {
  var dailyQuotes = getStockPrices(idToken, code);
  if (!dailyQuotes || dailyQuotes.length === 0) return null;
  var closeParam = 'AdjustmentClose';
  var firstYearPrice = dailyQuotes.slice(0, Math.min(12 * 20, dailyQuotes.length));
  var minPrice = Math.min(...firstYearPrice.map(p => p[closeParam]).filter(p => p !== null));
  return minPrice;
}

function estimateIPOmarketCap(idToken, code) {
  var statements = getFinancialStatements(idToken, code);
  if (statements && statements.length > 0) {
    var shares = statements[statements.length - 1].NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock;
    var minPrice = getMinStockPrice(idToken, code);
    if (shares && minPrice) {
      return shares * minPrice;
    }
  }
  return null;
}

function updateSheetWithMarketCap() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var codeColumn = headers.indexOf("コード") + 1;
  var marketCapColumn = headers.indexOf("時価総額_上場1年以内（億円）") + 1;

  if (codeColumn === 0 || marketCapColumn === 0) {
    Logger.log("「コード」または「時価総額_上場1年以内（億円）」のヘッダーが見つかりませんでした。");
    return;
  }

  var range = sheet.getRange(2, codeColumn, sheet.getLastRow() - 1, 1);
  var values = range.getValues();
  var idToken = getIdToken(refreshToken);

  if (!idToken) {
    Logger.log("IDトークンの取得に失敗しました。");
    return;
  }

  for (var i = 0; i < values.length; i++) {
    //if (i > 10) { break; } //debug

    var code = values[i][0];
    if (code) {
      var marketCap = estimateIPOmarketCap(idToken, code);
      var marketCapOku = marketCap ? (marketCap / 10**8).toFixed(1) : "None";
      Logger.log("時価総額_上場1年以内（億円）: " +  marketCapOku);
      sheet.getRange(i + 2, marketCapColumn).setValue(marketCapOku);
    }
  }
}
