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
from algo_scripts.algotrade.scripts.trading_style.intraday.core.intra_utils.db.screener.sg_relative_strength_repo import SgRelativeStrengthRepository, get_db_session, create_tables

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
chrome_options.add_argument("--headless") # Running in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--start-maximized")
prefs = {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
}
chrome_options.add_experimental_option("prefs", prefs)

# ---------------- CLEAN FUNCTION ----------------
def clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str) and v.strip().lower() == "nan":
        return None
    return str(v).strip()

# ---------------- MAIN FUNCTION ----------------
def main():
    driver = None
    try:
        logging.info("🌐 Opening Chrome browser...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # 1️⃣ LOGIN
        logging.info("🔑 Opening login page...")
        driver.get("https://intradayscreener.com/login")
        email_box = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="inputEmail"]')))
        pwd_box = driver.find_element(By.XPATH,
                                      '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/div[2]/div/input')
        login_btn = driver.find_element(By.XPATH,
                                        '/html/body/app-root/div/app-login-layout/div/app-signin/div/div[1]/div/div[2]/div/div/div/div/div/div/form/button')

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

        # 2️⃣ NAVIGATE TO RELATIVE STRENGTH SCANS
        # NOTE: This XPATH is an assumption. It assumes "Relative Strength Scans" is the second item in the "EOD Scans" dropdown.
        # This may need to be adjusted if the website structure is different.
        logging.info("📂 Navigating to Relative Strength Scans...")
        rs_scans_link = wait.until(EC.presence_of_element_located(
            (By.XPATH, '/html/body/app-root/div/app-home-layout/div[1]/app-nav-bar/div[1]/nav/div[3]/ul/li[5]/ul/li[2]/a')))
        driver.execute_script("arguments[0].click();", rs_scans_link)
        logging.info("✅ Reached Relative Strength Scans page")
        time.sleep(3)

        # 3️⃣ EXPORT CSV
        logging.info("⬇️ Clicking Export CSV...")
        # NOTE: This assumes the export button has the same XPATH as on the other page.
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, '/html/body/app-root/div/app-home-layout/div[2]/app-watch-list/div/div[2]/div/div[1]/div[2]/button'))
        ).click()
        time.sleep(5)
        logging.info("✅ CSV Exported")

        # 4️⃣ FIND DOWNLOADED FILE
        csv_file = None
        for f in os.listdir(download_dir):
            if f.endswith(".csv"):
                csv_file = os.path.join(download_dir, f)
                break
        if not csv_file:
            raise FileNotFoundError("❌ CSV file not found in downloads")
        logging.info(f"📄 Found CSV: {csv_file}")

        # 5️⃣ SAVE TO DATABASE
        logging.info("📝 Processing and saving data to the database...")
        create_tables()  # Ensure table exists

        df = pd.read_csv(csv_file)
        df.columns = df.columns.str.strip()

        # NOTE: Column names in the CSV are assumed based on the ORM model.
        # These may need to be adjusted if they are different in the actual CSV file.
        column_mapping = {
            "Symbol": "symbol",
            "Price": "price",
            "RS Rating": "rs_rating",
            "% Off High": "percent_off_high",
            "Ind Grp Rnk": "industry_group_rank",
            "Volume ROC": "volume_roc",
            "ADX": "adx",
        }
        df.rename(columns=column_mapping, inplace=True)

        # Convert dataframe to a list of dictionaries and apply final cleaning
        records = df.to_dict(orient='records')
        cleaned_records = [
            {k: clean_value(v) for k, v in record.items() if k in column_mapping.values()}
            for record in records
        ]

        db_session = next(get_db_session())
        repo = SgRelativeStrengthRepository(db_session)

        logging.info("🗑️ Deleting all old relative strength data...")
        repo.delete_all()

        logging.info(f"💾 Inserting {len(cleaned_records)} new records...")
        inserted_count = repo.bulk_insert(cleaned_records)

        if inserted_count > 0:
            logging.info(f"✅ Successfully inserted {inserted_count} records into the database.")
        else:
            logging.error("❌ Data insertion failed. Please check the logs above for errors.")

    except Exception as e:
        logging.error(f"❌ Error: {e}")
    finally:
        if driver:
            driver.quit()
            logging.info("🔒 Browser closed")
        # Clean up downloaded file
        if 'csv_file' in locals() and csv_file and os.path.exists(csv_file):
            os.remove(csv_file)
            logging.info(f"🗑️ Cleaned up downloaded file: {csv_file}")


# ---------------- API TRIGGER ----------------
def run_relative_strength_scraper():
    main()

# ---------------- RUN ----------------
if __name__ == "__main__":
    main()
