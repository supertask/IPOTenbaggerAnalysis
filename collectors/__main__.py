import sys
from .ipo_kiso_details_collector import IPOKisoDetailsCollector
from .ipo_kiso_list_collector import IPOKisoListCollector
from .ipo_traders_collector import IPOTradersAnalyzer
from .ipo_yfinance_collector import IPOYFinanceAnalyzer
from .ipo_combiner import IPOCombiner
from .ipo_ai_summary import AISummaryGenerator
from .comparision_collector import ComparisonCollector
from .edinet_report_downloader import EdinetReportDownloader

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m collectors <collector_name>")
        sys.exit(1)

    collector_name = sys.argv[1]

    if collector_name == "list":
        collector = IPOKisoListCollector()
        collector.run()
    elif collector_name == "details":
        collector = IPOKisoDetailsCollector()
        collector.run()
    elif collector_name == "traders":
        collector = IPOTradersAnalyzer()
        collector.run()
    elif collector_name == "yfinance":
        collector = IPOYFinanceAnalyzer()
        collector.run()
    elif collector_name == "edinet":
        downloader = EdinetReportDownloader()
        downloader.run()
    #elif collector_name == "edinet":
    #    collector = IPOEdinetCollector()
    #    collector.run()
    elif collector_name == "combiner":
        collector = IPOCombiner()
        collector.run()
    elif collector_name == "ai":
        num = int(sys.argv[2]) if len(sys.argv) == 3 else None
        collector = AISummaryGenerator(num)
        collector.run()
    elif collector_name == "comparison":
        collector = ComparisonCollector()
        collector.run()
    elif collector_name == "all":
        list_collector = IPOKisoListCollector()
        details_collector = IPOKisoDetailsCollector()
        traders_collector = IPOTradersAnalyzer()
        yfinance_collector = IPOYFinanceAnalyzer()
        edinet_collector = IPOEdinetCollector()
        combiner_collector = IPOCombiner()
        ai_summary_collector = AISummaryGenerator()
        list_collector.run()
        details_collector.run()
        traders_collector.run()
        yfinance_collector.run()
        edinet_collector.run()
        combiner_collector.run()
        ai_summary_collector.generate_summary()
        return
    else:
        print(f"Unknown collector: {collector_name}")
        sys.exit(1)

if __name__ == "__main__":
    main() 