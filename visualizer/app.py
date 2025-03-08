from flask import Flask, render_template, redirect, url_for
import os
from pathlib import Path

def create_app():
    """アプリケーションを作成する関数"""
    # プロジェクトのルートディレクトリを取得
    base_dir = Path(__file__).parent
    
    # past_tenbaggerのテンプレートディレクトリを取得
    past_tenbagger_template_dir = os.path.join(base_dir, 'past_tenbagger', 'templates')
    past_tenbagger_static_dir = os.path.join(base_dir, 'past_tenbagger', 'static')
    
    # テンプレートディレクトリの存在を確認
    if not os.path.exists(past_tenbagger_template_dir):
        print(f"警告: テンプレートディレクトリが見つかりません: {past_tenbagger_template_dir}")
    else:
        print(f"テンプレートディレクトリが見つかりました: {past_tenbagger_template_dir}")
        # index.htmlの存在を確認
        index_path = os.path.join(past_tenbagger_template_dir, 'index.html')
        if os.path.exists(index_path):
            print(f"index.htmlが見つかりました: {index_path}")
        else:
            print(f"警告: index.htmlが見つかりません: {index_path}")
    
    app = Flask(__name__, 
                template_folder=past_tenbagger_template_dir,
                static_folder=past_tenbagger_static_dir)
    
    # ルートURLにアクセスしたときにリンクを表示するページ
    @app.route('/')
    def root():
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>IPOデータコレクター</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { 
                    padding-top: 50px; 
                    background-color: #f8f9fa;
                }
                .card {
                    margin-bottom: 20px;
                    transition: transform 0.3s, box-shadow 0.3s;
                    border-radius: 10px;
                }
                .card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
                }
                .card-header {
                    background-color: #007bff;
                    color: white;
                    border-radius: 10px 10px 0 0 !important;
                    padding: 15px;
                }
                .card-body {
                    padding: 20px;
                }
                .btn-lg {
                    padding: 15px 25px;
                    font-size: 18px;
                    border-radius: 8px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="text-center mb-5">IPOデータコレクター</h1>
                <div class="row justify-content-center">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h3 class="card-title mb-0">過去のテンバガー企業分析</h3>
                            </div>
                            <div class="card-body text-center">
                                <p class="card-text mb-4">過去に株価が10倍以上になった企業（テンバガー）の分析ツールです。</p>
                                <a href="/past_tenbagger/" class="btn btn-primary btn-lg">分析ツールを開く</a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        return html
    
    # past_tenbaggerモジュールからアプリケーションをインポート
    from visualizer.past_tenbagger.app import create_app as create_past_tenbagger_app
    
    # past_tenbaggerアプリケーションを作成
    past_tenbagger_app = create_past_tenbagger_app()
    
    # past_tenbaggerアプリケーションのルートをマウント
    for rule in past_tenbagger_app.url_map.iter_rules():
        # staticエンドポイントはスキップする（衝突を避けるため）
        if rule.endpoint != 'static':
            endpoint = rule.endpoint
            view_func = past_tenbagger_app.view_functions[endpoint]
            app.add_url_rule(rule.rule, endpoint=endpoint, view_func=view_func, methods=rule.methods)
    
    return app

if __name__ == '__main__':
    app = create_app()
    print("アプリケーションを起動します...")
    print(f"テンプレートディレクトリ: {app.template_folder}")
    print(f"静的ファイルディレクトリ: {app.static_folder}")
    print(f"登録されたルート:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.endpoint}: {rule.rule} {rule.methods}")
    app.run(debug=True, port=5000) 