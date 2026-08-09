import re

# Windowsでファイル名に使用できない文字
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
# 改行・タブなどの制御文字（Windowsではファイル名に使用できない）
CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]+')


def sanitize_filename(name):
    """ ファイル名として使用できない文字を取り除く

    スクレイピング元のHTMLで社名が改行されていると、社名の文字列に改行が
    混ざったままファイル名に使われてしまう。macOS/Linuxでは作成できるが
    Windowsでは作成もチェックアウトもできないため、制御文字は削除する。
    """
    name = CONTROL_CHARS.sub('', name)
    name = INVALID_FILENAME_CHARS.sub('_', name)
    # Windowsは末尾のスペース・ピリオドを許容しない
    return name.strip().rstrip('. ')
