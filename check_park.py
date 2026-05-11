import os
import time
from playwright.sync_api import sync_playwright
from linebot import LineBotApi
from linebot.models import TextSendMessage

# GitHub Secretsから環境変数を読み込む
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
USER_ID = os.environ.get("USER_ID")

def check_park_availability():
    with sync_playwright() as p:
        # ブラウザを起動（ヘッドレスモード）
        browser = p.chromium.launch(headless=True)
        # サイトに弾かれないよう一般的なブラウザのふりをする
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. 予約システムトップページへ
            page.goto("https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp", wait_until="networkidle")

            # 2. 目的「野球」を選択
            page.select_option("#purpose-home", value="1000_1000")
            # 選択後の連動プルダウンの更新を待つ
            page.wait_for_timeout(1000)

            # 3. 施設「芝公園」を選択
            page.select_option("#bname-home", value="1010")

            # 4. 検索ボタンをクリック
            page.click("#btn-go")
            
            # 5. カレンダーの読み込み待ち（ここが重要）
            # 検索直後のページ遷移と、その後のアイコン描画の両方を待ちます
            page.wait_for_load_state("networkidle")
            
            # アイコン（calendar-statusクラス）が最低1つ表示されるまで最大15秒待機
            try:
                page.wait_for_selector(".calendar-status", timeout=15000)
            except:
                print("タイムアウト：空きアイコンが見つかりませんでした。")

            # 6. カレンダー内の空き状況を解析
            available_days = []
            
            # 日付セル（idがmonth_から始まるもの）を全取得
            cells = page.query_selector_all("td[id^='month_']")
            
            for cell in cells:
                # 画像のalt属性に「空き」という文字が含まれているかチェック
                # 「一部空き」「空き」の両方に反応します
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    # id (例: month_20260529) から日付部分だけ抜き出し
                    date_raw = cell.get_attribute("id").replace("month_", "")
                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}" # 05/29 形式
                    available_days.append(formatted_date)

            return available_days

        except Exception as e:
            print(f"スクレイピング中にエラーが発生しました: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    if not LINE_CHANNEL_ACCESS_TOKEN or not USER_ID:
        print("エラー: LINEのトークンまたはユーザーIDが設定されていません。")
    else:
        found_days = check_park_availability()
        
        if found_days:
            # 空きがあった場合のみ通知
            date_list = "、".join(found_days)
            message = f"【芝公園 野球場】空き発見！\n\n対象日：{date_list}\n\n今すぐ予約：\nhttps://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"
            
            line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
            line_bot_api.push_message(USER_ID, TextSendMessage(text=message))
            print(f"通知送信完了: {date_list}")
        else:
            # GitHub Actionsのログで確認用
            print("チェック完了：空きはありませんでした。")
