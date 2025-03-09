# このファイルは廃止されました。
# ビジネスロジックはroot.pyに移動し、ルーティングはvisualizer/app.pyに移動しました。
# 互換性のために残しています。

from .root import (
    index,
    company_view,
    get_securities_reports,
    get_securities_report_diff
)

# 以前のBlueprintの定義（互換性のために残しています）
from flask import Blueprint
next_tenbagger_bp = Blueprint('next_tenbagger', __name__, 
                             url_prefix='/next_tenbagger',
                             template_folder='templates') 