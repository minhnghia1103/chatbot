import streamlit as st
import json
import logging
import time
import psycopg2.extras  # Add this import at the top level

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.tool import ToolMessage

from virtual_sales_agent.graph import graph
from virtual_sales_agent.tools import create_order, update_customer_info, get_customer_info, cancel_order

from setupDatabase.postgresql_manager import PostgreSQLManager

db_manager = PostgreSQLManager()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#---------- Helper Functions ----------#

def parse_json_args(args):
    """Parse JSON args safely with enhanced debugging"""
    logging.info(f"Parsing args type: {type(args)}, content: {args}")
    
    if isinstance(args, dict):
        return args
    
    if isinstance(args, str):
        try:
            # First, try direct JSON parsing
            return json.loads(args)
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            
            # Try to clean the string and parse again
            try:
                # Replace single quotes with double quotes for valid JSON
                cleaned_args = args.replace("'", "\"")
                return json.loads(cleaned_args)
            except json.JSONDecodeError as e2:
                logging.error(f"Second JSON decode attempt failed: {e2}")
                
                # Try to extract JSON portion from string
                try:
                    import re
                    potential_json = re.search(r'\{.*\}', args, re.DOTALL)
                    if potential_json:
                        return json.loads(potential_json.group(0))
                except Exception as e3:
                    logging.error(f"JSON extraction failed: {e3}")
    
    # If we get here, all parsing attempts failed
    return {}

def process_events(event):
    """Process events from the graph and extract messages."""
    seen_ids = set()

    try:
        if isinstance(event, dict):
            if "configurable" in event.get("config", {}):
                logging.info(f"Config in event: {event['config']['configurable']}")
            
            if "messages" in event:
                messages = event["messages"]
                last_message = messages[-1] if messages else None

                if isinstance(last_message, AIMessage):
                    if last_message.id not in seen_ids and last_message.content:
                        seen_ids.add(last_message.id)
                        st.session_state.messages.append(last_message)
                        with st.chat_message("assistant"):
                            st.write(last_message.content)

                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        tool_call = last_message.tool_calls[0]
                        logging.info(f"Tool call detected: {tool_call['name']}")
                        
                        # Parse args if needed
                        if isinstance(tool_call.get('args', {}), str):
                            try:
                                tool_call['args'] = json.loads(tool_call['args'])
                                logging.info(f"Parsed tool call args: {tool_call['args']}")
                            except json.JSONDecodeError as e:
                                logging.error(f"Failed to parse tool call args: {e}")
                        return tool_call
    except Exception as e:
        logging.error(f"Error in process_events: {str(e)}")

    return None


