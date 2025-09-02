from scraper import run_scraper
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    """
    Main entry point for the application.
    """
    try:
        logging.info("--- Starting Intraday Screener Scraper ---")
        run_scraper()
        logging.info("--- Scraper finished successfully ---")
    except Exception as e:
        logging.error(f"An unhandled error occurred in the main application: {e}", exc_info=True)

if __name__ == "__main__":
    main()
