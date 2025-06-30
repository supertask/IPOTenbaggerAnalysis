# EDINETインクリメンタル更新システム

## 概要

EDINETからのデータダウンロードを最小限に抑える**インクリメンタル更新システム**を実装しました。

### 従来の問題
- ❌ 毎回10年分（約3,650日）のデータを全てダウンロード
- ❌ 週1回の制限下でキャッシュが古くなる問題
- ❌ 新しいIPO企業のデータが取得されない

### 新システムの利点
- ✅ **差分のみダウンロード**：前回更新以降の日付のみ取得
- ✅ **75%のダウンロード削減**：4週間運用で大幅削減
- ✅ **自動フォールバック**：エラー時は従来方式で安全に実行
- ✅ **データ整合性チェック**：更新後のデータを自動検証

## 使用方法

### 1. 基本的な使用

```python
from collectors.edinet_report_downloader import EdinetReportDownloader

# インクリメンタル更新で実行（デフォルト）
downloader = EdinetReportDownloader()
downloader.run()
```

### 2. モード切り替え

```python
# インクリメンタルモードを有効化（デフォルト）
downloader.enable_incremental_mode()

# 従来の全期間更新モードに切り替え
downloader.disable_incremental_mode()

# キャッシュ状態を確認
downloader.show_cache_status()
```

### 3. テストスクリプトの使用

```bash
# キャッシュ状態を確認
python3 test_incremental_update.py --status

# インクリメンタル更新をテスト実行
python3 test_incremental_update.py --test

# 強制的に全期間更新（緊急時）
python3 test_incremental_update.py --full
```

## 動作例

### 初回実行
```
🔄 インクリメンタル更新開始
📅 前回キャッシュ最新日: 2015-07-04
🆕 更新対象期間: 3651日間
📥 差分データダウンロード: 2015-07-04 ～ 2025-07-01
📊 初回作成: 15,432件
💾 保存完了: 15,432件 → incremental_doc_indexes.tsv.gz
✅ インクリメンタル更新完了
```

### 2回目実行（1週間後）
```
🔄 インクリメンタル更新開始
📅 前回キャッシュ最新日: 2025-07-01
🆕 更新対象期間: 7日間
📥 差分データダウンロード: 2025-07-02 ～ 2025-07-08
📊 既存データ: 15,432件 + 新規データ: 156件
💾 保存完了: 15,588件 → incremental_doc_indexes.tsv.gz
✅ インクリメンタル更新完了
```

## キャッシュファイル

- **インクリメンタルキャッシュ**: `data/output/edinet_db/edinet_codes/incremental_doc_indexes.tsv.gz`
- **従来キャッシュ**: `data/output/edinet_db/edinet_codes/10years_ago_to_0years_ago__doc_indexes.tsv.gz`

## 安全機能

### 1. 自動フォールバック
エラー発生時は自動的に従来の全期間更新に切り替わります。

### 2. データ整合性チェック
- データの存在確認
- 日付の連続性チェック
- 直近データの存在確認

### 3. デバッグ情報
詳細なログで動作状況を確認できます。

## トラブルシューティング

### Q: インクリメンタル更新でエラーが発生する
```bash
# 強制的に全期間更新を実行
python3 test_incremental_update.py --full
```

### Q: キャッシュの状態を確認したい
```bash
# キャッシュ状態を表示
python3 test_incremental_update.py --status
```

### Q: 一時的に従来方式で実行したい
```python
downloader = EdinetReportDownloader()
downloader.disable_incremental_mode()
downloader.run()
```

## 運用推奨設定

### 週1回の定期実行
```bash
# 毎週月曜日に実行（crontab例）
0 9 * * 1 cd /path/to/project && python3 test_incremental_update.py --test
```

### 緊急時の対応
```bash
# 問題が発生した場合の完全リセット
python3 test_incremental_update.py --full
```

## パフォーマンス比較

| 実行回数 | 従来方式 | インクリメンタル | 削減効果 |
|----------|----------|------------------|----------|
| 初回     | 3,650日分 | 3,650日分        | 0%       |
| 2週目    | 3,650日分 | 7日分            | 99.8%    |
| 3週目    | 3,650日分 | 7日分            | 99.8%    |
| 4週目    | 3,650日分 | 7日分            | 99.8%    |
| **合計** | **14,600日分** | **3,671日分** | **74.9%** |

## 設定の詳細

### EdinetReportDownloader.__init__()
```python
self.incremental_mode = True  # インクリメンタル更新を有効化
self.incremental_cache_file = "incremental_doc_indexes.tsv.gz"
```

この設定により、自動的にインクリメンタル更新が有効になります。 