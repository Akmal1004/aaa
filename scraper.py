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

from algo_scripts.algotrade.scripts.trading_style.intraday.core.intra_utils.db.screener.sg_relative_outperformance_repo import (
    SgRelativeOutperformanceRepository,
    get_db_session,
    create_tables,
)

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- LOAD ENV ----------------
load_dotenv()
EMAIL = os.getenv("INTRADAY_SCREENER_EMAIL")
PWD = os.getenv("INTRADAY_SCREENER_PWD")
if not EMAIL or not PWD:
    raise ValueError("❌ Please set INTRADAY_SCREENER_EMAIL and INTRADAY_SCREENER_PWD in .env file")

# ---------------- DOWNLOAD DIR ----------------
download_dir = os.path.join(os.getcwd(), "downloads")
os.makedirs(download_dir, exist_ok=True)

# ---------------- CHROME OPTIONS ----------------
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--start-maximized")
prefs = {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True,
}
chrome_options.add_experimental_option("prefs", prefs)

# ---------------- HELPER FUNCTIONS ----------------
def clean_downloads_directory(directory):
    """Deletes all .csv files in the specified directory."""
    logging.info(f"Cleaning downloads directory: {directory}")
    try:
        for filename in os.listdir(directory):
            if filename.endswith(".csv"):
                file_path = os.path.join(directory, filename)
                os.remove(file_path)
                logging.info(f"Removed old file: {filename}")
        logging.info("Downloads directory cleaned.")
    except FileNotFoundError:
        logging.warning(f"Downloads directory not found at {directory}. Skipping cleanup.")
    except Exception as e:
        logging.error(f"Error cleaning downloads directory: {e}")

def clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str) and v.strip().lower() in ["nan", "none"]:
        return None
    return str(v).strip()

# ---------------- HELPER FOR DOWNLOAD ----------------
def download_for_tab_group(driver, wait, segment_name, tab_xpaths, tab_descriptions, export_button_xpath):
    """Clicks through a list of tabs and exports the data for each."""
    logging.info(f"--- Processing {segment_name} tabs ---")
    for i in range(len(tab_xpaths)):
        description = tab_descriptions[i]
        xpath = tab_xpaths[i]
        logging.info(f"⬇️ Exporting CSV for {segment_name} - {description}...")
        try:
            # Click the data tab
            tab_to_click = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].click();", tab_to_click)
            time.sleep(2)  # Wait for the tab content to load

            # Click the export button
            export_button = wait.until(EC.element_to_be_clickable((By.XPATH, export_button_xpath)))
            driver.execute_script("arguments[0].click();", export_button)
            time.sleep(3)  # Wait for the download to initiate
            logging.info(f"✅ Successfully initiated download for {segment_name} - {description}")
        except Exception as e:
            logging.error(f"❌ Failed to download for {segment_name} - {description}. Error: {e}")


