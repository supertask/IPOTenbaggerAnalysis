import re
import csv
import gzip
import os
import requests
import zipfile
import io
import pandas as pd
import urllib3
import chardet
import shutil
from datetime import datetime, timedelta

from collectors.file_utils import sanitize_filename

# Suppress the InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class EdinetReportDownloader:

    def __init__(self):
        self.use_cache = True
        # インクリメンタル更新専用
        self.incremental_cache_file = "incremental_doc_indexes.tsv.gz"

        self.meta_begin_x_year_ago = 10
        self.meta_end_x_year_ago = 0

        self.begin_x_year_ago = 10 #実際には過去10年しか取得できないが、10年だと一部抜ける書類があるかもしれないのでバッファーとして1年
        self.end_x_year_ago = 0
        
        # 有価証券届出書と四半期報告書の取得期間（年）
        self.recent_docs_years = 10

        #self.begin_x_year_ago = 0.5 #過去13年分を辿る
        self.is_debug = True
        
        # EDINETの書類種別コード
        self.DOC_TYPE_CODE_SECURITIES_REGISTRATION = '030'  # 有価証券届出書
        self.DOC_TYPE_CODE_SECURITIES_REPORT = '120'  # 有価証券報告書
        self.DOC_TYPE_CODE_QUARTERLY_REPORT = '140'  # 四半期報告書
        
        #self.current_dir = os.path.dirname(os.path.abspath(__file__))
        #print(self.current_dir)

        self.API_KEY = os.environ['EDINET_API_KEY'].rstrip()
        self.BASE_URL = "https://api.edinet-fsa.go.jp/api/v2/documents"
        self.edinet_url = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"

        self.OUTPUT_DIR = os.path.join('data', 'output', 'edinet_db')
        self.REPORTS_DIR = os.path.join(self.OUTPUT_DIR, 'ipo_reports')
        self.NEW_REPORTS_DIR = os.path.join(self.OUTPUT_DIR, 'ipo_reports_new')
        self.EDINET_CODE_DIR = os.path.join(self.OUTPUT_DIR, 'edinet_codes')
        self.edinet_codes_csv_path = os.path.join(self.EDINET_CODE_DIR, "EdinetcodeDlInfo.csv")
        self.edinet_codes_zip_path = os.path.join(self.EDINET_CODE_DIR, "Edinetcode.zip")

        if not os.path.exists(self.OUTPUT_DIR):
            os.makedirs(self.OUTPUT_DIR)
        if not os.path.exists(self.REPORTS_DIR):
            os.mkdir(self.REPORTS_DIR)
        if not os.path.exists(self.EDINET_CODE_DIR):
            os.mkdir(self.EDINET_CODE_DIR)
        if not os.path.exists(self.EDINET_CODE_DIR):
            os.makedirs(self.EDINET_CODE_DIR)


    def download_and_extract_edinet_zip(self):

        # ZIPファイルをダウンロード
        response = requests.get(self.edinet_url)
        with open(self.edinet_codes_zip_path, "wb") as file:
            file.write(response.content)

        # ZIPファイルを展開
        with zipfile.ZipFile(self.edinet_codes_zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.EDINET_CODE_DIR)

        # ZIPファイルを削除（必要に応じて）
        os.remove(self.edinet_codes_zip_path)

        #print(f"ファイルは {self.EDINET_CODE_DIR} に展開されました。")
        
        # CSVファイルを読み込み、「証券コード」をキーに「ＥＤＩＮＥＴコード」を値とする辞書を作成
        code5_to_edinet_dict = {}
        edinet_to_company_dict = {}
        #with open(self.edinet_codes_csv_path, "r", encoding='shift_jis') as csvfile:
        with open(self.edinet_codes_csv_path, "r", encoding='cp932') as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # 最初の行をスキップ
            header = next(reader)  # ヘッダー行を読み込む
            for row in reader:
                # ヘッダーに基づいて行を辞書として解析
                row_dict = dict(zip(header, row))
                edinet_code = row_dict['ＥＤＩＮＥＴコード']
                company_code = row_dict['証券コード']
                company_name = row_dict['提出者名']
                if len(company_code) == 0:
                    # 非上場か上場廃止の時に該当する
                    continue

                code5_to_edinet_dict[company_code] = {
                    'edinet_code': edinet_code,
                    'company_name': company_name
                }
                edinet_to_company_dict[edinet_code] = {
                    'company_code': company_code, #5桁
                    'company_name': company_name
                }

        #print(code5_to_edinet_dict)
        #print(edinet_to_company_dict)
        return code5_to_edinet_dict, edinet_to_company_dict

    def get_company_dict(self):
        code5_to_edinet_dict, edinet_to_company_dict = self.download_and_extract_edinet_zip()
        return edinet_to_company_dict

    def get_ipo_company_dict(self, companies_list):
        code5_to_edinet_dict, edinet_to_company_dict = self.download_and_extract_edinet_zip()
        ipo_edinet_to_company_dict = {}
        for companies in companies_list:
            for index, company in enumerate(companies):
                company_code4, company_name = company
                company_code5 = company_code4 + '0'
                if company_code5 in code5_to_edinet_dict:
                    edinet_info = code5_to_edinet_dict[company_code5]
                    edinet_code = edinet_info['edinet_code']
                    #company_code = edinet_info['company_code']
                    ipo_edinet_to_company_dict[edinet_code] = {
                        'company_code': company_code5,
                        'company_name': company_name
                    }
        return ipo_edinet_to_company_dict

    def request_doc_json(self, date):
        params = {
        "type" : 2,
        "date" : date,
        "Subscription-Key": self.API_KEY
        }
        try:
            res = requests.get(self.BASE_URL + ".json", params=params, verify=False)
            res.raise_for_status()  # HTTPエラーを確認
            json_data = res.json()
            #if self.is_debug:
            #    print(f"DEBUG: json_data: {json_data}")

            if 'results' in json_data:
                return json_data['results']
            elif 'metadata' in json_data and json_data['metadata'].get('status') == '404':
                raise ValueError("Error 404: The requested resource was not found.")
            else:
                raise KeyError("The key 'results' was not found in the response.")
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            print(f"An error occurred: {req_err}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        return []

    def request_doc_elements(self, date, doc_id, doc_name):
        params = {
            "type" : 5, #csv
            "date" : date,
            "Subscription-Key": self.API_KEY
        }
        try:
            response = requests.get(f"{self.BASE_URL}/{doc_id}", params=params, verify=False)
            response.raise_for_status()  # HTTPエラーが発生した場合、例外がスローされます
            if 'application/octet-stream' not in response.headers.get('Content-Type', ''):
                content_type = response.headers.get('Content-Type', 'Unknown')
                print(f"Error: Response is not a ZIP file (octet-stream). Content-Type: {content_type}.")
                print(f"Response: {response.json()}")
                #print(f"Response content1: {response.content[:1000]}")  # 最初の1000バイトのみ出力して内容を確認
                return []
            #tsv_df = self.extract_tsv_from_zip(response)
            tsv_raw_data = self.extract_tsv_from_zip(response)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching document elements for doc_id {doc_id} on {date}: {e}")
            return []
        return tsv_raw_data


    def extract_tsv_from_zip(self, response):

        with zipfile.ZipFile(io.BytesIO(response.content)) as the_zip:
            for file_name in the_zip.namelist():
                #print(f"file_name: {file_name}")
                if file_name.startswith('XBRL_TO_CSV/jpcrp') and file_name.endswith('.csv'):
                    with the_zip.open(file_name) as the_file:
                        raw_data = the_file.read()
                        return raw_data

    def save_securities_reports_in_one_day(self, date_str, edinet_to_company_dict):
        doc_metas = self.request_doc_json(date_str)
        tsv_rows = []
        for meta in doc_metas:
            edinet_code = meta['edinetCode']
            if not edinet_code in edinet_to_company_dict:
                continue # 上場廃止である可能性があるのでスキップ

            if meta['csvFlag'] == '1' and (
                meta['docTypeCode'] == self.DOC_TYPE_CODE_SECURITIES_REPORT or 
                meta['docTypeCode'] == self.DOC_TYPE_CODE_SECURITIES_REGISTRATION or
                meta['docTypeCode'] == self.DOC_TYPE_CODE_QUARTERLY_REPORT):
                if self.is_debug:
                    print(f"name = {meta['filerName']}, docDescription = {meta['docDescription']}, docId = {meta['docID']}")
                tsv_rows.append([date_str, edinet_code, meta['docTypeCode'], meta['docID']])
        
        return tsv_rows

    def save_securities_docs(self, company_doc_info, doc_type_code, company_folder, doc_name, company_code4, company_name, start_date=None, end_date=None):
        sorted_documents = company_doc_info[company_doc_info['docTypeCode'] == doc_type_code].sort_values('date', ascending=True)

        if sorted_documents.empty:
            print(f"\033[91mError: No documents found for {company_name} ({company_code4}) on doc_type_code = {doc_type_code}\033[0m")
            return

        # 日付フィルタリングの処理
        if start_date is None or end_date is None:
            # 従来のロジック：最も古いドキュメントの日付から計算
            oldest_date = sorted_documents.iloc[0]['date']
            calc_start_date = datetime.strptime(oldest_date, '%Y-%m-%d')
            calc_end_date = calc_start_date + timedelta(days=(self.begin_x_year_ago - self.end_x_year_ago) * 365)
            
            # 文字列形式に変換
            start_date_str = calc_start_date.strftime('%Y-%m-%d')
            end_date_str = calc_end_date.strftime('%Y-%m-%d')
        else:
            # 引数で指定された日付を使用
            start_date_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, datetime) else start_date
            end_date_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, datetime) else end_date

        # 日付でフィルタリング
        filtered_documents = sorted_documents[
            (start_date_str <= sorted_documents['date']) &
            (sorted_documents['date'] <= end_date_str)
        ]

        os.makedirs(company_folder, exist_ok=True)

        for i in range(len(filtered_documents)):
            document = filtered_documents.iloc[i]
            tsv_raw_data = self.request_doc_elements(document['date'], document['docID'], doc_name)
            if tsv_raw_data:
                file_path = f"{company_folder}/{document['date']}_{doc_name}.tsv"
                with open(file_path, 'wb') as debug_file:
                    debug_file.write(tsv_raw_data)
                print(f"Saved: {file_path}")
            else:
                print(f"\033[91mError: No valid '{doc_name}' found for {company_name} ({company_code4}) on {document['date']}\033[0m")




    def get_last_cached_date(self, cache_path):
        """
        既存キャッシュから最新の日付を取得
        キャッシュがない場合は指定年数前の日付を返す
        """
        if not os.path.exists(cache_path):
            # 初回実行時は指定年数前から開始
            return datetime.now() - timedelta(days=self.meta_begin_x_year_ago * 365)
        
        try:
            with gzip.open(cache_path, 'rt', encoding='utf-8') as f:
                existing_data = pd.read_csv(f, sep='\t', dtype={'date': str})
            
            if existing_data.empty:
                return datetime.now() - timedelta(days=self.meta_begin_x_year_ago * 365)
            
            # 最新の日付を取得
            last_date_str = existing_data['date'].max()
            return datetime.strptime(last_date_str, '%Y-%m-%d')
            
        except Exception as e:
            print(f"キャッシュファイル読み込みエラー: {e}")
            return datetime.now() - timedelta(days=self.meta_begin_x_year_ago * 365)

    def get_missing_date_range(self, cache_path):
        """
        ダウンロードが必要な日付範囲を計算
        """
        last_cached_date = self.get_last_cached_date(cache_path)
        current_date = datetime.now()
        
        # 最新キャッシュの翌日から現在日付まで
        start_date = last_cached_date + timedelta(days=1)
        end_date = current_date
        
        return start_date, end_date, last_cached_date

    def download_incremental_data(self, start_date, end_date, companies_dict):
        """
        指定された日付範囲のみEDINETからダウンロード
        """
        if self.is_debug:
            print(f"📥 差分データダウンロード: {start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')}")
        
        new_data = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if self.is_debug:
                print(f"  処理中: {date_str}")
            
            # 既存のメソッドを使用してEDINET APIを呼び出し
            day_data = self.save_securities_reports_in_one_day(date_str, companies_dict)
            new_data.extend(day_data)
            
            current_date += timedelta(days=1)
        
        return pd.DataFrame(new_data, columns=['date', 'edinet_code', 'docTypeCode', 'docID'])

    def merge_and_save_cache(self, new_data, cache_path):
        """
        既存キャッシュと新しいデータを結合して保存
        """
        if os.path.exists(cache_path):
            # 既存データを読み込み
            with gzip.open(cache_path, 'rt', encoding='utf-8') as f:
                existing_data = pd.read_csv(f, sep='\t', dtype={'date': str, 'edinet_code': str, 'docTypeCode': str, 'docID': str})
            
            # 新旧データを結合
            combined_data = pd.concat([existing_data, new_data], ignore_index=True)
            if self.is_debug:
                print(f"📊 既存データ: {len(existing_data)}件 + 新規データ: {len(new_data)}件")
        else:
            combined_data = new_data
            if self.is_debug:
                print(f"📊 初回作成: {len(new_data)}件")
        
        # 重複削除（同じ日付・企業・文書種別の重複を除去）
        combined_data = combined_data.drop_duplicates(
            subset=['date', 'edinet_code', 'docTypeCode'], 
            keep='last'
        )
        
        # 日付順でソート
        combined_data = combined_data.sort_values('date')
        
        # 圧縮保存
        with gzip.open(cache_path, 'wt', encoding='utf-8') as f:
            combined_data.to_csv(f, sep='\t', index=False)
        
        if self.is_debug:
            print(f"💾 保存完了: {len(combined_data)}件 → {cache_path}")
        return combined_data

    def run_incremental_update(self, cache_path, companies_dict):
        """
        インクリメンタル更新のメイン処理
        """
        if self.is_debug:
            print("🔄 インクリメンタル更新開始")
        
        # 1. 不足している日付範囲を計算
        start_date, end_date, last_cached_date = self.get_missing_date_range(cache_path)
        
        if start_date > end_date:
            if self.is_debug:
                print("✅ 更新不要: キャッシュは最新状態です")
            return
        
        if self.is_debug:
            print(f"📅 前回キャッシュ最新日: {last_cached_date.strftime('%Y-%m-%d')}")
            print(f"🆕 更新対象期間: {(end_date - start_date).days + 1}日間")
        
        # 2. 差分データのみダウンロード
        new_data = self.download_incremental_data(start_date, end_date, companies_dict)
        
        if new_data.empty:
            if self.is_debug:
                print("⚠️  新しいデータがありませんでした")
            return
        
        # 3. 既存データと結合して保存
        self.merge_and_save_cache(new_data, cache_path)
        
        if self.is_debug:
            print("✅ インクリメンタル更新完了")

    def validate_incremental_update(self, cache_path):
        """
        インクリメンタル更新後のデータ整合性をチェック
        """
        try:
            with gzip.open(cache_path, 'rt', encoding='utf-8') as f:
                data = pd.read_csv(f, sep='\t', dtype={'date': str})
            
            # 基本的なデータ存在チェック
            if data.empty:
                return False, "データが空です"
            
            # 日付の連続性チェック（簡易版）
            dates = sorted(data['date'].unique())
            if len(dates) < 2:
                return True, "データが少ないため連続性チェックをスキップ"
            
            # 最新データの存在確認
            current_date = datetime.now().strftime('%Y-%m-%d')
            recent_dates = [d for d in dates if d >= (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')]
            
            if not recent_dates:
                return False, "直近7日間のデータが存在しません"
            
            return True, f"検証成功: {len(data)}件のデータ"
            
        except Exception as e:
            return False, f"検証エラー: {e}"


    def save_securities_reports(self, companies_list = None, skip_json = True):
        tracking_days = int(365 * self.meta_begin_x_year_ago)
        if companies_list:
            edinet_to_company_dict = self.get_ipo_company_dict(companies_list)
        else:
            edinet_to_company_dict = self.get_company_dict()

        # インクリメンタル更新専用
        doc_meta_path = os.path.join(self.EDINET_CODE_DIR, self.incremental_cache_file)
        print(f"DEBUG: インクリメンタルモード - cache_path: {doc_meta_path}")
        
        # インクリメンタル更新実行
        self.run_incremental_update(doc_meta_path, edinet_to_company_dict)
        
        # データ整合性チェック
        is_valid, message = self.validate_incremental_update(doc_meta_path)
        if not is_valid:
            print(f"⚠️  データ整合性エラー: {message}")
            raise RuntimeError(f"インクリメンタル更新でエラーが発生しました: {message}")
        
        if self.is_debug:
            print(f"✅ {message}")

        # Load the single TSV file
        with gzip.open(doc_meta_path, 'rt', encoding='utf-8') as f:
            full_data = pd.read_csv(f, sep='\t', dtype={'date': str, 'edinet_code': str, 'docTypeCode': str, 'docID': str})

        # Process each company to get the latest reports
        for edinet_code, company_doc_info in full_data.groupby('edinet_code'):
            if edinet_code not in edinet_to_company_dict:
                continue  # 辞書に存在しないedinet_codeはスキップ
            company = edinet_to_company_dict[edinet_code]
            company_code5 = company['company_code']
            company_name = company['company_name']
            company_code4 = company_code5[:-1]
            if self.is_debug:
                print(f"DEBUG: code = {company_code4}, name = {company_name}")
            
            # 有価証券届出書と四半期報告書は過去2年間のデータのみ取得
            current_date = datetime.now()
            two_years_ago = current_date - timedelta(days=self.recent_docs_years * 365)
            
            # 日付文字列に変換
            start_date_str = two_years_ago.strftime('%Y-%m-%d')
            end_date_str = current_date.strftime('%Y-%m-%d')

            # 有価証券届出書を保存（事業の内容が書かれてない場合が多いかも？？）
            company_folder = f"{self.NEW_REPORTS_DIR}/{company_code4}_{sanitize_filename(company_name)}/securities_registration_statement"
            self.save_securities_docs(company_doc_info, self.DOC_TYPE_CODE_SECURITIES_REGISTRATION, company_folder, '有価証券届出書', company_code4, company_name, start_date_str, end_date_str)
            
            # 四半期報告書を保存
            #company_folder = f"{self.NEW_REPORTS_DIR}/{company_code4}_{company_name}/quarterly_reports"
            #self.save_securities_docs(company_doc_info, self.DOC_TYPE_CODE_QUARTERLY_REPORT, company_folder, '四半期報告書', company_code4, company_name, start_date_str, end_date_str)

            # 有価証券報告書を保存
            #company_folder = f"{self.REPORTS_DIR}/{company_code4}_{company_name}/annual_securities_reports"
            #self.save_securities_docs(company_doc_info, self.DOC_TYPE_CODE_SECURITIES_REPORT, company_folder, '有価証券報告書', company_code4, company_name)

    def run(self):
        self.save_securities_reports()
        self.save_companies_info_list()
    
    def save_companies_info_list(self):
        pass

    def show_cache_status(self):
        """キャッシュの状態を表示"""
        print("📊 キャッシュ状態:")
        
        # インクリメンタルキャッシュの状態
        incremental_cache = os.path.join(self.EDINET_CODE_DIR, self.incremental_cache_file)
        if os.path.exists(incremental_cache):
            mtime = datetime.fromtimestamp(os.path.getmtime(incremental_cache))
            print(f"  インクリメンタルキャッシュ: 存在 (更新日時: {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
            
            try:
                last_cached_date = self.get_last_cached_date(incremental_cache)
                print(f"  最新データ日付: {last_cached_date.strftime('%Y-%m-%d')}")
                
                # 次回更新で取得される日付範囲を表示
                start_date, end_date, _ = self.get_missing_date_range(incremental_cache)
                if start_date <= end_date:
                    days_count = (end_date - start_date).days + 1
                    print(f"  次回更新対象: {start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')} ({days_count}日間)")
                else:
                    print("  次回更新対象: なし（最新状態）")
            except Exception as e:
                print(f"  キャッシュ解析エラー: {e}")
        else:
            print("  インクリメンタルキャッシュ: 存在しません（初回実行時に作成）")



    # 日付を抽出してソート
    def extract_date(self, file_path):
        file_name = os.path.basename(file_path)
        match = re.match(r'(\d{4}-\d{2}-\d{2})_', file_name)
        if match:
            return datetime.strptime(match.group(1), '%Y-%m-%d')
        return None

    def find_report_path(self, code, latest=False):
        # codeに該当するフォルダを見つける
        code_folder_pattern = f"{code}_.*"
        code_folders = [f for f in os.listdir(self.REPORTS_DIR) if os.path.isdir(os.path.join(self.REPORTS_DIR, f)) and re.match(code_folder_pattern, f)]
        
        all_files = []

        for folder in code_folders:
            securities_path = os.path.join(self.REPORTS_DIR, folder, 'securities_registration_statement')
            annual_path = os.path.join(self.REPORTS_DIR, folder, 'annual_securities_reports')

            # securities_registration_statementフォルダをチェック
            if os.path.exists(securities_path):
                for file in os.listdir(securities_path):
                    if file.endswith('.tsv'):
                        all_files.append(os.path.join(securities_path, file))

            # annual_securities_reportsフォルダをチェック
            if os.path.exists(annual_path):
                for file in os.listdir(annual_path):
                    if file.endswith('.tsv'):
                        all_files.append(os.path.join(annual_path, file))

        if not all_files:
            return None

        all_files.sort(key=lambda x: self.extract_date(x), reverse=latest)
        return all_files[0] if all_files else None



if __name__ == "__main__":
    tsv = EdinetReportDownloader()
    tsv.run()

    #print(report_dict)
    #tsv.save_ipo_securities_reports(companies = {
    #    'E38948': {'company_code': '55880', 'company_name': 'ファーストアカウンティング'}
    #})
