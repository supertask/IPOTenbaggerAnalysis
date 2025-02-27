// 定数の定義
const CEO_SHAREHOLDERS_MIN = 0.1;
const CEO_SHAREHOLDERS_MAX = 100.0;
const MARKET_CAP_THRESHOLD = 250;
const MULTIPLE_THRESHOLDS = [5, 7, 10]; // 5倍, 7倍, 10倍の閾値
const CEO_SHARE_RANGES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]; // 社長株%の範囲
const MARKET_CAP_RANGES = [0, 50, 100, 150, 200, 250, 300, 400, 500, 1000, Infinity]; // 時価総額の範囲
var SHEET_NAMES = ["2015", "2016", "2017", "2018", "2019"];
const TABLES_ROW = 35;


const BIG_INT = 9999999;
const NO_BAGGER_INDUSTRIES = [
  "家庭用品・個人用品", "娯楽", "ソフトウェア - インフラストラクチャ", "レジャー", "ツール・アクセサリー", "REIT - ホテル・モーテル", "信用サービス",
  "銀行 - 地域", "保険 - 生命", "レストラン", "出版", "工学・建設", "建材", "不動産 - 多様化", "人材派遣・雇用サービス", "REIT - 住宅", "石油・ガス精製・販売",
  "医療機器・用品", "特殊産業機械", "リゾート・カジノ", "電子機器・コンピュータ流通", "住宅建設", "REIT - 医療施設", "農産物", "資産運用", "住宅ローン金融",
  "REIT - 多様化", "REIT - 特殊", "フットウェア＆アクセサリー", "鉄道", "化学製品", "健康情報サービス", "医療施設", "資本市場", "食品流通", "食料品店", "旅行サービス",
  "REIT - 産業", "宿泊施設", "衣料品製造", "統合貨物・物流", "家具、備品、家電", "木材・木製品生産", "通信機器", "不動産開発", "高級品", "業務用機器・用品",
  "コンシューマーエレクトロニクス", "専門小売", "コンピュータハードウェア", "百貨店", "多様化保険", "紙・紙製品", "金属製造", "医療流通", "包装および容器",
  "レンタルおよびリースサービス", "セキュリティおよび保護サービス", "REIT - オフィス", "REIT - 小売"
];

const STRONG_INDUSTRIES = [
  "不動産_不動産サービス", //不動産の10倍株は結構簡単そう
  //"技術_情報技術サービス",
  //"産業_専門ビジネスサービス",
  //"通信サービス_インターネットコンテンツ・情報",
  //"ヘルスケア_バイオテクノロジー",
  //"産業_コンサルティングサービス",
  //"消費者防衛_教育・訓練サービス",
  //"通信サービス_広告代理店",
  //"技術_ソフトウェア - アプリケーション",
  //"通信サービス_電気通信サービス",
  //"ヘルスケア_医薬品メーカー - 専門・ジェネリック",
  //"消費者循環_個人サービス",
  //"消費者循環_衣料品小売",
  //"技術_電子部品",
  //"消費者循環_インターネット小売",
  //"技術_半導体",
  //"基礎材料_特殊化学品",
  //"消費者防衛_包装食品",
  //"消費者循環_自動車・トラック販売",
  //"産業_廃棄物管理",
  //"公共事業_再生可能エネルギー",
  //"産業_コングロマリット",
  //"通信サービス_電子ゲーム・マルチメディア"
];

function processCategoryData(data, categoryKey, nXStocksData, categoryYearsToNX, categoryNXCounts) {
  var categoryCounts = {};
  data.forEach(function(stock) { // 全体の会社数をカウント
    var categoryType = stock[categoryKey];
    
    if (categoryType in categoryCounts) {
      categoryCounts[categoryType]++;
    } else {
      categoryCounts[categoryType] = 1;
    }
  });

  nXStocksData.forEach(function(stock) {
    var categoryType = stock[categoryKey];

    if (!isNaN(stock.yearsToMultiple) && stock.yearsToMultiple !== "None") {
      if (categoryType in categoryNXCounts) {
        categoryNXCounts[categoryType]++;
      } else {
        categoryNXCounts[categoryType] = 1;
      }

      if (!categoryYearsToNX[categoryType]) {
        categoryYearsToNX[categoryType] = [];
      }
      categoryYearsToNX[categoryType].push(stock.yearsToMultiple);
    }
  });

  var categoryYearsToNXAvg = {};
  var categoryYearsToNXMedian = {};
  for (var category in categoryYearsToNX) {
    var years = categoryYearsToNX[category];
    var sum = years.reduce((a, b) => a + b, 0);
    var avg = sum / years.length;
    var median = calculateMedian(years);

    categoryYearsToNXAvg[category] = avg.toFixed(2);
    categoryYearsToNXMedian[category] = median.toFixed(2);
  }

  return {
    categoryCounts: categoryCounts,
    categoryYearsToNXAvg: categoryYearsToNXAvg,
    categoryYearsToNXMedian: categoryYearsToNXMedian
  };
}

