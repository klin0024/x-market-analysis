"""
產生 X（Twitter）登入 session，儲存為 auth_state.json。

用法：
    python scripts/x_login.py [--output auth_state.json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="產生 X 登入 session")
    parser.add_argument("--output", default="auth_state.json", help="輸出檔案路徑（預設 auth_state.json）")
    args = parser.parse_args()

    output = Path(args.output)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("錯誤：請先安裝 playwright：pip install playwright && playwright install chromium")
        sys.exit(1)

    print("開啟瀏覽器，請手動登入 X（Twitter）...")
    print("登入完成後回到此視窗按 Enter。\n")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://x.com/login")

            input("登入後按 Enter 儲存 session...")

            context.storage_state(path=str(output))
            browser.close()
    except Exception as e:
        print(f"錯誤：{e}")
        print("提示：請確認已執行 playwright install chromium")
        sys.exit(1)

    print(f"Session 已儲存至 {output}")


if __name__ == "__main__":
    main()
