"""Build the visualizer SQLite index from collected data.

Run after collectors finish:

    python -m visualizer.build_index

Writes to `data/output/index/visualizer.db.tmp` first, then renames on success.
The visualizer reads the resulting DB read-only via `visualizer.db.get_conn()`.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from visualizer.db import BASE_DIR, DB_PATH, INDEX_DIR, SCHEMA_VERSION

logger = logging.getLogger(__name__)

DATA_DIR = BASE_DIR / "data"
COMBINER_DIR = DATA_DIR / "output" / "combiner"
COMPARISON_DIR = DATA_DIR / "output" / "comparison"
IPO_REPORTS_NEW_DIR = DATA_DIR / "output" / "edinet_db" / "ipo_reports_new"
IPO_REPORTS_DIR = DATA_DIR / "output" / "edinet_db" / "ipo_reports"

ALL_COMPANIES_PATH = COMBINER_DIR / "all_companies.tsv"
RECENT_IPO_COMPANIES_PATH = COMBINER_DIR / "recent_ipo_companies.tsv"


SCHEMA_SQL = """
CREATE TABLE build_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE companies (
    code               TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    ipo_date           TEXT,
    ipo_year           INTEGER,
    market             TEXT,
    sector             TEXT,
    industry           TEXT,
    current_multiple   REAL,
    max_multiple       REAL,
    president_share    REAL,
    market_cap         REAL,
    all_companies_json TEXT,
    company_dir_new    TEXT,
    company_dir_old    TEXT
);
CREATE INDEX idx_companies_ipo_year ON companies(ipo_year);

CREATE TABLE financial_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code    TEXT NOT NULL,
    report_type     TEXT NOT NULL,
    report_date     TEXT NOT NULL,
    element_id      TEXT NOT NULL,
    element_name    TEXT,
    context_id      TEXT,
    relative_period TEXT,
    consolidation   TEXT,
    period_type     TEXT,
    unit_id         TEXT,
    unit            TEXT,
    value           TEXT
);
CREATE INDEX idx_fm_lookup ON financial_metrics(company_code, element_id);
CREATE INDEX idx_fm_report ON financial_metrics(company_code, report_type, report_date);

CREATE TABLE business_descriptions (
    company_code                TEXT PRIMARY KEY,
    latest_html                 TEXT,
    latest_source_report_type   TEXT,
    latest_source_report_date   TEXT,
    oldest_html                 TEXT,
    oldest_source_report_type   TEXT,
    oldest_source_report_date   TEXT
);

CREATE TABLE officers_info (
    company_code                TEXT PRIMARY KEY,
    latest_html                 TEXT,
    latest_source_report_type   TEXT,
    latest_source_report_date   TEXT,
    oldest_html                 TEXT,
    oldest_source_report_type   TEXT,
    oldest_source_report_date   TEXT
);

-- 有価証券報告書に載る大株主と役員の所有株式数。年ごとに拾っておくと、
-- 期をまたいで突き合わせて「誰が何株売った／買った」が追える。
CREATE TABLE share_holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_code TEXT NOT NULL,
    report_date  TEXT NOT NULL,
    holder_type  TEXT NOT NULL,   -- 'major'（大株主） / 'officer'（役員）
    holder_name  TEXT NOT NULL,
    shares       REAL,
    ratio        REAL
);
CREATE INDEX idx_holdings_lookup ON share_holdings(company_code, report_date);

CREATE TABLE competitors (
    company_code    TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    competitor_code TEXT,
    competitor_name TEXT,
    PRIMARY KEY (company_code, rank)
);
CREATE INDEX idx_comp_lookup ON competitors(company_code);

CREATE TABLE report_files (
    company_code TEXT NOT NULL,
    report_type  TEXT NOT NULL,
    report_date  TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    file_mtime   REAL,
    PRIMARY KEY (company_code, report_type, report_date)
);

CREATE TABLE x_bagger_conditions (
    condition_index INTEGER PRIMARY KEY,
    category        TEXT,
    condition_text  TEXT
);

CREATE TABLE x_bagger_probability (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_list TEXT,
    row_json       TEXT
);
"""


def _normalize_code(raw) -> Optional[str]:
    """Strip market suffix like '1383.T' → '1383'. Return None for invalid."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    return s.split(".", 1)[0]


