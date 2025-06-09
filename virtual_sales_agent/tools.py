from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
import json
import logging  # Add logging import
import unicodedata
import re

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import psycopg2.extras

from setupDatabase.postgresql_manager import PostgreSQLManager

db_manager = PostgreSQLManager()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add function to check database content
def debug_products_in_db():
    """Debug function to check what products exist in database"""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT product_name FROM products WHERE quantity > 0")
        products = cursor.fetchall()
        logging.info("All products in database:")
        for product in products:
            logging.info(f"  - {repr(product['product_name'])}")  # Use repr to see exact characters
        return products

@tool
def chitchat(message: Optional[str] = None) -> Dict[str, str]:
    """
    Trả lời các câu hỏi chung chung hoặc trò chuyện với người dùng, đặc biệt là các câu chào hỏi như 'xin chào', 'hello', 'hi', 'chào', v.v.
    Sử dụng tool này khi người dùng muốn trò chuyện, hỏi thăm, chào hỏi hoặc hỏi về trợ lý.
    
    Arguments:
        message (Optional[str]): Tin nhắn hoặc câu hỏi của người dùng để có phản hồi phù hợp
    
    Returns:
        Dict[str, str]: Trả lời từ hệ thống phù hợp với ngữ cảnh.

    Xử lý các loại câu hỏi như: chào hỏi, giới thiệu bản thân, hỏi về thời tiết, 
    câu hỏi chung về cửa hàng và dịch vụ.
    """
    if not message:
        return {"response": "Xin chào! Tôi là trợ lý ảo của cửa hàng đồ thủ công mỹ nghệ. Tôi có thể giúp bạn tìm kiếm sản phẩm, tạo đơn hàng và trả lời các câu hỏi. Bạn cần hỗ trợ gì không?"}
    
    message_lower = message.lower()
    
    # Chào hỏi
    if any(greeting in message_lower for greeting in ["xin chào", "hello", "hi", "chào"]):
        return {"response": "Xin chào! Rất vui được gặp bạn. Tôi là trợ lý ảo của cửa hàng đồ thủ công mỹ nghệ. Tôi có thể giúp bạn tìm sản phẩm, đặt hàng hoặc trả lời thắc mắc. Bạn cần hỗ trợ gì hôm nay?"}
    
    # Hỏi về danh tính
    elif any(identity in message_lower for identity in ["bạn là ai", "giới thiệu", "who are you"]):
        return {"response": "Tôi là trợ lý ảo thông minh của cửa hàng đồ thủ công mỹ nghệ. Tôi chuyên hỗ trợ khách hàng tìm kiếm sản phẩm trong các danh mục: thời trang, đồ dùng nhà cửa, đồ chơi/trò chơi, và phụ kiện. Tôi có thể giúp bạn đặt hàng, kiểm tra đơn hàng, và trả lời mọi thắc mắc về sản phẩm."}
    
    # Hỏi về thời tiết
    elif any(weather in message_lower for weather in ["thời tiết", "weather", "trời"]):
        return {"response": "Tôi không thể kiểm tra thời tiết, nhưng tôi có thể giúp bạn tìm những sản phẩm phù hợp với mọi thời tiết! Ví dụ như áo mưa, ô dù, hoặc quần áo mùa hè. Bạn có muốn xem các sản phẩm thời trang không?"}
    
    # Cảm ơn
    elif any(thanks in message_lower for thanks in ["cảm ơn", "thank", "thanks"]):
        return {"response": "Không có gì! Tôi luôn sẵn sàng hỗ trợ bạn. Nếu cần thêm thông tin về sản phẩm hoặc muốn đặt hàng, đừng ngần ngại hỏi nhé!"}
    
    # Tạm biệt
    elif any(goodbye in message_lower for goodbye in ["tạm biệt", "bye", "goodbye", "chào tạm biệt"]):
        return {"response": "Tạm biệt và cảm ơn bạn đã ghé thăm! Hẹn gặp lại bạn sớm. Nếu cần hỗ trợ gì, tôi luôn sẵn sàng giúp đỡ!"}
    
    # Hỏi về cửa hàng
    elif any(shop in message_lower for shop in ["cửa hàng", "shop", "store", "bán gì"]):
        return {"response": "Cửa hàng chúng tôi chuyên bán các đồ thủ công mỹ nghệ chất lượng cao gồm 4 danh mục chính: Thời trang (quần áo, nón, túi xách), Đồ dùng nhà cửa, Đồ chơi/Trò chơi, và Phụ kiện. Bạn muốn xem sản phẩm nào không?"}
    
    # Câu trả lời mặc định cho các câu hỏi khác
    else:
        return {"response": "Tôi hiểu bạn muốn trò chuyện! Tôi chuyên hỗ trợ về các sản phẩm đồ thủ công mỹ nghệ. Bạn có muốn tìm hiểu về sản phẩm nào không? Hoặc cần hỗ trợ gì về đặt hàng và dịch vụ?"}


