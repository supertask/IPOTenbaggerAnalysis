import os
import pandas as pd
import re
import time
import sys
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

from collectors.ipo_analyzer_core import IPOAnalyzerCore

def bussiness_potential_prompt(company_code, company_name, business_content, equipment_status):
    return [
        f"""
===
{business_content}

{equipment_status}
===
日本の上場企業で、銘柄コード: {company_code}, 企業名: {company_name}に関して、上記の===と===の間に書かれた有価証券報告書の内容を元に質問に答えてください。

<銘柄コード>\t<企業名>\t<ビジネスモデル名(str)>\t<店舗数(int)>\t<サブスク数(int)>\t<従業員数(int)>\t<保証数(int)>\t<海外進出を視野に(bool)>\t<目標世界一か(bool)>\t<参入障壁があるか>\t<参入障壁があると思う理由>
をタブ区切りで出力してください。

ビジネスモデル名: <多店舗展開ビジネス, サブスクビジネス, 営業人員依存型ビジネス, 保証ビジネス, その他, のいずれか>
店舗数: 多店舗展開ビジネスの場合でわかれば、その数を解らないなら-2を。それ以外のビジネスモデルは-1
サブスク数: サブスクビジネスの場合でわかれば、その数を解らないなら-2を。それ以外のビジネスモデルは-1
従業員数: 営業人員依存型ビジネスの場合でわかれば、その数を解らないなら-2を。それ以外のビジネスモデルは-1
保証数: 保証ビジネスの場合でわかれば、その数を解らないなら-2を。それ以外のビジネスモデルは-1,
海外進出を視野に: 海外進出を視野に入れているかを true / false で答えてください。
目標世界一か: その業界や分野で世界一を目指しているかを true / false で答えてください。
参入障壁があるか: 他の企業がなかなか真似できない参入障壁を持っているか。true / false で答えてください。
参入障壁があると思う理由：<参入障壁があるか>がtrueの際、その理由を答えてください。
"""
    ]

class AISummaryGenerator:
    def __init__(self, rank_index=None):
        self.settings = AISummarySettings()
        self.groq = ChatGroq(model_name="deepseek-r1-distill-llama-70b", groq_api_key=os.environ["GROQ_API_KEY"])
        os.makedirs(self.settings.output_dir, exist_ok=True)

        system_prompt = "あなたは有能な投資分析アシスタントです。"
        self.memory = ConversationBufferWindowMemory(k=5, memory_key="chat_history", return_messages=True)

        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{human_input}"),
        ])
        
        self.rank_index = rank_index

    def load_combiner_data(self):
        file_path = os.path.join(self.settings.combiner_input_dir, 'all_companies.tsv')
        return pd.read_csv(file_path, sep='\t')

    def load_edinet_data(self):
        edinet_file_path = os.path.join(self.settings.edinet_input_dir, "all_companies.tsv")
        return pd.read_csv(edinet_file_path, sep='\t')

    def generate_summary(self):
        combiner_df = self.load_combiner_data()
        edinet_df = self.load_edinet_data()
        df_sorted = combiner_df.sort_values(by='現在何倍株', ascending=False)
        top_companies = df_sorted.head(self.settings.top_n_companies)

        if self.rank_index is not None:
            if self.rank_index < 0 or self.rank_index > len(top_companies):
                print(f"Error: 指定された順位 {self.rank_index} は無効です（0 から {len(top_companies)} の間で指定してください）。")
                return
            
            row = top_companies.iloc[self.rank_index]  # X番目の企業を取得（0-indexed）
            self.process_company(row, edinet_df)
        else:
            for _, row in top_companies.iterrows():
                self.process_company(row, edinet_df)

    def process_company(self, row, edinet_df):
        company_code = row['コード']
        company_name = row['企業名']
        business_content = edinet_df[edinet_df['コード'] == company_code]['事業の内容'].values[0]
        equipment_status = edinet_df[edinet_df['コード'] == company_code]['主要な設備の状況'].values[0]

        prompts = bussiness_potential_prompt(company_code, company_name, business_content, equipment_status)
        #conversation = LLMChain(llm=self.groq, prompt=self.prompt_template, verbose=False, memory=self.memory)

        for prompt in prompts:
            print(f"Code: {company_code}, Company: {company_name}")
            print(f"{prompt}")

            #response = conversation.predict(human_input=prompt)
            #print(f"Code: {company_code}\nCompany: {company_name}\nPrompt: {prompt}\nResponse: {response}\n{'='*80}")
            #response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
            #print(response)

    def run(self):
        self.generate_summary()

if __name__ == '__main__':
    rank_index = int(sys.argv[1]) if len(sys.argv) > 1 else None
    generator = AISummaryGenerator(rank_index)
    generator.run()
