"""
Configuration settings for the NL-to-SQL application.
"""
import os

# --- Directory Settings ---
# Base directory of the application.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory for DuckDB database files.
DATABASE_DIR = os.path.join(BASE_DIR, "database")

# Directory for data files like CSVs.
DATA_DIR = os.path.join(BASE_DIR, "data")
