import json
import uuid
import logging  # Add missing logging import

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.tool import ToolMessage
from virtual_sales_agent.tools import (
    login_customer,
    register_customer,
    search_products_by_image,  # Thêm import tool search ảnh
    search_products,           # Import tool search text
)
import tempfile
import os

from virtual_sales_agent.graph import graph
from virtual_sales_agent.ui import (
    create_order_ui,
    update_order_ui,
    cancel_order_ui,
    customer_profile_form,
    send_tool_response,
    process_events
)

def set_page_config():
    st.set_page_config(
        page_title="Virtual Sales Agent Chat",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def set_page_style():
    st.markdown(
        f"""
        <style>
        {open("assets/style.css").read()}
        
        /* Improved fixed chat input styles */
        .fixed-chat-input {{
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            right: 0 !important;
            background-color: #ffffff !important;
            padding: 15px 60px 15px 60px !important;
            z-index: 9999 !important;
            border-top: 1px solid #ddd !important;
            box-shadow: 0px -5px 15px rgba(0,0,0,0.08) !important;
            margin: 0 !important;
            min-height: 80px !important;
        }}
        
        /* Chat input positioning - fixed at bottom */
        .stChatInput {{
            position: fixed !important;
            bottom: 0 !important;
            left: 270px !important;
            right: 20px !important;
            z-index: 10000 !important;
            background: white !important;
        }}
        
        /* Keep chat input container styled properly */
        .stChatInput > div {{
            padding-bottom: 10px !important;
        }}
        
        /* Move streamlit branding out of the way */
        .reportview-container .main footer {{
            position: relative !important;
        }}
        
        /* Ensure main container has padding to account for fixed input */
        .main .block-container {{
            padding-bottom: 100px !important;
        }}
        
        /* Make chat messages area scrollable but not extending behind input */
        .chat-history {{
            height: calc(100vh - 220px) !important;
            overflow-y: auto !important;
            padding-bottom: 90px !important;
            margin-bottom: 20px !important;
        }}
        
        /* Hide Streamlit's default footer */
        footer {{
            display: none !important;
        }}
        
        /* Ensure tabs display above fixed input */
        .stTabs {{
            z-index: 1 !important;
        }}
        </style>
    """,
        unsafe_allow_html=True,
    )


def initialize_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())

    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

    if "config" not in st.session_state:
        st.session_state.config = {
            "configurable": {
                "customer_id": "123456789",  # Default value, sẽ được cập nhật khi đăng nhập
                "thread_id": st.session_state.thread_id,
            }
        }


