import logging
from setupDatabase.postgresql_manager import PostgreSQLManager

def test_database_connection():
    """Test database connection and verify tables."""
    logging.info("Testing database connection...")
    db_manager = PostgreSQLManager()
    
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Test orders table
            cursor.execute("SELECT COUNT(*) FROM orders")
            orders_count = cursor.fetchone()[0]
            logging.info(f"Found {orders_count} orders in database")
            
            # Test customers table
            cursor.execute("SELECT COUNT(*) FROM customers")
            customers_count = cursor.fetchone()[0]
            logging.info(f"Found {customers_count} customers in database")
            
            # Test products table
            cursor.execute("SELECT COUNT(*) FROM products")
            products_count = cursor.fetchone()[0]
            logging.info(f"Found {products_count} products in database")
            
            logging.info("Database connection test successful")
            return True
    except Exception as e:
        logging.error(f"Database connection test failed: {str(e)}")
        return False

def list_recent_orders(limit=5):
    """List recent orders from the database for debugging."""
    logging.info(f"Listing {limit} most recent orders...")
    db_manager = PostgreSQLManager()
    
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT o.order_id, o.customer_id, o.order_date, o.status, 
                       COUNT(od.order_detail_id) as product_count
                FROM orders o
                LEFT JOIN orders_details od ON o.order_id = od.order_id
                GROUP BY o.order_id, o.customer_id, o.order_date, o.status
                ORDER BY o.order_date DESC
                LIMIT %s
            """, (limit,))
            
            orders = cursor.fetchall()
            
            for order in orders:
                logging.info(f"Order ID: {order[0]}, Customer: {order[1]}, Date: {order[2]}, Status: {order[3]}, Products: {order[4]}")
            
            return orders
    except Exception as e:
        logging.error(f"Error listing recent orders: {str(e)}")
        return []

def verify_customer_session(customer_id):
    """Verify if a customer exists in the database."""
    logging.info(f"Verifying customer ID: {customer_id}")
    db_manager = PostgreSQLManager()
    
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, email FROM customers WHERE customer_id = %s", (customer_id,))
            customer = cursor.fetchone()
            
            if customer:
                logging.info(f"Customer found: {customer[0]} ({customer[1]})")
                return True
            else:
                logging.warning(f"Customer ID {customer_id} not found in database")
                return False
    except Exception as e:
        logging.error(f"Error verifying customer: {str(e)}")
        return False
