import os
from playwright.sync_api import sync_playwright
from linebot import LineBotApi
from linebot.models import TextSendMessage

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
            page.wait_for_timeout(1000) # リスト更新待ち

            print("3. 公園（芝公園）を選択...")
            page.select_option("#bname-home", value="1010")
            page.wait_for_timeout(1000)

            print("4. 検索ボタンを「人間らしく」クリック...")
            # ボタンが見えるまで待ってからクリック
            page.wait_for_selector("#btn-go")
            page.click("#btn-go")
            
            print("5. 画面遷移を待機中...")
            # ページ全体の読み込みが落ち着くまで待つ
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000) # 念のための追加待機

            # ここで「カレンダー展開ボタン」が出るかチェック
            print("6. カレンダー展開ボタンを探しています...")
            try:
                # タイムアウトを15秒に延長
                expand_btn = page.wait_for_selector("div[data-target='#monthly']", timeout=15000)
                print("   - ボタン発見。クリックします。")
                expand_btn.click()
            except Exception as e:
                print(f"   - ボタンが見つかりません。現在のURL: {page.url}")
                print(f"   - ページタイトル: {page.title()}")
                # 失敗した時のHTML構造を少しだけログに出す（解析用）
                content = page.content()
                print(f"   - ページソース(抜粋): {content[:500]}")
                raise e

            print("7. 月表示カレンダーの中身を待機...")
            # 空きアイコン(img)がテーブル内に出るまで待つ
            page.wait_for_selector("#month-info img.calendar-status", timeout=10000)

            print(f"8. 解析実行... 月: {page.inner_text('#month-head')}")

            available_days = []
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}"
                    available_days.append(formatted_date)
                    print(f"   - 発見: {formatted_date} ({alt_text})")

            return available_days

        except Exception as e:
            print(f"エラー詳細: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    found_days = check_park_availability()
    if found_days:
        date_list = "、".join(sorted(list(set(found_days))))
        message = f"【芝公園 野球場】空き発見！\n対象日：{date_list}\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
        LineBotApi(LINE_CHANNEL_ACCESS_TOKEN).push_message(USER_ID, TextSendMessage(text=message))
        print(f"LINE送信: {date_list}")
    else:
        print("最終結果: 空きなし（またはエラー）")