def get_order_by_id(order_id):
    """Get order details by ID"""
    try:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT 
                    o.order_id,
                    o.customer_id,
                    o.order_date,
                    o.status,
                    p.product_name,
                    od.quantity,
                    od.unit_price
                FROM orders o
                LEFT JOIN orders_details od ON o.order_id = od.order_id
                LEFT JOIN products p ON od.product_id = p.product_id
                WHERE o.order_id = %s
            """, (order_id,))
            
            rows = cursor.fetchall()
        
        if not rows:
            return None

        return {
            "order_id": rows[0]["order_id"],
            "customer_id": rows[0]["customer_id"],
            "order_date": rows[0]["order_date"],
            "status": rows[0]["status"],
            "products": [
                {
                    "product_name": row["product_name"],
                    "quantity": row["quantity"],
                    "unit_price": float(row["unit_price"]) if row["unit_price"] else 0
                }
                for row in rows if row["product_name"] is not None
            ]
        }
    except Exception as e:
        logging.error(f"Error fetching order {order_id}: {str(e)}")
        return None


def send_tool_response(tool_call_id, content, config):
    """Send a response for a tool call"""
    try:
        if isinstance(content, dict):
            content = json.dumps(content)
            
        result = graph.invoke(
            {
                "messages": [
                    ToolMessage(
                        tool_call_id=tool_call_id,
                        content=content,
                    )
                ]
            },
            config,
        )
        return result
    except Exception as e:
        logging.error(f"Error sending tool response: {str(e)}")
        raise e


#---------- UI Components ----------#

def customer_profile_form():
    """Display and allow editing of customer information"""
    st.markdown("### 👤 Thông tin cá nhân")
    
    if "customer_id" not in st.session_state or not st.session_state.customer_id:
        st.warning("Vui lòng đăng nhập để xem và cập nhật thông tin cá nhân")
        return
    
    # Fetch current customer information
    try:
        customer_info = get_customer_info.invoke({"customer_id": st.session_state.customer_id})
        
        if "error" in customer_info:
            st.error(f"Không thể tải thông tin khách hàng: {customer_info['error']}")
            return
            
        with st.form(key="profile_form"):
            # Use columns for better layout
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Họ và tên", value=customer_info.get("name", ""))
                phone = st.text_input("Số điện thoại", value=customer_info.get("phone", ""))
            
            with col2:
                email = st.text_input("Email", value=customer_info.get("email", ""), disabled=True,
                                    help="Email không thể thay đổi vì đây là tài khoản đăng nhập của bạn")
                
            address = st.text_area("Địa chỉ giao hàng", value=customer_info.get("address", ""), height=100)
            
            submitted = st.form_submit_button("Cập nhật thông tin", use_container_width=True)
            
            if submitted:
                try:
                    # Call update_customer_info API and save the result
                    update_result = update_customer_info.invoke(
                        {"full_name": name, "address": address, "phone": phone},
                        config=st.session_state.config
                    )
                    
                    if update_result.get("status") == "success":
                        st.success("✅ Thông tin cá nhân đã được cập nhật thành công!")
                    else:
                        st.error(f"❌ Lỗi cập nhật thông tin: {update_result.get('message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"❌ Lỗi: {str(e)}")
    
    except Exception as e:
        st.error(f"Lỗi khi tải thông tin khách hàng: {str(e)}")


def create_order_ui(last_message, tool_call):
    """UI for creating and customizing orders"""
    # Initialize session state for order
    if "adjusted_quantities" not in st.session_state:
        st.session_state.adjusted_quantities = {}
    
    if "customer_info_edited" not in st.session_state:
        st.session_state.customer_info_edited = False
    
    if "shipping_info" not in st.session_state:
        st.session_state.shipping_info = {}
    
    # Debug the incoming tool call
    logging.info(f"create_order_ui received tool_call: {tool_call}")
    
    # Get args with enhanced parsing
    args = tool_call.get("args", {})
    logging.info(f"Raw args from tool_call: {args}")
    
    # Try parsing with our enhanced parser
    parsed_args = parse_json_args(args)
    logging.info(f"Parsed args: {parsed_args}")
    
    # Update tool_call with parsed args
    tool_call["args"] = parsed_args
    
    if not parsed_args:
        st.error("Error: Could not parse order details. Please try again.")
        # Display diagnostic info for developers
        with st.expander("Troubleshooting Info", expanded=False):
            st.code(f"Original args: {args}")
            st.markdown("Please check the logs for more details.")
        return
    
    # Check if products exists in the args
    products = parsed_args.get("products", [])
    if not products:
        st.error("Error: No products found in order details.")
        return
    
    logging.info(f"Found {len(products)} products in the order")
    
    # Process products to ensure they have the required fields
    processed_products = []
    for product in products:
        if isinstance(product, str):
            try:
                product = json.loads(product)
            except json.JSONDecodeError:
                # Try to extract product details from string representation
                try:
                    import re
                    # Extract product_name
                    name_match = re.search(r"product_name['\"]?\s*:\s*['\"](.+?)['\"]", product)
                    # Extract quantity
                    quantity_match = re.search(r"quantity['\"]?\s*:\s*(\d+)", product)
                    
                    if name_match and quantity_match:
                        product = {
                            "product_name": name_match.group(1),
                            "quantity": int(quantity_match.group(1))
                        }
                except Exception as e:
                    logging.error(f"Failed to extract product info from string: {e}")
                    continue
        
        if isinstance(product, dict):
            # Make sure each product has product_id or product_name field
            if "product_id" in product or "product_name" in product:
                # Make sure each product has a quantity field
                if "quantity" not in product:
                    product["quantity"] = 1
                processed_products.append(product)

    if not processed_products:
        st.error("Error: Failed to process product details.")
        return
    
    # Update products in args
    parsed_args["products"] = processed_products

    # Rest of the function remains the same but use parsed_args instead of args
    with st.container():
        # Use tabs to organize the order flow
        tab1, tab2, tab3 = st.tabs(["🛒 Giỏ hàng", "📦 Thông tin giao hàng", "💳 Xác nhận đặt hàng"])
        
        with tab1:
            st.markdown("### 🛒 Giỏ hàng của bạn")
            
            try:
                # Use processed_products here
                products = parsed_args.get("products", [])
                
                if not products:
                    st.warning("Không có sản phẩm nào trong giỏ hàng.")
                    return
                
                # Display product table
                for idx, item in enumerate(products):
                    if isinstance(item, str):
                        try:
                            item = json.loads(item)
                        except:
                            logging.error(f"Failed to parse product item: {item}")
                            continue
                        
                    name = item.get("product_name", f"Sản phẩm {idx+1}")
                    default_qty = max(1, item.get("quantity", 1))
                    unit_price = item.get("unit_price", 0)
                    
                    with st.container():
                        cols = st.columns([3, 1, 1, 1])
                        
                        with cols[0]:
                            st.markdown(f"**{name}**")
                            
                        with cols[1]:
                            key = f"{name}_qty"
                            adjusted_qty = st.number_input(
                                "Số lượng", 
                                min_value=1, 
                                step=1, 
                                value=st.session_state.adjusted_quantities.get(key, default_qty), 
                                key=key
                            )
                            st.session_state.adjusted_quantities[key] = adjusted_qty
                            
                        with cols[2]:
                            st.markdown(f"**{unit_price:,.0f}đ**")
                            
                        with cols[3]:
                            st.markdown(f"**{(unit_price * adjusted_qty):,.0f}đ**")
                
                # Calculate total
                adjusted_total = 0
                for item in products:
                    if isinstance(item, str):
                        try:
                            item = json.loads(item)
                        except:
                            continue
                    
                    name = item.get("product_name", "")
                    key = f"{name}_qty"
                    adjusted_qty = st.session_state.adjusted_quantities.get(key, item.get("quantity", 1))
                    unit_price = item.get("unit_price", 0)
                    adjusted_total += adjusted_qty * unit_price
                
                st.markdown("---")
                st.markdown(f"### Tổng cộng: **{adjusted_total:,.0f}đ**")
                st.info("👉 Nhấn vào tab 'Thông tin giao hàng' để tiếp tục.")
                
            except Exception as e:
                logging.error(f"Error processing products: {str(e)}")
                st.error(f"Error: {str(e)}")
        
        # Tab 2: Shipping Information
        with tab2:
            st.markdown("### 📦 Thông tin giao hàng")
            
            # Get customer info if available
            customer_info = {}
            if "customer_id" in st.session_state and st.session_state.customer_id:
                try:
                    customer_info = get_customer_info.invoke({"customer_id": st.session_state.customer_id})
                    
                    # Initialize shipping info with customer info if not edited yet
                    if not st.session_state.customer_info_edited:
                        st.session_state.shipping_info = {
                            "name": customer_info.get("name", ""),
                            "phone": customer_info.get("phone", ""),
                            "address": customer_info.get("address", "")
                        }
                        st.session_state.customer_info_edited = True
                except Exception as e:
                    logging.error(f"Error fetching customer info: {str(e)}")
            
            # Shipping info form
            with st.form(key="shipping_info_form"):
                st.subheader("Thông tin người nhận")
                
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input(
                        "Họ tên người nhận", 
                        value=st.session_state.shipping_info.get("name", "")
                    )
                
                with col2:
                    phone = st.text_input(
                        "Số điện thoại", 
                        value=st.session_state.shipping_info.get("phone", "")
                    )
                
                address = st.text_area(
                    "Địa chỉ giao hàng", 
                    value=st.session_state.shipping_info.get("address", "")
                )
                
                notes = st.text_area(
                    "Ghi chú cho đơn hàng (Tùy chọn)",
                    value=st.session_state.shipping_info.get("notes", "")
                )
                
                submitted = st.form_submit_button("Cập nhật thông tin giao hàng")
                
                if submitted:
                    st.session_state.shipping_info = {
                        "name": name,
                        "phone": phone,
                        "address": address,
                        "notes": notes
                    }
                    st.success("✅ Đã cập nhật thông tin giao hàng!")
                
            # Validate shipping info
            if not all([
                st.session_state.shipping_info.get("name", ""),
                st.session_state.shipping_info.get("phone", ""),
                st.session_state.shipping_info.get("address", "")
            ]):
                st.warning("⚠️ Vui lòng điền đầy đủ thông tin giao hàng để tiếp tục.")
            else:
                st.info("👉 Nhấn vào tab 'Xác nhận đặt hàng' để hoàn tất.")
        
        # Tab 3: Order Confirmation
        with tab3:
            st.markdown("### 💳 Xác nhận đặt hàng")
            
            # Validate shipping info
            if not all([
                st.session_state.shipping_info.get("name", ""),
                st.session_state.shipping_info.get("phone", ""),
                st.session_state.shipping_info.get("address", "")
            ]):
                st.warning("⚠️ Vui lòng điền đầy đủ thông tin giao hàng ở tab 'Thông tin giao hàng' trước.")
                return
            
            # Show order summary
            st.subheader("Tóm tắt đơn hàng")
            
            # Products summary
            st.markdown("**Sản phẩm:**")
            products_summary = ""
            total = 0
            updated_products = []
            
            for item in args.get("products", []):
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except:
                        continue
                
                name = item.get("product_name", "")
                key = f"{name}_qty"
                adjusted_qty = st.session_state.adjusted_quantities.get(key, item.get("quantity", 1))
                unit_price = item.get("unit_price", 0)
                subtotal = adjusted_qty * unit_price
                total += subtotal
                
                # Add to updated products list for order creation
                updated_products.append({
                    "product_name": name,
                    "quantity": adjusted_qty
                })
                
                products_summary += f"- {name} x {adjusted_qty} = {subtotal:,.0f}đ\n"
            
            st.markdown(products_summary)
            st.markdown(f"**Tổng tiền:** {total:,.0f}đ")
            
            # Delivery info
            st.markdown("**Thông tin giao hàng:**")
            st.markdown(f"""
            - **Người nhận:** {st.session_state.shipping_info.get('name', '')}
            - **Số điện thoại:** {st.session_state.shipping_info.get('phone', '')}
            - **Địa chỉ:** {st.session_state.shipping_info.get('address', '')}
            """)
            
            if st.session_state.shipping_info.get("notes"):
                st.markdown(f"**Ghi chú:** {st.session_state.shipping_info.get('notes')}")
            
            # Action buttons
            st.markdown("### Xác nhận đặt hàng")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("✅ Xác nhận đặt hàng", key="confirm_order", use_container_width=True):
                    with st.spinner("Đang xử lý đơn hàng..."):
                        try:
                            # Update customer info if needed
                            if "customer_id" in st.session_state and st.session_state.customer_id:
                                shipping_info = st.session_state.shipping_info
                                update_customer_info.invoke({
                                    "full_name": shipping_info.get("name", ""),
                                    "phone": shipping_info.get("phone", ""),
                                    "address": shipping_info.get("address", "")
                                }, config=st.session_state.config)
                            
                            # Create the order
                            order_result = create_order.invoke(
                                {"products": updated_products}, 
                                config=st.session_state.config
                            )
                            
                            if order_result.get("status") == "success":
                                st.success(f"""
                                ### ✅ Đơn hàng đã được đặt thành công!
                                
                                **Mã đơn hàng:** {order_result.get('order_id')}
                                **Tổng tiền:** {order_result.get('total_amount'):,.0f}đ
                                
                                Chúng tôi sẽ liên hệ với bạn trong thời gian sớm nhất để xác nhận đơn hàng.
                                Cảm ơn bạn đã mua sắm tại cửa hàng của chúng tôi!
                                """)
                                
                                # Add the success message to chat
                                success_message = f"""
                                ✅ **Đơn hàng đã được đặt thành công!**
                                
                                **Mã đơn hàng:** {order_result.get('order_id')}
                                **Tổng tiền:** {order_result.get('total_amount'):,.0f}đ
                                
                                Chúng tôi sẽ liên hệ với bạn trong thời gian sớm nhất để xác nhận đơn hàng.
                                Cảm ơn bạn đã mua sắm tại cửa hàng của chúng tôi!
                                """
                                success_ai_message = AIMessage(content=success_message)
                                st.session_state.messages.append(success_ai_message)
                                
                                # Clean up session state
                                st.session_state.adjusted_quantities = {}
                                st.session_state.customer_info_edited = False
                                st.session_state.shipping_info = {}
                                st.session_state.pending_approval = None
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"❌ Lỗi tạo đơn hàng: {order_result.get('message', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"❌ Lỗi khi đặt hàng: {str(e)}")
            
            with col2:
                if st.button("❌ Hủy đơn hàng", key="cancel_order", use_container_width=True):
                    try:
                        cancel_message = "Tôi đã hủy đơn hàng theo yêu cầu của bạn. Bạn có thể tiếp tục mua sắm hoặc hỏi tôi về các sản phẩm khác."
                        cancel_ai_message = AIMessage(content=cancel_message)
                        st.session_state.messages.append(cancel_ai_message)
                        st.info("🛑 Đã hủy đơn hàng")
                        st.session_state.pending_approval = None
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Lỗi khi hủy đơn hàng: {str(e)}")


def update_order_ui(last_message, tool_call):
    """UI for updating existing orders"""
    # Parse args
    args = parse_json_args(tool_call.get("args", {}))
    if not args:
        st.error("Error: Could not parse order details. Please try again.")
        return
            
    # Initialize session state
    if "edited_orders" not in st.session_state:
        st.session_state.edited_orders = {}
    
    # Initialize contact info state if needed
    if "contact_info" not in st.session_state:
        st.session_state.contact_info = {}
        
    # Get order ID and data
    order_id = args.get("order_id")
    if not order_id:
        st.error("Order ID not found in request")
        return
            
    order_data = get_order_by_id(order_id)
    if not order_data:
        st.error(f"Order #{order_id} not found")
        return
            
    products = order_data.get("products", [])
    if not products:
        st.warning("This order has no products to update.")
        return

    # UI for editing order
    st.markdown(f"### ✏️ Cập nhật đơn hàng #{order_id}")

    # Get/initialize edited products list
    edited_products = st.session_state.edited_orders.setdefault(order_id, products.copy())
    
    # Create tabs for different sections of the order update
    tab1, tab2, tab3 = st.tabs(["📦 Sản phẩm", "🏠 Thông tin giao hàng", "✅ Xác nhận"])
    
    with tab1:
        # Create order product editing form
        st.markdown("#### Cập nhật sản phẩm trong đơn hàng")
        
        # Table header
        cols = st.columns([3, 2, 1])
        with cols[0]:
            st.markdown("**Tên sản phẩm**")
        with cols[1]:
            st.markdown("**Số lượng**")
        with cols[2]:
            st.markdown("**Giá**")
            
        # Product editor rows
        updated_products = []
        for idx, product in enumerate(edited_products):
            cols = st.columns([3, 2, 1])
            with cols[0]:
                product_name = st.text_input(
                    f"Tên sản phẩm {idx+1}",
                    value=product.get("product_name", ""),
                    key=f"name_{order_id}_{idx}",
                    disabled=True  # Disable product name editing
                )
            with cols[1]:
                quantity = st.number_input(
                    f"Số lượng {idx+1}",
                    min_value=1,
                    value=int(product.get("quantity", 1)),
                    step=1,
                    key=f"qty_{order_id}_{idx}"
                )
            with cols[2]:
                unit_price = float(product.get("unit_price", 0))
                st.text(f"{unit_price:,.0f}đ")
                
            # Add to update list
            updated_products.append({
                "product_name": product_name,
                "quantity": quantity,
                "unit_price": unit_price
            })
            
        # Calculate total
        total = sum(p["quantity"] * p["unit_price"] for p in updated_products)
        st.markdown(f"**Tổng tiền: {total:,.0f}đ**")
        
        # Save products in session state
        st.session_state.edited_orders[order_id] = updated_products
        
        st.info("👉 Chuyển qua tab 'Thông tin giao hàng' để cập nhật địa chỉ và số điện thoại")
    
    with tab2:
        # Get customer info
        try:
            customer_id = st.session_state.config["configurable"].get("customer_id")
            customer_info = get_customer_info.invoke({"customer_id": customer_id})
            
            # Initialize contact info from customer info if not already set
            if order_id not in st.session_state.contact_info:
                st.session_state.contact_info[order_id] = {
                    "name": customer_info.get("name", ""),
                    "phone": customer_info.get("phone", ""),
                    "address": customer_info.get("address", "")
                }
        except Exception as e:
            logging.error(f"Error getting customer info: {str(e)}")
            if order_id not in st.session_state.contact_info:
                st.session_state.contact_info[order_id] = {"name": "", "phone": "", "address": ""}
        
        # Contact info form
        st.markdown("#### Cập nhật thông tin liên hệ và giao hàng")
        
        contact_info = st.session_state.contact_info[order_id]
        
        with st.form(key=f"contact_form_{order_id}"):
            name = st.text_input(
                "Tên người nhận", 
                value=contact_info.get("name", ""),
                key=f"contact_name_{order_id}"
            )
            
            phone = st.text_input(
                "Số điện thoại", 
                value=contact_info.get("phone", ""),
                key=f"contact_phone_{order_id}"
            )
            
            address = st.text_area(
                "Địa chỉ giao hàng",
                value=contact_info.get("address", ""),
                key=f"contact_address_{order_id}"
            )
            
            notes = st.text_area(
                "Ghi chú đơn hàng (tùy chọn)",
                value=contact_info.get("notes", ""),
                key=f"contact_notes_{order_id}"
            )
            
            if st.form_submit_button("Cập nhật thông tin liên hệ", use_container_width=True):
                st.session_state.contact_info[order_id] = {
                    "name": name,
                    "phone": phone,
                    "address": address,
                    "notes": notes
                }
                st.success("✅ Đã cập nhật thông tin liên hệ!")
        
        # Validate contact info
        if all([
            st.session_state.contact_info[order_id].get("name", ""),
            st.session_state.contact_info[order_id].get("phone", ""),
            st.session_state.contact_info[order_id].get("address", "")
        ]):
            st.info("👉 Chuyển qua tab 'Xác nhận' để hoàn tất cập nhật đơn hàng")
        else:
            st.warning("⚠️ Vui lòng điền đầy đủ thông tin liên hệ")
    
    with tab3:
        st.markdown("#### Xác nhận cập nhật đơn hàng")
        
        # Check if we have all required info
        products_updated = order_id in st.session_state.edited_orders
        contact_updated = order_id in st.session_state.contact_info and all([
            st.session_state.contact_info[order_id].get("name", ""),
            st.session_state.contact_info[order_id].get("phone", ""),
            st.session_state.contact_info[order_id].get("address", "")
        ])
        
        if not products_updated or not contact_updated:
            st.warning("⚠️ Vui lòng cập nhật đầy đủ thông tin sản phẩm và thông tin liên hệ trước khi xác nhận")
        else:
            # Show order summary
            st.markdown("**Thông tin đơn hàng sau khi cập nhật:**")
            
            # Products summary
            st.markdown("**Sản phẩm:**")
            for product in st.session_state.edited_orders[order_id]:
                subtotal = product["quantity"] * product["unit_price"]
                st.markdown(f"- {product['product_name']} x {product['quantity']} = {subtotal:,.0f}đ")
            
            # Contact info summary
            contact = st.session_state.contact_info[order_id]
            st.markdown("**Thông tin giao hàng:**")
            st.markdown(f"""
            - **Người nhận:** {contact.get('name', '')}
            - **Số điện thoại:** {contact.get('phone', '')}
            - **Địa chỉ:** {contact.get('address', '')}
            """)
            
            if contact.get("notes"):
                st.markdown(f"**Ghi chú:** {contact.get('notes', '')}")
            
            # Action buttons with more prominence
            st.markdown("### Hành động")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("✅ Xác nhận cập nhật", key=f"confirm_update_{order_id}", use_container_width=True):
                    try:
                        # Update customer contact info
                        update_customer_info.invoke({
                            "full_name": contact.get("name", ""),
                            "address": contact.get("address", ""),
                            "phone": contact.get("phone", "")
                        }, config=st.session_state.config)
                        
                        # Create payload for order update
                        payload = {
                            "order_id": order_id,
                            "updated_products": [
                                {"product_name": p["product_name"], "quantity": p["quantity"]}
                                for p in st.session_state.edited_orders[order_id]
                            ]
                        }
                        
                        # Send order update
                        result = send_tool_response(tool_call["id"], payload, st.session_state.config)
                        
                        st.success("✅ Đơn hàng đã được cập nhật thành công!")
                        process_events(result)
                        
                        # Clean up session state
                        if order_id in st.session_state.edited_orders:
                            del st.session_state.edited_orders[order_id]
                        if order_id in st.session_state.contact_info:
                            del st.session_state.contact_info[order_id]
                        
                        st.session_state.pending_approval = None
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Lỗi khi cập nhật đơn hàng: {str(e)}")
                        logging.error(f"Order update failed: {str(e)}")
            
            with col2:
                if st.button("❌ Hủy", key=f"cancel_update_{order_id}", use_container_width=True):
                    try:
                        # Cancel update
                        result = send_tool_response(
                            tool_call["id"],
                            "Order update cancelled by user.",
                            st.session_state.config
                        )
                        
                        st.info("🛑 Đã hủy cập nhật đơn hàng.")
                        process_events(result)
                        
                        # Clean up session state
                        if order_id in st.session_state.edited_orders:
                            del st.session_state.edited_orders[order_id]
                        if order_id in st.session_state.contact_info:
                            del st.session_state.contact_info[order_id]
                            
                        st.session_state.pending_approval = None
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Lỗi khi hủy cập nhật: {str(e)}")
            
            # Add a section for canceling the entire order
            st.markdown("---")
            st.markdown("### Hủy đơn hàng")
            st.warning("⚠️ Hủy đơn hàng sẽ hủy hoàn toàn đơn hàng này và không thể hoàn tác. Bạn có chắc chắn muốn hủy đơn hàng không?")
            
            if st.button("🚫 Hủy đơn hàng này", key=f"cancel_order_{order_id}", type="primary", use_container_width=True):
                try:
                    # Get the cancel order tool
                    from virtual_sales_agent.tools import cancel_order
                    
                    # Call cancel order tool directly - Convert order_id to string
                    cancel_result = cancel_order.invoke(
                        {"order_id": str(order_id)},  # Convert to string here
                        config=st.session_state.config
                    )
                    
                    if cancel_result.get("status") == "success":
                        st.success("✅ Đơn hàng đã được hủy thành công!")
                        
                        # Add success message to chat
                        success_message = f"""
                        ✅ **Đơn hàng #{order_id} đã được hủy thành công!**
                        
                        Các sản phẩm đã được trả lại kho. Bạn có thể đặt đơn hàng mới bất cứ lúc nào.
                        """
                        success_ai_message = AIMessage(content=success_message)
                        st.session_state.messages.append(success_ai_message)
                        
                        # Clean up session state
                        if order_id in st.session_state.edited_orders:
                            del st.session_state.edited_orders[order_id]
                        if order_id in st.session_state.contact_info:
                            del st.session_state.contact_info[order_id]
                            
                        st.session_state.pending_approval = None
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Lỗi khi hủy đơn hàng: {cancel_result.get('message', 'Unknown error')}")
                        
                except Exception as e:
                    st.error(f"❌ Lỗi khi hủy đơn hàng: {str(e)}")
                    logging.error(f"Order cancellation failed: {str(e)}")


def cancel_order_ui(last_message, tool_call):
    """UI for confirming order cancellation (not deletion)"""
    # Parse args
    args = parse_json_args(tool_call.get("args", {}))
    if not args:
        st.error("Error: Could not parse order details. Please try lại.")
        return

    order_id = args.get("order_id")
    if not order_id:
        st.error("❌ Không tìm thấy mã đơn hàng.")
        return

    try:
        # Get order data
        order_data = get_order_by_id(order_id)
        if not order_data:
            st.error(f"❌ Không tìm thấy đơn hàng #{order_id}")
            return

        # Display order details for confirmation
        st.markdown(f"### 🚫 Xác nhận hủy đơn hàng #{order_id}")

        # Order details
        st.markdown("#### Chi tiết đơn hàng")
        st.markdown(f"**Trạng thái:** {order_data.get('status', 'N/A')}")
        st.markdown(f"**Ngày đặt:** {order_data.get('order_date', 'N/A')}")

        # Products
        st.markdown("**Sản phẩm:**")
        total = 0
        for product in order_data.get("products", []):
            product_name = product.get("product_name", "N/A")
            quantity = product.get("quantity", 0)
            unit_price = product.get("unit_price", 0)
            subtotal = quantity * unit_price
            total += subtotal
            st.markdown(f"- {product_name} x {quantity} = {subtotal:,.0f}đ")

        st.markdown(f"**Tổng tiền:** {total:,.0f}đ")

        # Warning
        st.warning("⚠️ **Cảnh báo:** Hủy đơn hàng sẽ trả lại sản phẩm về kho và không thể hoàn tác.")

        # Action buttons
        col1, col2 = st.columns(2)

        with col1:
            if st.button("✅ Xác nhận hủy", key=f"confirm_cancel_{order_id}", use_container_width=True):
                try:
                    # Gửi ToolMessage để agent thực thi cancel_order
                    result = send_tool_response(
                        tool_call["id"],
                        {"order_id": str(order_id)},
                        st.session_state.config
                    )
                    print(result)
                    st.success(f"✅ Đơn hàng #{order_id} đã được hủy thành công.")
                    process_events(result)
                    st.session_state.pending_approval = None
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Lỗi khi hủy đơn hàng: {str(e)}")
                    logging.error(f"Error cancelling order: {str(e)}")

        with col2:
            if st.button("❌ Không hủy nữa", key=f"cancel_cancel_{order_id}", use_container_width=True):
                try:
                    # Cancel cancellation
                    result = send_tool_response(
                        tool_call["id"],
                        "Order cancellation aborted by user.",
                        st.session_state.config
                    )
                    st.info("🛑 Đã hủy thao tác hủy đơn hàng.")
                    process_events(result)
                    st.session_state.pending_approval = None
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Lỗi khi hủy thao tác: {str(e)}")
                    logging.error(f"Error aborting cancellation: {str(e)}")

    except Exception as e:
        st.error(f"❌ Lỗi khi xử lý yêu cầu: {str(e)}")
        logging.error(f"Error in cancel_order_ui: {str(e)}")