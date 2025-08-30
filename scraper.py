import os
import time
import logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
from algo_scripts.algotrade.scripts.trading_style.intraday.core.intra_utils.db.screener.sg_nextday_watchlist_repo import SgNextDayWatchlistRepository, get_db_session, create_tables
import argparse

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- CLEAN FUNCTION ----------------
def clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str) and v.strip().lower() == "nan":
        return None
    return str(v).strip()

# ---------------- WEBDRIVER SETUP ----------------
def setup_driver(download_dir: str, headless: bool = False) -> webdriver.Chrome:
    """Sets up the Chrome driver with necessary options."""
    logging.info("🌐 Setting up Chrome driver...")
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")
    else:
        chrome_options.add_argument("--start-maximized")

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    logging.info("✅ Chrome driver setup complete.")
    return driver

# ---------------- LOGIN ----------------
def login_to_site(driver: webdriver.Chrome, wait: WebDriverWait, email: str, pwd: str):
    """Logs into the intraday screener website."""
    logging.info("🔑 Opening login page...")
    driver.get("https://intradayscreener.com/login")

    # Using more robust locators with explicit waits for all elements
    email_box = wait.until(EC.presence_of_element_located((By.ID, 'inputEmail')))
    pwd_box = wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="password"]')))
    login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[text()="Login"]')))

    email_box.send_keys(email)
    pwd_box.send_keys(pwd)
    login_btn.click()
    logging.info("✅ Logged in successfully")

    try:
        # Using a more specific and robust locator for the popup close button
        close_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="whatsnewModal"]//button[contains(@class, "close")]'))
        )
        close_button.click()
        logging.info("ℹ️ Closed 'What's New' popup.")
    except:
        logging.info("ℹ️ No popup appeared.")

# ---------------- NAVIGATION & EXPORT ----------------
def navigate_to_watchlist_and_export(driver: webdriver.Chrome, wait: WebDriverWait):
    """Navigates to EOD scans, selects F&O, and exports CSV."""
    logging.info("📂 Navigating to EOD scans...")
    eod_scans = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//a[contains(text(), "EOD Scans")]')))
    driver.execute_script("arguments[0].click();", eod_scans)
    logging.info("✅ Reached Next Day Watchlist page")

    logging.info("🔀 Clicking F&O button...")
    fno_button = wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//button[contains(text(), "F&O")]')))
    fno_button.click()
    logging.info("✅ Switched to F&O watchlist")

    # Wait for the table to reload by waiting for the loader to disappear
    try:
        logging.info("⏳ Waiting for table data to load...")
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, 'div.loader-container')))
        logging.info("✅ Table data loaded.")
    except:
        logging.warning("⚠️ Loader not found or did not disappear, proceeding with caution.")

    logging.info("⬇️ Clicking Export CSV...")
    wait.until(EC.element_to_be_clickable(
        (By.XPATH, '//button[contains(text(), "Export CSV")]'))
    ).click()
    logging.info("✅ CSV Export initiated.")

# ---------------- FILE HANDLING ----------------
def wait_for_download_and_get_filepath(download_dir: str, timeout: int = 30) -> str:
    """Waits for a new CSV file to be downloaded and returns its full path."""
    logging.info(f"🕒 Waiting for download to complete in '{download_dir}'...")
    seconds = 0
    dl_wait = True
    while dl_wait and seconds < timeout:
        time.sleep(1)
        dl_wait = False
        files = os.listdir(download_dir)
        if not any(f.endswith('.csv') for f in files):
            dl_wait = True
        for fname in files:
            if fname.endswith('.crdownload'):
                dl_wait = True
        seconds += 1

    if dl_wait:
        raise FileNotFoundError(f"❌ Download did not complete within {timeout} seconds.")

    files = [os.path.join(download_dir, f) for f in os.listdir(download_dir) if f.endswith('.csv')]
    if not files:
        raise FileNotFoundError("❌ CSV file not found in downloads directory.")

    latest_file = max(files, key=os.path.getctime)
    logging.info(f"📄 Found downloaded CSV: {latest_file}")
    return latest_file

# ---------------- DATABASE OPERATIONS ----------------
def process_and_save_data(csv_file: str):
    """Processes the CSV data and saves it to the database."""
    logging.info("📝 Processing and saving data to the database...")
    create_tables()

    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()

    if 'Price' in df.columns:
        df['Price'] = df['Price'].apply(lambda x: str(x).split('\n')[0].strip())
    for col in ["Momentum", "1D/5D Vol"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: ', '.join(str(x).split('\n')))

    column_mapping = {
        "Symbol": "symbol", "Price": "price", "Momentum": "momentum",
        "1D/5D Vol": "vol_1d_5d", "Weekly BO": "weekly_bo", "Monthly BO": "monthly_bo",
        "Yearly BO": "yearly_bo", "OI CHG": "oi_chg", "Buy Level": "buy_level",
        "Sell Level": "sell_level",
    }
    df.rename(columns=column_mapping, inplace=True)

    records = df.to_dict(orient='records')
    cleaned_records = [{k: clean_value(v) for k, v in record.items() if k in column_mapping.values()} for record in records]

    db_session = next(get_db_session())
    repo = SgNextDayWatchlistRepository(db_session)

    logging.info("🗑️ Deleting all old watchlist data...")
    repo.delete_all()

    logging.info(f"💾 Inserting {len(cleaned_records)} new records...")
    inserted_count = repo.bulk_insert(cleaned_records)

    if inserted_count > 0:
        logging.info(f"✅ Successfully inserted {inserted_count} records.")
    else:
        logging.error("❌ Data insertion failed.")

# ---------------- MAIN FUNCTION ----------------
def main():
    parser = argparse.ArgumentParser(description="Scrape Next Day Watchlist from IntradayScreener.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    args = parser.parse_args()

    load_dotenv()
    EMAIL = os.getenv("INTRADAY_SCREENER_EMAIL")
    PWD = os.getenv("INTRADAY_SCREENER_PWD")
    if not EMAIL or not PWD:
        raise ValueError("❌ Please set INTRADAY_SCREENER_EMAIL and INTRADAY_SCREENER_PWD in .env file")

    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    driver = None
    csv_file = None
    try:
        driver = setup_driver(download_dir, headless=args.headless)
        wait = WebDriverWait(driver, 20)

        login_to_site(driver, wait, EMAIL, PWD)
        navigate_to_watchlist_and_export(driver, wait)

        csv_file = wait_for_download_and_get_filepath(download_dir)

        process_and_save_data(csv_file)

    except Exception as e:
        logging.error(f"❌ An unexpected error occurred: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logging.info("🔒 Browser closed")
        if csv_file and os.path.exists(csv_file):
            try:
                os.remove(csv_file)
                logging.info(f"🧹 Cleaned up downloaded file: {csv_file}")
            except Exception as e:
                logging.error(f"⚠️ Error during file cleanup: {e}")

# ---------------- API TRIGGER ----------------
def run_nextday_watchlist_scraper():
    main()

# ---------------- RUN ----------------
if __name__ == "__main__":
    main()
