from flask import Flask, render_template, redirect, url_for, jsonify, request
import os
from pathlib import Path
import logging
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.exceptions import NotFound

# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_root_app():
    """ルートアプリケーションを作成する関数"""
    app = Flask(__name__)
    
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
                .card-header.next {
                    background-color: #0d6efd;
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
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header next">
                                <h3 class="card-title mb-0">次のテンバガー企業予測</h3>
                            </div>
                            <div class="card-body text-center">
                                <p class="card-text mb-4">直近3年で上場した企業から次のテンバガー候補を分析するツールです。</p>
                                <a href="/next_tenbagger/" class="btn btn-primary btn-lg">分析ツールを開く</a>
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
    
    return app

def create_next_tenbagger_app():
    """next_tenbaggerアプリケーションを作成する関数"""
    # プロジェクトのルートディレクトリを取得
    base_dir = Path(__file__).parent
    
    # next_tenbaggerのテンプレートディレクトリを指定してアプリケーションを作成
    template_dir = os.path.join(base_dir, 'next_tenbagger', 'templates')
    static_dir = os.path.join(base_dir, 'next_tenbagger', 'static')
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    
    # next_tenbaggerのビジネスロジックをインポート
    from visualizer.next_tenbagger.root import (
        index as next_tenbagger_index,
        company_view as next_tenbagger_company_view,
        get_securities_reports as next_tenbagger_get_securities_reports,
        securities_report_diff as next_tenbagger_securities_report_diff
    )
    
    @app.route('/')
    def index():
        """トップページ - 直近3年でIPOした企業一覧"""
        data, error, status_code = next_tenbagger_index()
        if error:
            return error, status_code
        return render_template('index.html', **data)
    
    @app.route('/<company_code>')
    def company_view(company_code):
        """企業の詳細ページ"""
        data, error, status_code = next_tenbagger_company_view(company_code)
        if error:
            return error, status_code
        return render_template('company.html', **data)
    
    @app.route('/api/securities_reports/<company_code>')
    def get_securities_reports(company_code):
        """四半期報告書の一覧を取得するAPI"""
        data, error, status_code = next_tenbagger_get_securities_reports(company_code)
        if error:
            return jsonify({"error": error}), status_code
        return jsonify(data), status_code
    
    @app.route('/api/securities_report_diff/<company_code>', methods=['POST'])
    def get_securities_report_diff(company_code):
        """四半期報告書の差分を計算するAPI"""
        data, error, status_code = next_tenbagger_securities_report_diff(company_code)
        if error:
            return jsonify({"error": error}), status_code
        return jsonify(data), status_code
    
    return app

def create_past_tenbagger_app():
    """past_tenbaggerアプリケーションを作成する関数"""
    # プロジェクトのルートディレクトリを取得
    base_dir = Path(__file__).parent
    
    # past_tenbaggerのテンプレートディレクトリを指定してアプリケーションを作成
    template_dir = os.path.join(base_dir, 'past_tenbagger', 'templates')
    static_dir = os.path.join(base_dir, 'past_tenbagger', 'static')
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    
    # past_tenbaggerのビジネスロジックをインポート
    from visualizer.past_tenbagger.root import (
        index as past_tenbagger_index,
        company_view as past_tenbagger_company_view,
        get_securities_reports as past_tenbagger_get_securities_reports,
        get_securities_report_diff as past_tenbagger_get_securities_report_diff
    )
    
    @app.route('/')
    def index():
        """トップページ - テンバガー企業一覧"""
        companies, error, status_code = past_tenbagger_index()
        if error:
            return error, status_code
        return render_template('index.html', companies=companies)
    
    @app.route('/<company_code>')
    def company_view(company_code):
        """企業の詳細ページ"""
        data, error, status_code = past_tenbagger_company_view(company_code)
        if error:
            return error, status_code
        return render_template('company.html', **data)
    
    @app.route('/api/securities_reports/<company_code>')
    def get_securities_reports(company_code):
        """四半期報告書の一覧を取得するAPI"""
        response, status_code = past_tenbagger_get_securities_reports(company_code)
        return jsonify(response), status_code
    
    @app.route('/api/securities_report_diff/<company_code>', methods=['POST'])
    def get_securities_report_diff(company_code):
        """四半期報告書の差分を計算するAPI"""
        data = request.json
        response, status_code = past_tenbagger_get_securities_report_diff(company_code, data)
        return jsonify(response), status_code
    
    return app

def create_app():
    """アプリケーションを作成する関数"""
    # ルートアプリケーションを作成
    root_app = create_root_app()
    
    # next_tenbaggerアプリケーションを作成
    next_tenbagger_app = create_next_tenbagger_app()
    
    # past_tenbaggerアプリケーションを作成
    past_tenbagger_app = create_past_tenbagger_app()
    
    # DispatcherMiddlewareを使用して、各アプリケーションをマウント
    app = DispatcherMiddleware(root_app, {
        '/next_tenbagger': next_tenbagger_app,
        '/past_tenbagger': past_tenbagger_app
    })
    
    return app

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    app = create_app()
    print("アプリケーションを起動します...")
    run_simple('0.0.0.0', 5000, app, use_reloader=True, use_debugger=True) 