def _normalize_date(raw) -> Optional[str]:
    """Convert '2011/11/29' or '2011-11-29' → 'YYYY-MM-DD'. None on failure."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d")


def _to_float(raw) -> Optional[float]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_int(raw) -> Optional[int]:
    f = _to_float(raw)
    if f is None:
        return None
    return int(f)


def _row_to_json(row: pd.Series) -> str:
    payload = {}
    for key, value in row.items():
        if pd.isna(value):
            continue
        if isinstance(value, (int, float)):
            payload[str(key)] = value
        else:
            payload[str(key)] = str(value)
    return json.dumps(payload, ensure_ascii=False)


def _load_all_companies(conn: sqlite3.Connection) -> int:
    if not ALL_COMPANIES_PATH.exists():
        logger.warning("all_companies.tsv not found at %s, skipping", ALL_COMPANIES_PATH)
        return 0
    df = pd.read_csv(ALL_COMPANIES_PATH, sep="\t", dtype=str)
    df = df.drop_duplicates(subset=["コード"], keep="last")
    rows = []
    for _, row in df.iterrows():
        code = _normalize_code(row.get("コード"))
        if not code:
            continue
        rows.append(
            (
                code,
                str(row.get("企業名") or "").strip() or code,
                _normalize_date(row.get("上場日")),
                _to_int(row.get("上場年")),
                str(row.get("市場") or "").strip() or None,
                str(row.get("sector") or "").strip() or None,
                str(row.get("industry") or "").strip() or None,
                _to_float(row.get("現在何倍株")),
                _to_float(row.get("最大何倍株")),
                _to_float(row.get("社長_株%")),
                _to_float(row.get("想定時価総額")),
                _row_to_json(row),
                None,
                None,
            )
        )
    conn.executemany(
        """INSERT OR REPLACE INTO companies
           (code, name, ipo_date, ipo_year, market, sector, industry,
            current_multiple, max_multiple, president_share, market_cap,
            all_companies_json, company_dir_new, company_dir_old)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    logger.info("companies: loaded %d rows from all_companies.tsv", len(rows))
    return len(rows)


def _load_recent_ipo(conn: sqlite3.Connection) -> int:
    if not RECENT_IPO_COMPANIES_PATH.exists():
        logger.info("recent_ipo_companies.tsv not present, skipping")
        return 0
    df = pd.read_csv(RECENT_IPO_COMPANIES_PATH, sep="\t", dtype=str)
    updated = 0
    for _, row in df.iterrows():
        code = _normalize_code(row.get("コード"))
        if not code:
            continue
        ipo_date = _normalize_date(row.get("IPO日"))
        ipo_year = _to_int(ipo_date[:4]) if ipo_date else None
        name = str(row.get("企業名") or "").strip() or code
        conn.execute(
            """INSERT INTO companies (code, name, ipo_date, ipo_year)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(code) DO UPDATE SET
                 ipo_date = COALESCE(excluded.ipo_date, companies.ipo_date),
                 ipo_year = COALESCE(excluded.ipo_year, companies.ipo_year),
                 name     = CASE WHEN companies.name = companies.code
                                 THEN excluded.name ELSE companies.name END""",
            (code, name, ipo_date, ipo_year),
        )
        updated += 1
    conn.commit()
    logger.info("companies: applied %d rows from recent_ipo_companies.tsv", updated)
    return updated


_DIR_NAME_RE = re.compile(r"^([^_]+)_(.+)$")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# XBRL element IDs the visualizer actually queries — everything else is dropped
# during build to keep the DB small.
#
# The set is derived from each app's METRIC_ALIASES rather than hand-maintained:
# a hand-written copy silently drifts from the aliases, and a dropped row shows
# up as a whole chart missing from the page rather than as an error. Adding a
# metric to METRIC_ALIASES and rebuilding is enough.
def _collect_metric_element_ids() -> frozenset:
    ids = set()
    for module_name in (
        "visualizer.past_tenbagger.config",
        "visualizer.next_tenbagger.config",
    ):
        module = import_module(module_name)
        for aliases in getattr(module, "METRIC_ALIASES", {}).values():
            ids.update(aliases)
    if not ids:
        raise RuntimeError("METRIC_ALIASES から要素IDを1件も取得できませんでした")
    return frozenset(ids)


_METRIC_ELEMENT_IDS = _collect_metric_element_ids()

# 抽出側(DataService._extract_single_metric)は要素IDを部分一致で拾うので、
# ビルド側も部分一致で残す。完全一致にすると、例えばエイリアスが
# EquityToAssetRatioSummaryOfBusinessResult（末尾s無し）で実データが
# ...Results のとき、DB経路だけ該当行がゼロになりチャートが丸ごと消える。
_METRIC_ID_PATTERN = "|".join(sorted(re.escape(i) for i in _METRIC_ELEMENT_IDS))

_BUSINESS_ELEMENT_ID = "jpcrp_cor:DescriptionOfBusinessTextBlock"
_OFFICERS_ELEMENT_ID = "jpcrp_cor:InformationAboutOfficersTextBlock"