@tool
def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Tìm kiếm thông tin sản phẩm dựa trên các tiêu chí khác nhau.
    Nếu người dùng chỉ hỏi sản phẩm(query) mà không cung cấp thêm thông tin gì về thể loại thì bạn hãy tự chọn category_name.
    Trả lời chính xác tên, giá, url, url hình ảnh ; không được bịa đặt những thông tin này.
    Nếu không tìm thấy sản phẩm nào phù hợp với tiêu chí tìm kiếm, hãy trả về một danh sách rỗng.

    category_name chỉ gồm bốn loại:
        - thoi-trang: Thời trang gồm áo thun, nón, áo polo, túi, ...
        - do-dung-nha-cua: bao gồm các loại như bản đồ, tranh áp phích, đèn bàn, đồ dùng nhà bếp, ...
        - games-toys: bao gồm các loại trò chơi như cờ vua, cờ tướng, poker, ...
        - phu-kien: bao gồm bao da hộ chiếu, bookmar, móc khóa, bưu thiếp, nam châm, pin gỗ, sổ tay

    Arguments:
        query (Optional[str]): Từ khóa tìm kiếm cho tên sản phẩm hoặc mô tả
        category (Optional[str]): Lọc theo danh mục sản phẩm
        min_price (Optional[float]): Lọc giá tối thiểu
        max_price (Optional[float]): Lọc giá tối đa

    Returns:
        Dict[str, Any]: Kết quả tìm kiếm với sản phẩm và metadata

    Example:
        search_products(query="áo", category="thoi-trang", max_price=500000)
    """
    

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Debug: log all products in database first
        debug_products_in_db()
        
        # Log để debug
        if query:
            logging.info(f"Searching for query: '{query}'")
            logging.info(f"Query repr: {repr(query)}")
        
        # Xây dựng query với logic rõ ràng hơn
        query_parts = ["""
            SELECT p.*, c.category_name 
            FROM products p 
            JOIN categories c ON p.id_category = c.id_category 
            WHERE p.quantity > 0
        """]
        params = []

        # Xử lý điều kiện category trước (ưu tiên cao nhất)
        if category:
            query_parts.append("AND LOWER(c.category_name) = %s")
            params.append(category.lower())

        # Xử lý điều kiện query (tìm kiếm trong tên sản phẩm và mô tả)
        if query:
            search_patterns = []
            search_params = []
            
            # 1. Tìm kiếm chính xác trong tên sản phẩm
            search_patterns.append("LOWER(p.product_name) = %s")
            search_params.append(query.lower())
            
            # 2. Tìm kiếm LIKE trong tên sản phẩm
            search_patterns.append("LOWER(p.product_name) LIKE %s")
            search_params.append(f"%{query.lower()}%")
            
            # 3. Tìm kiếm từng từ trong tên sản phẩm
            words = query.split()
            for word in words:
                if len(word) > 2:
                    search_patterns.append("LOWER(p.product_name) LIKE %s")
                    search_params.append(f"%{word.lower()}%")
            
            # 4. Tìm kiếm trong mô tả
            search_patterns.append("LOWER(p.description) LIKE %s")
            search_params.append(f"%{query.lower()}%")
            
            # Kết hợp tất cả patterns với OR (chỉ trong phạm vi tìm kiếm query)
            query_parts.append(f"AND ({' OR '.join(search_patterns)})")
            params.extend(search_params)

        # Xử lý điều kiện giá
        if min_price is not None and min_price > 0:
            query_parts.append("AND p.price >= %s")
            params.append(min_price)

        if max_price is not None and max_price > 0:
            query_parts.append("AND p.price <= %s")
            params.append(max_price)

        # Thêm ORDER BY để ưu tiên kết quả khớp chính xác hơn
        if query:
            query_parts.append("""
                ORDER BY 
                    CASE WHEN LOWER(p.product_name) = %s THEN 1 
                         WHEN LOWER(p.product_name) LIKE %s THEN 2 
                         WHEN LOWER(p.description) LIKE %s THEN 3
                         ELSE 4 END,
                    p.product_name
            """)
            params.extend([query.lower(), f"%{query.lower()}%", f"%{query.lower()}%"])
        else:
            query_parts.append("ORDER BY p.product_name")

        query_parts.append("LIMIT 2")

        sql_query = " ".join(query_parts)
        logging.info(f"SQL Query: {sql_query}")
        logging.info(f"Parameters: {params}")
        
        try:
            cursor.execute(sql_query, params)
            products = cursor.fetchall()
            logging.info(f"Found {len(products)} products")
            
            # Log tên sản phẩm và category tìm được
            for product in products:
                logging.info(f"Found product: '{product['product_name']}' in category: '{product['category_name']}'")
                
        except Exception as e:
            logging.error(f"Database error: {str(e)}")
            # Fallback query đơn giản hơn
            query_parts_fallback = ["""
                SELECT p.*, c.category_name 
                FROM products p 
                JOIN categories c ON p.id_category = c.id_category 
                WHERE p.quantity > 0
            """]
            params_fallback = []

            if category:
                query_parts_fallback.append("AND LOWER(c.category_name) = %s")
                params_fallback.append(category.lower())

            if query:
                query_parts_fallback.append("AND (LOWER(p.product_name) LIKE %s OR LOWER(p.description) LIKE %s)")
                search_term = f"%{query.lower()}%"
                params_fallback.extend([search_term, search_term])

            if min_price is not None and min_price > 0:
                query_parts_fallback.append("AND p.price >= %s")
                params_fallback.append(min_price)

            if max_price is not None and max_price > 0:
                query_parts_fallback.append("AND p.price <= %s")
                params_fallback.append(max_price)

            query_parts_fallback.append("ORDER BY p.product_name LIMIT 2")
            sql_query_fallback = " ".join(query_parts_fallback)
            
            logging.info(f"Using fallback query: {sql_query_fallback}")
            cursor.execute(sql_query_fallback, params_fallback)
            products = cursor.fetchall()

        # Get available categories for metadata
        cursor.execute(
            """
            SELECT c.category_name, COUNT(*) as count 
            FROM products p
            JOIN categories c ON p.id_category = c.id_category
            WHERE p.quantity > 0 
            GROUP BY c.category_name
        """
        )
        categories = cursor.fetchall()

        # Get price range for metadata
        cursor.execute(
            """
            SELECT 
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price
            FROM products
            WHERE quantity > 0
        """
        )
        price_stats = cursor.fetchone()

        return {
            "status": "success",
            "products": [
                {
                    "product_id": str(product["product_id"]),
                    "url": product.get("url"),
                    "name": product["product_name"],
                    "category": product["category_name"],
                    "description": product["description"],
                    "price": float(product["price"]),
                    "stock": product["quantity"],
                    "image_url": product.get("image_url"),
                    "usage_instructions": product.get("usage_instructions")
                }
                for product in products
            ],
            "metadata": {
                "total_results": len(products),
                "categories": [
                    {"name": cat["category_name"], "product_count": cat["count"]}
                    for cat in categories
                ],
                "price_range": {
                    "min": float(price_stats["min_price"]) if price_stats["min_price"] else 0,
                    "max": float(price_stats["max_price"]) if price_stats["max_price"] else 0,
                    "average": round(float(price_stats["avg_price"]), 2) if price_stats["avg_price"] else 0,
                },
                "search_info": {
                    "query": query,
                    "query_repr": repr(query) if query else None,
                    "normalized_query": query if query else None
                }
            },
        }


@tool
def create_order(
    products: List[Dict[str, Any]], *, config: RunnableConfig
) -> Dict[str, str]:
    """
    Tạo đơn hàng mới cho khách hàng.

     Arguments:
         products (List[Dict[str, Any]]): Danh sách sản phẩm cần mua.

     Returns:
         Dict[str, str]: Chi tiết đơn hàng bao gồm trạng thái và thông báo

     Example:
         create_order([{"product_name": "Áo thun", "quantity": 2}, {"product_name": "Quần jean", "quantity": 1}])
    """

    logging.info("=== CREATE ORDER TOOL CALLED ===")
    logging.info(f"Received products: {products}")
    logging.info(f"Received config: {config}")
    
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)
    
    logging.info(f"Creating order with customer_id: {customer_id}")
    logging.info(f"Products to order: {products}")

    if not customer_id:
        logging.error("Customer ID not found in configuration")
        return {"status": "error", "message": "Không tìm thấy ID khách hàng."}

    with db_manager.get_connection() as conn:
        logging.info("Database connection established")
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("BEGIN")
            logging.info("DB transaction started")

            # Create order
            cursor.execute(
                """INSERT INTO orders (customer_id, order_date, status) 
                   VALUES (%s, %s, %s) RETURNING order_id""",
                (customer_id, datetime.now(), "Pending"),
            )
            result = cursor.fetchone()
            order_id = result["order_id"]
            logging.info(f"Created order with ID: {order_id}")

            total_amount = Decimal("0")
            ordered_products = []

            # Process each product
            for item in products:
                # Chỉ lấy product_name, không lấy ProductName
                product_name = item.get("product_name")
                if not product_name:
                    logging.error(f"Missing product_name in item: {item}")
                    raise ValueError("Thiếu tên sản phẩm (product_name) trong danh sách sản phẩm.")
                quantity = item.get("quantity") or 0

                # Đảm bảo quantity là số nguyên
                try:
                    quantity = int(quantity)
                except Exception:
                    logging.error(f"Invalid quantity for {product_name}: {quantity}")
                    quantity = 0

                logging.info(f"Processing product: {product_name}, quantity: {quantity}")
                
                # Get product details
                cursor.execute(
                    "SELECT product_id, price, quantity FROM products WHERE LOWER(product_name) = LOWER(%s)",
                    (product_name,),
                )
                product = cursor.fetchone()

                if not product:
                    logging.error(f"Product not found: {product_name}")
                    raise ValueError(f"Không tìm thấy sản phẩm: {product_name}")

                if product["quantity"] < quantity:
                    logging.error(f"Insufficient stock for {product_name}: requested {quantity}, available {product['quantity']}")
                    raise ValueError(f"Không đủ hàng cho sản phẩm {product_name}")

                # Add order detail
                cursor.execute(
                    """INSERT INTO orders_details (order_id, product_id, quantity, unit_price) 
                       VALUES (%s, %s, %s, %s)""",
                    (order_id, product["product_id"], quantity, product["price"]),
                )
                logging.info(f"Added order detail for product_id: {product['product_id']}")

                # Update inventory
                cursor.execute(
                    "UPDATE products SET quantity = quantity - %s WHERE product_id = %s",
                    (quantity, product["product_id"]),
                )
                logging.info(f"Updated inventory for product_id: {product['product_id']}")

                total_amount += Decimal(str(product["price"])) * Decimal(str(quantity))
                ordered_products.append(
                    {
                        "name": product_name,
                        "quantity": quantity,
                        "unit_price": float(product["price"]),
                    }
                )

            cursor.execute("COMMIT")
            logging.info("Order transaction committed successfully")
            
            result_data = {
                "order_id": str(order_id),
                "status": "success",
                "message": "Đơn hàng được tạo thành công",
                "total_amount": float(total_amount),
                "products": ordered_products,
                "customer_id": str(customer_id),
            }
            logging.info(f"=== CREATE ORDER SUCCESS: {result_data} ===")
            return result_data

        except Exception as e:
            cursor.execute("ROLLBACK")
            logging.error(f"Error creating order: {str(e)}")
            error_result = {
                "status": "error",
                "message": f"Lỗi tạo đơn hàng: {str(e)}",
                "customer_id": str(customer_id),
            }
            logging.error(f"=== CREATE ORDER ERROR: {error_result} ===")
            return error_result


@tool
def check_order_status(
    order_id: Union[str, None], *, config: RunnableConfig
) -> Dict[str, Union[str, None]]:
    """
    Kiểm tra trạng thái của một đơn hàng cụ thể hoặc tất cả đơn hàng của khách hàng.

    Arguments:
        order_id (Union[str, None]): ID của đơn hàng cần kiểm tra. Nếu None, sẽ trả về tất cả đơn hàng của khách hàng.
    """
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)

    if not customer_id:
        return {"status": "error", "message": "Không tìm thấy ID khách hàng."}

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if order_id:
            # Query specific order
            cursor.execute(
                """
                SELECT 
                    o.order_id,
                    o.order_date,
                    o.status,
                    STRING_AGG(p.product_name || ' (x' || od.quantity || ')', ', ') as products,
                    SUM(od.quantity * od.unit_price) as total_amount
                FROM orders o
                JOIN orders_details od ON o.order_id = od.order_id
                JOIN products p ON od.product_id = p.product_id
                WHERE o.order_id = %s AND o.customer_id = %s
                GROUP BY o.order_id, o.order_date, o.status
            """,
                (order_id, customer_id),
            )

            order = cursor.fetchone()
            if not order:
                return {
                    "status": "error",
                    "message": "Không tìm thấy đơn hàng",
                    "customer_id": str(customer_id),
                    "order_id": str(order_id),
                }

            return {
                "status": "success",
                "order_id": str(order["order_id"]),
                "order_date": order["order_date"].strftime("%Y-%m-%d %H:%M:%S"),
                "order_status": order["status"],
                "products": order["products"],
                "total_amount": float(order["total_amount"]),
                "customer_id": str(customer_id),
            }
        else:
            # Query all customer orders
            cursor.execute(
                """
                SELECT 
                    o.order_id,
                    o.order_date,
                    o.status,
                    COUNT(od.order_detail_id) as item_count,
                    SUM(od.quantity * od.unit_price) as total_amount
                FROM orders o
                JOIN orders_details od ON o.order_id = od.order_id
                WHERE o.customer_id = %s
                GROUP BY o.order_id, o.order_date, o.status
                ORDER BY o.order_date DESC
            """,
                (customer_id,),
            )

            orders = cursor.fetchall()
            return {
                "status": "success",
                "customer_id": str(customer_id),
                "orders": [
                    {
                        "order_id": str(order["order_id"]),
                        "order_date": order["order_date"].strftime("%Y-%m-%d %H:%M:%S"),
                        "status": order["status"],
                        "item_count": order["item_count"],
                        "total_amount": float(order["total_amount"]),
                    }
                    for order in orders
                ],
            }

@tool
def update_order(
    order_id: int, updated_products: List[Dict[str, Any]], *, config: RunnableConfig
) -> Dict[str, Any]:
    """
    Cập nhật sản phẩm và số lượng trong đơn hàng hiện có.

    Arguments:
        order_id (int): ID của đơn hàng cần cập nhật.
        updated_products (List[Dict[str, Any]]): Danh sách sản phẩm mới với tên và số lượng.

    Example:
        update_order(
            123,
            [
                {"product_name": "Áo polo", "quantity": 3},
                {"product_name": "Quần kaki", "quantity": 1}
            ]
        )
    """
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)

    if not customer_id:
        return {"status": "error", "message": "Không tìm thấy ID khách hàng."}

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("BEGIN")

            # Restore previous quantities first
            cursor.execute(
                """
                SELECT od.product_id, od.quantity 
                FROM orders_details od 
                WHERE od.order_id = %s
                """,
                (order_id,)
            )
            previous_items = cursor.fetchall()
            
            for item in previous_items:
                cursor.execute(
                    "UPDATE products SET quantity = quantity + %s WHERE product_id = %s",
                    (item["quantity"], item["product_id"])
                )

            # Delete old order details
            cursor.execute("DELETE FROM orders_details WHERE order_id = %s", (order_id,))

            updated_ordered_products = []
            total_amount = Decimal("0")

            for item in updated_products:
                product_name = item.get("product_name")
                if not product_name:
                    raise ValueError("Thiếu tên sản phẩm trong danh sách sản phẩm.")
                quantity = item.get("quantity") or item.get("Quantity") or 0

                cursor.execute(
                    "SELECT product_id, price, quantity FROM products WHERE LOWER(product_name) = LOWER(%s)",
                    (product_name,),
                )
                product = cursor.fetchone()

                if not product:
                    raise ValueError(f"Không tìm thấy sản phẩm: {product_name}")

                if product["quantity"] < quantity:
                    raise ValueError(f"Không đủ hàng cho sản phẩm {product_name}")

                cursor.execute(
                    """INSERT INTO orders_details (order_id, product_id, quantity, unit_price)
                       VALUES (%s, %s, %s, %s)""",
                    (order_id, product["product_id"], quantity, product["price"]),
                )

                cursor.execute(
                    "UPDATE products SET quantity = quantity - %s WHERE product_id = %s",
                    (quantity, product["product_id"]),
                )

                total_amount += Decimal(str(product["price"])) * Decimal(str(quantity))
                updated_ordered_products.append({
                    "name": product_name,
                    "quantity": quantity,
                    "unit_price": float(product["price"]),
                })

            cursor.execute(
                "UPDATE orders SET status = %s, order_date = %s WHERE order_id = %s",
                ("Updated", datetime.now(), order_id)
            )

            cursor.execute("COMMIT")

            return {
                "order_id": str(order_id),
                "status": "success",
                "message": "Đơn hàng được cập nhật thành công",
                "total_amount": float(total_amount),
                "products": updated_ordered_products,
                "customer_id": str(customer_id),
            }

        except Exception as e:
            cursor.execute("ROLLBACK")
            return {
                "status": "error",
                "message": f"Lỗi cập nhật đơn hàng: {str(e)}",
                "customer_id": str(customer_id),
            }

@tool
def delete_order(
    order_id: str, *, config: RunnableConfig
) -> Dict[str, Union[str, bool]]:
    """
    Xóa đơn hàng theo ID nếu thuộc về khách hàng hiện tại.

    Arguments:
        order_id (str): ID của đơn hàng cần xóa.
    """
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)

    if not customer_id:
        return {"status": "error", "message": "Không tìm thấy ID khách hàng."}

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("BEGIN")

            # Restore product quantities first
            cursor.execute(
                """
                SELECT od.product_id, od.quantity 
                FROM orders_details od 
                WHERE od.order_id = %s
                """,
                (order_id,)
            )
            order_items = cursor.fetchall()
            
            for item in order_items:
                cursor.execute(
                    "UPDATE products SET quantity = quantity + %s WHERE product_id = %s",
                    (item["quantity"], item["product_id"])
                )

            # Check if the order exists and belongs to the customer
            cursor.execute(
                "SELECT 1 FROM orders WHERE order_id = %s AND customer_id = %s",
                (order_id, customer_id),
            )
            if not cursor.fetchone():
                return {
                    "status": "error",
                    "message": "Không tìm thấy đơn hàng hoặc đơn hàng không thuộc về khách hàng này.",
                    "order_id": order_id,
                    "customer_id": str(customer_id),
                }

            # Delete related order details first (foreign key constraint)
            cursor.execute("DELETE FROM orders_details WHERE order_id = %s", (order_id,))
            cursor.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
            cursor.execute("COMMIT")

            return {
                "status": "success",
                "message": f"Đơn hàng {order_id} đã được xóa thành công.",
                "order_id": order_id,
                "customer_id": str(customer_id),
            }

        except Exception as e:
            cursor.execute("ROLLBACK")
            return {
                "status": "error",
                "message": f"Lỗi xóa đơn hàng: {str(e)}",
                "order_id": order_id,
                "customer_id": str(customer_id),
            }

@tool
def register_customer(
    username: str,
    password: str,
    email: str,
    phone: str,
    address: str,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Registers a new customer with username, password, email, phone, and address.

    Arguments:
        username (str): Username of the customer.
        password (str): Password for the account (should be hashed in production).
        email (str): Email address of the customer.
        phone (str): Phone number of the customer.
        address (str): Home address of the customer.

    Returns:
        Dict[str, Any]: Registration result and status.

    Example:
        register_customer(
            username="nguyen_van_a",
            password="secret123",
            email="nguyen@example.com",
            phone="0987654321",
            address="123 Đường Lê Lợi, Quận 1, TP.HCM"
        )
    """
    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute("BEGIN")

            # Check if email already exists
            cursor.execute(
                "SELECT customer_id FROM customers WHERE email = %s",
                (email,)
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError("Email already registered.")

            # Check if phone already exists
            cursor.execute(
                "SELECT customer_id FROM customers WHERE phone = %s",
                (phone,)
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError("Phone number already registered.")

            # Insert new customer
            cursor.execute(
                """
                INSERT INTO customers (username, password, email, phone, address)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING customer_id
                """,
                (username, password, email, phone, address)
            )

            result = cursor.fetchone()
            customer_id = result["customer_id"]
            cursor.execute("COMMIT")

            return {
                "status": "success",
                "message": "Customer registered successfully.",
                "customer_id": str(customer_id),
            }

        except Exception as e:
            cursor.execute("ROLLBACK")
            return {
                "status": "error",
                "message": str(e),
            }

@tool
def login_customer(
    email: str,
    password: str,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Logs in a customer using email and password.

    Arguments:
        email (str): Email of the customer.
        password (str): Password of the customer.

    Returns:
        Dict[str, Any]: Login status and customer details if successful.

    Example:
        login_customer(
            email="nguyen@example.com",
            password="secret123"
        )
    """
    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Fetch customer by email
            cursor.execute(
                "SELECT customer_id, username, password FROM customers WHERE email = %s",
                (email,)
            )
            customer = cursor.fetchone()

            if not customer:
                return {"status": "error", "message": "Customer not found."}

            # Compare password (plain text)
            if password != customer["password"]:
                return {"status": "error", "message": "Incorrect password."}

            return {
                "status": "success",
                "message": "Login successful.",
                "customer_id": str(customer["customer_id"]),
                "username": customer["username"]
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

@tool
def update_customer_info(
    full_name: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,  # Added phone parameter
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Updates customer personal information such as full name, address, and/or phone number.

    Arguments:
        full_name (Optional[str]): New full name of the customer.
        address (Optional[str]): New home address of the customer.
        phone (Optional[str]): New phone number of the customer.
    
    Returns:
        Dict[str, Any]: Update status and message.

    Example:
        update_customer_info(
            full_name="Trần Thị B",
            address="45 Nguyễn Huệ, TP Huế",
            phone="0912345678"
        )
    """
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)

    if not customer_id:
        return {"status": "error", "message": "Customer ID not found in config."}

    fields = []
    values = []

    # Use correct column names that match your database schema
    if full_name:
        fields.append("username = %s")  # Changed from FullName to username
        values.append(full_name)
    if address:
        fields.append("address = %s")  # Changed from Address to address (lowercase)
        values.append(address)
    if phone:
        fields.append("phone = %s")  # Added phone
        values.append(phone)

    if not fields:
        return {"status": "error", "message": "No information provided to update."}

    values.append(customer_id)

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN")
            query = f"UPDATE customers SET {', '.join(fields)} WHERE customer_id = %s"
            cursor.execute(query, tuple(values))
            cursor.execute("COMMIT")

            return {
                "status": "success",
                "message": "Customer information updated successfully."
            }

        except Exception as e:
            cursor.execute("ROLLBACK")
            return {
                "status": "error",
                "message": str(e)
            }

@tool
def cancel_order(
    order_id: str,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Cancels an existing order for the customer, if it is still pending.

    Arguments:
        order_id (str): The ID of the order to cancel.

    Returns:
        Dict[str, Any]: Cancel status and message.

    Example:
        cancel_order(order_id="123")
    """

    print("hello my friend, I am cancel order tool")
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)
    print(f"=== CANCEL ORDER TOOL CALLED ===: ", order_id, customer_id)

    if not customer_id:
        return {"status": "error", "message": "No customer ID configured."}

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            print(f"=== CANCEL ORDER TOOL CALLED ===: ", order_id, customer_id)
            cursor.execute("BEGIN")  # Sửa từ "BEGIN TRANSACTION" thành "BEGIN"

            # Check if order exists and belongs to customer
            cursor.execute(
                """
                SELECT order_id, status FROM orders
                WHERE order_id = %s AND customer_id = %s
                """,
                (order_id, customer_id),
            )
            order = cursor.fetchone()

            if not order:
                raise ValueError("Order not found or does not belong to this customer.")

            if order["status"].lower() != "pending":
                raise ValueError(f"Only pending orders can be cancelled. Current status: {order['status']}")

            # Update order status to Cancelled
            cursor.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                ("Cancelled", order_id),
            )

            # Restore product quantities
            cursor.execute(
                """
                SELECT product_id, quantity FROM orders_details
                WHERE order_id = %s
                """,
                (order_id,),
            )
            order_items = cursor.fetchall()

            for item in order_items:
                cursor.execute(
                    """
                    UPDATE products
                    SET quantity = quantity + %s
                    WHERE product_id = %s
                    """,
                    (item["quantity"], item["product_id"]),
                )

            cursor.execute("COMMIT")
            print(f"=== CANCEL ORDER SUCCESS ===: ", order_id, customer_id)

            return {
                "status": "success",
                "message": "Order cancelled successfully.",
                "order_id": str(order_id),
                "customer_id": str(customer_id),
            }

        except Exception as e:
            cursor.execute("ROLLBACK")
            return {
                "status": "error",
                "message": str(e),
                "order_id": str(order_id),
                "customer_id": str(customer_id),
            }

@tool
def get_order_details(
    order_id: str,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Retrieves full details of a specific order including product list, quantity, price, and status.

    Arguments:
        order_id (str): The ID of the order to retrieve.

    Returns:
        Dict[str, Any]: Order details or error message.

    Example:
        get_order_details(order_id="123")
    """
    configuration = config.get("configurable", {})
    customer_id = configuration.get("customer_id", None)

    if not customer_id:
        return {"status": "error", "message": "No customer ID configured."}

    with db_manager.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Fetch order info
            cursor.execute(
                """
                SELECT order_id, order_date, status
                FROM orders
                WHERE order_id = %s AND customer_id = %s
                """,
                (order_id, customer_id),
            )
            order = cursor.fetchone()

            if not order:
                return {
                    "status": "error",
                    "message": "Order not found.",
                    "order_id": order_id,
                }

            # Fetch order items
            cursor.execute(
                """
                SELECT p.product_name, od.quantity, od.unit_price
                FROM orders_details od
                JOIN products p ON od.product_id = p.product_id
                WHERE od.order_id = %s
                """,
                (order_id,),
            )
            items = cursor.fetchall()

            product_list = []
            total_amount = 0
            for item in items:
                subtotal = float(item["quantity"]) * float(item["unit_price"])
                product_list.append({
                    "product_name": item["product_name"],
                    "quantity": item["quantity"],
                    "unit_price": float(item["unit_price"]),
                    "subtotal": subtotal,
                })
                total_amount += subtotal

            return {
                "status": "success",
                "order_id": str(order["order_id"]),
                "order_date": order["order_date"],
                "order_status": order["status"],
                "products": product_list,
                "total_amount": total_amount,
                "customer_id": str(customer_id),
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "order_id": order_id,
            }

@tool
def get_customer_info(customer_id: str) -> Dict[str, Any]:
    """
    Retrieve customer information including username, phone number, and address.
    
    Args:
        customer_id: The ID of the customer to retrieve information for.
        
    Returns:
        A dictionary containing customer information: name, phone, address, etc.
    """
    try:
        # Connect to the database
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Query to get customer information - use actual column names from your database
        cursor.execute("""
            SELECT username as name, phone, address, email 
            FROM customers 
            WHERE customer_id = %s
        """, (customer_id,))
        
        customer = cursor.fetchone()
        
        if not customer:
            return {"error": "Customer not found"}
        
        # Return customer information
        return {
            "name": customer["name"],
            "phone": customer["phone"],
            "address": customer["address"],
            "email": customer["email"]
        }
        
    except Exception as e:
        logging.error(f"Error getting customer info: {e}")
        return {"error": f"Failed to retrieve customer information: {str(e)}"}

@tool
def save_message_history(
    user_message: str,
    bot_response: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    *,
    config: RunnableConfig
) -> Dict[str, Any]:
    """
    Save a conversation exchange between user and bot to the database.
    
    Arguments:
        user_message (str): The message sent by the user
        bot_response (str): The response from the bot
        tool_calls (Optional[List[Dict[str, Any]]]): Any tool calls that were made
        
    Returns:
        Dict[str, Any]: Status of the save operation
    """
    try:
        configuration = config.get("configurable", {})
        customer_id = configuration.get("customer_id", None)
        
        if not customer_id or customer_id == "123456789":
            # Skip saving for anonymous users or default customer ID
            return {"status": "skipped", "message": "No customer ID or using default ID"}
        
        # First check if the table exists, if not create it
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'conversation_history'
                )
            """)
            table_exists = cursor.fetchone()[0]
            
            # Create the table if it doesn't exist
            if not table_exists:
                logging.info("Creating conversation_history table")
                cursor.execute("""
                    CREATE TABLE conversation_history (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(50),
                        user_message TEXT,
                        bot_response TEXT,
                        tool_calls JSON,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logging.info("conversation_history table created successfully")
            
            timestamp = datetime.now()
            
            # Convert tool_calls to JSON string if present
            tool_calls_json = None
            if tool_calls:
                try:
                    tool_calls_json = json.dumps(tool_calls)
                except Exception as e:
                    logging.error(f"Error serializing tool calls: {e}")
            
            # Save to conversation_history table
            cursor.execute(
                """
                INSERT INTO conversation_history 
                (customer_id, user_message, bot_response, tool_calls, timestamp)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (customer_id, user_message, bot_response, tool_calls_json, timestamp)
            )
            conn.commit()
            
            return {
                "status": "success",
                "message": "Conversation saved successfully",
                "timestamp": timestamp.isoformat()
            }
            
    except Exception as e:
        logging.error(f"Error saving conversation history: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to save conversation: {str(e)}"
        }

@tool
def search_products_by_image(
    image_path: str,
    *,
    config: dict = None
) -> dict:
    """
    Tìm kiếm sản phẩm tương đồng dựa trên ảnh.
    Gửi ảnh đến API search ảnh và trả về danh sách sản phẩm tương đồng.

    Arguments:
        image_path (str): Đường dẫn tới file ảnh trên máy chủ.
        config (dict, optional): Cấu hình bổ sung, ví dụ: timeout, headers.

    Returns:
        dict: Kết quả trả về với các trường 'status', 'message', và 'products'.
    """
    # Kiểm tra file ảnh

    import requests
    import json
    from pathlib import Path
    try:
        image_file = Path(image_path)
        if not image_file.is_file():
            logging.error(f"File not found: {image_path}")
            return {"status": "error", "message": f"File not found: {image_path}", "products": []}
        # Thêm .webp vào danh sách định dạng được hỗ trợ
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        if image_file.suffix.lower() not in supported_formats:
            logging.warning(f"Unsupported file format: {image_path}")
            return {"status": "error", "message": f"Unsupported file format: {image_file.suffix}", "products": []}
    except Exception as e:
        logging.error(f"Error checking file {image_path}: {str(e)}")
        return {"status": "error", "message": f"Error accessing file: {str(e)}", "products": []}

    # Địa chỉ API search ảnh
    api_url = "https://8267-34-169-57-82.ngrok-free.app/search"

    # Cấu hình mặc định
    default_config = {
        "timeout": 10,  # Timeout 10 giây
        "headers": {
            'Accept': 'application/json; charset=utf-8',
            'Accept-Encoding': 'utf-8'
        }
    }
    if config:
        default_config.update(config)

    # Gửi yêu cầu tới API
    try:
        with open(image_path, 'rb') as f:
            files = {'image': f}
            logging.info(f"Sending image {image_path} to API: {api_url}")
            response = requests.post(api_url, files=files, headers=default_config["headers"], timeout=default_config["timeout"])
        
        # Kiểm tra mã trạng thái
        if response.status_code != 200:
            logging.error(f"API request failed with status {response.status_code}: {response.text[:500]}")
            return {
                "status": "error",
                "message": f"API request failed with status {response.status_code}",
                "products": []
            }

        # Phân tích JSON
        response.encoding = response.apparent_encoding or 'utf-8'
        raw_results = response.json()
        logging.info(f"Successfully parsed JSON, found {len(raw_results)} products")

        # Xử lý kết quả
        processed_products: List[Dict] = []
        for product in raw_results:
            try:
                processed_product = {
                    "product_name": str(product.get("product_name", "Sản phẩm không tên")),
                    "category": str(product.get("category", "unknown")),
                    "description": str(product.get("description", "")),
                    "price": sanitize_price(product.get("price", "0")),
                    "link_url": str(product.get("link_url", "")),
                    "image_url": str(product.get("image_url", "")),
                }
                processed_products.append(processed_product)
            except Exception as e:
                logging.warning(f"Error processing product {product.get('name', 'unknown')}: {str(e)}")
                continue

        return {
            "status": "success",
            "message": f"Found {len(processed_products)} products",
            "products": processed_products
        }

    except requests.RequestException as e:
        logging.error(f"API request error: {str(e)}")
        return {"status": "error", "message": f"API request failed: {str(e)}", "products": []}
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {str(e)}")
        logging.error(f"Response content: {response.text[:500]}...")
        return {"status": "error", "message": "Error decoding API response", "products": []}
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "products": []}

# Helper function to convert price strings to float
def sanitize_price(price_str) -> float:
    """
    Chuyển đổi chuỗi giá thành số float, xử lý các định dạng khác nhau.
    
    Args:
        price_str: Chuỗi giá (ví dụ: '4.880.000', '4,880', '4.880,00')
    
    Returns:
        float: Giá đã được chuyển đổi, hoặc 0.0 nếu lỗi.
    """
    if not price_str or not isinstance(price_str, str):
        logging.warning(f"Invalid price string: {price_str}")
        return 0.0
    
    try:
        # Loại bỏ ký tự không phải số, trừ dấu chấm và phẩy
        clean_price = re.sub(r'[^\d.,]', '', price_str)
        
        # Xử lý các trường hợp
        if clean_price.count('.') > 1:  # Ví dụ: '4.880.000' -> '4880000'
            clean_price = clean_price.replace('.', '')
        elif clean_price.count(',') == 1 and clean_price.count('.') == 0:  # Ví dụ: '4,880' -> '4.880'
            clean_price = clean_price.replace(',', '.')
        elif clean_price.count('.') > 0 and clean_price.count(',') > 0:  # Ví dụ: '4.880,00' -> '4880.00'
            clean_price = clean_price.replace('.', '').replace(',', '.')
        
        return float(clean_price)
    except Exception as e:
        logging.error(f"Error converting price '{price_str}' to float: {str(e)}")
        return 0.0

