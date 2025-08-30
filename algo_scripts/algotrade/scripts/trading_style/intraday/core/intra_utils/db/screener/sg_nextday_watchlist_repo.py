import logging

def get_db_session():
    logging.info("Called dummy get_db_session")
    yield None

def create_tables():
    logging.info("Called dummy create_tables")
    pass

class SgNextDayWatchlistRepository:
    def __init__(self, session):
        logging.info("Initialized dummy SgNextDayWatchlistRepository")
        self.session = session

    def delete_all(self):
        logging.info("Called dummy delete_all")
        return 0

    def bulk_insert(self, records):
        logging.info(f"Called dummy bulk_insert with {len(records)} records")
        return len(records)
