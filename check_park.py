import os
from playwright.sync_api import sync_playwright
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")
STATUS_FILE = "last_status.txt"
# Actions側で設定した環境変数を取得
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME")

def check_park_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle")
            page.select_option("#purpose-home", value="1000_1000")
            page.wait_for_timeout(1000)
            page.select_option("#bname-home", value="1010")
            page.wait_for_timeout(1000)
            page.click("#btn-go")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            expand_btn = page.wait_for_selector("div[data-target='#monthly']", timeout=15000)
            expand_btn.click()
            page.wait_for_selector("#month-info img.calendar-status", timeout=10000)

            current_slots = []
            cells = page.query_selector_all("#month-info td[id^='month_']")
            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}"
                    status_symbol = "○" if alt_text == "空き" else "▲"
                    current_slots.append(f"{formatted_date}{status_symbol}")
            return current_slots
        except Exception as e:
            print(f"エラー: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    current_slots = check_park_availability()
    if current_slots is None: exit(1)

    # 手動実行またはLINEからの合図なら「強制モード（全件通知）」
    is_force = EVENT_NAME in ["workflow_dispatch", "repository_dispatch"]

    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    # 差分（新着）を抽出
    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 今回の状態を保存
    with open(STATUS_FILE, "w") as f:
        f.write("\n".join(current_slots))

    # 通知対象の決定
    target_slots = current_slots if is_force else new_slots

    if target_slots:
        title = "【現在の空き状況】" if is_force else "【新着空き！】"
        info_list = "、".join(sorted(target_slots))
        message_text = f"{title}\n\n対象枠：\n{info_list}\n\n予約：\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        
        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(PushMessageRequest(
                to=USER_ID, messages=[TextMessage(text=message_text)]
            ))
        print(f"通知送信: {info_list}")
    else:
        print("通知対象なし")
