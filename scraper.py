import os
import time
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re

# ==============================================================================
# --- CONFIGURATION: PLEASE UPDATE THESE VALUES ---
# ==============================================================================
# The user of this script will need to inspect the intradayscreener.com website
# to find the correct selectors and URLs. The values below are placeholders.
#
# How to find them:
# 1. Open Chrome, log in to the website.
# 2. Navigate to the page you want to scrape.
# 3. Right-click on an element (e.g., the username field) and click "Inspect".
# 4. In the developer tools, find the element's unique identifier, like 'id',
#    'name', 'class', or an XPath.
# 5. Update the corresponding value in the `CONFIG` dictionary below.
# ==============================================================================
CONFIG = {
    "base_url": "https://intradayscreener.com/",
    "login_page": "login",
    "selectors": {
        "login": {
            "email_input": (By.NAME, "email"), # E.g., (By.ID, "user-email")
            "password_input": (By.NAME, "password"), # E.g., (By.NAME, "password")
            "login_button": (By.XPATH, "//button[contains(text(), 'Login')]"),
            "login_success_indicator": (By.XPATH, "//a[contains(@href, '/dashboard')]")
        },
        "scan_page": {
            # This is the element to wait for to ensure the page's data table has loaded
            "table_container": (By.CLASS_NAME, "data-table-container"),
            # This is the main table element from which to scrape data
            "data_table": (By.CSS_SELECTOR, "table.table-striped"),
        }
    },
    "scan_urls": {
        "fno": {
            "Outperforming Short & Medium": "scan/outperforming-short-medium-term-fno",
            "Underperforming Short & Medium": "scan/underperforming-short-medium-term-fno",
            "Outperforming 6Month": "scan/outperforming-last-6-months-fno",
            "Underperforming 6Month": "scan/underperforming-last-6-months-fno",
        },
        "cash": {
            "Outperforming Short & Medium": "scan/outperforming-short-medium-term-cash",
            "Underperforming Short & Medium": "scan/underperforming-short-medium-term-cash",
            "Outperforming 6Month": "scan/outperforming-last-6-months-cash",
            "Underperforming 6Month": "scan/underperforming-last-6-months-cash",
        }
    }
}


class IntradayScreenerScraper:
    """
    A class to scrape relative outperformance data from intradayscreener.com.
    """
    def __init__(self):
        load_dotenv()
        self.username = os.getenv("INTRADAY_USERNAME")
        self.password = os.getenv("INTRADAY_PASSWORD")
        if not self.username or not self.password:
            raise ValueError("Username or password not found in .env file.")

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1200")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        print("WebDriver initialized.")

    def login(self):
        login_url = CONFIG["base_url"] + CONFIG["login_page"]
        self.driver.get(login_url)
        print("Navigated to login page.")

        # Use selectors from the CONFIG dictionary
        s = CONFIG["selectors"]["login"]
        self.wait.until(EC.presence_of_element_located(s["email_input"]))

        self.driver.find_element(*s["email_input"]).send_keys(self.username)
        self.driver.find_element(*s["password_input"]).send_keys(self.password)
        self.driver.find_element(*s["login_button"]).click()

        self.wait.until(EC.presence_of_element_located(s["login_success_indicator"]))
        print("Login successful.")

    def _navigate_to_scan(self, scan_path):
        scan_url = CONFIG["base_url"] + scan_path
        self.driver.get(scan_url)
        self.wait.until(EC.presence_of_element_located(CONFIG["selectors"]["scan_page"]["table_container"]))
        print(f"Navigated to {scan_url}")

    def _parse_ltp_cell(self, cell_text):
        cell_text = cell_text.strip()
        match = re.search(r'([\d,]+\.\d+)\s*\((\-?[\d\.]+)%\)', cell_text)
        if match:
            ltp = float(match.group(1).replace(',', ''))
            ltp_percent_change = float(match.group(2))
            return ltp, ltp_percent_change
        try:
            return float(cell_text.replace(',', '')), None
        except ValueError:
            return None, None

    def _parse_performance_cell(self, cell_text):
        try:
            return float(cell_text.strip().replace('%', ''))
        except (ValueError, AttributeError):
            return None

    def scrape_page_data(self, scan_type, stock_segment):
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        # Use selector from the CONFIG dictionary
        table_selector = CONFIG["selectors"]["scan_page"]["data_table"][1] # Get CSS selector string
        table = soup.select_one(table_selector)

        if not table:
            print(f"No data table found for {scan_type} - {stock_segment}.")
            return pd.DataFrame()

        rows = []
        for row in table.find('tbody').find_all('tr'):
            cols = row.find_all('td')
            if len(cols) < 5:
                continue

            symbol = cols[0].text.strip()
            ltp, ltp_percent_change = self._parse_ltp_cell(cols[1].text)
            seven_day_outperformance = self._parse_performance_cell(cols[2].text)
            six_month_outperformance = self._parse_performance_cell(cols[3].text)
            relative_outperformance = cols[4].text.strip()

            rows.append({
                'symbol': symbol,
                'ltp': ltp,
                'ltp_percent_change': ltp_percent_change,
                'seven_day_outperformance': seven_day_outperformance,
                'six_month_outperformance': six_month_outperformance,
                'relative_outperformance_wrt_index': relative_outperformance,
                'scan_type': scan_type,
                'stock_segment': stock_segment
            })

        return pd.DataFrame(rows)

    def run_scraper(self):
        self.login()
        all_data = []

        for segment, scans in CONFIG["scan_urls"].items():
            for scan_name, scan_path in scans.items():
                print(f"--- Scraping {scan_name} for {segment.upper()} ---")
                try:
                    self._navigate_to_scan(scan_path)
                    page_data = self.scrape_page_data(scan_name, segment.upper())
                    if not page_data.empty:
                        all_data.append(page_data)
                        print(f"Scraped {len(page_data)} rows.")
                except Exception as e:
                    print(f"Could not scrape {scan_name} for {segment.upper()}. Error: {e}")
                time.sleep(2)

        if not all_data:
            print("No data was scraped.")
            return pd.DataFrame()

        return pd.concat(all_data, ignore_index=True)

    def close(self):
        if self.driver:
            self.driver.quit()
            print("WebDriver closed.")