function displayCategoryData(resultSheet, categoryData, categoryStatsRow, categoryLabelStartColumn, categoryChartValStartColunn) {
  // categoryDataのキーを取得し、必要なデータをペアにして配列に格納
  var data = Object.keys(categoryData.categoryCounts).map(function(category) {
    var categoryNXCount = categoryData.categoryNXCounts.hasOwnProperty(category) ? categoryData.categoryNXCounts[category] : 0;
    var ratio = (categoryNXCount / categoryData.categoryCounts[category] * 100).toFixed(1);
    return {
      category: category,
      ratio: ratio,
      categoryNXCount: categoryNXCount,
      categoryCount: categoryData.categoryCounts[category],
      avg: categoryData.categoryYearsToNXAvg[category] || BIG_INT,
      median: categoryData.categoryYearsToNXMedian[category] || BIG_INT
    };
  });

  // ratioに基づいてデータをソート
  data.sort(function(a, b) {
    return a.median - b.median; //return b.ratio - a.ratio;
  });

  // ソート済みデータをスプレッドシートに設定
  data.forEach(function(item, index) {
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryLabelStartColumn, 1, 1).setValue(item.category);
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryChartValStartColunn, 1, 1).setValue(item.ratio || "0");
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryChartValStartColunn + 1, 1, 1).setValue(Math.floor(item.categoryNXCount) || "0");
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryChartValStartColunn + 2, 1, 1).setValue(item.categoryCount || "0");
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryChartValStartColunn + 3, 1, 1).setValue(item.avg);
    resultSheet.getRange(categoryStatsRow + 1 + index, categoryChartValStartColunn + 4, 1, 1).setValue(item.median);
  });

  // 5倍まで何年（中央値）が書かれていない項目（-）を除外したデータを返す
  return data.filter(function(item) {
    return item.median !== BIG_INT;
  });
}
function generateConditionTable(resultSheet, N_BAGGER_THRESHOLD, marketCapThreshold, data, row) {

  // 全体の割合計算
  var totalStocks = data.length;
  var nXStocks = data.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var nXPercentage = ((nXStocks / totalStocks) * 100).toFixed(1);

  // 社長株%の割合計算
  var ceoFilterData = data.filter(function(stock) {
    return CEO_SHAREHOLDERS_MIN <= stock.ceoShare && stock.ceoShare <= CEO_SHAREHOLDERS_MAX;
  });
  var ceoNXStocks = ceoFilterData.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var ceoTotalStocks = ceoFilterData.length;
  var ceoNXPercentage = ((ceoNXStocks / ceoTotalStocks) * 100).toFixed(1);

  // 時価総額の割合計算
  var marketCapFilterData = data.filter(function(stock) {
    return stock.marketCap <= marketCapThreshold;
  });
  var marketCapNXStocks = marketCapFilterData.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var marketCapTotalStocks = marketCapFilterData.length;
  var marketCapNXPercentage = ((marketCapNXStocks / marketCapTotalStocks) * 100).toFixed(1);

  // ノーバガー産業を除く
  var noBaggerFilterData = data.filter(function(stock) {
    return !NO_BAGGER_INDUSTRIES.includes(stock.industry);
  });
  var noBaggerNXStocks = noBaggerFilterData.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var noBaggerTotalStocks = noBaggerFilterData.length;
  var noBaggerNXPercentage = ((noBaggerNXStocks / noBaggerTotalStocks) * 100).toFixed(1);

  // 「不動産 - 多様化」かつ「不動産サービス」
  var realEstateFilterData = data.filter(function(stock) {
    return stock.industry === "不動産 - 多様化" || stock.industry === "不動産サービス";
  });
  var realEstateNXStocks = realEstateFilterData.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var realEstateTotalStocks = realEstateFilterData.length;
  var realEstateNXPercentage = ((realEstateNXStocks / realEstateTotalStocks) * 100).toFixed(1);

  // 「インターネットコンテンツ・情報」かつ「ソフトウェア - アプリケーション」
  var adSoftwareFilterData = data.filter(function(stock) {
    return stock.industry === "インターネットコンテンツ・情報" || stock.industry === "ソフトウェア - アプリケーション";
  });
  var adSoftwareNXStocks = adSoftwareFilterData.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var adSoftwareTotalStocks = adSoftwareFilterData.length;
  var adSoftwareNXPercentage = ((adSoftwareNXStocks / adSoftwareTotalStocks) * 100).toFixed(1);

  // 条件を組み合わせた割合計算
  var combinedFilterData1 = data.filter(function(stock) {
    return CEO_SHAREHOLDERS_MIN <= stock.ceoShare && stock.ceoShare <= CEO_SHAREHOLDERS_MAX
      && stock.marketCap <= marketCapThreshold;
  });
  var combinedNXStocks1 = combinedFilterData1.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var combinedTotalStocks1 = combinedFilterData1.length;
  var combinedNXPercentage1 = ((combinedNXStocks1 / combinedTotalStocks1) * 100).toFixed(1);

  var combinedFilterData2 = combinedFilterData1.filter(function(stock) {
    return !NO_BAGGER_INDUSTRIES.includes(stock.industry);
  });
  var combinedNXStocks2 = combinedFilterData2.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var combinedTotalStocks2 = combinedFilterData2.length;
  var combinedNXPercentage2 = ((combinedNXStocks2 / combinedTotalStocks2) * 100).toFixed(1);

  var combinedFilterData3 = combinedFilterData2.filter(function(stock) {
    return stock.industry === "不動産 - 多様化" || stock.industry === "不動産サービス";
  });
  var combinedNXStocks3 = combinedFilterData3.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var combinedTotalStocks3 = combinedFilterData3.length;
  var combinedNXPercentage3 = ((combinedNXStocks3 / combinedTotalStocks3) * 100).toFixed(1);

  var combinedFilterData4 = combinedFilterData2.filter(function(stock) {
    return stock.industry === "インターネットコンテンツ・情報" || stock.industry === "ソフトウェア - アプリケーション";
  });
  var combinedNXStocks4 = combinedFilterData4.filter(function(stock) {
    return stock.maxMultiple >= N_BAGGER_THRESHOLD;
  }).length;
  var combinedTotalStocks4 = combinedFilterData4.length;
  var combinedNXPercentage4 = ((combinedNXStocks4 / combinedTotalStocks4) * 100).toFixed(1);

  // 結果をシートに表示
  resultSheet.appendRow(["", "条件", N_BAGGER_THRESHOLD + "倍株 %"]);
  resultSheet.appendRow(["", "全体", nXPercentage]);
  resultSheet.appendRow(["条件①", CEO_SHAREHOLDERS_MIN + " <= 社長株 % <= " + CEO_SHAREHOLDERS_MAX, ceoNXPercentage]);
  resultSheet.appendRow(["条件②", "時価総額_上場1年以内 <= " + marketCapThreshold + "億円", marketCapNXPercentage]);
  resultSheet.appendRow(["条件③", "ノーバガー産業を除く", noBaggerNXPercentage]);
  resultSheet.appendRow(["条件④", "「不動産 - 多様化」かつ「不動産サービス」", realEstateNXPercentage]);
  resultSheet.appendRow(["条件⑤", "「インターネットコンテンツ・情報」かつ「ソフトウェア - アプリケーション」", adSoftwareNXPercentage]);
  resultSheet.appendRow(["", "条件 ①と②", combinedNXPercentage1]);
  resultSheet.appendRow(["", "条件 ①と②と③", combinedNXPercentage2]);
  resultSheet.appendRow(["", "条件 ①と②と③と④", combinedNXPercentage3]);
  resultSheet.appendRow(["", "条件 ①と②と③と⑤", combinedNXPercentage4]);
}



