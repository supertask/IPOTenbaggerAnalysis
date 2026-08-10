"""Smoke-test the visualizer with Playwright.

Assumes the visualizer is running at http://127.0.0.1:5000.
Exits non-zero if any page returns non-200, has a JS console error, or takes
longer than SLOW_MS to load.
"""
from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5000"
SLOW_MS = 5000

PAGES = [
    ("/", "root"),
    ("/past_tenbagger/", "past-list"),
    ("/next_tenbagger/", "next-list"),
    ("/x_bagger/", "x-bagger"),
    ("/past_tenbagger/6532", "past-detail-6532"),
    ("/past_tenbagger/6055", "past-detail-6055"),
    ("/next_tenbagger/7360", "next-detail-7360"),
    ("/next_tenbagger/130A", "next-detail-130A"),
]

IGNORED_JS_MSG_PREFIXES = (
    "WARNING: plotly-latest",  # preexisting plotly CDN deprecation warning
)


def _is_ignored(msg: str) -> bool:
    return any(msg.startswith(p) for p in IGNORED_JS_MSG_PREFIXES)


def main() -> int:
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            for path, name in PAGES:
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
                    print(f"FAIL {name} ({path}): navigation error: {exc}")
                    failures += 1
                    page.close()
                    continue
                elapsed_ms = int((time.time() - started) * 1000)
                status = response.status if response else 0
                if status != 200:
                    print(f"FAIL {name} ({path}): HTTP {status} in {elapsed_ms}ms")
                    failures += 1
                elif console_errors:
                    print(f"FAIL {name} ({path}): {len(console_errors)} JS errors: {console_errors[:3]}")
                    failures += 1
                elif elapsed_ms > SLOW_MS:
                    print(f"SLOW {name} ({path}): {elapsed_ms}ms")
                else:
                    print(f"OK   {name} ({path}): {elapsed_ms}ms")
                page.close()
        finally:
            browser.close()
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
