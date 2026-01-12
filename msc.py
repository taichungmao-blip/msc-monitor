import time
import re
import os
import json
import hashlib
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# ================= 設定區 =================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 設定過濾條件 (數值)
# 使用者需求：500美金以下。網站為英鎊，500英鎊約等於600多美金，設定 450-500 都可以涵蓋。
TARGET_PRICE_MAX = 500  
TARGET_PRICE_MIN = 50 

# 記憶檔案名稱 (用來存已經通知過的行程)
HISTORY_FILE = "history.json"
# =========================================

def load_history():
    """讀取歷史紀錄"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history_data):
    """儲存歷史紀錄"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 儲存歷史紀錄失敗: {e}")

def get_unique_id(price, info):
    """產生唯一識別碼 (避免重複通知)"""
    raw_str = f"{price}-{info}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def send_discord_notify(message_text):
    if not DISCORD_WEBHOOK_URL:
        print("❌ 未設定 Webhook URL，跳過發送。")
        return

    try:
        data = {
            "content": message_text,
            "username": "MSC 價格監控機器人",
        }
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"❌ 發送錯誤: {e}")

def get_msc_cruises(port, history):
    print(f"🚀 啟動爬蟲: {port} (搜尋 < {TARGET_PRICE_MAX})...")

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = None
    new_items_count = 0

    try:
        driver = uc.Chrome(options=options)
        url = f"https://www.msccruises.co.uk/search?embkPort={port}"
        
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Price per person')]"))
        )
        time.sleep(5) 

        soup = BeautifulSoup(driver.page_source, "html.parser")
        keywords = soup.find_all(string=re.compile(r"Price per person", re.IGNORECASE))
        
        print(f"🔍 掃描到 {len(keywords)} 個行程...")

        for label_node in keywords:
            # 往上找 6 層以確保包含完整資訊
            container = label_node.parent
            for _ in range(6): 
                if container.parent:
                    container = container.parent
            
            full_text = container.get_text(separator=" ", strip=True)
            
            # 1. 抓取價格
            price_match = re.search(r"Price per person.*?£\s*(\d{1,5})", full_text, re.IGNORECASE)
            if not price_match:
                continue
            
            price = int(price_match.group(1))

            # 過濾價格：只通知範圍內的
            if price < TARGET_PRICE_MIN or price > TARGET_PRICE_MAX:
                continue

            # 2. 抓取天數
            duration_match = re.search(r"(\d+)\s*NIGHTS", full_text, re.IGNORECASE)
            duration_text = duration_match.group(0) if duration_match else "未知天數"

            # 3. 抓取航線
            route_info = "未知航線"
            if "FROM:" in full_text:
                route_match = re.search(r"(FROM:.*?)(?=VISITING|Price|View|$)", full_text, re.IGNORECASE)
                if route_match:
                    route_info = route_match.group(1).strip()
            
            info_text = f"【{duration_text}】 {route_info}"
            
            # --- 檢查重複邏輯 ---
            unique_id = get_unique_id(price, info_text)
            
            if unique_id in history:
                print(f"   😴 跳過已通知: £{price} | {duration_text}")
                continue
            
            # 這是新行程，發送通知
            print(f"   🔔 新發現！發送通知: £{price} | {info_text}")
            
            msg = (
                f"**🚢 MSC 價格監控通知**\n"
                f"💰 **價格**: £{price}\n"
                f"🗓️ **行程**: {info_text}\n"
                f"🔗 [點擊查看行程]({url})"
            )
            send_discord_notify(msg)
            
            # 加入歷史紀錄
            history.append(unique_id)
            new_items_count += 1
            time.sleep(1) # 避免 Discord Rate Limit

    except Exception as e:
        print(f"❌ 執行錯誤: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return new_items_count

if __name__ == "__main__":
    # 1. 讀取歷史紀錄
    current_history = load_history()
    print(f"📖 目前已記錄 {len(current_history)} 筆歷史資料")

    total_new = 0
    # 2. 執行爬蟲
    for port in ["TYO", "KEE"]:
        total_new += get_msc_cruises(port, current_history)

    # 3. 如果有新發現，將歷史紀錄寫回檔案 (讓 GitHub Action 稍後 Commit)
    if total_new > 0:
        save_history(current_history)
        print(f"💾 已更新歷史紀錄檔案 (新增 {total_new} 筆)")
    else:
        print("💤 本次沒有新行程，不更新檔案。")
