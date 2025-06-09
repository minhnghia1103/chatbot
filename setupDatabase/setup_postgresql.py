from postgresql_manager import PostgreSQLManager, logger
from postgresql_config import DEFAULT_POSTGRESQL_CONFIG


def main():
    """Main function to set up PostgreSQL database and import CSV data."""
    logger.info("Starting PostgreSQL database setup...")

    # Initialize database manager
    db_manager = PostgreSQLManager(DEFAULT_POSTGRESQL_CONFIG)

    # Create database and schema
    if not db_manager.create_database():
        logger.error("Failed to create database or execute schema")
        return False

    logger.info("Database and schema created successfully")

    # Import data from CSV
    if db_manager.config.csv_path:
        logger.info(f"Importing data from CSV: {db_manager.config.csv_path}")
        if not db_manager.import_products_from_csv():
            logger.error("Failed to import products from CSV")
            return False
        
        # Show import results
        product_count = db_manager.get_product_count()
        logger.info(f"Successfully imported {product_count} products")
        
        # Show some sample products
        sample_products = db_manager.get_all_products()[:5]
        logger.info("Sample products:")
        for product in sample_products:
            logger.info(f"- {product['product_name']} (Category: {product['category_name']}, Price: {product['price']})")

    logger.info("PostgreSQL database setup completed successfully")
    return True


if __name__ == "__main__":
    main()
