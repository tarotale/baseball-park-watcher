import os
from playwright.sync_api import sync_playwright
# 新しいSDKのインポート形式
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")

def check_park_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("1. トップページへアクセス...")
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle")

            print("2. 目的（野球）を選択...")
            page.select_option("#purpose-home", value="1000_1000")
            page.wait_for_timeout(1000)

            print("3. 公園（芝公園）を選択...")
            page.select_option("#bname-home", value="1010")
            page.wait_for_timeout(1000)

            print("4. 検索ボタンをクリック...")
            page.click("#btn-go")
            
            print("5. 画面遷移を待機中...")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            print("6. カレンダー展開ボタンをクリック...")
            expand_btn = page.wait_for_selector("div[data-target='#monthly']", timeout=15000)
            expand_btn.click()

            print("7. 月表示カレンダーの中身を待機...")
            page.wait_for_selector("#month-info img.calendar-status", timeout=10000)

            print(f"8. 解析実行... 月: {page.inner_text('#month-head')}")

            available_info = [] # 日付と状態をセットで保存
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt") # 「空き」or「一部空き」
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}"
                    
                    # 状態によって記号を変える（分かりやすさのため）
                    status_symbol = "○" if alt_text == "空き" else "▲"
                    available_info.append(f"{formatted_date}({status_symbol})")
                    print(f"   - 発見: {formatted_date} ({alt_text})")

            return available_info

        except Exception as e:
            print(f"エラー詳細: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    found_info = check_park_availability()
    if found_info:
        # 重複を排除してソート
        info_list = "、".join(sorted(list(set(found_info))))
        message_text = (
            f"【芝公園 野球場】空き発見！\n\n"
            f"対象日：\n{info_list}\n\n"
            f"※○=空き、▲=一部空き\n"
            f"https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        )
        
        # LINE SDK v3の送信処理
        configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=USER_ID,
                messages=[TextMessage(text=message_text)]
            )
            line_bot_api.push_message(push_message_request)
            
        print(f"LINE送信完了: {info_list}")
    else:
        print("最終結果: 空きなし")
