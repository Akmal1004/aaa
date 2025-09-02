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
from database import (
    create_tables,
    get_db_session,
    SgRelativeOutperformanceRepository,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()
EMAIL = os.getenv("INTRADAY_USERNAME")
PWD = os.getenv("INTRADAY_PASSWORD")
if not EMAIL or not PWD:
    raise ValueError("Please set INTRADAY_USERNAME and INTRADAY_PASSWORD in .env file")

def _get_latest_file(directory: str) -> str:
    """Finds the most recently created file in a directory."""
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith('.csv')]
    if not files:
        raise FileNotFoundError("No CSV file found in the download directory.")
    return max(files, key=os.path.getctime)

def _parse_and_clean_csv(file_path: str) -> pd.DataFrame:
    """Reads, parses, and cleans the data from a given CSV file."""
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

    return df[final_columns]


def scrape_data():
    """Main function to perform the scraping and database operations."""
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    # Clear downloads directory
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    driver = None
    try:
        # --- WebDriver Setup ---
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1200")
        prefs = {"download.default_directory": download_dir, "download.prompt_for_download": False}
        chrome_options.add_experimental_option("prefs", prefs)

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # --- Login ---
        logging.info("Logging in...")
        driver.get("https://intradayscreener.com/login")
        wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="inputEmail"]'))).send_keys(EMAIL)
        driver.find_element(By.XPATH, '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/div[2]/div/input').send_keys(PWD)
        driver.find_element(By.XPATH, '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/button').click()
        wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="navbarSupportedContent"]/li[5]/ul/li[3]/a')))
        logging.info("Login successful.")

        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="whatsnewModal"]/div/div/div[1]/button/span'))).click()
            logging.info("Closed popup.")
        except TimeoutException:
            logging.info("No popup appeared.")

        # --- Navigation ---
        logging.info("Navigating to Relative Outperformance page...")
        rel_out_link = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="navbarSupportedContent"]/li[5]/ul/li[3]/a')))
        driver.execute_script("arguments[0].click();", rel_out_link)
        time.sleep(3)

        # --- Download CSVs ---
        # This logic mimics the user's reference code, which downloads multiple
        # files but only processes the last one.

        # F&O Scans
        logging.info("--- Downloading F&O Scans ---")
        driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[1]'))))
        time.sleep(2)

        scan_tabs = ["pills-home-tab", "pills-profile-tab", "pills-contact-tab", "pills-message-tab"]
        for i, tab_id in enumerate(scan_tabs):
            logging.info(f"Downloading F&O Scan {i+1}...")
            driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.ID, tab_id))))
            time.sleep(1)
            wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="pills-tab"]/button'))).click()
            time.sleep(2) # Wait for download to initiate

        # Cash Scans
        logging.info("--- Downloading CASH Scans ---")
        driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[2]'))))
        time.sleep(2)

        for i, tab_id in enumerate(scan_tabs):
            logging.info(f"Downloading Cash Scan {i+1}...")
            driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.ID, tab_id))))
            time.sleep(1)
            wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="pills-tab"]/button'))).click()
            time.sleep(2)

        # --- Process the latest CSV ---
        logging.info("Processing the latest downloaded file...")
        latest_csv = _get_latest_file(download_dir)
        df = _parse_and_clean_csv(latest_csv)

        # --- Database Operations ---
        if not df.empty:
            create_tables()
            db_session = next(get_db_session())
            repo = SgRelativeOutperformanceRepository(db_session)

            logging.info("Deleting all old records...")
            repo.delete_all()

            records = df.to_dict(orient="records")
            logging.info(f"Inserting {len(records)} new records...")
            repo.bulk_insert(records)
        else:
            logging.warning("No data to insert into the database.")

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logging.info("Browser closed.")

# Entry point function to be called by main.py
def run_scraper():
    scrape_data()
