// 過去何年分の決算データを参考にするか
var FINANCE_CHECK_YEARS = 3;
var CAPITAL_THRESHOLD = 250;  // 時価総額閾値
var CEO_STOCK_THRESHOLD = 10;  // 社長株比率閾値
var FINANCE_VALUE_EPSILON = 0.05; //決算の右肩上がりかを判定する際の誤差(0.0 ~ 1.0)


//最後の決算を取得
function getLastValue(data) {
  var keys = Object.keys(data);
  keys.sort();
  return data[keys[keys.length - 1]];
}

//業績が右肩上がりか
function countIncreasingYears(data, yearsToCheck, normalizedTolerance) {
  var keys = Object.keys(data);
  keys.sort(); // 年月順に並べる
  
  var newerYearValue = null;
  var increasingStreak = 1;  // 連続増加年数

  //未来から過去の決算の順で見る
  for (var i = keys.length - 1; i >= 0; i--) {
    var key = keys[i];
    var yearValue = data[key];
    
    if (yearValue == null || yearValue == "") continue;
    
    if (newerYearValue != null) {
      var toleranceValue = newerYearValue * normalizedTolerance;
      if (yearValue <= newerYearValue + toleranceValue) {
        increasingStreak++;
      } else {
        break;
      }
    }
    
    newerYearValue = yearValue;
  }
  
  return increasingStreak;
}

//業績が右肩下がりか
function countDecreasingYears(data, yearsToCheck, normalizedTolerance) {
  var keys = Object.keys(data);
  keys.sort(); // 年月順に並べる
  
  var newerYearValue = null;
  var decreasingStreak = 1;  // 連続減少年数

  //未来から過去の決算の順で見る
  for (var i = keys.length - 1; i >= 0; i--) {
    var key = keys[i];
    var yearValue = data[key];
    
    if (yearValue == null || yearValue == "") continue;
    
    if (newerYearValue != null) {
      var toleranceValue = yearValue * normalizedTolerance;
      if (newerYearValue <= yearValue + toleranceValue) {
        decreasingStreak++;
      } else {
        break;
      }
    }
    
    newerYearValue = yearValue;
  }
  
  return decreasingStreak;
}

//
// テンバガー指標とノーバガー指標の計算
//
function calculateTenBaggerIndicators() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var range = sheet.getDataRange();
  var values = range.getValues();
  
  var headerRow = values[0];
  var numRows = values.length;
  var numCols = headerRow.length;

  // ヘッダーを検索して列インデックスを取得
  var dataStartCol = -1;
  var tenBaggerCol = -1;
  var noBaggerCol = -1;
  var shareholdersCol = -1;
  var marketCapCol = -1;
  
  for (var j = 0; j < numCols; j++) {
    if (headerRow[j] == "企業業績のデータ（5年分）") {
      dataStartCol = j;
    } else if (headerRow[j] == "テンバガー指標") {
      tenBaggerCol = j;
    } else if (headerRow[j] == "ノーバガー指標") {
      noBaggerCol = j;
    } else if (headerRow[j] == "株主名と比率") {
      shareholdersCol = j;
    } else if (headerRow[j] == "想定時価総額（億円）") {
      marketCapCol = j;
    }
  }
  
  if (dataStartCol == -1 || tenBaggerCol == -1 || noBaggerCol == -1 || shareholdersCol == -1 || marketCapCol == -1) {
    Browser.msgBox("必要なヘッダーが見つかりません。");
    return;
  }
  
  for (var i = 1; i < numRows; i++) {
    var performanceDataJson = values[i][dataStartCol];
    var shareholdersDataJson = values[i][shareholdersCol];
    var marketCapital = values[i][marketCapCol];
    //Logger.log(i + ": " + performanceDataJson);

    if (!performanceDataJson || performanceDataJson.trim() === "") {
      Logger.log("企業業績のデータ（5年分）が空です。i=" + i + "numRows: " + numRows);
      break;
    }
    
    var performanceData;
    try {
      performanceData = JSON.parse(performanceDataJson);
    } catch (e) {
      Logger.log("Invalid JSON in row " + (i + 1) + ": " + performanceDataJson);
      sheet.getRange(i + 1, tenBaggerCol + 1).setValue("JSON Error");
      continue;
    }

    Logger.log(performanceDataJson);

    var ceoStockRatio = 0;
    try {
      var shareholdersData = JSON.parse(shareholdersDataJson);
      shareholdersData.forEach(function(shareholder) {
        if (shareholder.isCEO) {
          ceoStockRatio = shareholder.比率;
        }
      });
    } catch (e) {
      Logger.log("Invalid JSON in row " + (i + 1) + ": " + shareholdersDataJson);
    }
    
    var tenBaggerIndicators = [];
    var noBaggerIndicators = [];
    
    performanceData.forEach(function(data) {
      for (var key in data) {
        var increasingYears = countIncreasingYears(data[key], FINANCE_CHECK_YEARS, FINANCE_VALUE_EPSILON);
        var decreasingYears = countDecreasingYears(data[key], FINANCE_CHECK_YEARS, 0);
        
        if (key == "売上高（百万円）") {
          if (increasingYears >= FINANCE_CHECK_YEARS) {
            tenBaggerIndicators.push("売上" + increasingYears + "年連続↗︎");
          }
          if (decreasingYears >= FINANCE_CHECK_YEARS) {
            noBaggerIndicators.push("売上" + decreasingYears + "年連続↘︎");
          }
        }
        if (key == "経常利益（百万円）") {
          if (increasingYears >= FINANCE_CHECK_YEARS) {
            tenBaggerIndicators.push("経常利益" + increasingYears + "年連続↗︎");
          }
          if (decreasingYears >= FINANCE_CHECK_YEARS) {
            noBaggerIndicators.push("経常利益" + decreasingYears + "年連続↘︎");
          }
          // 最後の決算が赤字かどうかをチェック
          var lastValue = getLastValue(data[key]);
          if (lastValue < 0) {
            noBaggerIndicators.push("経常利益赤字");
          }
        }
        if (key == "当期純利益（百万円）") {
          if (increasingYears >= FINANCE_CHECK_YEARS) {
            tenBaggerIndicators.push("純利益" + increasingYears + "年連続↗︎");
          }
          if (decreasingYears >= FINANCE_CHECK_YEARS) {
            noBaggerIndicators.push("純利益" + decreasingYears + "年連続↘︎");
          }
          // 最後の決算が赤字かどうかをチェック
          var lastValue = getLastValue(data[key]);
          if (lastValue < 0) {
            noBaggerIndicators.push("純利益赤字");
          }
        }
      }
    });


    // 時価総額判定
    if (marketCapital <= CAPITAL_THRESHOLD) {
      tenBaggerIndicators.push("時価" + CAPITAL_THRESHOLD + "億↓");
    }

    // 社長株比率判定
    if (ceoStockRatio > CEO_STOCK_THRESHOLD) {
      tenBaggerIndicators.push("社長株" + ceoStockRatio + "%↑");
    }

    sheet.getRange(i + 1, tenBaggerCol + 1).setValue(tenBaggerIndicators.join("\n"));
    sheet.getRange(i + 1, noBaggerCol + 1).setValue(noBaggerIndicators.join("\n"));

  }
  
  Logger.log("テンバガー指標の計算が完了しました。");
}



