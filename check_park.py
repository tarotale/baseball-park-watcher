import os
from datetime import datetime
from playwright.sync_api import sync_playwright
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")
STATUS_FILE = "last_status.txt"
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME")

def check_park_availability():
    with sync_playwright() as p:
        # ブラウザを「日本語設定」で起動
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
            timezone_id="Asia/Tokyo"
        )
        page = context.new_page()
        
        try:
            print("1. サイトにアクセス中...")
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="commit", timeout=60000)
            
            # 画面が読み込まれるまで少し待つ
            page.wait_for_timeout(5000)
            
            # 【重要】今、画面に何が見えているかログに出す（デバッグ用）
            page_text = page.inner_text("body")
            print(f"--- 現在の画面テキスト(冒頭100文字) ---\n{page_text[:100]}\n--------------------------------")

            if "現在、大変混み合っております" in page_text:
                print("サーバーが混雑しているようです。")
                return None

            print("2. 目的（野球）を選択...")
            # セレクタが見つからない場合に備え、存在を確認してから操作
            page.wait_for_selector("#purpose-home", state="attached", timeout=20000)
            page.select_option("#purpose-home", label="野球")
            page.wait_for_timeout(2000)

            print("3. 公園（芝公園）を選択...")
            page.wait_for_selector("#bname-home", state="attached", timeout=20000)
            page.select_option("#bname-home", label="芝公園")
            page.wait_for_timeout(2000)

            print("4. 検索実行...")
            # 強制クリック
            page.click("#btn-go", force=True)
            
            print("5. 画面遷移を待機中...")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            print("6. 月表示カレンダーを展開...")
            expand_btn = page.wait_for_selector("div[data-target='#monthly']", timeout=20000)
            expand_btn.click()
            
            print("7. カレンダーの中身を待機...")
            page.wait_for_selector("#month-info", timeout=20000)
            page.wait_for_timeout(3000)

            current_slots = []
            weeks = ['月', '火', '水', '木', '金', '土', '日']
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    date_obj = datetime.strptime(date_raw, '%Y%m%d')
                    week_label = weeks[date_obj.weekday()]
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}({week_label})"
                    status_symbol = "○" if alt_text == "空き" else "▲"
                    current_slots.append(f"{formatted_date}{status_symbol}")
            
            return current_slots
        except Exception as e:
            print(f"エラー発生: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # (メイン処理部分は前回と同じ)
    current_slots = check_park_availability()
    # ...以下略...
