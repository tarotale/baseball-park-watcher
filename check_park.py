import os
from datetime import datetime
from playwright.sync_api import sync_playwright
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, TextMessage
)

# 環境変数の取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")
STATUS_FILE = "last_status.txt"
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME")

def check_park_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            print("1. サイトにアクセス中...")
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
            weeks = ['月', '火', '水', '木', '金', '土', '日']
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    
                    # 曜日取得
                    date_obj = datetime.strptime(date_raw, '%Y%m%d')
                    week_label = weeks[date_obj.weekday()]

                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}({week_label})"
                    status_symbol = "○" if alt_text == "空き" else "▲"
                    current_slots.append(f"{formatted_date}{status_symbol}")
            
            return current_slots
        except Exception as e:
            print(f"スクレイピングエラー: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # LINEのトークンチェック
    if not LINE_CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("エラー: LINEの設定(Secrets)が足りません。")
        exit(1)

    # スクレイピング実行
    current_slots = check_park_availability()
    if current_slots is None:
        print("スクレイピングに失敗したため終了します。")
        exit(1)

    # 強制モード判定
    is_force = EVENT_NAME in ["workflow_dispatch", "repository_dispatch"]

    # 履歴管理
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    # 新着のみ抽出
    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 今回の状態を上書き保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    # 通知対象の決定
    target_slots = current_slots if is_force else new_slots

    if target_slots:
        title = "【現在の空き状況】" if is_force else "【新着空き！】"
        info_list = "、".join(sorted(list(set(target_slots))))
        message_text = f"{title}\n\n対象枠：\n{info_list}\n\n予約：\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        
        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=USER_ID,
                messages=[TextMessage(text=message_text)]
            )
            line_bot_api.push_message(push_message_request)
        print(f"通知完了: {info_list}")
    else:
        print("通知の必要はありません。")
