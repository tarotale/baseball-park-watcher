import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, PushMessageRequest, BroadcastRequest, TextMessage
)

# --- 環境設定（GitHub Secretsから取得） ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
DEFAULT_USER_ID = os.environ.get("USER_ID") # ShotaroさんのID
STATUS_FILE = "last_status.txt"
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME")
# GASから送られてくる「宛先ID」を含むデータ
EVENT_PAYLOAD = os.environ.get("GITHUB_EVENT_PAYLOAD")

def check_park_availability():
    """東京都公園予約サイトをスクレイピングする"""
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
                print("サーバー混雑中")
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

            print("4. カレンダー情報を取得...")
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
            print(f"スクレイピング失敗: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not DEFAULT_USER_ID:
        print("必要な環境変数が設定されていません。")
        exit(1)

    # --- 宛先決定の徹底ロジック ---
    target_user_id = DEFAULT_USER_ID
    is_line_request = False

    if EVENT_PAYLOAD:
        try:
            # GASからの client_payload を解析
            payload_data = json.loads(EVENT_PAYLOAD)
            # 送信元ユーザーID(reply_user_id)があれば、それを宛先にする
            if "reply_user_id" in payload_data:
                target_user_id = payload_data["reply_user_id"]
                is_line_request = True
                print(f"LINEからのリクエストを受信。宛先ID: {target_user_id}")
        except Exception as e:
            print(f"ペイロード解析失敗: {e}")

    # スクレイピング実行
    current_slots = check_park_availability()
    if current_slots is None:
        exit(1)

    # 差分チェック
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 今回の状態を保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    # 要件：LINEリクエストなら全件、自動なら新着のみ
    target_slots = current_slots if is_line_request else new_slots

    if target_slots:
        title = "【現在の空き状況】" if is_line_request else "【新着空き！】"
        info_list = "、".join(sorted(list(set(target_slots))))
        message_text = f"{title}\n\n対象枠：\n{info_list}\n\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        
        try:
            configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                
                if is_line_request:
                    # 「確認」と送った本人にだけPush通知
                    line_bot_api.push_message(PushMessageRequest(
                        to=target_user_id,
                        messages=[TextMessage(text=message_text)]
                    ))
                    print("個別返信を送信しました。")
                else:
                    # 自動実行（差分あり）なら全員に一斉送信
                    line_bot_api.broadcast(BroadcastRequest(
                        messages=[TextMessage(text=message_text)]
                    ))
                    print("一斉送信を完了しました。")
        except Exception as e:
            print(f"LINE送信エラー: {e}")
    else:
        print("通知の必要なし（空きなし or 差分なし）")
