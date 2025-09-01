import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, select, delete, Float
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

# ---------------- LOAD ENV AND SETUP LOGGING ----------------
load_dotenv()
# Default to a local SQLite DB if DATABASE_URL is not set, for portability
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nextday_watchlist.db")
if not DATABASE_URL:
    raise ValueError("❌ Please set DATABASE_URL in .env file or ensure the script can create a local sqlite db.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    """Returns the current time in IST timezone."""
    return datetime.now(IST)

# ---------------- SQLALCHEMY SETUP ----------------
try:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
except Exception as e:
    logger.critical(f"Failed to connect to the database: {e}")
    exit(1)


def get_db_session():
    """Provides a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables in the metadata if they do not exist."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Table initialization complete.")


# ---------------- ORM TABLE ----------------
class SgRelativeStrength(Base):
    __tablename__ = "relative_strength_info"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    symbol = Column("Symbol", String(50), nullable=False, unique=True)
    price = Column("Price", String(50))
    rs_rating = Column("RS Rating", String(50))
    percent_off_high = Column("% Off High", String(50))
    industry_group_rank = Column("Ind Grp Rnk", String(50))
    volume_roc = Column("Volume ROC", String(50))
    adx = Column("ADX", String(50))
    created_at = Column(String(100), default=lambda: now_ist().isoformat())

    def __repr__(self):
        return f"<SgRelativeStrength(symbol='{self.symbol}', price='{self.price}', rs_rating='{self.rs_rating}', created_at='{self.created_at}')>"


# ---------------- REPOSITORY ----------------
class SgRelativeStrengthRepository:
    """
    Handles all database operations for the SgRelativeStrength table.
    """
    def __init__(self, db_session: Session):
        self.session = db_session

    def insert(self, record: dict):
        """Inserts a single record into the database."""
        try:
            new_record = SgRelativeStrength(**record)
            self.session.add(new_record)
            self.session.commit()
            logger.info(f"Successfully inserted record for {record.get('symbol')}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error inserting record for {record.get('symbol')}: {e}", exc_info=True)
            self.session.rollback()
            return False

    def bulk_insert(self, records: list[dict]):
        """Bulk inserts a list of records."""
        if not records:
            logger.info("No records to bulk insert.")
            return 0
        try:
            self.session.bulk_insert_mappings(SgRelativeStrength, records)
            self.session.commit()
            count = len(records)
            logger.info(f"Successfully bulk inserted {count} records.")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Error during bulk insert: {e}", exc_info=True)
            self.session.rollback()
            return 0

    def get_all(self, limit: int = 100):
        """Retrieves all records, up to a given limit."""
        try:
            query = select(SgRelativeStrength).limit(limit)
            result = self.session.execute(query).scalars().all()
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving all records: {e}", exc_info=True)
            return []

    def get_by_symbol(self, symbol: str):
        """Retrieves a single record by its symbol."""
        try:
            query = select(SgRelativeStrength).where(SgRelativeStrength.symbol == symbol)
            result = self.session.execute(query).scalar_one_or_none()
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving record by symbol {symbol}: {e}", exc_info=True)
            return None

    def delete_by_symbol(self, symbol: str):
        """Deletes records for a given symbol."""
        try:
            stmt = delete(SgRelativeStrength).where(SgRelativeStrength.symbol == symbol)
            result = self.session.execute(stmt)
            self.session.commit()
            logger.info(f"Deleted {result.rowcount} record(s) for symbol {symbol}.")
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error deleting record by symbol {symbol}: {e}", exc_info=True)
            self.session.rollback()
            return 0

    def delete_all(self):
        """Deletes all records from the table."""
        try:
            stmt = delete(SgRelativeStrength)
            result = self.session.execute(stmt)
            self.session.commit()
            logger.info(f"Deleted all {result.rowcount} records from the table.")
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error deleting all records: {e}", exc_info=True)
            self.session.rollback()
            return 0


# ---------------- MAIN BLOCK FOR DEMONSTRATION ----------------
if __name__ == "__main__":
    logger.info("Starting script execution...")

    create_tables()

    db_session = next(get_db_session())
    repo = SgRelativeStrengthRepository(db_session)

    # Clean up previous test data for a fresh run
    logger.info("--- Cleaning up old data with delete_all ---")
    repo.delete_all()

    # Sample data for insertion
    sample_records = [
        {
            "symbol": "AAPL", "price": "150.20", "rs_rating": "95", "percent_off_high": "5%",
            "industry_group_rank": "A", "volume_roc": "1.5", "adx": "25",
        },
        {
            "symbol": "GOOGL", "price": "2800.00", "rs_rating": "92", "percent_off_high": "3%",
            "industry_group_rank": "A+", "volume_roc": "1.1", "adx": "22",
        },
    ]

    logger.info("--- Testing Bulk Insert ---")
    repo.bulk_insert(sample_records)

    logger.info("--- Testing Single Insert ---")
    repo.insert({
        "symbol": "MSFT", "price": "300.50", "rs_rating": "88", "percent_off_high": "8%",
        "industry_group_rank": "B", "volume_roc": "0.9", "adx": "20",
    })

    logger.info("--- Retrieving all records ---")
    all_data = repo.get_all()
    if all_data:
        for item in all_data:
            logger.info(f"  - {item}")
    else:
        logger.warning("  No data found.")

    logger.info("--- Retrieving record for 'GOOGL' ---")
    googl_data = repo.get_by_symbol("GOOGL")
    if googl_data:
        logger.info(f"  - Found: {googl_data}")
    else:
        logger.warning("  - 'GOOGL' not found.")

    logger.info("--- Deleting record for 'AAPL' ---")
    repo.delete_by_symbol("AAPL")

    logger.info("--- Retrieving all records to verify deletion ---")
    all_data_after_delete = repo.get_all()
    if all_data_after_delete:
        for item in all_data_after_delete:
            logger.info(f"  - {item}")
    else:
        logger.warning("  No data found.")

    logger.info("--- Script execution finished ---")
