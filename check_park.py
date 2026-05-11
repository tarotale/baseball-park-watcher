import os
from datetime import datetime  # ← これを冒頭に追加
from playwright.sync_api import sync_playwright
# ...（中略）...

            current_slots = []
            cells = page.query_selector_all("#month-info td[id^='month_']")
            
            # 曜日の変換リスト
            weeks = ['月', '火', '水', '木', '金', '土', '日']

            for cell in cells:
                img = cell.query_selector("img[alt*='空き']")
                if img:
                    alt_text = img.get_attribute("alt")
                    date_raw = cell.get_attribute("id").replace("month_", "") # 例: 20260529
                    
                    # --- 曜日取得の追加 ---
                    date_obj = datetime.strptime(date_raw, '%Y%m%d')
                    w_num = date_obj.weekday() # 0(月)～6(日)の数値を取得
                    week_label = weeks[w_num]
                    # --------------------

                    formatted_date = f"{date_raw[4:6]}/{date_raw[6:]}({week_label})" # 05/29(金) 形式
                    
                    status_symbol = "○" if alt_text == "空き" else "▲"
                    current_slots.append(f"{formatted_date}{status_symbol}")
            
            return current_slots