function parseAndFormatData() {
  //highlightRows();

  calculateTenBaggerIndicators();

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  // 「企業業績のデータ（5年分）」, 「決算」, 「決算伸び率%」 の列番号を取得
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const shareholderColumn = headers.indexOf("企業業績のデータ（5年分）") + 1;
  const decisionColumn = headers.indexOf("決算") + 1;
  const decisionPercentColumn = headers.indexOf("決算伸び率%") + 1;
  
  if (shareholderColumn === 0 || decisionColumn === 0 || decisionPercentColumn === 0) {
    Logger.log("「企業業績のデータ（5年分）」または「決算」または「決算伸び率%」のヘッダーが見つかりませんでした。");
    return;
  }

  const dataRange = sheet.getRange(2, shareholderColumn, sheet.getLastRow() - 1, 1);
  const dataValues = dataRange.getValues();
  const resultColumn = sheet.getRange(2, decisionColumn, sheet.getLastRow() - 1, 1);
  const resultPercentColumn = sheet.getRange(2, decisionPercentColumn, sheet.getLastRow() - 1, 1);
  
  const keysToInclude = ["売上高（百万円）", "経常利益（百万円）", "当期純利益（百万円）"];
  
  let result = [];
  let resultPercent = [];
  let maxColumnWidths = {};

  // Calculate maximum width for each column
  dataValues.forEach((row) => {
    if (row[0]) {
      const jsonData = JSON.parse(row[0]);
      jsonData.forEach((item) => {
        for (let key in item) {
          if (keysToInclude.includes(key)) {
            const dates = Object.keys(item[key]);
            dates.forEach((date, colIndex) => {
              const value = item[key][date] !== undefined && item[key][date] !== null ? item[key][date].toString() : "-";
              if (!maxColumnWidths[colIndex] || value.length > maxColumnWidths[colIndex]) {
                maxColumnWidths[colIndex] = value.length;
              }
            });
          }
        }
      });
    }
  });

  // Create formatted strings
  dataValues.forEach((row) => {
    if (row[0]) {
      const jsonData = JSON.parse(row[0]);
      let formattedString = "";
      let percentageString = "";

      jsonData.forEach((item) => {
        for (let key in item) {
          if (keysToInclude.includes(key)) {
            formattedString += key + "\t";
            const dates = Object.keys(item[key]);
            let previousValue = null;
            let percentageLine = "\t";
            
            dates.forEach((date, colIndex) => {
              let value = item[key][date] !== undefined && item[key][date] !== null ? item[key][date].toString() : "-";
              value = value.padEnd(maxColumnWidths[colIndex], ' '); // Pad with spaces
              formattedString += value + "\t";
              
              if (previousValue !== null && item[key][date] !== null) {
                const percentageIncrease = ((item[key][date] - previousValue) / Math.abs(previousValue)) * 100;
                percentageLine += Math.round(percentageIncrease).toString() + "%\t";
              } else {
                percentageLine += "None\t"; // Placeholder value for initial year
              }
              
              previousValue = item[key][date];
            });
            formattedString = formattedString.trim() + "\t\n";
            percentageString += percentageLine.trim() + "\n";
          }
        }
      });

      result.push([formattedString.trim()]);
      resultPercent.push([percentageString.trim()]);
    } else {
      result.push([""]);
      resultPercent.push([""]);
    }
  });

  resultColumn.setValues(result);
  resultPercentColumn.setValues(resultPercent);
}