function analyzeStocks() {

  // スプレッドシートの取得
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  MULTIPLE_THRESHOLDS.forEach(function(N_BAGGER_THRESHOLD, index) {
    // 各N倍株用のシートを作成
    var outputSheetName = "集計" + N_BAGGER_THRESHOLD + "倍株";
    var resultSheet = ss.getSheetByName(outputSheetName) || ss.insertSheet(outputSheetName);
    resultSheet.clear();
    resultSheet.getCharts().forEach(function(chart) {
      resultSheet.removeChart(chart);
    });

    var data = [];

    // 各シートからデータを取得
    SHEET_NAMES.forEach(function(sheetName) {
      var sheet = ss.getSheetByName(sheetName);
      if (!sheet) return;

      var values = sheet.getDataRange().getValues();
      var headers = values[0];
      var codeIndex = headers.indexOf("コード");
      var maxMultipleIndex = headers.indexOf("最大何倍株");
      var ceoShareIndex = headers.indexOf("社長株%");
      var marketCapIndex = headers.indexOf("時価総額_上場1年以内（億円）");
      var sectorIndex = headers.indexOf("Sector");
      var industryIndex = headers.indexOf("Industry");
      var yearsToMultipleIndex = headers.indexOf("5,7,10,N倍まで何年");

      for (var i = 1; i < values.length; i++) {
        var row = values[i];
        if (row[codeIndex]) { // コード列が空でない場合
          var yearsToMultiple = row[yearsToMultipleIndex].split('\n').map(parseFloat);
          data.push({
            maxMultiple: row[maxMultipleIndex],
            ceoShare: row[ceoShareIndex],
            marketCap: row[marketCapIndex],
            sector: row[sectorIndex],
            industry: row[industryIndex],
            yearsToMultiple: yearsToMultiple[index] // 適切な倍率までの年数
          });
        }
      }
    });

    //N倍株になる確率を出力する
    generateConditionTable(resultSheet, N_BAGGER_THRESHOLD, MARKET_CAP_THRESHOLD, data, 2);

    // 社長株%の範囲ごとの割合を計算
    var ceoShareDistribution = new Array(CEO_SHARE_RANGES.length - 1).fill(0);
    var nXStocksData = data.filter(function(stock) {
      return stock.maxMultiple >= N_BAGGER_THRESHOLD;
    });

    nXStocksData.forEach(function(stock) {
      for (var i = 0; i < CEO_SHARE_RANGES.length - 1; i++) {
        if (stock.ceoShare >= CEO_SHARE_RANGES[i] && stock.ceoShare < CEO_SHARE_RANGES[i + 1]) {
          ceoShareDistribution[i]++;
          break;
        }
      }
    });

    ceoShareDistribution = ceoShareDistribution.map(function(count) {
      return count;
    });

    // 結果をシートに表示（既存の表と2列間隔をあける）
    var ceoHoldingRow = TABLES_ROW;
    var ceoLabelStartColumn = resultSheet.getLastColumn() + 2;
    var ceoChartValStartColunn = ceoLabelStartColumn + 1;
    resultSheet.getRange(ceoHoldingRow, ceoLabelStartColumn, 1, 1).setValue("社長株保有率別");
    resultSheet.getRange(ceoHoldingRow + 1, ceoLabelStartColumn, CEO_SHARE_RANGES.length - 1, 1).setValues(CEO_SHARE_RANGES.slice(1).map(function(range, i) {
      return [[CEO_SHARE_RANGES[i] + " ~ " + range + "%"]];
    }));
    resultSheet.getRange(ceoHoldingRow + 1, ceoChartValStartColunn, CEO_SHARE_RANGES.length - 1, 1).setValues(ceoShareDistribution.map(function(value) {
      return [value];
    }));

    // 時価総額別の範囲ごとの割合を計算
    var marketCapDistribution = new Array(MARKET_CAP_RANGES.length - 1).fill(0);

    nXStocksData.forEach(function(stock) {
      for (var i = 0; i < MARKET_CAP_RANGES.length - 1; i++) {
        if (stock.marketCap >= MARKET_CAP_RANGES[i] && stock.marketCap < MARKET_CAP_RANGES[i + 1]) {
          marketCapDistribution[i]++;
          break;
        }
      }
    });

    marketCapDistribution = marketCapDistribution.map(function(count) {
      return count;
    });

    // 時価総額別の結果をシートに表示
    var marketCaptialRow = ceoHoldingRow;
    var capitalLabelStartColumn = resultSheet.getLastColumn() + 2;
    var capitalChartValStartColunn = capitalLabelStartColumn + 1;
    resultSheet.getRange(marketCaptialRow, capitalLabelStartColumn, 1, 1).setValue("時価総額別");
    resultSheet.getRange(marketCaptialRow + 1, capitalLabelStartColumn, MARKET_CAP_RANGES.length - 1, 1).setValues(MARKET_CAP_RANGES.slice(1).map(function(range, i) {
      return [[MARKET_CAP_RANGES[i] + " ~ " + (range === Infinity ? "以上" : range + "億")]];
    }));
    resultSheet.getRange(marketCaptialRow + 1, capitalChartValStartColunn, MARKET_CAP_RANGES.length - 1, 1).setValues(marketCapDistribution.map(function(value) {
      return [value];
    }));

    // Sector別の範囲ごとの割合を計算
    var sectorYearsToNX = {};
    var sectorNXCounts = {};
    var sectorData = processCategoryData(data, 'sector', nXStocksData, sectorYearsToNX, sectorNXCounts);

    // Sector別の結果をシートに表示
    var sectorStatsRow = ceoHoldingRow;
    var sectorLabelStartColumn = resultSheet.getLastColumn() + 2;
    var sectorChartValStartColunn = sectorLabelStartColumn + 1;
    resultSheet.getRange(sectorStatsRow, sectorChartValStartColunn, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍の会社割合（％）");
    resultSheet.getRange(sectorStatsRow, sectorChartValStartColunn + 1, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍になる会社数");
    resultSheet.getRange(sectorStatsRow, sectorChartValStartColunn + 2, 1, 1).setValue("会社数");
    resultSheet.getRange(sectorStatsRow, sectorChartValStartColunn + 3, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍まで何年（平均）");
    resultSheet.getRange(sectorStatsRow, sectorChartValStartColunn + 4, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍まで何年（中央値）");

    var filteredSectorData = displayCategoryData(resultSheet, { categoryCounts: sectorData.categoryCounts, categoryNXCounts: sectorNXCounts, categoryYearsToNXAvg: sectorData.categoryYearsToNXAvg, categoryYearsToNXMedian: sectorData.categoryYearsToNXMedian }, sectorStatsRow, sectorLabelStartColumn, sectorChartValStartColunn);

    // Industry別の範囲ごとの割合を計算
    var industryYearsToNX = {};
    var industryNXCounts = {};
    var industryData = processCategoryData(data, 'industry', nXStocksData, industryYearsToNX, industryNXCounts);

    // Industry別の結果をシートに表示
    var industryRow = ceoHoldingRow;
    var industryLabelStartColumn = resultSheet.getLastColumn() + 2;
    var industryChartValStartColunn = industryLabelStartColumn + 1;
    resultSheet.getRange(industryRow, industryLabelStartColumn, 1, 1).setValue("Industry別");
    resultSheet.getRange(industryRow + 1, industryLabelStartColumn, Object.keys(industryData.categoryCounts).length, 1).setValues(Object.keys(industryData.categoryCounts).map(function(value) {
      return [value];
    }));

    resultSheet.getRange(industryRow + 1, industryChartValStartColunn, Object.keys(industryData.categoryCounts).length, 1).setValues(Object.keys(industryData.categoryCounts).map(function(key) {
      return [industryData.categoryCounts[key]];
    }));

    var industryStatsRow = industryRow;
    resultSheet.getRange(industryStatsRow, industryChartValStartColunn, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍の会社割合（％）");
    resultSheet.getRange(industryStatsRow, industryChartValStartColunn + 1, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍になる会社数");
    resultSheet.getRange(industryStatsRow, industryChartValStartColunn + 2, 1, 1).setValue("会社数");
    resultSheet.getRange(industryStatsRow, industryChartValStartColunn + 3, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍まで何年（平均）");
    resultSheet.getRange(industryStatsRow, industryChartValStartColunn + 4, 1, 1).setValue(N_BAGGER_THRESHOLD + "倍まで何年（中央値）");

    var filteredIndustryData = displayCategoryData(resultSheet, { categoryCounts: industryData.categoryCounts, categoryNXCounts: industryNXCounts, categoryYearsToNXAvg: industryData.categoryYearsToNXAvg, categoryYearsToNXMedian: industryData.categoryYearsToNXMedian }, industryStatsRow, industryLabelStartColumn, industryChartValStartColunn);

    createPieChart(resultSheet, "社長株保有率別", ceoHoldingRow + 1, ceoLabelStartColumn, ceoShareDistribution.length, 1, ceoLabelStartColumn);
    createPieChart(resultSheet, "時価総額別", marketCaptialRow + 1, capitalLabelStartColumn, marketCapDistribution.length, 15, ceoLabelStartColumn);

    createBarChart(resultSheet, "Sector別", N_BAGGER_THRESHOLD, filteredSectorData, sectorStatsRow + 1, sectorLabelStartColumn, 700, 500);
    createBarChart(resultSheet, "Industry別", N_BAGGER_THRESHOLD, filteredIndustryData, industryRow + 1, industryLabelStartColumn, 1250, 700);
  });
}


function createBarChart(sheet, title, nBaggerThreshold, filteredData, row, column, width, height) {
  //Logger.log("length: " + filteredData.length);

  var labelRange = sheet.getRange(row, column, filteredData.length, 1);
  var ratioRange = sheet.getRange(row, column + 1, filteredData.length, 1);
  var medianRange = sheet.getRange(row, column + 5, filteredData.length, 1);

  // グラフの作成
  var chart = sheet.newChart()
    .setChartType(Charts.ChartType.COLUMN) // 縦の棒グラフに変更
    .addRange(labelRange)
    .addRange(medianRange)
    .addRange(ratioRange)
    .setPosition(1, column, 0, 0) // セルの参照を使用して位置を設定
    .setOption('title', title)
    .setOption('width', width) // 幅を設定
    .setOption('height', height) // 高さを設定
    .setOption('legend', {position: 'top', fontSize: 11 })
    .setOption('vAxes', {
      0: { title: 'Years', minValue: 0, maxValue: 7 },  // 左軸（5倍まで何年（中央値））
      1: { title: 'Percentage', minValue: 0, maxValue: 75 } // 右軸（5倍の会社割合（％））
    })
    .setOption('series', {
      0: { targetAxisIndex: 0, color: 'blue', labelInLegend: nBaggerThreshold + '倍まで何年（中央値）' }, // 凡例に名前を設定
      1: { targetAxisIndex: 1, color: 'red', labelInLegend: nBaggerThreshold + '倍の会社割合（％）' }
    })
    .setOption('hAxis', {
      title: title.split(" ")[0],
      slantedText: true,
      slantedTextAngle: 45, // X軸のテキストを45度傾ける
      textStyle: { fontSize: 11 } // テキストのサイズを変更
    })
    //.setOption('hAxis', { title: title.split(" ")[0] }) // X軸のタイトルを設定
    .build();

  sheet.insertChart(chart);
}

function createPieChart(sheet, title, row, column, length, visualizeRow, visualizeColumn) {
  // グラフの作成
  var range = sheet.getRange(row, column, length, 2); // ラベルと値の範囲を選択

  var chart = sheet.newChart()
    .setChartType(Charts.ChartType.PIE)
    .addRange(range)
    .setPosition(visualizeRow, visualizeColumn, 0, 0) // セルの参照を使用して位置を設定
    .setOption('title', title)
    .setOption('width', 500) // 幅を設定
    .setOption('height', 270) // 高さを設定
    .build();

  sheet.insertChart(chart);
}

function calculateMedian(values) {
  values.sort(function(a, b) {
    return a - b;
  });
  var half = Math.floor(values.length / 2);

  if (values.length % 2) {
    return values[half];
  } else {
    return (values[half - 1] + values[half]) / 2.0;
  }
}
