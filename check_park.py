import os
from playwright.sync_api import sync_playwright
from linebot import LineBotApi
from linebot.models import TextSendMessage

# GitHub Secretsから読み込む
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_ACCESS_TOKEN"]
USER_ID = os.environ["USER_ID"]

def check_park_availability():
    with sync_playwright() as p:
        # ブラウザ起動（ヘッドレスモード）
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 指定のページへ移動
        page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp")
        
        # 野球(1000_1000)を選択
        page.select_option("#purpose-home", value="1000_1000")
        page.wait_for_timeout(1000)
        
        # 芝公園(1010)を選択
        page.select_option("#bname-home", value="1010")
        
        # 検索ボタンをクリック
        page.click("#btn-go")
        page.wait_for_load_state("networkidle")

        # カレンダーが展開されるのを待つ
        # 展開アイコンがあればクリック
        if page.is_visible(".span-icon-down"):
            page.click(".span-icon-down")
            page.wait_for_timeout(2000)

        available_days = []
        # 「一部空き」の画像がある日付セル(td)をすべて探す
        cells = page.query_selector_all("td[id^='month_']")
        for cell in cells:
            if cell.query_selector("img[alt='一部空き']"):
                date_str = cell.get_attribute("id").replace("month_", "")
                available_days.append(f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}")

        browser.close()
        return available_days

if __name__ == "__main__":
    try:
        days = check_park_availability()
        if days:
            message = "【芝公園 野球場】空きが出ました！\n\n" + "\n".join(days)
            LineBotApi(LINE_CHANNEL_ACCESS_TOKEN).push_message(USER_ID, TextSendMessage(text=message))
    except Exception as e:
        print(f"Error: {e}")
