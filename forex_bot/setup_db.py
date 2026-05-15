"""
Run this once to create the SQLite database and all tables.
Usage:  python setup_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from database.db import DatabaseManager, _DEFAULT_DB_URL

print(f"Creating database at: {_DEFAULT_DB_URL}")

db = DatabaseManager(_DEFAULT_DB_URL)
db.init_db()

print("Database ready. Tables created:")
from database.models import Base
from sqlalchemy import create_engine, inspect
engine = create_engine(_DEFAULT_DB_URL, connect_args={"check_same_thread": False})
inspector = inspect(engine)
for table in inspector.get_table_names():
    cols = len(inspector.get_columns(table))
    print(f"  {table} ({cols} columns)")

print("\nDone. You can now run: python main.py")
