# Docker環境でのIPOデータビジュアライザー

このREADMEでは、OCIのUbuntu仮想環境でDocker化されたFlaskアプリケーションを実行する方法について説明します。

## 前提条件

- OCIのUbuntu仮想環境
- sudo権限を持つユーザーアカウント
- ポート5000へのアクセスが許可されたファイアウォール設定

## セットアップ手順

1. リポジトリをクローンまたはコピーします。

```bash
git clone [リポジトリURL] または既存のファイルを使用
cd [プロジェクトディレクトリ]
```

2. セットアップスクリプトに実行権限を付与します。

```bash
chmod +x setup.sh
```

3. セットアップスクリプトを実行します。

```bash
./setup.sh
```

このスクリプトは以下を実行します：
- Dockerとdocker-composeのインストール
- ユーザーをdockerグループに追加
- Dockerコンテナのビルドと起動

4. アプリケーションにアクセスする

ブラウザで以下のURLにアクセスします：
```
http://[サーバーのIP]:5000
```

## 手動セットアップ

セットアップスクリプトがうまく機能しない場合は、以下の手順で手動セットアップを行えます：

1. Dockerをインストールします。

```bash
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
```

2. Docker Composeをインストールします。

```bash
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

3. アプリケーションをビルドして起動します。

```bash
sudo docker-compose up --build -d
```

## トラブルシューティング

### ポートの競合

エラー: `Error starting userland proxy: listen tcp4 0.0.0.0:5000: bind: address already in use`

解決策: 既存のプロセスがポート5000を使用している場合、以下のコマンドでそのプロセスを確認して終了するか、docker-compose.ymlファイルを編集して別のポートを使用することができます。

```bash
# ポート5000を使用しているプロセスを確認
sudo lsof -i :5000

# プロセスを終了（PIDは上記コマンドの出力から取得）
sudo kill -9 PID
```

### Docker Composeコマンドが見つからない

エラー: `docker-compose: command not found`

解決策:

```bash
# docker-composeが正しく設置されていることを確認
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 新しいバージョンのDocker Composeでは`docker compose`（スペース区切り）の形式を使用することもできます
sudo docker compose up --build -d
```

### コンテナがすぐに終了する

問題: コンテナが起動してもすぐに停止する

解決策: ログを確認して問題を特定します。

```bash
# コンテナのログを確認
sudo docker logs ipo_data_visualizer

# 対話モードでコンテナを実行してデバッグ
sudo docker-compose run --rm web sh
```

## メンテナンス

### コンテナの再起動

```bash
sudo docker-compose restart
```

### アプリケーションの更新

コードを変更した後は、コンテナを再ビルドして再起動します：

```bash
sudo docker-compose down
sudo docker-compose up --build -d
```

### コンテナの停止

```bash
sudo docker-compose down
``` 