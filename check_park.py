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
EVENT_PAYLOAD = os.environ.get("GITHUB_EVENT_PAYLOAD")

# ★監視したい公園のリスト
TARGET_PARKS = ["芝公園", "砧公園", "上野恩賜公園", "東綾瀬公園", "大井ふ頭海浜公園Ａ", "大井ふ頭海浜公園Ｂ"]

def get_park_slots(page, park_name):
    """特定の公園の空き状況を取得する内部関数"""
    try:
        print(f"--- {park_name} を確認中 ---")
        # トップに戻る
        page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="commit")
        page.wait_for_timeout(3000)

        # 野球を選択
        page.wait_for_selector("#purpose-home")
        page.select_option("#purpose-home", label="野球")
        page.wait_for_timeout(1000)

        # 公園名を選択
        page.wait_for_selector("#bname-home")
        page.select_option("#bname-home", label=park_name)
        page.wait_for_timeout(1000)

        # 検索実行
        page.click("#btn-go")
        page.wait_for_load_state("networkidle")
        
        # カレンダー表示
        page.wait_for_selector("div[data-target='#monthly']", state="visible", timeout=15000)
        page.click("div[data-target='#monthly']")
        page.wait_for_selector("#month-info", timeout=15000)
        page.wait_for_timeout(2000)

        slots = []
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
                    # どの公園の空きか分かるように公園名を付ける
                    slots.append(f"【{park_name}】{formatted_date}{status_symbol}")
                except:
                    continue
        return slots
    except Exception as e:
        print(f"{park_name} の取得中にエラー: {e}")
        return []

def main():
    all_current_slots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", timezone_id="Asia/Tokyo"
        )
        page = context.new_page()

        # リストにある全公園をループで回す
        for park in TARGET_PARKS:
            slots = get_park_slots(page, park)
            all_current_slots.extend(slots)
            page.wait_for_timeout(2000) # サーバー負荷軽減のため少し待つ

        browser.close()

    # --- 宛先判定 ---
    target_user_id = DEFAULT_USER_ID
    is_line_request = False
    if EVENT_PAYLOAD:
        try:
            payload_data = json.loads(EVENT_PAYLOAD)
            if "reply_user_id" in payload_data:
                target_user_id = payload_data["reply_user_id"]
                is_line_request = True
        except:
            pass

    # 差分チェック
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    new_slots = [slot for slot in all_current_slots if slot not in last_slots]

    # 状態保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(all_current_slots))

    # --- 送信 ---
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if is_line_request:
            msg = "【現在の空き状況】\n\n" + ("\n".join(all_current_slots) if all_current_slots else "空き枠はありません。")
            line_bot_api.push_message(PushMessageRequest(to=target_user_id, messages=[TextMessage(text=msg[:4900])]))
        elif new_slots:
            msg = "【新着空き！】\n\n" + "\n".join(new_slots)
            line_bot_api.broadcast(BroadcastRequest(messages=[TextMessage(text=msg[:4900])]))

if __name__ == "__main__":
    main()
