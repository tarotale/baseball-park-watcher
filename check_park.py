import os
from playwright.sync_api import sync_playwright
from linebot import LineBotApi
from linebot.models import TextSendMessage

# GitHub Secretsから環境変数を読み込む
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")

def check_park_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 画面サイズを大きめにして要素が隠れないようにする
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            print("1. トップページへアクセス...")
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle")

            print("2. 条件をセットして検索実行...")
            page.evaluate("""() => {
                document.querySelector('#purpose-home').value = '1000_1000'; // 野球
                changePurpose(document.form1, false);
            }""")
            page.wait_for_timeout(1500)

            page.evaluate("""() => {
                document.querySelector('#bname-home').value = '1010'; // 芝公園
                doSearchHome(document.form1, gRsvWOpeInstSrchVacantAction);
            }""")
            
            print("3. 検索結果ページの読み込みを待機...")
            page.wait_for_load_state("networkidle")
            # カレンダーの枠（月表示のボタン）が出るまで待機
            page.wait_for_selector(".collapse-btn-right", timeout=10000)

            print("4. 月表示カレンダーを展開...")
            # data-target="#monthly" を持つボタンをクリック
            page.click("div[data-target='#monthly']")
            
            print("   - カレンダーデータ（Ajax）の読み込みを待機...")
            # カレンダー内の「空きアイコン」が読み込まれるまで待機
            # セレクタをtd内の画像に絞って確実に待ちます
            page.wait_for_selector("#month-info img.calendar-status", timeout=15000)

            print(f"5. 解析中... 月: {page.inner_text('#month-head')}")

            available_days = []
            # 月表示カレンダー(#month-info)の中にある日付セルをスキャン
            cells = page.query_selector_all("#month-info td[id^='month_']")
            print(f"   - 解析対象セル数: {len(cells)}")

            for cell in cells:
                # セル内に「空き」または「一部空き」の画像があるか
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    # 20260529 -> 05/29
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}"
                    available_days.append(formatted_date)
                    print(f"   - 【発見】: {formatted_date} ({alt_text})")

            return available_days

        except Exception as e:
            print(f"エラー発生: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("設定エラー: LINEのトークンまたはユーザーIDがSecretsに登録されていません。")
    else:
        found_days = check_park_availability()
        if found_days:
            # 重複を除去してソート
            unique_days = sorted(list(set(found_days)))
            date_list = "、".join(unique_days)
            
            message = f"【芝公園 野球場】空きが出ました！\n\n対象日：{date_list}\n\n予約はこちら：\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
            
            LineBotApi(LINE_CHANNEL_ACCESS_TOKEN).push_message(USER_ID, TextSendMessage(text=message))
            print(f"LINE送信完了: {date_list}")
        else:
            print("最終結果: 現在、空きはありません。")