# ---------------- MAIN FUNCTION ----------------
def main():
    driver = None
    try:
        # Clean the downloads directory before starting the browser
        clean_downloads_directory(download_dir)

        logging.info("🌐 Opening Chrome browser...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # 1️ LOGIN
        logging.info("🔑 Logging in...")
        driver.get("https://intradayscreener.com/login")
        email_box = wait.until(EC.presence_of_element_located((By.ID, "inputEmail")))
        pwd_box = driver.find_element(By.XPATH, '//input[@type="password"]')
        login_btn = driver.find_element(By.XPATH, '//button[@type="submit"]')

        email_box.send_keys(EMAIL)
        pwd_box.send_keys(PWD)
        login_btn.click()
        logging.info("✅ Logged in successfully")

        # Close popup if exists
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="whatsnewModal"]/div/div/div[1]/button/span'))
            ).click()
        except:
            logging.info("ℹ️ No popup appeared")

        # 2️ NAVIGATE TO RELATIVE OUTPERFORMANCE
        logging.info("📂 Navigating to Relative Outperformance...")
        rel_out_link = wait.until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="navbarSupportedContent"]/li[5]/ul/li[3]/a'))
        )
        driver.execute_script("arguments[0].click();", rel_out_link)
        time.sleep(3)

        driver.refresh()
        time.sleep(3)

        # Define tab selectors and descriptions.
        # This version uses a more specific XPath assuming a standard list-item tab structure.
        tab_xpaths = [
            '//*[@id="pills-home-tab"]',
            '//*[@id="pills-home-tab"]/../following-sibling::li[1]/a',
            '//*[@id="pills-home-tab"]/../following-sibling::li[2]/a',
            '//*[@id="pills-home-tab"]/../following-sibling::li[3]/a',
        ]
        tab_descriptions = [
            "Outperforming Short & Medium",
            "Underperforming Short & Medium",
            "Outperforming 6Month",
            "Underperforming 6Month",
        ]
        export_button_xpath = '//*[@id="pills-tab"]/button'

        # ==============================
        # SWITCH TO CASH & DOWNLOAD
        # ==============================
        logging.info("🔄 Switching to CASH tab...")
        cash_tab = wait.until(
            EC.presence_of_element_located((By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[2]'))
        )
        driver.execute_script("arguments[0].click();", cash_tab)
        time.sleep(2)
        download_for_tab_group(driver, wait, "Cash", tab_xpaths, tab_descriptions, export_button_xpath)

        # ==============================
        # SWITCH TO F&O & DOWNLOAD
        # ==============================
        logging.info("🔄 Switching to F&O tab...")
        fo_tab = wait.until(
            EC.presence_of_element_located((By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-index-panel/div/div[2]/div/button[1]'))
        )
        driver.execute_script("arguments[0].click();", fo_tab)
        time.sleep(2)
        download_for_tab_group(driver, wait, "F&O", tab_xpaths, tab_descriptions, export_button_xpath)


        # ==============================
        # PROCESS ALL DOWNLOADED CSVs
        # ==============================
        csv_files = [os.path.join(download_dir, f) for f in os.listdir(download_dir) if f.endswith(".csv")]
        if not csv_files:
            raise FileNotFoundError("❌ No CSV files found in the downloads directory.")

        all_records = []
        logging.info(f"Found {len(csv_files)} CSV files to process.")

        for csv_file in csv_files:
            try:
                logging.info(f"📄 Processing file: {csv_file}")
                df = pd.read_csv(csv_file)
                # Clean column names: strip whitespace and remove trailing colons
                df.columns = [col.strip().rstrip(':').strip() for col in df.columns]

                # Parse LTP column
                ltp_parts = df['LTP'].astype(str).str.extract(r'([\d\.]+)\s*\((.+)\)')

                # Prepare DataFrame for database insertion, handling different column sets
                # Dynamically find the performance index column to handle variations
                performance_col = next((col for col in df.columns if 'relative out performance' in col.lower()), None)

                db_df = pd.DataFrame({
                    'symbol': df['Symbol'],
                    'ltp_price': ltp_parts[0],
                    'ltp_percent_change': ltp_parts[1],
                    'out_performance_7d_percent': df.get('7 day Out Performance'),
                    'out_performance_3m_percent': df.get('3M Out Performance'),
                    'out_performance_6m_percent': df.get('6 Month Out Performance'),
                    'relative_out_performance_wrt_index': df[performance_col] if performance_col else None
                })

                records = db_df.to_dict(orient="records")
                cleaned_records = [{k: clean_value(v) for k, v in record.items()} for record in records]
                all_records.extend(cleaned_records)
            except Exception as e:
                logging.error(f"❌ Failed to process file {csv_file}. Error: {e}")

        if not all_records:
            logging.error("❌ No records were extracted from the CSV files. Nothing to insert into the database.")
            return

        # Sort records to ensure consistent priority during de-duplication.
        # We prioritize 'underperforming' so it overwrites 'outperforming' for the same symbol.
        def sort_key(record):
            # Using startswith() for a more specific and robust check after stripping whitespace.
            status = record.get('relative_out_performance_wrt_index', '').strip().lower()
            if status.startswith('outperforming'):
                return 1  # Process first
            if status.startswith('underperforming'):
                return 2  # Process second, will overwrite
            return 0  # Should not happen

        all_records.sort(key=sort_key)

        # De-duplicate the records based on the 'symbol' key. The last one seen wins.
        unique_records_dict = {record['symbol']: record for record in all_records}
        unique_records = list(unique_records_dict.values())
        logging.info(f"Removed {len(all_records) - len(unique_records)} duplicate records, prioritizing underperforming status.")

        # Database operations: upsert all records.
        create_tables()
        db_session = next(get_db_session())
        repo = SgRelativeOutperformanceRepository(db_session)

        logging.info(f"💾 Upserting {len(unique_records)} unique records into the database...")
        upserted_count = repo.bulk_upsert(unique_records)

        if upserted_count > 0:
            logging.info(f"✅ Successfully upserted {upserted_count} records.")
        else:
            logging.error("❌ No records were upserted into the database.")

    except Exception as e:
        logging.error(f"❌ An error occurred during the scraping process: {e}")
    finally:
        if driver:
            driver.quit()
            logging.info("🔒 Browser closed")

# ---------------- RUN ----------------
def run_relative_outperformance_scraper():
    main()

if __name__ == "__main__":
    run_relative_outperformance_scraper()
