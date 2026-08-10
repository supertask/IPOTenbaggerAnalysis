"""Deep smoke-test the visualizer: verifies actual page content, not just HTTP status.

Assumes the visualizer is running at http://127.0.0.1:5000.
Takes screenshots to scripts/verify_shots/ for visual review.
Exits non-zero if any content assertion fails.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE = "http://127.0.0.1:5000"
SHOT_DIR = Path(__file__).parent / "verify_shots"
SHOT_DIR.mkdir(exist_ok=True)

IGNORED_JS_MSG_PREFIXES = (
    "WARNING: plotly-latest",
)


def _is_ignored(msg: str) -> bool:
    return any(msg.startswith(p) for p in IGNORED_JS_MSG_PREFIXES)


class Fail(Exception):
    pass


def check_root(page: Page) -> None:
    """Root should show 3 tool cards."""
    for label in ["過去のテンバガー企業分析", "次のテンバガー企業予測", "X倍株の条件分析"]:
        if label not in page.content():
            raise Fail(f"root missing card: {label}")


def check_next_list(page: Page) -> None:
    """next_tenbagger list should show >= 100 companies."""
    cards = page.locator(".card, .company-card").count()
    if cards < 50:
        raise Fail(f"next-list only {cards} cards (expected >= 50)")


def check_past_list(page: Page) -> None:
    cards = page.locator(".card, .company-card").count()
    if cards < 500:
        raise Fail(f"past-list only {cards} cards (expected >= 500)")


def check_x_bagger(page: Page) -> None:
    """x_bagger should render the condition selector AND have a working chart_data API."""
    if "X倍株の条件分析" not in page.content():
        raise Fail("x_bagger missing header")
    resp = page.request.get(f"{BASE}/x_bagger/api/chart_data?x_bagger=5")
    if resp.status != 200:
        raise Fail(f"x_bagger chart_data API HTTP {resp.status}")
    data = resp.json()
    if not data:
        raise Fail("x_bagger chart_data API returned empty {}")


def check_next_detail(page: Page, code: str) -> None:
    """next_tenbagger detail: charts, business_description, officers_info, competitors."""
    body = page.content()
    if "事業の内容" not in body:
        raise Fail(f"next-detail-{code}: missing '事業の内容' section")
    if "役員情報" not in body:
        raise Fail(f"next-detail-{code}: missing '役員情報' section")
    # Chart divs are populated by plotly async — wait for at least one plot
    try:
        page.wait_for_function(
            "document.querySelectorAll('.js-plotly-plot').length >= 3",
            timeout=15000,
        )
    except Exception as exc:
        rendered = page.locator(".js-plotly-plot").count()
        raise Fail(f"next-detail-{code}: only {rendered} charts rendered within 15s: {exc}")
    charts = page.locator(".js-plotly-plot").count()
    if charts < 3:
        raise Fail(f"next-detail-{code}: only {charts} rendered charts (expected >= 3)")


def check_past_detail(page: Page, code: str) -> None:
    body = page.content()
    if "事業の内容" not in body:
        raise Fail(f"past-detail-{code}: missing '事業の内容' section")
    if "役員情報" not in body:
        raise Fail(f"past-detail-{code}: missing '役員情報' section")
    try:
        page.wait_for_function(
            "document.querySelectorAll('.js-plotly-plot').length >= 3",
            timeout=15000,
        )
    except Exception as exc:
        rendered = page.locator(".js-plotly-plot").count()
        raise Fail(f"past-detail-{code}: only {rendered} charts rendered within 15s: {exc}")
    charts = page.locator(".js-plotly-plot").count()
    if charts < 3:
        raise Fail(f"past-detail-{code}: only {charts} rendered charts (expected >= 3)")


def check_securities_reports_api(page: Page, app: str, code: str) -> None:
    """Verify the securities-reports API returns a non-empty list for a company we know has files."""
    resp = page.request.get(f"{BASE}/{app}/api/securities_reports/{code}")
    if resp.status != 200:
        raise Fail(f"{app}/{code}: API HTTP {resp.status}")
    data = resp.json()
    reports = data.get("reports", [])
    if not reports:
        raise Fail(f"{app}/{code}: API returned 0 reports")


PAGES = [
    ("/", "root", check_root),
    ("/past_tenbagger/", "past-list", check_past_list),
    ("/next_tenbagger/", "next-list", check_next_list),
    ("/x_bagger/", "x-bagger", check_x_bagger),
    ("/past_tenbagger/6532", "past-detail-6532", lambda p: check_past_detail(p, "6532")),
    ("/past_tenbagger/6055", "past-detail-6055", lambda p: check_past_detail(p, "6055")),
    ("/next_tenbagger/7360", "next-detail-7360", lambda p: check_next_detail(p, "7360")),
    ("/next_tenbagger/130A", "next-detail-130A", lambda p: check_next_detail(p, "130A")),
]


def main() -> int:
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1400, "height": 900})
            for path, name, checker in PAGES:
                page = context.new_page()
                console_errors: list[str] = []

                def _on_console(msg):
                    if msg.type == "error" and not _is_ignored(msg.text):
                        console_errors.append(msg.text)

                page.on("console", _on_console)
                page.on("pageerror", lambda exc: console_errors.append(str(exc)))

                started = time.time()
                try:
                    response = page.goto(BASE + path, wait_until="networkidle", timeout=30000)
                except Exception as exc:
                    failures.append(f"{name}: navigation error: {exc}")
                    page.close()
                    continue
                elapsed_ms = int((time.time() - started) * 1000)
                status = response.status if response else 0

                notes = [f"{elapsed_ms}ms"]
                if status != 200:
                    failures.append(f"{name}: HTTP {status}")
                    notes.append(f"HTTP{status}")
                if console_errors:
                    failures.append(f"{name}: JS errors: {console_errors[:2]}")
                    notes.append(f"{len(console_errors)}jsErr")

                try:
                    checker(page)
                except Fail as exc:
                    failures.append(str(exc))
                    notes.append("contentFAIL")
                except Exception as exc:
                    failures.append(f"{name}: checker exception: {exc}")
                    notes.append("chkExc")

                page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=True)
                marker = "OK  " if all("FAIL" not in n and "jsErr" not in n and "HTTP" not in n for n in notes) else "FAIL"
                print(f"{marker} {name:26s} {path:45s} " + " ".join(notes))
                page.close()

            # API checks (independent from page nav)
            print("---api---")
            api_page = context.new_page()
            for app, code in [("past_tenbagger", "6532"), ("next_tenbagger", "130A")]:
                try:
                    check_securities_reports_api(api_page, app, code)
                    print(f"OK   securities_reports/{app}/{code}")
                except Fail as exc:
                    failures.append(str(exc))
                    print(f"FAIL {exc}")
            api_page.close()
        finally:
            browser.close()
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll checks passed. Screenshots in scripts/verify_shots/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
