# インクリメンタル更新機能

## 概要

EDINETからの文書メタデータ取得を効率化するため、**インクリメンタル更新**機能を実装しました。

## 特徴

- ⚡ **高速化**：差分のみ取得で処理時間を大幅短縮
- 💾 **キャッシュ活用**：既存データを活用し無駄な通信を削減
- 🔄 **継続性**：中断されても次回実行時に継続可能
- 📊 **透明性**：詳細なログで実行状況を把握可能

## 基本的な使用方法

```python
from collectors.edinet_report_downloader import EdinetReportDownloader

# 通常の使用方法（自動的にインクリメンタル更新）
downloader = EdinetReportDownloader()
downloader.save_securities_reports()
```

## インクリメンタル更新の仕組み

### 1. キャッシュファイル
- `incremental_doc_indexes.tsv.gz`: 累積データを圧縮保存
- 初回実行時は過去10年分のデータを取得
- 2回目以降は前回実行日以降の差分のみ取得

### 2. 差分取得プロセス
1. **最新キャッシュ日の確認**
2. **不足期間の計算**
3. **差分データの取得**
4. **既存データとの結合**
5. **データ整合性チェック**

## 利用可能なメソッド

```python
# キャッシュ状況の確認
downloader.show_cache_status()
```

## パフォーマンス比較

| 実行回数 | インクリメンタル | 削減効果 |
|----------|------------------|----------|
| 初回実行 | 約30-60分 | - |
| 2回目以降 | 約1-5分 | 90%以上削減 |

## エラーハンドリング

データ整合性チェックでエラーが発生した場合、処理が中断されエラーメッセージが表示されます。

## FAQ

### Q: キャッシュファイルが破損した場合は？
```python
# キャッシュを削除して再実行
import os
cache_path = "data/output/edinet_db/edinet_codes/incremental_doc_indexes.tsv.gz"
if os.path.exists(cache_path):
    os.remove(cache_path)
```

### Q: 特定の日付からやり直したい場合は？
上記のキャッシュファイル削除と同様に、キャッシュを削除して再実行してください。

## 実装の詳細

### キャッシュファイル構造
```
data/output/edinet_db/edinet_codes/
└── incremental_doc_indexes.tsv.gz  # インクリメンタルキャッシュ
```

### データ形式
```tsv
date	edinet_code	docTypeCode	docID
2024-01-01	E12345	030	S1234567
2024-01-02	E67890	120	S7890123
```

## 注意事項

- 初回実行時は従来と同じ時間がかかります
- EDINET APIの制限に注意してください
- キャッシュファイルのサイズにご注意ください（年間数MB程度） 