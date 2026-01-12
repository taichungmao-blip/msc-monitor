import time
import re
import os
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# ================= 設定區 =================
# 專門讀取 GitHub Actions 環境變數
# 如果沒有設定 Secrets，這裡會抓不到，導致發送失敗
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 設定過濾條件 (英鎊)
TARGET_PRICE_MAX = 300
TARGET_PRICE_MIN = 50 
# =========================================

def send_discord_notify(message_text):
    if not DISCORD_WEBHOOK_URL:
        print("❌ 錯誤：找不到 DISCORD_WEBHOOK_URL 環境變數，請檢查 GitHub Secrets 設定。")
        return

    try:
        data = {
            "content": message_text,
            "username": "MSC 價格監控機器人",
        }
        result = requests.post(DISCORD_WEBHOOK_URL, json=data)
        
        if 200 <= result.status_code < 300:
            print("✅ Discord 通知已發送！")
        else:
            print(f"❌ 發送失敗: {result.status_code}, {result.text}")
    except Exception as e:
        print(f"❌ 發送錯誤: {e}")

def get_msc_cruises(port):
    print(f"🚀 啟動爬蟲: {port} (門檻 > £{TARGET_PRICE_MIN})...")

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        driver = uc.Chrome(options=options)
    except Exception as e:
        print(f"❌ 瀏覽器啟動失敗: {e}")
        return None

    url = f"https://www.msccruises.co.uk/search?embkPort={port}"
    candidates = []

    try:
        driver.get(url)
        # 等待關鍵元素出現
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Price per person')]"))
        )
        time.sleep(5) 

        soup = BeautifulSoup(driver.page_source, "html.parser")
        keywords = soup.find_all(string=re.compile(r"Price per person", re.IGNORECASE))
        print(f"🔍 掃描到 {len(keywords)} 個價格標籤...")

        for label_node in keywords:
            # 關鍵修改：往上找 6 層，確保包含左側的「天數」與「行程」資訊
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

            if price < TARGET_PRICE_MIN or price > TARGET_PRICE_MAX:
                continue

            # 2. 抓取天數 (NIGHTS)
            duration_match = re.search(r"(\d+)\s*NIGHTS", full_text, re.IGNORECASE)
            duration_text = duration_match.group(0) if duration_match else "未知天數"

            # 3. 抓取航線 (簡單抓取 FROM 到 VISITING 之間)
            route_info = "未知航線"
            if "FROM:" in full_text:
                route_match = re.search(r"(FROM:.*?)(?=VISITING|Price|View|$)", full_text, re.IGNORECASE)
                if route_match:
                    route_info = route_match.group(1).strip()
            
            # 組合資訊
            info_text = f"【{duration_text}】 {route_info}"
            print(f"   ✅ 發現: £{price} | {info_text}")
            candidates.append({"price": price, "info": info_text, "url": url})

    except Exception as e:
        print(f"❌ 執行錯誤: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

    if candidates:
        # 取最低價
        candidates.sort(key=lambda x: x["price"])
        best = candidates[0]
        
        msg = (
            f"**🚢 MSC 價格監控通知**\n"
            f"💰 **最低價**: £{best['price']}\n"
            f"🗓️ **行程**: {best['info']}\n"
            f"🔗 [點擊查看行程]({best['url']})"
        )
        return msg
    return None

if __name__ == "__main__":
    for port in ["TYO", "KEE"]:
        msg = get_msc_cruises(port)
        if msg:
            send_discord_notify(msg)
