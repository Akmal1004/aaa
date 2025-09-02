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
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==============================================================================
# --- CONFIGURATION ---
# ==============================================================================
CONFIG = {
    "base_url": "https://intradayscreener.com/",
    "login_page": "login",
    "selectors": {
        "login": {
            "email_input": (By.XPATH, '//*[@id="inputEmail"]'),
            "password_input": (By.XPATH, '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/div[2]/div/input'),
            "login_button": (By.XPATH, '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/button')
        },
        "login_success_indicator": (By.XPATH, '//*[@id="navbarSupportedContent"]/li[5]/ul/li[3]/a'),
        "popup_close_button": (By.XPATH, '//*[@id="whatsnewModal"]/div/div/div[1]/button/span'),
        "relative_outperformance_link": (By.XPATH, '//*[@id="navbarSupportedContent"]/li[5]/ul/li[3]/a'),
        "fno_tab": (By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[1]'),
        "cash_tab": (By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[2]'),
        "export_csv_button": (By.XPATH, '//*[@id="pills-tab"]/button'),
        "scan_tabs": {
            "Outperforming Short & Medium": (By.ID, "pills-home-tab"),
            "Underperforming Short & Medium": (By.ID, "pills-profile-tab"),
            "Outperforming 6Month": (By.ID, "pills-contact-tab"),
            "Underperforming 6Month": (By.ID, "pills-message-tab"),
        }
    }
}


class IntradayScreenerScraper:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv("INTRADAY_USERNAME")
        self.password = os.getenv("INTRADAY_PASSWORD")
        if not self.username or not self.password:
            raise ValueError("Username or password not found in .env file.")

        self.download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1200")
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
        }
        chrome_options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)
        logging.info("WebDriver initialized.")

    def _clear_downloads(self):
        for f in os.listdir(self.download_dir):
            os.remove(os.path.join(self.download_dir, f))

    def login(self):
        logging.info("Attempting to log in...")
        self.driver.get(CONFIG["base_url"] + CONFIG["login_page"])

        s = CONFIG["selectors"]["login"]
        email_box = self.wait.until(EC.presence_of_element_located(s["email_input"]))
        pwd_box = self.driver.find_element(*s["password_input"])
        login_btn = self.driver.find_element(*s["login_button"])

        email_box.send_keys(self.username)
        pwd_box.send_keys(self.password)
        login_btn.click()

        self.wait.until(EC.presence_of_element_located(CONFIG["selectors"]["login_success_indicator"]))
        logging.info("Login successful.")

        try:
            close_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(CONFIG["selectors"]["popup_close_button"])
            )
            close_btn.click()
            logging.info("Closed 'What's new' popup.")
        except TimeoutException:
            logging.info("No 'What's new' popup appeared.")

    def run_scraper(self):
        self._clear_downloads()
        self.login()

        logging.info("Navigating to Relative Outperformance page...")
        rel_out_link = self.wait.until(
            EC.element_to_be_clickable(CONFIG["selectors"]["relative_outperformance_link"])
        )
        self.driver.execute_script("arguments[0].click();", rel_out_link)
        time.sleep(3)

        all_dataframes = []
        segments = { "FNO": CONFIG["selectors"]["fno_tab"], "CASH": CONFIG["selectors"]["cash_tab"] }

        for segment_name, segment_selector in segments.items():
            logging.info("--- Switching to %s segment ---", segment_name)
            self.driver.execute_script("arguments[0].click();", self.wait.until(EC.element_to_be_clickable(segment_selector)))
            time.sleep(2)

            for scan_name, scan_selector in CONFIG["selectors"]["scan_tabs"].items():
                logging.info("Processing scan: %s for %s", scan_name, segment_name)
                try:
                    self.driver.execute_script("arguments[0].click();", self.wait.until(EC.element_to_be_clickable(scan_selector)))
                    time.sleep(1)

                    self.wait.until(EC.element_to_be_clickable(CONFIG["selectors"]["export_csv_button"])).click()
                    logging.info("Clicked 'Export CSV'.")

                    latest_file = self._wait_for_download()
                    df = self._parse_csv(latest_file)
                    all_dataframes.append(df)
                except Exception as e:
                    logging.error("Could not process scan %s for %s. Error: %s", scan_name, segment_name, e, exc_info=True)

        if not all_dataframes:
            logging.warning("No data was scraped.")
            return pd.DataFrame()

        # Consolidate and remove duplicates, keeping the first occurrence of each symbol
        final_df = pd.concat(all_dataframes, ignore_index=True)
        final_df.drop_duplicates(subset=['symbol'], keep='first', inplace=True)
        logging.info("Successfully consolidated data from all CSVs into %d unique symbols.", len(final_df))
        return final_df

    def _wait_for_download(self, timeout=20):
        logging.info("Waiting for CSV download...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            files = [os.path.join(self.download_dir, f) for f in os.listdir(self.download_dir) if f.endswith('.csv')]
            if files:
                latest_file = max(files, key=os.path.getctime)
                logging.info("Found downloaded file: %s", latest_file)
                time.sleep(1)
                return latest_file
            time.sleep(1)
        raise FileNotFoundError("CSV download timeout.")

    def _parse_csv(self, file_path):
        logging.info("Parsing file: %s", file_path)
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        # Helper to parse 'LTP' column
        def parse_ltp(ltp_str):
            if not isinstance(ltp_str, str): return None, None
            match = re.search(r'([\d,]+\.\d+)\s*\((\-?[\d\.]+)%\)', ltp_str)
            return (float(match.group(1).replace(',', '')), float(match.group(2))) if match else (None, None)

        ltp_data = df['LTP'].apply(parse_ltp)
        df['ltp_price'] = [item[0] for item in ltp_data]
        df['ltp_percent_change'] = [item[1] for item in ltp_data]

        # Helper to clean percentage columns
        def clean_performance(value):
            if isinstance(value, str):
                try:
                    return float(value.replace('%', '').strip())
                except (ValueError, TypeError):
                    return None
            return value if pd.notna(value) else None

        # Clean all potential performance columns
        perf_cols = ['7 day Out Performance', '3M Out Performance', '6M Out Performance']
        for col in perf_cols:
            if col in df.columns:
                df[col] = df[col].apply(clean_performance)

        # Rename columns to match the database schema
        rename_map = {
            'Symbol': 'symbol',
            '7 day Out Performance': 'out_performance_7d_percent',
            '3M Out Performance': 'out_performance_3m_percent',
            '6M Out Performance': 'six_month_outperformance',
            'Relative Out Performance wrt Index': 'relative_out_performance_wrt_index'
        }
        df.rename(columns=rename_map, inplace=True)

        # Ensure all required columns exist, adding missing ones as None
        final_columns = [
            'symbol', 'ltp_price', 'ltp_percent_change', 'out_performance_7d_percent',
            'out_performance_3m_percent', 'six_month_outperformance',
            'relative_out_performance_wrt_index'
        ]
        for col in final_columns:
            if col not in df.columns:
                df[col] = None

        os.remove(file_path)
        logging.info("Processed and removed file: %s", file_path)
        return df[final_columns]

    def close(self):
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver closed.")
