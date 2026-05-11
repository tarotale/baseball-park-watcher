import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, BroadcastRequest, TextMessage
)

# --- 設定情報 ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
DEFAULT_USER_ID = os.environ.get("USER_ID")
STATUS_FILE = "last_status.txt"
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME")
EVENT_PAYLOAD = os.environ.get("GITHUB_EVENT_PAYLOAD")

def check_park_availability():
    """芝公園の空き状況をスクレイピング"""
    with sync_playwright() as p:
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
            page.wait_for_timeout(5000)

            if "現在、大変混み合っております" in page.inner_text("body"):
                return None

            print("2. 野球・芝公園を選択...")
            page.wait_for_selector("#purpose-home", state="attached", timeout=20000)
            page.select_option("#purpose-home", label="野球")
            page.wait_for_timeout(2000)
            page.wait_for_selector("#bname-home", state="attached", timeout=20000)
            page.select_option("#bname-home", label="芝公園")
            
            print("3. 検索実行...")
            page.click("#btn-go", force=True)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            print("4. カレンダー展開...")
            page.wait_for_selector("div[data-target='#monthly']", state="visible", timeout=20000)
            page.click("div[data-target='#monthly']")
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
                    try:
                        date_obj = datetime.strptime(date_raw, '%Y%m%d')
                        week_label = weeks[date_obj.weekday()]
                        formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}({week_label})"
                        status_symbol = "○" if alt_text == "空き" else "▲"
                        current_slots.append(f"{formatted_date}{status_symbol}")
                    except:
                        continue
            return current_slots
        except Exception as e:
            print(f"エラー: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    # 宛先判定の初期化
    target_user_id = DEFAULT_USER_ID
    is_line_request = False
    
    # GASからのバトンパス(client_payload)を確認
    if EVENT_PAYLOAD:
        try:
            payload_data = json.loads(EVENT_PAYLOAD)
            if "reply_user_id" in payload_data:
                target_user_id = payload_data["reply_user_id"]
                is_line_request = True
        except:
            pass

    current_slots = check_park_availability()
    if current_slots is None:
        exit(1)

    # 差分用履歴の読み込み
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 今回の状態を保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    # --- 送信判定 ---
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if is_line_request:
            # LINEで「確認」と言われた場合は、空きがなくても必ず返信する
            if not current_slots:
                msg = "【現在の空き状況】\n\n現在、空き枠はありません。"
            else:
                info_list = "、".join(sorted(list(set(current_slots))))
                msg = f"【現在の空き状況】\n\n対象枠：\n{info_list}\n\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
            
            line_bot_api.push_message(PushMessageRequest(
                to=target_user_id,
                messages=[TextMessage(text=msg)]
            ))
            print(f"個別返信完了: {target_user_id}")

        elif new_slots:
            # 30分おきの自動実行で「新着」がある場合のみ全員に送信
            info_list = "、".join(sorted(list(set(new_slots))))
            msg = f"【新着空き！】\n\n対象枠：\n{info_list}\n\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
            
            line_bot_api.broadcast(BroadcastRequest(
                messages=[TextMessage(text=msg)]
            ))
            print("一斉送信完了")
        else:
            print("通知の必要なし（自動実行かつ新着なし）")
