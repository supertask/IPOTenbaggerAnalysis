import os
import csv
from tqdm import tqdm
from collectors.edinet_report_downloader import EdinetReportDownloader    
from collectors.settings import GeneralSettings, ScraperSettings, EdinetCollectorSettings
from collectors.ipo_analyzer_core import IPOAnalyzerCore 


class IPOEdinetCollector(IPOAnalyzerCore):
    def __init__(self):
        super().__init__()
        self.edinet_settings = EdinetCollectorSettings()
        self.collector = EdinetReportDownloader()

    def on_each_company(self, year, company_code, company_name, ipo_info_url):
        report_dict = self.collector.get_report_dict(code)
        filtered_report_dict = {}
        filtered_report_dict['企業名'] = company_name
        filtered_report_dict['コード'] = code

        keys_to_filter = ['事業の内容', '主要な設備の状況', '役員の状況']
        if report_dict:
            filtered_report_dict |= {key: report_dict.get(key, None) for key in keys_to_filter}
        else:
            filtered_report_dict |= {key: None for key in keys_to_filter}
        return filtered_report_dict

    def collect(self):
        self.save_companies_info_to_tsv(self.edinet_settings.output_dir, self.on_each_company)

    
    def run(self):
        self.collect()
        self.combine_all_files(self.edinet_settings.output_dir)


if __name__ == "__main__":
    collector = IPOEdinetCollector()
    collector.run()