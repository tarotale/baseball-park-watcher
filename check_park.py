import os
from playwright.sync_api import sync_playwright
from linebot import LineBotApi
from linebot.models import TextSendMessage

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")

def check_park_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 1000})
        page = context.new_page()

        try:
            print("1. サイトにアクセス中...")
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle")

            print("2. 野球を選択中...")
            page.select_option("#purpose-home", value="1000_1000")
            page.wait_for_timeout(1000)

            print("3. 芝公園を選択中...")
            page.select_option("#bname-home", value="1010")
            page.wait_for_timeout(500)

            print("4. 検索ボタンをクリック...")
            # ページ遷移を確実に待つためにclickとwait_for_navigationを併用
            with page.expect_navigation(wait_until="networkidle"):
                page.click("#btn-go")

            print("5. カレンダー展開チェック...")
            # カレンダーが隠れている場合（スマホ版表示など）を考慮し、展開ボタンがあれば押す
            toggle_btn = page.query_selector(".span-icon-down")
            if toggle_btn:
                toggle_btn.click()
                print("   - 展開ボタンをクリックしました")
                page.wait_for_timeout(2000)

            # アイコンが出るまでじっくり待機
            print("6. 空きアイコンの読み込みを待機中...")
            try:
                page.wait_for_selector(".calendar-status", timeout=15000)
            except:
                print("   - 警告: アイコンが時間内に見つかりませんでした")

            # デバッグ用：今の画面の状態をログに出す（Actionのログで文字として見れます）
            print(f"現在表示されている月: {page.inner_text('#month-head') if page.query_selector('#month-head') else '不明'}")

            available_days = []
            cells = page.query_selector_all("td[id^='month_']")
            print(f"解析対象のセル数: {len(cells)}")

            for cell in cells:
                # すべての画像タグをチェックして、altに「空き」が含まれるか確認
                imgs = cell.query_selector_all("img")
                for img in imgs:
                    alt_text = img.get_attribute("alt") or ""
                    if "空き" in alt_text:
                        date_raw = cell.get_attribute("id").replace("month_", "")
                        formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}"
                        available_days.append(formatted_date)
                        print(f"   - 発見: {formatted_date} ({alt_text})")

            return available_days

        except Exception as e:
            print(f"エラー発生: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    found_days = check_park_availability()
    if found_days:
        date_list = "、".join(sorted(list(set(found_days))))
        message = f"【芝公園 野球場】空き発見！\n対象日：{date_list}\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        LineBotApi(LINE_CHANNEL_ACCESS_TOKEN).push_message(USER_ID, TextSendMessage(text=message))
    else:
        # デバッグ用に「空きなし」時もログを出す
        print("最終結果: 空きは見つかりませんでした。")
