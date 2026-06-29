import os
import json
import re
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

TARGET_PARKS = ["芝公園", "砧公園", "上野恩賜公園", "東綾瀬公園", "大井ふ頭海浜公園Ａ", "大井ふ頭海浜公園Ｂ"]

def get_park_slots(page, park_name):
    """特定の公園の空き状況を取得する（リトライ機能付き）"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"--- {park_name} を確認中 (試行 {attempt + 1}/{max_retries}) ---")
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            # 1. 種目「野球」を選択
            page.wait_for_selector("#purpose-home")
            page.select_option("#purpose-home", label="野球")
            
            # 2. 公園リストが有効になるまで少し待つ
            page.wait_for_timeout(3000)
            
            # 公園名を選択できるかチェック
            park_select = page.locator("#bname-home")
            if park_select.is_disabled():
                print(f"  [警告] 公園リストがまだ無効です。再試行します...")
                continue
            
            # 3. 公園名を選択
            page.select_option("#bname-home", label=park_name)
            page.wait_for_timeout(1000)

            # 4. 検索実行
            page.click("#btn-go")
            
            # 5. カレンダー表示ボタンが「見える」まで待ってからクリック
            page.wait_for_selector("div[data-target='#monthly']", state="visible", timeout=30000)
            page.click("div[data-target='#monthly']")
            
            # 6. カレンダー(table)が「隠れていない(visible)」状態になるまで最大30秒待つ
            page.wait_for_selector("#month-info", state="visible", timeout=30000)
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
                        slots.append(f"【{park_name}】{formatted_date}{status_symbol}")
                    except:
                        continue
            
            print(f"  [成功] {len(slots)}件の空きが見つかりました")
            return slots

        except Exception as e:
            print(f"  [エラー] {park_name} の取得中に問題発生: {e}")
            if attempt == max_retries - 1:
                return []
            page.wait_for_timeout(5000)

def format_message(slots_list, title_prefix):
    """取得したスロットを公園ごとにグループ化して整形する"""
    if not slots_list:
        return f"{title_prefix}\n\n現在、空き枠はありません。"
    
    grouped_slots = {}
    for item in slots_list:
        match = re.match(r"【(.*?)】(.*)", item)
        if match:
            p_name, p_date = match.groups()
            if p_name not in grouped_slots:
                grouped_slots[p_name] = []
            grouped_slots[p_name].append(p_date)

    msg_parts = [title_prefix]
    for p_name in TARGET_PARKS:
        if p_name in grouped_slots:
            p_dates = grouped_slots[p_name]
            sorted_dates = sorted(list(set(p_dates)))
            msg_parts.append(f"\n【{p_name}】\n" + "、".join(sorted_dates))
    
    msg_parts.append("\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp")
    return "\n".join(msg_parts)

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

        for park in TARGET_PARKS:
            slots = get_park_slots(page, park)
            all_current_slots.extend(slots)
            page.wait_for_timeout(2000)

        browser.close()

    # --- 宛先判定 ---
    target_user_id = DEFAULT_USER_ID
    is_line_request = False
    if EVENT_PAYLOAD:
        try:
            payload_data = EVENT_PAYLOAD if isinstance(EVENT_PAYLOAD, dict) else json.loads(EVENT_PAYLOAD)
            if payload_data and "reply_user_id" in payload_data:
                target_user_id = payload_data["reply_user_id"]
                is_line_request = True
        except:
            pass

    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    new_slots = [slot for slot in all_current_slots if slot not in last_slots]
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(all_current_slots))

    # --- LINE送信（ここに対策が入っています） ---
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        try:
            if is_line_request:
                msg = format_message(all_current_slots, "【現在の空き状況】")
                line_bot_api.push_message(PushMessageRequest(to=target_user_id, messages=[TextMessage(text=msg[:4900])]))
                print("個別返信の送信に成功しました。")
            elif new_slots:
                msg = format_message(new_slots, "【新着空き！】")
                line_bot_api.broadcast(BroadcastRequest(messages=[TextMessage(text=msg[:4900])]))
                print("新着通知（一斉送信）に成功しました。")
        except Exception as line_error:
            # ★ LINE送信でエラー（上限到達など）が起きても、ここでエラーをキャッチして安全にスルーします
            print(f"[警告] LINE送信中にエラーが発生しました（上限到達の可能性があります）: {line_error}")

if __name__ == "__main__":
    main()
