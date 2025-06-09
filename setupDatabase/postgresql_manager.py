import logging
import psycopg2
import psycopg2.extras
from psycopg2.extras import DictCursor, execute_values
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, List, Dict, Any
import pandas as pd
import csv
import re

from .postgresql_config import DEFAULT_POSTGRESQL_CONFIG, PostgreSQLConfig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PostgreSQLManager:
    """Manages PostgreSQL database operations including setup, connection, and data insertion."""

    def __init__(self, config: PostgreSQLConfig = DEFAULT_POSTGRESQL_CONFIG):
        self.config = config

    def create_database(self) -> bool:
        """
        Creates database and sets up the schema.

        Returns:
            bool: True if database creation was successful, False otherwise.
        """
        try:
            # Test connection first
            with self.get_connection() as conn:
                logger.info(f"Connected to PostgreSQL database: {self.config.database}")

            # Execute schema if provided
            if self.config.schema_path:
                return self.execute_sql_file(self.config.schema_path)
            return True

        except Exception as e:
            logger.error(f"Failed to create/connect to database: {e}")
            return False

    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """
        Context manager for database connections.

        Yields:
            psycopg2.connection: Database connection object.
        """
        conn = None
        try:
            conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password
            )
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()

    def execute_sql_file(self, file_path: str) -> bool:
        """
        Executes SQL commands from a file.

        Args:
            file_path (str): Path to the SQL file.

        Returns:
            bool: True if execution was successful, False otherwise.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                sql_script = file.read()
        except FileNotFoundError:
            logger.error(f"SQL file not found: {file_path}")
            return False

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql_script)
            logger.info(f"SQL script executed successfully from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Error executing SQL script: {e}")
            return False

    def get_category_id(self, category_name: str) -> Optional[int]:
        """
        Get category ID by category name, create if doesn't exist.

        Args:
            category_name (str): Name of the category.

        Returns:
            Optional[int]: Category ID if found/created, None otherwise.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    # Try to find existing category
                    cur.execute("SELECT id_category FROM categories WHERE category_name = %s", (category_name,))
                    result = cur.fetchone()
                    
                    if result:
                        return result['id_category']
                    
                    # Create new category if not exists
                    cur.execute(
                        "INSERT INTO categories (category_name) VALUES (%s) RETURNING id_category",
                        (category_name,)
                    )
                    result = cur.fetchone()
                    return result['id_category'] if result else None
                    
        except Exception as e:
            logger.error(f"Error getting/creating category: {e}")
            return None

    def clean_price(self, price_str: str) -> float:
        """
        Clean and convert price string to float.

        Args:
            price_str (str): Price string from CSV.

        Returns:
            float: Cleaned price value.
        """
        if not price_str:
            return 0.0
        
        # Remove all non-digit characters except decimal point
        cleaned = str(price_str).replace('.', '').replace(',', '.')
        
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            logger.warning(f"Could not convert price: {price_str}")
            return 0.0

    def insert_product_from_csv_row(self, row: Dict[str, Any]) -> bool:
        """
        Insert a single product from CSV row.

        Args:
            row (Dict[str, Any]): CSV row as dictionary.

        Returns:
            bool: True if insertion was successful, False otherwise.
        """
        try:
            # Get category ID
            # print("1111111111111: ", row)
            category_id = self.get_category_id(row.get('Category', 'other'))
            if not category_id:
                logger.error(f"Failed to get category ID for: {row.get('Category', 'other')}")
                return False

            # Clean price
            price = self.clean_price(row.get('Price', '0'))
            if price <= 0:
                logger.warning(f"Skip insert: price <= 0 for product: {row.get('Product_name', '')}")
                return False

            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO products (url, image_url, product_name, id_category, description, price, product_info, usage_instructions)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row.get("\ufeffURL", ''),
                        row.get('Image_URL'),
                        row.get('Product_name', ''),
                        category_id,
                        row.get('Description', ''),
                        price,
                        row.get('Product_info', ''),
                        row.get('Usage_instructions', '')
                    ))
            
            return True
            
        except Exception as e:
            logger.error(f"Error inserting product: {e}")
            return False

    def import_products_from_csv(self, csv_file_path: str = None) -> bool:
        """
        Import products from CSV file to PostgreSQL database.

        Args:
            csv_file_path (str, optional): Path to CSV file. Uses config path if None.

        Returns:
            bool: True if import was successful, False otherwise.
        """
        if not csv_file_path:
            csv_file_path = self.config.csv_path

        if not csv_file_path or not Path(csv_file_path).exists():
            logger.error(f"CSV file not found: {csv_file_path}")
            return False

        try:
            success_count = 0
            error_count = 0
            
            logger.info(f"Starting CSV import from: {csv_file_path}")
            
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                
                for row_num, row in enumerate(csv_reader, 1):
                    if self.insert_product_from_csv_row(row):
                        success_count += 1
                    else:
                        error_count += 1
                        logger.warning(f"Failed to insert row {row_num}: {row.get('Product_name', 'Unknown')}")
                    
                    # Log progress every 50 rows
                    if row_num % 50 == 0:
                        logger.info(f"Processed {row_num} rows...")

            logger.info(f"CSV import completed. Success: {success_count}, Errors: {error_count}")
            return error_count == 0

        except Exception as e:
            logger.error(f"Error importing CSV: {e}")
            return False

    def get_all_products(self) -> List[Dict[str, Any]]:
        """
        Get all products from database.

        Returns:
            List[Dict[str, Any]]: List of products as dictionaries.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("""
                        SELECT p.*, c.category_name 
                        FROM products p 
                        JOIN categories c ON p.id_category = c.id_category
                        ORDER BY p.product_id
                    """)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            return []

    def search_products(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search products by name or description.

        Args:
            query (str): Search query.
            limit (int): Maximum number of results.

        Returns:
            List[Dict[str, Any]]: List of matching products.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("""
                        SELECT p.*, c.category_name 
                        FROM products p 
                        JOIN categories c ON p.id_category = c.id_category
                        WHERE p.product_name ILIKE %s 
                           OR p.description ILIKE %s 
                           OR c.category_name ILIKE %s
                        ORDER BY p.product_id
                        LIMIT %s
                    """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []

    def get_product_count(self) -> int:
        """
        Get total number of products in database.

        Returns:
            int: Number of products.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM products")
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting product count: {e}")
            return 0

    def get_connection(self):
        """Get database connection using the configuration."""
        try:
            connection = psycopg2.connect(**self.config.to_dict())
            # Use cursor_factory instead of row_factory
            connection.cursor_factory = psycopg2.extras.RealDictCursor
            return connection
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {str(e)}")

    def __enter__(self):
        self.connection = self.get_connection()
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'connection'):
            self.connection.close()
