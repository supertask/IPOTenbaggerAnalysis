import os
import pandas as pd
import re
import sys
import glob
import json
import re
import time
from collectors.settings import AISummarySettings
from langchain.chains import LLMChain
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.messages import SystemMessage
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain_groq import ChatGroq
from collectors.settings import YFinanceScraperSettings

from collectors.ipo_analyzer_core import IPOAnalyzerCore


# 有価証券報告書の情報を格納するクラス
class SecuritiesReport:
    def __init__(self, business_content="", equipment_status="", officer_status=""):
        self.business_content = business_content
        self.equipment_status = equipment_status
        self.officer_status = officer_status


def bussiness_potential_prompts(knowledge, company_code, company_name, securities_report, competitors_reports=None):
    """
    ビジネスポテンシャルを分析するためのプロンプトを生成する
    
    Args:
        knowledge: 前提知識
        company_code: 企業コード
        company_name: 企業名
        securities_report: 有価証券報告書の情報
        competitors_reports: 競合企業の有価証券報告書情報のリスト (オプション)
        
    Returns:
        プロンプトのリスト
    """
    settings = AISummarySettings()
    prompts = []
    
    # 基本的なビジネスモデル分析プロンプト
    with open(settings.basic_prompt_template, 'r', encoding='utf-8') as f:
        basic_prompt_template = f.read()
    
    basic_prompt = basic_prompt_template.format(
        knowledge=knowledge,
        company_code=company_code,
        company_name=company_name,
        securities_report=securities_report
    )
    prompts.append(basic_prompt)
    
# NOTE: Groqが安くなるまで、ここをコメントアウト
#    # 役員情報の分析プロンプト（競合企業の情報がある場合）
#    if securities_report.officer_status and competitors_reports:
#        with open(settings.officers_prompt_template, 'r', encoding='utf-8') as f:
#            officers_prompt_template = f.read()
#        
#        # 競合企業の役員情報を構築
#        competitors_officers = ""
#        for comp in competitors_reports:
#            if comp['officer_status']:
#                competitors_officers += f"""
#企業名: {comp['company_name']} (コード: {comp['company_code']})
#{comp['officer_status']}
#"""
#        
#        officers_prompt = officers_prompt_template.format(
#            knowledge=knowledge,
#            company_code=company_code,
#            company_name=company_name,
#            securities_report=securities_report,
#            competitors_officers=competitors_officers
#        )
#        prompts.append(officers_prompt)
    
    return prompts


