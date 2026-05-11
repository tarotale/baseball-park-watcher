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
        # ブラウザの起動（日本語環境をシミュレート）
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
            # commit段階で次に進み、自前で待機を入れる
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="commit", timeout=60000)
            page.wait_for_timeout(5000)

            # デバッグ用：画面の文字情報を出力
            body_text = page.inner_text("body")
            print("--- 画面の冒頭テキスト ---")
            print(body_text.strip()[:150])
            print("-------------------------")

            if "現在、大変混み合っております" in body_text:
                print("混雑画面が表示されています。中断します。")
                return None

            print("2. 目的（野球）を選択...")
            # IDがDOMに存在するまで待機
            page.wait_for_selector("#purpose-home", state="attached", timeout=20000)
            page.select_option("#purpose-home", label="野球")
            page.wait_for_timeout(2000)

            print("3. 公園（芝公園）を選択...")
            page.wait_for_selector("#bname-home", state="attached", timeout=20000)
            page.select_option("#bname-home", label="芝公園")
            page.wait_for_timeout(2000)

            print("4. 検索実行...")
            # 強制的にクリックを実行
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
                    date_raw = cell.get_attribute("id").replace("month_", "") # 例: 20260529
                    
                    try:
                        # 日付から曜日を取得
                        date_obj = datetime.strptime(date_raw, '%Y%m%d')
                        week_label = weeks[date_obj.weekday()]
                        formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}({week_label})"
                        
                        status_symbol = "○" if alt_text == "空き" else "▲"
                        current_slots.append(f"{formatted_date}{status_symbol}")
                    except Exception as e:
                        print(f"日付解析スキップ: {date_raw} ({e})")
                        continue
            
            return current_slots

        except Exception as e:
            print(f"エラー発生: {e}")
            # 失敗時のURLを確認
            print(f"最終URL: {page.url}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("エラー: LINE_ACCESS_TOKEN または USER_ID が設定されていません。")
        exit(1)

    # スクレイピング実行
    current_slots = check_park_availability()
    if current_slots is None:
        print("スクレイピング結果が取得できなかったため終了します。")
        exit(1)

    # モード判定 (手動実行 or LINEからの確認メッセージ)
    is_force = EVENT_NAME in ["workflow_dispatch", "repository_dispatch"]

    # 前回の状態を読み込み
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            last_slots = f.read().splitlines()
    else:
        last_slots = []

    # 差分（新しく空いた枠）を抽出
    new_slots = [slot for slot in current_slots if slot not in last_slots]

    # 現在の状態を保存
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(current_slots))

    # 通知対象の決定
    target_slots = current_slots if is_force else new_slots

    if target_slots:
        mode_title = "【現在の空き状況】" if is_force else "【新着空き！】"
        info_list = "、".join(sorted(list(set(target_slots))))
        message_text = (
            f"{mode_title}\n\n"
            f"対象枠：\n{info_list}\n\n"
            f"※○=空き、▲=一部空き\n"
            f"https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        )
        
        # LINE送信処理 (v3)
        try:
            configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(PushMessageRequest(
                    to=USER_ID,
                    messages=[TextMessage(text=message_text)]
                ))
            print(f"LINE送信完了: {info_list}")
        except Exception as e:
            print(f"LINE送信エラー: {e}")
    else:
        print("通知が必要な空き情報はありませんでした。")
