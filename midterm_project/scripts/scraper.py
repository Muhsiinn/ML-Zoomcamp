import os
import time
import re
import argparse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --------------------
# Command-line setup
# --------------------
parser = argparse.ArgumentParser(description="Scrape Willhaben apartment listings")
parser.add_argument("city", type=str, help="City (e.g. wien, linz, graz)")
parser.add_argument("pages", type=int, help="Number of pages to scrape")
args = parser.parse_args()

city_key = args.city.lower()
pages_to_scrape = args.pages

# Supported city mapping
city_map = {
    "wien": "wien",
    "linz": "oberoesterreich/linz",
    "graz": "steiermark/graz"
}
if city_key not in city_map:
    raise ValueError(f"Unsupported city '{city_key}'. Supported: {list(city_map.keys())}")

base_url = f"https://www.willhaben.at/iad/immobilien/mietwohnungen/{city_map[city_key]}/"

# --------------------
# Chrome WebDriver setup
# --------------------
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
prefs = {"profile.managed_default_content_settings.images": 2}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --------------------
# Cookie handling
# --------------------
def accept_cookies():
    try:
        button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Akzeptieren') or contains(text(), 'Accept')]"))
        )
        button.click()
        print("Cookie banner accepted.")
    except:
        pass

# --------------------
# Scraping logic
# --------------------
all_listings = []

for page in range(1, pages_to_scrape + 1):
    url = base_url if page == 1 else base_url + f"?page={page}"
    driver.get(url)
    time.sleep(3)

    if page == 1:
        accept_cookies()

    # Scroll down to load dynamic content
    for i in range(5):
        driver.execute_script(f"window.scrollTo(0, {i * 1000});")
        time.sleep(1)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href, '/iad/immobilien/d/mietwohnungen/')]"))
        )
    except:
        print(f"Page {page} took too long to load.")
        continue

    listings = driver.find_elements(By.XPATH, "//a[contains(@href, '/iad/immobilien/d/mietwohnungen/')]")
    for l in listings:
        text = l.text.strip()
        href = l.get_attribute("href")
        if not text or "Zimmer" not in text or "€" not in text:
            continue

        title = text.split('\n')[0]
        postcode = re.search(r'\b\d{4}\b', text)
        size = re.search(r'\d+\s*m²', text)
        rooms = re.search(r'([\d.,]+)\s*Zimmer', text)
        price = re.search(r'€\s*[\d.,]+', text)

        all_listings.append({
            "Title": title,
            "Price": price.group(0) if price else None,
            "Size": size.group(0) if size else None,
            "Rooms": rooms.group(1) if rooms else None,
            "Postcode": postcode.group(0) if postcode else None,
            "URL": href
        })

    print(f"Scraped page {page}: {len(listings)} listings")

driver.quit()

# --------------------
# Data cleaning
# --------------------
df = pd.DataFrame(all_listings)
df.dropna(subset=["Price", "Size", "Rooms", "Postcode"], inplace=True)

df["Price"] = df["Price"].str.replace(r"\D+", "", regex=True).astype(int)
df["Size"] = df["Size"].str.replace(r"\D+", "", regex=True).astype(int)
df["Rooms"] = df["Rooms"].str.replace(",", ".").astype(float)

# Remove outliers
q_low, q_hi = 0.02, 0.98
df = df[
    (df["Size"].between(df["Size"].quantile(q_low), df["Size"].quantile(q_hi))) &
    (df["Price"].between(df["Price"].quantile(q_low), df["Price"].quantile(q_hi)))
]

# --------------------
# Save output
# --------------------
os.makedirs("data", exist_ok=True)
output_path = f"./data/willhaben_{city_key}_rent.csv"
df.to_csv(output_path, index=False)
print(f"Saved {len(df)} cleaned listings to {output_path}")
