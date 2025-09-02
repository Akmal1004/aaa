from scraper import IntradayScreenerScraper
from database import Repository

def main():
    """
    Main function to run the scraper and store the data in the database.
    """
    repo = Repository()
    # It's better to initialize the scraper here to ensure its __init__ runs
    # before the try block, making resource cleanup more reliable.
    scraper = IntradayScreenerScraper()

    try:
        # Establish database connection
        repo.connect()
        # Ensure table exists
        repo.create_table()

        # Run scraper to get data
        scraped_data_df = scraper.run_scraper()

        # Insert data into the database
        if scraped_data_df is not None and not scraped_data_df.empty:
            print(f"Total records scraped: {len(scraped_data_df)}")
            repo.insert_data(scraped_data_df)
        else:
            print("No data was scraped, so nothing to insert into the database.")

    except Exception as e:
        print(f"An error occurred during the main process: {e}")

    finally:
        # Ensure all resources are closed
        print("Closing scraper and database resources.")
        scraper.close()
        repo.close()

if __name__ == "__main__":
    main()
