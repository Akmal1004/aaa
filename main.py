import logging
from scraper import IntradayScreenerScraper
from database import (
    create_tables,
    get_db_session,
    SgRelativeOutperformanceRepository,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    """
    Main function to run the scraper and store the data in the database.
    """
    # 1. Initialize database tables
    # This ensures the table exists before we try to interact with it.
    create_tables()

    scraper = None
    try:
        # 2. Run the scraper to get data
        scraper = IntradayScreenerScraper()
        scraped_data_df = scraper.run_scraper()

        # 3. Perform database operations
        if scraped_data_df is not None and not scraped_data_df.empty:
            logging.info("Starting database operations...")
            db_session_generator = get_db_session()
            db_session = next(db_session_generator)

            repo = SgRelativeOutperformanceRepository(db_session)

            # a. Wipe all existing data
            logging.info("Deleting old records from the database...")
            repo.delete_all()

            # b. Convert DataFrame to list of dictionaries for bulk insert
            records_to_insert = scraped_data_df.to_dict(orient="records")

            # c. Bulk insert new data
            logging.info(f"Inserting {len(records_to_insert)} new records...")
            repo.bulk_insert(records_to_insert)

            logging.info("Database operations complete.")
        else:
            logging.warning("No data was scraped, skipping database operations.")

    except Exception as e:
        logging.error(f"An error occurred during the main process: {e}", exc_info=True)

    finally:
        # 4. Ensure scraper resources are always closed
        if scraper:
            logging.info("Closing scraper resources.")
            scraper.close()

if __name__ == "__main__":
    main()
