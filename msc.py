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
# 優先從環境變數讀取 Webhook (GitHub Actions 用)，如果沒有則使用預設值 (本地測試用)
# 在本地測試時，請將您的 URL 填入下方 default="..." 的引號中
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    default="您的_DISCORD_WEBHOOK_URL_填在這裡" 
)

# 設定過濾條件 (英鎊)
TARGET_PRICE_MAX = 300
TARGET_PRICE_MIN = 50 
# =========================================

def send_discord_notify(message_text):
    if "您的_DISCORD_WEBHOOK_URL" in DISCORD_WEBHOOK_URL:
        print("❌ 未設定 Webhook URL，跳過發送。")
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
    # GitHub Actions / Linux 環境必要參數
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        # 移除 version_main，讓 uc 自動抓取當前環境 Chrome 版本
        driver = uc.Chrome(options=options)
    except Exception as e:
        print(f"❌ 瀏覽器啟動失敗: {e}")
        return None

    url = f"https://www.msccruises.co.uk/search?embkPort={port}"
    candidates = []

    try:
        driver.get(url)
        # 等待價格載入
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Price per person')]"))
        )
        time.sleep(5) # 額外緩衝，確保動態內容渲染完畢

        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # 找到所有包含價格的區塊
        keywords = soup.find_all(string=re.compile(r"Price per person", re.IGNORECASE))
        print(f"🔍 掃描到 {len(keywords)} 個價格標籤...")

        for label_node in keywords:
            # 往上找父層容器 (通常是 Card 的一部分)
            container = label_node.parent
            for _ in range(4): #稍微擴大搜索範圍以確保包含標題和天數
                if container.parent:
                    container = container.parent
            
            full_text = container.get_text(separator=" ", strip=True)
            
            # --- 修正後的解析邏輯 ---
            
            # 1. 抓取價格
            price_match = re.search(r"Price per person.*?£\s*(\d{1,5})", full_text, re.IGNORECASE)
            if not price_match:
                continue
            
            price = int(price_match.group(1))

            if price < TARGET_PRICE_MIN or price > TARGET_PRICE_MAX:
                continue

            # 2. 精確抓取天數 (NIGHTS)
            # 尋找 "數字 + NIGHTS" 的模式
            duration_match = re.search(r"(\d+)\s*NIGHTS", full_text, re.IGNORECASE)
            duration_text = duration_match.group(0) if duration_match else "未知天數"

            # 3. 抓取航線資訊 (From ... To ...)
            # 嘗試抓取 FROM 到 VISITING 之間，或者簡單抓取包含 From 的那一段
            route_info = "未知航線"
            if "FROM:" in full_text:
                # 簡單的正則表達式來提取 FROM: ... 之後的一段文字
                route_match = re.search(r"(FROM:.*?)(?=VISITING|Price|View|$)", full_text, re.IGNORECASE)
                if route_match:
                    route_info = route_match.group(1).strip()
            
            # 組合顯示資訊
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
    # 可以同時監控基隆(KEE)與橫濱/東京(TYO)
    for port in ["TYO", "KEE"]:
        msg = get_msc_cruises(port)
        if msg:
            send_discord_notify(msg)