def setup_sidebar():
    """Configure the sidebar with agent information and controls."""
    with st.sidebar:
        st.markdown(
            """
            <div class="agent-profile">
                <div class="profile-header">
                    <div class="avatar">🤖</div>
                    <h1>Trợ lý bán hàng ảo</h1>
                </div>
                <div class="feature-list">
                    <div class="feature-item">
                        <span class="icon">🛒</span>
                        <span>Duyệt sản phẩm có sẵn</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">📦</span>
                        <span>Đặt hàng</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">🚚</span>
                        <span>Theo dõi đơn hàng</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">🎯</span>
                        <span>Nhận gợi ý cá nhân hóa</span>
                    </div>
                </div>
                <div class="status-card">
                    <div class="status-indicator"></div>
                    <span>Sẵn sàng hỗ trợ</span>
                </div>
            </div>
        """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        if st.button("🔄 Bắt đầu cuộc trò chuyện mới", use_container_width=True):
            # Chỉ xóa messages trong session, không xóa lịch sử database
            if "messages" in st.session_state:
                del st.session_state["messages"]
            st.rerun()

        if st.button("🔍 Xem sơ đồ làm việc", use_container_width=True):
            st.image("assets/graph.png")

        st.markdown(
            """
            <div class="sidebar-footer">
                <div class="powered-by">
                    Được tăng cường bởi AI • Được tạo cho bạn
                </div>
            </div>
        """,
            unsafe_allow_html=True,
        )


def display_chat_history():
    """Display the chat history."""
    if not st.session_state.messages:
        st.markdown(
            """
            <div style='text-align: center; padding: 30px;'>
                <h1>👋 Xin chào!</h1>
                <p>Tôi có thể giúp gì cho bạn hôm nay?</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.write(message.content)
            
def process_events(event):
    """Process events from the graph and extract messages."""
    seen_ids = set()

    try:
        if isinstance(event, dict) and "messages" in event:
            messages = event["messages"]
            last_message = messages[-1] if messages else None

            if isinstance(last_message, AIMessage):
                if last_message.id not in seen_ids and last_message.content:
                    seen_ids.add(last_message.id)
                    st.session_state.messages.append(last_message)
                    with st.chat_message("assistant"):
                        st.write(last_message.content)

                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    # Ensure tool_calls[0] is a dict and has required fields
                    tool_call = last_message.tool_calls[0]
                    if isinstance(tool_call, dict):
                        # Initialize args as empty dict if missing
                        if "args" not in tool_call or tool_call["args"] is None:
                            tool_call["args"] = {}
                            logging.warning(f"Empty args for tool {tool_call.get('name', 'unknown')}. Using empty dict.")
                        return tool_call
                    else:
                        logging.error(f"Invalid tool_call format: {type(tool_call)}")
    except Exception as e:
        logging.error(f"Error in process_events: {str(e)}")

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

def handle_tool_approval(snapshot, event):
    """Handle tool approval process."""
    st.write("⚠️ Trợ lý muốn thực hiện một hành động. Bạn có đồng ý không?")

    # Fix for accessing messages - properly handle the snapshot structure
    if isinstance(snapshot, dict) and "messages" in snapshot:
        messages = snapshot.get("messages", [])
        if messages:
            last_message = messages[-1]
            # print(f"Last message: {last_message}")
        else:
            st.error("No messages found in snapshot")
            return
    else:
        st.error("Invalid snapshot format")
        return

    if (
        isinstance(last_message, AIMessage)
        and hasattr(last_message, "tool_calls")
        and last_message.tool_calls
    ):
        tool_call = last_message.tool_calls[0]
        # print(f"Tool call: {tool_call}")
        
        # Add better validation for tool calls
        if not isinstance(tool_call, dict):
            st.error(f"Invalid tool call format: {type(tool_call)}")
            logging.error(f"Invalid tool call format: {type(tool_call)}")
            return
            
        # Ensure args exists and is at least an empty dict
        if "args" not in tool_call or tool_call["args"] is None:
            tool_call["args"] = {}
            logging.warning(f"No arguments provided for tool {tool_call.get('name', 'unknown')}. Using empty dict.")
        
        # Hiển thị thông tin tool được sử dụng
        tool_name = tool_call.get("name", "Unknown Tool")
        st.info(f"🔧 Tool được sử dụng: **{tool_name}**")
        
        # Log tool call information for debugging
        logging.info(f"Processing tool call: {tool_name} with args: {tool_call.get('args', {})}")
        
        if tool_name == "create_order":
            create_order_ui(last_message, tool_call)
        elif tool_name == "update_order":
            update_order_ui(last_message, tool_call)
        # elif tool_name == "delete_order":
        #     delete_order_ui(last_message, tool_call)
        elif tool_name == "cancel_order":
            # Use the delete_order_ui for cancel_order as they share similar functionality
            cancel_order_ui(last_message, tool_call)
        else:
            # Handle any other tool calls generically
            try:
                # For any other tool call, send a generic response
                result = send_tool_response(
                    tool_call["id"],
                    {"status": "success", "message": "Action approved by user"},
                    st.session_state.config
                )
                st.success(f"✅ {tool_name} executed successfully.")
                process_events(result)
                st.session_state.pending_approval = None
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error processing {tool_name}: {str(e)}")
                logging.error(f"Error processing tool call: {str(e)}")
    else:
        st.error("No valid tool call found in message")
        logging.error("No valid tool call found in message")

def main():
    set_page_config()
    set_page_style()
    initialize_session_state()
    
    # Kiểm tra trạng thái đăng nhập trước khi hiển thị bất cứ gì
    if "is_logged_in" not in st.session_state or not st.session_state.is_logged_in:
        # Nếu chưa đăng nhập, hiển thị trang đăng nhập/đăng ký
        handle_authentication()
    else:
        # Nếu đã đăng nhập, hiển thị giao diện chat
        setup_sidebar()
        display_chat_interface()

def handle_authentication():
    """Xử lý giao diện đăng nhập và đăng ký"""
    # Không hiển thị sidebar khi chưa đăng nhập
    st.markdown(
        """
        <div style='text-align: center; padding: 50px;'>
            <h1>🤖 Virtual Sales Agent</h1>
            <p>Vui lòng đăng nhập để tiếp tục</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    if "show_register" not in st.session_state:
        st.session_state.show_register = False
    
    if not st.session_state.show_register:
        # Hiển thị giao diện đăng nhập
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.subheader("Đăng nhập")
                
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Mật khẩu", type="password", key="login_password")
                
                col_login, col_register = st.columns(2)
                
                with col_login:
                    if st.button("Đăng nhập", key="login_button", use_container_width=True):
                        if email and password:
                            try:
                                login_result = login_customer.invoke({
                                    "email": email,
                                    "password": password
                                })
                                
                                if isinstance(login_result, dict) and login_result.get("status") == "success":
                                    st.success(f"Chào mừng lại, {login_result.get('username', 'Khách hàng')}!")
                                    st.session_state.is_logged_in = True
                                    st.session_state.customer_id = login_result["customer_id"]
                                    st.session_state.username = login_result["username"]
                                    # Cập nhật config với customer_id thực
                                    st.session_state.config["configurable"]["customer_id"] = login_result["customer_id"]
                                    st.rerun()
                                else:
                                    error_msg = login_result.get("message", "Đăng nhập thất bại") if isinstance(login_result, dict) else str(login_result)
                                    st.error(f"Lỗi: {error_msg}")
                            except Exception as e:
                                st.error(f"Lỗi đăng nhập: {str(e)}")
                        else:
                            st.error("Vui lòng nhập đầy đủ thông tin!")
                
                with col_register:
                    if st.button("Chưa có tài khoản? Đăng ký", key="show_register_button", use_container_width=True):
                        st.session_state.show_register = True
                        st.rerun()
    else:
        # Hiển thị giao diện đăng ký
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.subheader("Đăng ký tài khoản mới")
                
                username = st.text_input("Tên đăng nhập", key="register_username")
                email = st.text_input("Email", key="register_email")
                phone = st.text_input("Số điện thoại", key="register_phone")
                password = st.text_input("Mật khẩu", type="password", key="register_password")
                address = st.text_area("Địa chỉ", key="register_address")
                
                col_register, col_back = st.columns(2)
                
                with col_register:
                    if st.button("Đăng ký", key="register_button", use_container_width=True):
                        if username and email and phone and password and address:
                            try:
                                register_result = register_customer.invoke({
                                    "username": username,
                                    "email": email,
                                    "phone": phone,
                                    "password": password,
                                    "address": address
                                })
                                
                                if isinstance(register_result, dict) and register_result.get("status") == "success":
                                    st.success("Đăng ký thành công! Vui lòng đăng nhập.")
                                    st.session_state.show_register = False
                                    st.rerun()
                                else:
                                    error_msg = register_result.get("message", "Đăng ký thất bại") if isinstance(register_result, dict) else str(register_result)
                                    st.error(f"Lỗi: {error_msg}")
                            except Exception as e:
                                st.error(f"Lỗi đăng ký: {str(e)}")
                        else:
                            st.error("Vui lòng điền đầy đủ tất cả thông tin!")
                
                with col_back:
                    if st.button("Quay lại đăng nhập", key="back_to_login_button", use_container_width=True):
                        st.session_state.show_register = False
                        st.rerun()

def display_chat_interface():
    """Hiển thị giao diện chat chính"""
    # Hiển thị thông tin người dùng và tabs cho các chức năng
    with st.container():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Xin chào, {st.session_state.get('username', 'Khách hàng')}!**")
        with col2:
            if st.button("🚪 Đăng xuất", key="logout_button"):
                # Xóa tất cả thông tin đăng nhập
                for key in ['is_logged_in', 'customer_id', 'username', 'show_register']:
                    if key in st.session_state:
                        del st.session_state[key]
                # Reset config về customer_id mặc định
                st.session_state.config["configurable"]["customer_id"] = "123456789"
                st.rerun()
    
    # Tạo tabs cho các chức năng khác nhau (chỉ còn 2 tab)
    tab1, tab2 = st.tabs(["💬 Chat", "👤 Thông tin cá nhân"])
    
    with tab1:
        # Thêm phần tìm kiếm ảnh nổi bật phía trên chat history
        with st.container():
            st.markdown("""
                <div style="background-color: #f8f9fa; padding: 10px; border-radius: 8px; margin-bottom: 15px;">
                    <h3>🔍 Tìm sản phẩm bằng hình ảnh</h3>
                    <p>Tải lên hình ảnh sản phẩm bạn muốn tìm</p>
                </div>
            """, unsafe_allow_html=True)
            
            uploaded_file = st.file_uploader("Tải lên hình ảnh sản phẩm", type=["jpg", "jpeg", "png", "webp"], 
                                            key="search_image_file_prominent", 
                                            help="Hỗ trợ định dạng: JPG, PNG, WEBP")
            
            if uploaded_file is not None:
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.image(uploaded_file, width=150, caption="Hình ảnh đã tải lên")
                with col2:
                    search_query = st.text_input("Thêm từ khóa mô tả (không bắt buộc)", key="image_search_query")
                    if st.button("🔍 Tìm kiếm sản phẩm", key="search_button"):
                        # Xử lý tìm kiếm ảnh
                        with st.spinner("Đang xử lý hình ảnh..."):
                            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[-1]) as tmp_file:
                                tmp_file.write(uploaded_file.read())
                                tmp_path = tmp_file.name
                            
                            tool_result = search_products_by_image.invoke({
                                "image_path": tmp_path
                            }, st.session_state.config)
                            os.remove(tmp_path)
                            # print("1111111111111111111111111111111: ", tool_result)
                            
                            if tool_result.get("status") == "success":
                                user_msg = "Tìm kiếm sản phẩm bằng ảnh"
                                if search_query and search_query.strip():
                                    user_msg += f" và từ khóa: {search_query.strip()}"
                                
                                messages = [
                                    HumanMessage(content=user_msg),
                                    AIMessage(content=json.dumps(tool_result["products"]))
                                ]
                                
                                with st.chat_message("user"):
                                    st.write(user_msg)
                                
                                with st.spinner("Đang xử lý kết quả với AI..."):
                                    events = list(
                                        graph.stream(
                                            {"messages": messages},
                                            st.session_state.config,
                                            stream_mode="values",
                                        )
                                    )
                                    last_event = events[-1]
                                    if isinstance(last_event, dict) and "messages" in last_event:
                                        ai_msg = last_event["messages"][-1]
                                        with st.chat_message("assistant"):
                                            st.write(ai_msg.content)
                                        st.session_state.messages.append(HumanMessage(content=user_msg))
                                        st.session_state.messages.append(ai_msg)
                                    else:
                                        st.write(tool_result["products"])
                            else:
                                st.error(tool_result.get("message", "Lỗi không xác định"))
        
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        st.markdown('<div class="chat-history">', unsafe_allow_html=True)
        display_chat_history()
        if st.session_state.pending_approval:
            handle_tool_approval(*st.session_state.pending_approval)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab2:
        customer_profile_form()
    
    # Giữ lại phần chat input nhưng chỉ cho phép văn bản (di chuyển phần upload ảnh lên trên)
    st.markdown('<div class="stChatInput">', unsafe_allow_html=True)
    prompt = st.chat_input("Bạn muốn mua gì hôm nay? / What would you like to order today?")

    if prompt and prompt.strip():
        # Add user message to state
        human_message = HumanMessage(content=prompt.strip())
        st.session_state.messages.append(human_message)
        
        # Display user message
        with st.chat_message("user"):
            st.write(prompt.strip())
        
        # Process with graph
        with st.spinner("Đang xử lý..."):
            try:
                # Stream response from agent
                events = list(
                    graph.stream(
                        {"messages": st.session_state.messages},
                        st.session_state.config,
                        stream_mode="values",
                    )
                )
                
                # Get latest snapshot
                snapshot = events[-1] if events else None
                
                # Check if we need to handle a tool approval
                if snapshot and "messages" in snapshot:
                    last_message = snapshot["messages"][-1]
                    
                    # Check if we need to handle pending approval for sensitive tools
                    if (
                        isinstance(last_message, AIMessage) 
                        and hasattr(last_message, "tool_calls") 
                        and last_message.tool_calls
                        and isinstance(last_message.tool_calls[0], dict)
                        and last_message.tool_calls[0].get("name") in ["create_order", "update_order", "cancel_order", "delete_order", "update_customer_info"]
                    ):
                        # Store pending approval in session state
                        st.session_state.pending_approval = (snapshot, events)
                        st.rerun()
                    else:
                        # For regular messages or safe tools, process events
                        tool_call = process_events(snapshot)
                        if tool_call:
                            # Handle any returned tool calls
                            st.session_state.pending_approval = (snapshot, events)
                            st.rerun()
            except Exception as e:
                logging.error(f"Error processing chat: {str(e)}")
                st.error(f"Đã xảy ra lỗi: {str(e)}")
                # Still append the user's message even if there was an error
                with st.chat_message("assistant"):
                    st.write("Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại.")
    st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
