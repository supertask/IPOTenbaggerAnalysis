#!/bin/bash

# スクリプト実行中のエラー時に停止するように設定
set -e

echo "=== Dockerとdocker-composeのインストールを開始します ==="

# パッケージリストの更新
echo "システムのパッケージリストを更新中..."
sudo apt-get update -y

# 必要なパッケージのインストール
echo "必要なパッケージをインストール中..."
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Dockerの公式GPG鍵を追加
echo "Dockerの公式GPG鍵を追加中..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Dockerのリポジトリを設定
echo "Dockerのリポジトリを設定中..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# パッケージリストの更新
echo "パッケージリストを再度更新中..."
sudo apt-get update -y

# Dockerエンジンのインストール
echo "Dockerエンジンをインストール中..."
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# 現在のユーザーをdockerグループに追加して、sudoなしでdockerコマンドを実行できるようにする
echo "現在のユーザーをdockerグループに追加中..."
sudo usermod -aG docker $USER
echo "注意: dockerグループに追加された変更を有効にするには、ログアウトして再度ログインする必要があります。"

# Docker Composeのインストール
echo "Docker Composeをインストール中..."
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Dockerサービスの開始
echo "Dockerサービスを開始中..."
sudo systemctl start docker
sudo systemctl enable docker

echo "=== Dockerとdocker-composeのインストールが完了しました ==="

# Dockerとdocker-composeのバージョン確認
echo "インストールされたバージョン:"
docker --version
docker-compose --version

echo "=== Flaskアプリケーションのコンテナを構築して起動します ==="
sudo docker-compose up --build -d

echo "=== セットアップが完了しました ==="
echo "Flaskアプリケーションは http://[サーバーのIP]:5000 でアクセスできます" 