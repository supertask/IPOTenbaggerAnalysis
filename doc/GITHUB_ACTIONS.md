# GitHub Actions ワークフロー

## 概要

IPOデータ収集を自動化するワークフローを提供しています：

**data-collection-split.yml** - 処理を分割して段階的に実行

## 🚨 事前準備（重要）

### 必須環境変数の設定

GitHubリポジトリの **Settings > Secrets and variables > Actions** で以下のシークレットを設定してください：

```yaml
# 必須
EDINET_API_KEY: EDINETのAPIキー

# オプション（AI要約機能を使用する場合）
GROQ_API_KEY: GroqのAPIキー
```

**EDINET_API_KEY がないと処理が失敗します！**

### APIキーの取得方法

1. **EDINET API**: 
   - [EDINET公式サイト](https://disclosure.edinet-fsa.go.jp/)でAPIキーを申請
   - 無料で利用可能

2. **Groq API** (オプション):
   - [Groq Console](https://console.groq.com/)でアカウント作成
   - AI要約機能でのみ使用（現在はコメントアウト済み）

## ワークフローの特徴

### 分割実行ワークフロー (`data-collection-split.yml`)

- **実行タイミング**: 毎週日曜日午前1時（JST 10時）から段階的
- **タグトリガー**: `data-collection-split-*`
- **特徴**: 処理を3段階に分割（最適化済み）
  1. **基礎データ収集** (60分): list, details, traders, yfinance
  2. **分析処理** (30分): comparison（証券会社スクレイピング）
  3. **レポート生成** (180分): edinet, combiner

## 実行方法

### 定期実行
自動で毎週日曜日に実行されます。特に設定は不要です。

### タグによる手動実行

```bash
# 手動実行を trigger
git tag data-collection-split-$(date +%Y%m%d)
git push origin data-collection-split-$(date +%Y%m%d)
```

### GitHub UIからの手動実行

1. GitHubリポジトリの「Actions」タブへ移動
2. 実行したいワークフローを選択
3. 「Run workflow」ボタンをクリック
4. ブランチを選択して実行

### 部分実行オプション

手動実行時に特定の処理のみを実行可能です：

- `basic`: 基礎データ収集のみ（list, details, traders, yfinance）
- `analysis`: 分析処理のみ（comparison）
- `reports`: レポート生成のみ（edinet, combiner）
- `all`: 全ての処理（デフォルト）

## 環境変数の詳細設定

上記の必須設定に加えて、追加の環境変数が必要な場合：

```yaml
# カスタム設定例
CUSTOM_API_KEY: カスタムAPIキー
LOG_LEVEL: DEBUG  # ログレベルの調整
```

## 出力結果の確認

### Artifacts

実行完了後、以下のartifactsがダウンロード可能です：

- `basic-collection-{run_number}`: 基礎データ収集の結果（7日保持）
- `analysis-collection-{run_number}`: 分析処理の結果（7日保持）
- `final-results-{run_number}`: 最終統合結果（30日保持）

### ログの確認

1. GitHubの「Actions」タブから実行したワークフローをクリック
2. 各ステップのログを確認可能
3. 実行サマリーでファイル数やエラー情報を確認

## トラブルシューティング

### よくある問題

1. **実行時間超過**
   - 各ジョブは最適化済み（60分/30分/180分）
   - 必要に応じてタイムアウト時間を調整

2. **メモリ不足**
   - 処理対象データの量を確認
   - キャッシュの活用を検討

3. **外部API制限**
   - レート制限に注意
   - リトライ機能の実装を検討

4. **Playwright関連エラー**
   - Ubuntu環境での依存関係不足
   - `playwright install-deps` で解決

### エラー対応

1. **失敗したワークフローの再実行**
   ```bash
   # 同じタグで再実行
   git tag -d data-collection-split-$(date +%Y%m%d)
   git push origin :refs/tags/data-collection-split-$(date +%Y%m%d)
   git tag data-collection-split-$(date +%Y%m%d)
   git push origin data-collection-split-$(date +%Y%m%d)
   ```

2. **部分的な再実行**
   - 手動実行時にjob_typeを指定
   - 特定ステージのみの実行が可能

## コスト管理

GitHub Actionsの使用量を管理するため：

1. **実行頻度の調整**
   - cron設定を変更して実行頻度を調整

2. **タイムアウト設定**
   - 不要な長時間実行を防止

3. **Artifacts保持期間**
   - 必要に応じて保持期間を調整（現在：30日）

## 推奨設定

- **通常運用**: 毎週日曜日の自動実行
- **緊急時**: タグトリガーでの手動実行
- **テスト**: 手動実行で部分的にテスト（job_type指定）
- **本番環境**: 定期実行 + 必要時のタグトリガー

## タイムアウト設定

各ジョブの実行時間制限：
- **基礎データ収集**: 60分（list, details, traders, yfinance）
- **分析処理**: 30分（comparison - 証券会社スクレイピング）
- **レポート生成**: 180分（edinet, combiner）

合計最大実行時間: 約4.5時間 