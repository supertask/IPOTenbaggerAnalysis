function getEarningsPerShare(code, idToken) {
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
    var statements = json.statements;
    if (statements && statements.length > 0) {
      var earningsPerShare = statements[statements.length - 1].EarningsPerShare;
      return earningsPerShare;
    } else {
      return null;
    }
  } catch (error) {
    Logger.log("Error getting earnings per share for code " + code + ": " + error.message);
    return null;
  }
}

function getLatestStockPrice(code, idToken) {
  try {
    var url = "https://api.jquants.com/v1/prices/daily_quotes?code=" + code;
    var options = {
      method: "get",
      headers: {
        Authorization: "Bearer " + idToken
      },
      muteHttpExceptions: true
    };
    var response = UrlFetchApp.fetch(url, options);
    var json = JSON.parse(response.getContentText());
    var dailyQuotes = json.daily_quotes;
    if (dailyQuotes && dailyQuotes.length > 0) {
      var latestStockPrice = dailyQuotes[dailyQuotes.length - 1].Close;
      return latestStockPrice;
    } else {
      return null;
    }
  } catch (error) {
    Logger.log("Error getting latest stock price for code " + code + ": " + error.message);
    return null;
  }
}


function updateSheetWithPER() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var codeColumn = headers.indexOf("コード") + 1;
  var PERColumn = headers.indexOf("PER") + 1;

  if (codeColumn === 0 || PERColumn === 0) {
    Logger.log("「コード」または「PER」のヘッダーが見つかりませんでした。");
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
      var earningsPerShare = getEarningsPerShare(code, idToken);
      var latestStockPrice = getLatestStockPrice(code, idToken);

      if (earningsPerShare !== null && latestStockPrice !== null) {
        var per = (latestStockPrice / earningsPerShare).toFixed(1);
        sheet.getRange(i + 2, PERColumn).setValue(per);
      } else {
        sheet.getRange(i + 2, PERColumn).setValue("None");
      }
    }
  }
}