# 大株主と役員の持株。氏名と株数は別行なので、コンテキストIDで突き合わせる
_HOLDING_ELEMENTS = {
    "jpcrp_cor:NameMajorShareholders": ("major", "name"),
    "jpcrp_cor:NumberOfSharesHeld": ("major", "shares"),
    "jpcrp_cor:ShareholdingRatio": ("major", "ratio"),
    "jpcrp_cor:NameInformationAboutDirectorsAndCorporateAuditors": ("officer", "name"),
    "jpcrp_cor:NumberOfSharesHeldOrdinarySharesInformationAboutDirectorsAndCorporateAuditors":
        ("officer", "shares"),
}

# XBRL TSVs from EDINET are UTF-16 LE with BOM; some legacy files are UTF-8.
_FIN_ENCODINGS = ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp932")

# Order of columns in EDINET XBRL TSVs (fixed)
_FIN_COLUMNS = [
    "要素ID", "項目名", "コンテキストID", "相対年度", "連結・個別",
    "期間・時点", "ユニットID", "単位", "値",
]

_REPORT_SUBDIRS = {
    "annual_securities_reports": "annual",
    "quarterly_reports": "quarterly",
    "securities_registration_statement": "securities_registration",
}


def _scan_reports_dir(conn: sqlite3.Connection, root: Path, column: str) -> int:
    if not root.exists():
        logger.warning("directory not found: %s", root)
        return 0
    count = 0
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        m = _DIR_NAME_RE.match(entry.name)
        if not m:
            continue
        code, name = m.group(1), m.group(2)
        conn.execute(
            f"""INSERT INTO companies (code, name, {column})
                VALUES (?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                  {column} = excluded.{column},
                  name     = CASE WHEN companies.name = companies.code
                                  THEN excluded.name ELSE companies.name END""",
            (code, name, entry.name),
        )
        count += 1
    conn.commit()
    logger.info("companies: scanned %d directories in %s", count, root.name)
    return count


def _read_xbrl_tsv(path: Path) -> Optional[pd.DataFrame]:
    """Read an EDINET XBRL TSV file, trying known encodings."""
    for enc in _FIN_ENCODINGS:
        try:
            df = pd.read_csv(path, sep="\t", encoding=enc, dtype=str, on_bad_lines="skip")
            if len(df.columns) >= len(_FIN_COLUMNS):
                df.columns = _FIN_COLUMNS + list(df.columns[len(_FIN_COLUMNS):])
                return df
            df = df.reindex(columns=_FIN_COLUMNS)
            return df
        except (UnicodeError, UnicodeDecodeError):
            continue
        except Exception:
            continue
    return None


def _extract_report_date(file_path: Path) -> str:
    m = _DATE_RE.search(file_path.name)
    return m.group(1) if m else "0000-00-00"


def _iter_report_files() -> Iterable[tuple]:
    """Yield (code, report_type, report_date, path) tuples for every XBRL TSV."""
    for root_dir in (IPO_REPORTS_NEW_DIR, IPO_REPORTS_DIR):
        if not root_dir.exists():
            continue
        for company_dir in root_dir.iterdir():
            if not company_dir.is_dir():
                continue
            m = _DIR_NAME_RE.match(company_dir.name)
            if not m:
                continue
            code = m.group(1)
            for subdir_name, report_type in _REPORT_SUBDIRS.items():
                subdir = company_dir / subdir_name
                if not subdir.exists():
                    continue
                for tsv in sorted(subdir.glob("*.tsv")):
                    yield code, report_type, _extract_report_date(tsv), tsv


def _extract_holdings(df, code: str, report_date: str) -> list:
    """大株主・役員の持株を (会社, 報告日, 種別, 氏名, 株数, 比率) の形で取り出す。

    XBRLでは氏名・株数・比率がそれぞれ別行になっていて、同じコンテキストIDを
    持つものが1人分にあたる。
    """
    hit = df[df["要素ID"].isin(_HOLDING_ELEMENTS)]
    if hit.empty:
        return []

    people: dict = {}
    for _, row in hit.iterrows():
        holder_type, field = _HOLDING_ELEMENTS[row["要素ID"]]
        context = row.get("コンテキストID")
        if not context:
            continue
        entry = people.setdefault((holder_type, context), {})
        entry[field] = row.get("値")

    def number(value):
        if value is None:
            return None
        text = str(value).replace(",", "").replace("△", "-").strip()
        if text in ("", "-", "－", "―", "nan"):
            return None
        try:
            return float(text)
        except ValueError:
            return None

    rows = []
    for (holder_type, _), entry in people.items():
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        rows.append((code, report_date, holder_type, name.strip(),
                     number(entry.get("shares")), number(entry.get("ratio"))))
    return rows


