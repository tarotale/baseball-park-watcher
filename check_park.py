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
    """芝公園の空き状況をスクレイピングする関数"""
    with sync_playwright() as p:
        # 日本語環境とブラウザ偽装
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

            body_text = page.inner_text("body")
            if "現在、大変混み合っております" in body_text:
                print("混雑画面のため中断します。")
                return None

            print("2. 目的（野球）を選択...")
            page.wait_for_selector("#purpose-home", state="attached", timeout=20000)
            page.select_option("#purpose-home", label="野球")
            page.wait_for_timeout(2000)

            print("3. 公園（芝公園）を選択...")
            page.wait_for_selector("#bname-home", state="attached", timeout=20000)
            page.select_option("#bname-home", label="芝公園")
            page.wait_for_timeout(2000)

            print("4. 検索実行...")
            page.click("#btn-go", force=True)
            
            print("5. 画面遷移を待機中...")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)

            print("6. 月表示カレンダーを展開...")
            expand_btn = page.wait_for_selector("div[data-target='#monthly']", state="visible", timeout=20000)
            expand_btn.click()
            
            print("7. カレンダーの中身を待機...")
            page.wait_for_selector("#month-info", timeout=20000)
            page.wait_for_timeout(3000)

            current_slots = []
            weeks = ['月', '火', '水', '木', '金', '土', '日']
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            print(f"8. 解析開始 (取得セル数: {len(cells)})...")
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
            print(f"エラー発生: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not DEFAULT_USER_ID:
        print("LINE設定(Secrets)が不足しています。")
        exit(1)

    # --- 宛先と実行モードの判定 ---
    target_user_id = DEFAULT_USER_ID
    is_requested = (EVENT_NAME == "repository_dispatch") # LINEからの「確認」メッセージによる実行か
    
    if is_requested and EVENT_PAYLOAD:
        try:
            payload_data = json.loads(EVENT_PAYLOAD)
            if "reply_user_id" in payload_data:
                target_user_id = payload_data["reply_user_id"]
        except Exception as e:
            print(f"ペイロード解析失敗: {e}")

    # --- スクレイピング実行 ---
    current_slots = check_park_availability()
    if current_slots is None:
        exit(1)

    # --- 履歴の管理 ---
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    # 新着のみ抽出
    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 現在の状態を保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    # --- 通知対象の決定 ---
    # 1. LINEからのリクエストなら、その人に「全件」教える
    # 2. 自動実行なら、新着がある時だけ「新着分」を全員に教える
    target_slots = current_slots if is_requested else new_slots

    if target_slots:
        mode_title = "【現在の空き状況】" if is_requested else "【新着空き！】"
        info_list = "、".join(sorted(list(set(target_slots))))
        message_text = (
            f"{mode_title}\n\n"
            f"対象枠：\n{info_list}\n\n"
            f"※○=空き、▲=一部空き\n"
            f"https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        )
        
        try:
            configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                
                if is_requested:
                    # 個別送信（リクエストした本人へ）
                    line_bot_api.push_message(PushMessageRequest(
                        to=target_user_id,
                        messages=[TextMessage(text=message_text)]
                    ))
                    print(f"個別送信完了: {target_user_id}")
                else:
                    # 一斉送信（友達登録者全員へ）
                    line_bot_api.broadcast(BroadcastRequest(
                        messages=[TextMessage(text=message_text)]
                    ))
                    print("一斉送信完了")
                    
        except Exception as e:
            print(f"LINE送信エラー: {e}")
    else:
        print("通知が必要な情報はありませんでした。")
