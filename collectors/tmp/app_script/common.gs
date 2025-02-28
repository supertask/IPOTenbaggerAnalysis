const refreshToken = ScriptProperties.getProperty('JQUANTS_KEY');

function getIdToken(refreshToken) {
  try {
    var url = "https://api.jquants.com/v1/token/auth_refresh?refreshtoken=" + refreshToken;
    var options = {
      method: "post",
      muteHttpExceptions: true
    };
    var response = UrlFetchApp.fetch(url, options);
    var json = JSON.parse(response.getContentText());
    return json.idToken;
  } catch (error) {
    Logger.log("Error getting ID token: " + error.message);
    return null;
  }
}

function getStockPrices(idToken, code) {
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
    return json.daily_quotes;
  } catch (error) {
    Logger.log("Error getting stock prices for code " + code + ": " + error.message);
    return null;
  }
}