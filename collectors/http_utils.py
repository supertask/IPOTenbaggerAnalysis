import random
import time

import requests

# 素のPython製User-Agentだと弾かれるサイトがあるため、ブラウザ相当を名乗る
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# 連続リクエストの間隔（秒）。429を食らうと最大値まで自動で広がり、成功が続くと戻る
MIN_REQUEST_INTERVAL = 1.0
MAX_REQUEST_INTERVAL = 30.0
# 429を食らうたびに最低これだけは間隔を広げる（乗算だけだと0から増えないため）
INTERVAL_GROWTH_STEP = 1.0

# 再試行の待ち時間は RETRY_BACKOFF_BASE * 2^n 秒（上限 MAX_RETRY_WAIT 秒）
RETRY_BACKOFF_BASE = 5.0
MAX_RETRY_WAIT = 120.0

# 再試行対象のステータスコード（429 = Too Many Requests）
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

_session = None
_last_request_at = 0.0
_current_interval = MIN_REQUEST_INTERVAL


def get_session():
    """ User-Agentを設定した使い回しのSessionを返す """
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return _session


def reset_session():
    """ 接続が切られた後は張り直す（プール内の死んだ接続を掴み続けないため） """
    global _session
    if _session is not None:
        _session.close()
    _session = None


def _throttle():
    """ 直前のリクエストから現在の間隔ぶん空くまで待つ """
    global _last_request_at
    wait = _current_interval - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _slow_down():
    """ 制限を食らったのでリクエスト間隔を広げる """
    global _current_interval
    grown = max(_current_interval * 2, _current_interval + INTERVAL_GROWTH_STEP)
    _current_interval = min(grown, MAX_REQUEST_INTERVAL)


def _speed_up():
    """ 成功が続いたら間隔を少しずつ戻す """
    global _current_interval
    _current_interval = max(_current_interval * 0.9, MIN_REQUEST_INTERVAL)


def _retry_after_seconds(response):
    """ Retry-Afterヘッダ（秒数形式のみ）を読む。無ければNone """
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        # HTTP-date形式は扱わず、指数バックオフにフォールバックする
        return None


def _backoff_wait(attempt):
    return min(RETRY_BACKOFF_BASE * (2 ** attempt), MAX_RETRY_WAIT) + random.uniform(0, 1)


def get_with_retry(url, max_retries=5, timeout=30, **kwargs):
    """ 429/5xxや接続エラーが起きたらバックオフして再試行する requests.get

    待ち時間はRetry-Afterヘッダを優先し、無ければ指数バックオフ（+ジッター）。
    レート制限を受けている間はリクエスト間隔自体も自動で広がる。

    再試行しても解消しない場合、HTTPエラーなら最後のレスポンスをそのまま返すので、
    ステータスコードの判定は呼び出し側でこれまで通り行える。
    接続そのものが確立できない場合は requests の例外をそのまま送出する。
    """
    response = None

    for attempt in range(max_retries + 1):
        _throttle()
        try:
            response = get_session().get(url, timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            # 接続断・タイムアウトもレート制限の一形態として扱い、間隔を広げて粘る
            reset_session()
            _slow_down()
            if attempt == max_retries:
                raise
            wait = _backoff_wait(attempt)
            print(f"接続エラー {url} ({type(e).__name__}) -> {wait:.1f}秒待って再試行 ({attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue

        if response.status_code not in RETRY_STATUS_CODES:
            _speed_up()
            return response

        _slow_down()
        if attempt == max_retries:
            break

        wait = _retry_after_seconds(response)
        if wait is None:
            wait = _backoff_wait(attempt)
        print(f"{response.status_code} {url} -> {wait:.1f}秒待って再試行 ({attempt + 1}/{max_retries})")
        time.sleep(wait)

    return response