class AISummaryGenerator:
    # 期待されるJSONレスポンスのキー
    EXPECTED_KEYS = [
        "銘柄コード", "企業名", "ビジネスモデル名", "店舗数", "サブスク数", 
        "従業員数", "保証数", "海外進出を視野に", "目標世界一か", 
        "参入障壁があるか", "参入障壁があると思う理由", 
        "テンバガーになりそうか", "テンバガーになりそうな理由"
    ]
    
    def __init__(self, rank_index=None):
        self.settings = AISummarySettings()
        self.groq = ChatGroq(model_name="qwen-qwq-32b", groq_api_key=os.environ["GROQ_API_KEY"])
        os.makedirs(self.settings.output_dir, exist_ok=True)

        system_prompt = "あなたは有能な投資分析アシスタントです。JSONフォーマットで回答してください。"
        self.memory = ConversationBufferWindowMemory(k=5, memory_key="chat_history", return_messages=True)

        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{human_input}"),
        ])
        
        self.rank_index = rank_index
        self.reports_base_dir = os.path.join(self.settings.edinet_input_dir, 'ipo_reports')
        self.analysis_results = []  # 分析結果を保存するリスト
        
    def get_competitors(self, company_code):
        """
        指定された企業コードの競合企業リストを取得
        """
        # yfinanceのall_companies.tsvファイルのパスを指定
        yfinance_settings = YFinanceScraperSettings()
        all_companies_file = os.path.join(yfinance_settings.output_dir, "all_companies.tsv")
        
        if not os.path.exists(all_companies_file):
            return []
        
        try:
            # all_companies.tsvファイルを読み込む
            df = pd.read_csv(all_companies_file, sep='\t')
            
            # 企業コードに一致する行を探す
            company_row = df[df['コード'].astype(str) == str(company_code)]
            
            if company_row.empty or pd.isna(company_row['競合リスト'].values[0]):
                return []
            
            return json.loads(company_row['競合リスト'].values[0])
        except Exception as e:
            print(f"競合企業リストの取得中にエラー: {e}")
            return []
    
    def get_securities_report(self, company_code, company_name):
        """
        有価証券報告書の情報を取得
        """
        # ディレクトリを探す（コードで始まるディレクトリを検索）
        company_dirs = glob.glob(os.path.join(self.reports_base_dir, f"{company_code}_*"))
        
        if not company_dirs:
            print(f"Warning: {company_code}_{company_name} に対応するディレクトリが見つかりません。")
            return None
        
        # 最初に見つかったディレクトリを使用
        company_dir = company_dirs[0]
        reports_dir = os.path.join(company_dir, 'annual_securities_reports')
        
        if not os.path.exists(reports_dir):
            print(f"Warning: {reports_dir} が存在しません。")
            return None
        
        # 最新の有価証券報告書を取得（ファイル名でソート）
        tsv_files = sorted(glob.glob(os.path.join(reports_dir, '*.tsv')), reverse=True)
        
        if not tsv_files:
            print(f"Warning: {reports_dir} に有価証券報告書が見つかりません。")
            return None
        
        latest_report = tsv_files[0]
        
        try:
            # UTF-16エンコーディングを指定して読み込む
            report_df = pd.read_csv(latest_report, sep='\t', encoding='utf-16')
            
            # 事業の内容を取得
            business_content_rows = report_df[report_df['要素ID'] == 'jpcrp_cor:DescriptionOfBusinessTextBlock']
            business_content = business_content_rows['値'].iloc[0] if not business_content_rows.empty else "事業の内容が見つかりません。"
            
            # 主要な設備の状況を取得
            equipment_status_rows = report_df[report_df['要素ID'] == 'jpcrp_cor:MajorFacilitiesTextBlock']
            equipment_status = equipment_status_rows['値'].iloc[0] if not equipment_status_rows.empty else "主要な設備の状況が見つかりません。"
            
            # 役員の状況を取得
            officer_status_rows = report_df[report_df['要素ID'] == 'jpcrp_cor:InformationAboutOfficersTextBlock']
            officer_status = officer_status_rows['値'].iloc[0] if not officer_status_rows.empty else ""
            
            return SecuritiesReport(business_content, equipment_status, officer_status)
        except Exception as e:
            print(f"有価証券報告書の読み込み中にエラー: {e}")
            return None

    def load_combiner_data(self):
        file_path = os.path.join(self.settings.combiner_input_dir, 'all_companies.tsv')
        return pd.read_csv(file_path, sep='\t')

    def generate_summary(self):
        combiner_df = self.load_combiner_data()
        df_sorted = combiner_df.sort_values(by='現在何倍株', ascending=False)
        top_companies = df_sorted.head(self.settings.top_n_companies)

        # 既存のall_companies.tsvファイルを読み込む
        existing_companies = set()
        output_file = os.path.join(self.settings.output_dir, 'all_companies.tsv')
        if os.path.exists(output_file):
            try:
                existing_df = pd.read_csv(output_file, sep='\t')
                existing_companies = set(existing_df['銘柄コード'].astype(str))
                print(f"既存の企業コード数: {len(existing_companies)}")
            except Exception as e:
                print(f"既存ファイルの読み込みエラー: {e}")

        if self.rank_index is not None:
            if self.rank_index < 0 or self.rank_index > len(top_companies):
                print(f"Error: 指定された順位 {self.rank_index} は無効です（0 から {len(top_companies)} の間で指定してください）。")
                return
            
            row = top_companies.iloc[self.rank_index]  # X番目の企業を取得（0-indexed）
            company_code = str(row['コード'])
            if company_code in existing_companies:
                print(f"企業コード {company_code} は既に処理済みです。スキップします。")
            else:
                self.process_company(row)
        else:
            for _, row in top_companies.iterrows():
                company_code = str(row['コード'])
                if company_code in existing_companies:
                    print(f"企業コード {company_code} は既に処理済みです。スキップします。")
                else:
                    self.process_company(row)

    def process_company(self, row):
        company_code = row['コード']
        company_name = row['企業名']
        
        # 有価証券報告書の情報を取得
        securities_report = self.get_securities_report(company_code, company_name)
        if not securities_report:
            print(f"Warning: {company_code}_{company_name} の有価証券報告書が取得できませんでした。スキップします。")
            return
        
        # 競合企業の情報を取得
        competitors = self.get_competitors(company_code)
        competitors_reports = []
        
        if competitors:
            for comp in competitors:
                comp_code = comp['code']
                comp_name = comp['name']
                comp_report = self.get_securities_report(comp_code, comp_name)
                if comp_report:
                    competitors_reports.append({
                        'company_code': comp_code,
                        'company_name': comp_name,
                        'officer_status': comp_report.officer_status
                    })
        
        # プロンプトを生成
        prompts = bussiness_potential_prompts(
            self.settings.stock_bussiness_knowledge, 
            company_code, 
            company_name, 
            securities_report,
            competitors_reports if competitors_reports else None
        )
        
        conversation = LLMChain(llm=self.groq, prompt=self.prompt_template, verbose=False, memory=self.memory)

        company_results = {
            '銘柄コード': company_code,
            '企業名': company_name,
        }
        
        # 競合企業情報を追加
        if competitors:
            company_results['競合リスト'] = json.dumps(competitors, ensure_ascii=False)
            company_results['競合企業数'] = len(competitors)
            
            # 競合企業名のリストを作成
            competitor_names = [comp['name'] for comp in competitors]
            company_results['競合企業名'] = ', '.join(competitor_names)

        for i, prompt in enumerate(prompts):
            print(f"Code: {company_code}, Company: {company_name}")
            print(f"Analyzing prompt {i+1}/{len(prompts)}...")

            response = conversation.predict(human_input=prompt)
            
            print(f"Raw response: {response}")
            
            # JSONブロックを抽出するための正規表現（より柔軟に）
            json_pattern = r'({[\s\S]*?})'
            json_matches = re.finditer(json_pattern, response)
            
            valid_json = None
            for match in json_matches:
                json_str = match.group(1)
                try:
                    # JSONをパース
                    parsed_json = json.loads(json_str)
                    valid_json = parsed_json
                    print(f"Successfully parsed JSON: {json.dumps(parsed_json, ensure_ascii=False, indent=2)}")
                    break
                except json.JSONDecodeError:
                    continue
            
            if valid_json:
                # 結果を保存（JSONファイルへの出力は不要）
                prompt_type = "business_model" if i == 0 else "officers_analysis"
                
                print(f"Analysis completed")
                print(f"Result keys: {list(valid_json.keys())}")
                
                # basic_prompt.txtの新しい項目を確認
                missing_keys = [key for key in self.EXPECTED_KEYS if key not in valid_json]
                if missing_keys:
                    print(f"Warning: 以下のキーがレスポンスに含まれていません: {missing_keys}")
                
                # 結果をcompany_resultsに追加
                if prompt_type == "business_model":
                    for key, value in valid_json.items():
                        if key not in ['銘柄コード', '企業名']:  # 既に追加済みの項目は除外
                            company_results[key] = value
                            print(f"Added key to results: {key}")
                elif prompt_type == "officers_analysis":
                    for key, value in valid_json.items():
                        company_results[f"役員分析_{key}"] = value
                        print(f"Added key to results: 役員分析_{key}")
            else:
                print(f"No valid JSON found in response.")
                
            time.sleep(60)
        
        # 会社ごとの結果をリストに追加
        self.analysis_results.append(company_results)
        
        # 各会社の処理が終わるたびにall_companies.tsvを保存
        self.save_to_all_companies_tsv()

    def save_to_all_companies_tsv(self):
        """現在の分析結果をall_companies.tsvに保存する"""
        if not self.analysis_results:
            return
            
        # 結果をDataFrameに変換
        df = pd.DataFrame(self.analysis_results)
        print(f"DataFrame列: {df.columns.tolist()}")
        
        # 既存のall_companies.tsvファイルがあれば読み込んで結合
        output_file = os.path.join(self.settings.output_dir, 'all_companies.tsv')
        if os.path.exists(output_file):
            try:
                existing_df = pd.read_csv(output_file, sep='\t')
                # 既存のデータと新しいデータを結合
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                # 重複を削除（同じコードの企業は最新のデータを保持）
                combined_df = combined_df.drop_duplicates(subset=['銘柄コード'], keep='first')
                # TSVファイルに保存
                combined_df.to_csv(output_file, sep='\t', index=False, encoding='utf-8')
            except Exception as e:
                print(f"既存ファイルの読み込みエラー: {e}")
                # エラーの場合は新しいデータだけを保存
                df.to_csv(output_file, sep='\t', index=False, encoding='utf-8')
        else:
            # 既存ファイルがない場合は新規作成
            df.to_csv(output_file, sep='\t', index=False, encoding='utf-8')
        
        print(f"分析結果を {output_file} に保存しました。")

    def run(self):
        self.generate_summary()

if __name__ == '__main__':
    rank_index = int(sys.argv[1]) if len(sys.argv) > 1 else None
    generator = AISummaryGenerator(rank_index)
    generator.run()
