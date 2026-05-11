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
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        try:
            print("1. サイトにアクセス中...")
            # タイムアウトを長めに設定
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle", timeout=60000)

            print("2. 目的（野球）を選択...")
            # IDではなく、表示されているテキストで選択（より確実）
            page.wait_for_selector("select#purpose-home", timeout=20000)
            page.select_option("select#purpose-home", label="野球")
            
            # 選択後の連動待ち
            page.wait_for_timeout(2000)

            print("3. 公園（芝公園）を選択...")
            page.wait_for_selector("select#bname-home", timeout=20000)
            page.select_option("select#bname-home", label="芝公園")
            page.wait_for_timeout(2000)

            print("4. 検索実行...")
            # 「検索する」ボタンのテキストを狙い撃ち
            search_button = page.get_by_role("button", name="検索する")
            search_button.click()
            
            print("5. 画面遷移を待機中...")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000) # 念入りに待機

            print("6. 月表示カレンダーを展開...")
            # クラス名だけでなく、属性で正確に特定
            expand_btn = page.wait_for_selector("div[data-target='#monthly']", timeout=20000)
            expand_btn.click()
            
            print("7. カレンダーの中身を待機...")
            # カレンダーのテーブルが表示されるまで待つ
            page.wait_for_selector("#month-info", timeout=20000)
            # アイコンが出るまで少し待機
            page.wait_for_timeout(3000)

            current_slots = []
            weeks = ['月', '火', '水', '木', '金', '土', '日']
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            print(f"8. 解析開始 (セル数: {len(cells)})...")
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
            print(f"エラー詳細: {e}")
            # 失敗した時の画面の状態を特定するためのヒント
            print(f"現在のURL: {page.url}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("LINE設定エラー")
        exit(1)

    current_slots = check_park_availability()
    if current_slots is None:
        exit(1)

    is_force = EVENT_NAME in ["workflow_dispatch", "repository_dispatch"]

    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    new_slots = [slot for slot in current_slots if slot not in last_slots]

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    target_slots = current_slots if is_force else new_slots

    if target_slots:
        title = "【現在の空き状況】" if is_force else "【新着空き！】"
        info_list = "、".join(sorted(list(set(target_slots))))
        message_text = f"{title}\n\n対象枠：\n{info_list}\n\n予約：\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        
        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message(PushMessageRequest(
                to=USER_ID, messages=[TextMessage(text=message_text)]
            ))
        print(f"通知完了: {info_list}")
    else:
        print("通知対象なし")
