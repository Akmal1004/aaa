import sqlite3
import pandas as pd

class Repository:
    def __init__(self, db_name='screener_data.db'):
        """
        Initializes the Repository. Does not connect automatically.
        """
        self.db_name = db_name
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establishes the database connection."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
            print("Database connection established.")

    def close(self):
        """Closes the database connection if it exists."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
            print("Database connection closed.")

    def create_table(self):
        """
        Creates the 'relative_performance' table if it does not exist.
        Assumes that a connection is already established.
        """
        if self.conn is None:
            raise Exception("Database not connected. Call connect() before using the repository.")

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS relative_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                ltp REAL,
                ltp_percent_change REAL,
                seven_day_outperformance REAL,
                six_month_outperformance REAL,
                relative_outperformance_wrt_index TEXT,
                scan_type TEXT,
                stock_segment TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, scan_type, stock_segment)
            )
        ''')
        self.conn.commit()
        print("Table 'relative_performance' created or already exists.")

    def insert_data(self, data_df: pd.DataFrame):
        """
        Inserts data using a 'delete-then-insert' approach (upsert).
        Assumes that a connection is already established.
        """
        if self.conn is None:
            raise Exception("Database not connected. Call connect() before using the repository.")

        if data_df.empty:
            print("No data to insert.")
            return

        unique_scans = data_df[['scan_type', 'stock_segment']].drop_duplicates().to_dict('records')

        with self.conn: # Use a transaction for the whole operation
            for scan in unique_scans:
                scan_type, stock_segment = scan['scan_type'], scan['stock_segment']
                print(f"Deleting old data for {scan_type} - {stock_segment}...")
                self.cursor.execute(
                    "DELETE FROM relative_performance WHERE scan_type = ? AND stock_segment = ?",
                    (scan_type, stock_segment)
                )

            print("Inserting new data...")
            data_df.to_sql(
                'relative_performance',
                self.conn,
                if_exists='append',
                index=False
            )

        print(f"Upserted {len(data_df)} records into 'relative_performance'.")
