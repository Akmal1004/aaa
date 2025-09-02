import os
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, select, delete, func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

# ---------------- LOAD ENV AND SETUP LOGGING ----------------
load_dotenv()

# Default to a local SQLite DB if DATABASE_URL is not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./relative_outperformance.db")
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
class SgRelativeOutperformance(Base):
    __tablename__ = "relative_outperformance_info"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    symbol = Column("symbol", String(50), nullable=False, unique=True)
    ltp_price = Column("ltp_price", String(50))
    ltp_percent_change = Column("ltp_percent_change", String(50))
    out_performance_7d_percent = Column("out_performance_7d_percent", String(50), nullable=True)
    out_performance_3m_percent = Column("out_performance_3m_percent", String(50), nullable=True)
    out_performance_6m_percent = Column("out_performance_6m_percent", String(50), nullable=True)
    relative_out_performance_wrt_index = Column("relative_out_performance_wrt_index", Text)
    created_at = Column(String(100), default=lambda: now_ist().isoformat())

    def __repr__(self):
        return f"<SgRelativeOutperformance(symbol='{self.symbol}', ltp_price='{self.ltp_price}', created_at='{self.created_at}')>"

# ---------------- REPOSITORY ----------------
class SgRelativeOutperformanceRepository:
    """ Handles all database operations for the SgRelativeOutperformance table. """
    def __init__(self, db_session: Session):
        self.session = db_session

    def bulk_insert(self, records: list[dict]):
        """Bulk inserts a list of records."""
        if not records:
            logger.info("No records to bulk insert.")
            return 0
        try:
            self.session.bulk_insert_mappings(SgRelativeOutperformance, records)
            self.session.commit()
            count = len(records)
            logger.info(f"Successfully bulk inserted {count} records.")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Error during bulk insert: {e}", exc_info=True)
            self.session.rollback()
            return 0

    def delete_all(self):
        """Deletes all records from the table."""
        try:
            stmt = delete(SgRelativeOutperformance)
            result = self.session.execute(stmt)
            self.session.commit()
            logger.info(f"Deleted all {result.rowcount} records from the table.")
            return result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Error deleting all records: {e}", exc_info=True)
            self.session.rollback()
            return 0

    def bulk_upsert(self, records: list[dict]):
        """
        Performs a bulk 'upsert' (insert on duplicate key update) for MySQL.
        This version intelligently merges data, preventing existing values from
        being overwritten by NULLs.
        """
        if not records:
            logger.info("No records provided for bulk upsert.")
            return 0

        try:
            insert_stmt = mysql_insert(SgRelativeOutperformance).values(records)

            # Define the update logic for duplicate keys.
            # We use COALESCE to keep the existing value if the new value is NULL.
            # This effectively merges records from different file types.
            # The 'relative_out_performance_wrt_index' is always updated to reflect the latest status
            # based on the pre-sorted record list.
            update_cols = {
                'ltp_price': func.coalesce(insert_stmt.inserted.ltp_price, SgRelativeOutperformance.ltp_price),
                'ltp_percent_change': func.coalesce(insert_stmt.inserted.ltp_percent_change, SgRelativeOutperformance.ltp_percent_change),
                'out_performance_7d_percent': func.coalesce(insert_stmt.inserted.out_performance_7d_percent, SgRelativeOutperformance.out_performance_7d_percent),
                'out_performance_3m_percent': func.coalesce(insert_stmt.inserted.out_performance_3m_percent, SgRelativeOutperformance.out_performance_3m_percent),
                'out_performance_6m_percent': func.coalesce(insert_stmt.inserted.out_performance_6m_percent, SgRelativeOutperformance.out_performance_6m_percent),
                'relative_out_performance_wrt_index': insert_stmt.inserted.relative_out_performance_wrt_index,
            }

            upsert_stmt = insert_stmt.on_duplicate_key_update(update_cols)

            self.session.execute(upsert_stmt)
            self.session.commit()
            logger.info(f"Successfully bulk upserted {len(records)} records.")
            return len(records)
        except SQLAlchemyError as e:
            logger.error(f"Database error during bulk upsert: {e}", exc_info=True)
            self.session.rollback()
            return 0

if __name__=="__main__":
    create_tables()