def _update_textblock_tracker(
    tracker: dict[str, dict], code: str, value: str, report_type: str, report_date: str
) -> None:
    """Track latest + oldest per company for one text block element."""
    slot = tracker.setdefault(code, {"latest": None, "oldest": None})
    entry = (value, report_type, report_date)
    if slot["latest"] is None or report_date > slot["latest"][2]:
        slot["latest"] = entry
    if slot["oldest"] is None or report_date < slot["oldest"][2]:
        slot["oldest"] = entry


def _textblock_rows(tracker: dict[str, dict]) -> list[tuple]:
    out = []
    for code, slot in tracker.items():
        latest = slot["latest"] or (None, None, None)
        oldest = slot["oldest"] or (None, None, None)
        out.append((code, *latest, *oldest))
    return out


def _load_financials(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
    """Load financial_metrics, business_descriptions, officers_info, report_files."""
    metric_rows = 0
    business_tracker: dict[str, dict] = {}
    officers_tracker: dict[str, dict] = {}
    file_rows: list[tuple] = []
    holding_rows: list[tuple] = []
    processed = 0
    failed = 0
    started = time.time()

    metric_buffer: list[tuple] = []
    BATCH = 5000

    def flush_metrics() -> None:
        nonlocal metric_rows
        if not metric_buffer:
            return
        conn.executemany(
            """INSERT INTO financial_metrics
               (company_code, report_type, report_date, element_id, element_name,
                context_id, relative_period, consolidation, period_type,
                unit_id, unit, value)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            metric_buffer,
        )
        metric_rows += len(metric_buffer)
        metric_buffer.clear()

    for code, report_type, report_date, path in _iter_report_files():
        processed += 1
        try:
            stat = path.stat()
            file_rows.append((
                code, report_type, report_date,
                str(path.relative_to(BASE_DIR)).replace("\\", "/"),
                stat.st_mtime,
            ))
        except OSError:
            failed += 1
            continue

        df = _read_xbrl_tsv(path)
        if df is None:
            failed += 1
            continue

        # Business description / officers — track latest AND oldest per company
        for elem_id, tracker in (
            (_BUSINESS_ELEMENT_ID, business_tracker),
            (_OFFICERS_ELEMENT_ID, officers_tracker),
        ):
            hit = df[df["要素ID"] == elem_id]
            if hit.empty:
                continue
            value = hit.iloc[0].get("値")
            if not isinstance(value, str) or not value.strip():
                continue
            _update_textblock_tracker(tracker, code, value, report_type, report_date)

        # 大株主・役員の持株（有報のみ。届出書は上場前の姿なので比較に使わない）
        if report_type == "annual":
            holding_rows.extend(_extract_holdings(df, code, report_date))

        # Financial metrics: whitelist filter（抽出側と同じ部分一致）
        filtered = df[df["要素ID"].str.contains(_METRIC_ID_PATTERN, na=False, regex=True)]
        if filtered.empty:
            continue
        for _, row in filtered.iterrows():
            metric_buffer.append((
                code, report_type, report_date,
                row.get("要素ID"),
                row.get("項目名"),
                row.get("コンテキストID"),
                row.get("相対年度"),
                row.get("連結・個別"),
                row.get("期間・時点"),
                row.get("ユニットID"),
                row.get("単位"),
                row.get("値"),
            ))
            if len(metric_buffer) >= BATCH:
                flush_metrics()

        if processed % 1000 == 0:
            flush_metrics()
            conn.commit()
            elapsed = time.time() - started
            logger.info(
                "financials: processed %d files (%.0f files/s, %d metric rows, %d failed)",
                processed, processed / elapsed, metric_rows, failed,
            )

    flush_metrics()

    conn.executemany(
        """INSERT OR REPLACE INTO report_files
           (company_code, report_type, report_date, file_path, file_mtime)
           VALUES (?,?,?,?,?)""",
        file_rows,
    )
    conn.executemany(
        """INSERT INTO share_holdings
           (company_code, report_date, holder_type, holder_name, shares, ratio)
           VALUES (?,?,?,?,?,?)""",
        holding_rows,
    )
    logger.info("share holdings: %d rows", len(holding_rows))
    conn.executemany(
        """INSERT OR REPLACE INTO business_descriptions
           (company_code,
            latest_html, latest_source_report_type, latest_source_report_date,
            oldest_html, oldest_source_report_type, oldest_source_report_date)
           VALUES (?,?,?,?,?,?,?)""",
        _textblock_rows(business_tracker),
    )
    conn.executemany(
        """INSERT OR REPLACE INTO officers_info
           (company_code,
            latest_html, latest_source_report_type, latest_source_report_date,
            oldest_html, oldest_source_report_type, oldest_source_report_date)
           VALUES (?,?,?,?,?,?,?)""",
        _textblock_rows(officers_tracker),
    )
    conn.commit()
    elapsed = time.time() - started
    logger.info(
        "financials: %d files in %.1fs (%d metric rows, %d business, %d officers, %d failed)",
        processed, elapsed, metric_rows, len(business_tracker), len(officers_tracker), failed,
    )
    return processed, metric_rows, len(business_tracker), len(officers_tracker)


def _load_competitors(conn: sqlite3.Connection) -> int:
    files = sorted(COMPARISON_DIR.glob("companies_*.tsv"), reverse=True)
    if not files:
        logger.warning("no comparison/companies_*.tsv files found")
        return 0
    seen = set()
    rows = []
    for path in files:
        try:
            df = pd.read_csv(path, sep="\t", dtype=str)
        except Exception as exc:
            logger.warning("failed to read %s: %s", path, exc)
            continue
        for _, row in df.iterrows():
            code = _normalize_code(row.get("コード"))
            if not code or code in seen:
                continue
            raw_list = row.get("競合リスト")
            if raw_list is None or pd.isna(raw_list):
                continue
            try:
                items = json.loads(raw_list)
            except (TypeError, ValueError) as exc:
                logger.debug("bad JSON for %s in %s: %s", code, path.name, exc)
                continue
            if not isinstance(items, list) or not items:
                continue
            seen.add(code)
            for rank, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                rows.append(
                    (
                        code,
                        rank,
                        _normalize_code(item.get("code")),
                        (item.get("name") or "").strip() or None,
                    )
                )
    conn.executemany(
        """INSERT OR REPLACE INTO competitors
           (company_code, rank, competitor_code, competitor_name)
           VALUES (?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    logger.info("competitors: loaded %d rows for %d companies", len(rows), len(seen))
    return len(rows)


def _load_x_bagger(conn: sqlite3.Connection) -> tuple[int, int]:
    """Load x_bagger conditions and probability tables."""
    xb_dir = COMBINER_DIR / "x_bagger_probability"
    cond_path = xb_dir / "x_bagger_conditions.tsv"
    prob_path = xb_dir / "x_bagger_probability.tsv"

    cond_count = 0
    if cond_path.exists():
        df = pd.read_csv(cond_path, sep="\t", dtype=str)
        rows = []
        for _, row in df.iterrows():
            idx = _to_int(row.get("条件index"))
            if idx is None:
                continue
            rows.append((
                idx,
                (row.get("対象の条件") or "").strip() or None,
                (row.get("条件") or "").strip() or None,
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO x_bagger_conditions (condition_index, category, condition_text) VALUES (?, ?, ?)",
            rows,
        )
        cond_count = len(rows)

    prob_count = 0
    if prob_path.exists():
        df = pd.read_csv(prob_path, sep="\t", dtype=str)
        rows = []
        for _, row in df.iterrows():
            payload = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
            rows.append((
                (row.get("条件リスト") or "").strip() or None,
                json.dumps(payload, ensure_ascii=False),
            ))
        conn.executemany(
            "INSERT INTO x_bagger_probability (condition_list, row_json) VALUES (?, ?)",
            rows,
        )
        prob_count = len(rows)

    conn.commit()
    logger.info("x_bagger: %d conditions, %d probability rows", cond_count, prob_count)
    return cond_count, prob_count


def build(target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    try:
        conn.executescript(SCHEMA_SQL)

        _load_all_companies(conn)
        _load_recent_ipo(conn)
        _scan_reports_dir(conn, IPO_REPORTS_NEW_DIR, "company_dir_new")
        _scan_reports_dir(conn, IPO_REPORTS_DIR, "company_dir_old")
        _load_competitors(conn)
        _load_financials(conn)
        _load_x_bagger(conn)

        conn.execute(
            "INSERT INTO build_meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        conn.execute(
            "INSERT INTO build_meta (key, value) VALUES ('built_at', ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        conn.commit()
    finally:
        conn.close()

    if target.exists():
        target.unlink()
    tmp.rename(target)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DB_PATH,
        help=f"Output SQLite path (default: {DB_PATH})",
    )
    args = parser.parse_args(argv)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    logger.info("Building visualizer index at %s", args.output)
    build(args.output)
    logger.info("Done in %.1fs", time.time() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
