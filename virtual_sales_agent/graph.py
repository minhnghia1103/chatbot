import os
from datetime import datetime
from typing import Annotated
import json

from dotenv import load_dotenv
from google.cloud import aiplatform
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_google_vertexai import ChatVertexAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langgraph.prebuilt import tools_condition
from typing_extensions import TypedDict
from langchain_together import ChatTogether
from langchain_openai import ChatOpenAI

from virtual_sales_agent.tools import (
    check_order_status,
    create_order,
    # get_available_categories,
    search_products,
    # search_products_recommendations,
    update_order,
    cancel_order,
    # delete_order,
    register_customer,
    login_customer,
    update_customer_info,
    save_message_history,
    chitchat,
    get_customer_info,  # Add this new tool to get customer information
    search_products_by_image
)
from virtual_sales_agent.utils import create_tool_node_with_fallback

load_dotenv()

os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGCHAIN_ENDPOINT")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT")
os.environ["TOGETHER_API_KEY"] = os.getenv("TOGETHER_API_KEY")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str
    verified_product: dict  # Để lưu thông tin sản phẩm đã được xác minh


class Assistant:
    def __init__(self, runnable: Runnable):
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        while True:
            configuration = config.get("configurable", {})
            customer_id = configuration.get("customer_id", None)

            # Lấy 5 đoạn hội thoại gần nhất từ state["messages"]
            conversation_history = ""
            messages = state.get("messages", [])
            if messages:
                # Lấy 5 cặp user-bot gần nhất (nếu có)
                history_parts = []
                count = 0
                for msg in reversed(messages):
                    if hasattr(msg, 'type') and msg.type == "human":
                        history_parts.append(f"User: {msg.content}")
                        count += 1
                    elif hasattr(msg, 'type') and msg.type == "ai":
                        history_parts.append(f"Bot: {msg.content}")
                    if count >= 5:
                        break
                conversation_history = "\n".join(reversed(history_parts))

            state_with_context = {
                **state, 
                "user_info": customer_id,
                "conversation_history": conversation_history
            }

            result = self.runnable.invoke(state_with_context)

            # Lưu tin nhắn vào database sau khi có phản hồi (bao gồm tool calls)
            if customer_id and customer_id != "123456789":
                try:
                    # Lấy tin nhắn cuối cùng của user
                    last_user_message = ""
                    for msg in reversed(state["messages"]):
                        if hasattr(msg, 'type') and msg.type == "human":
                            last_user_message = msg.content
                            break

                    if last_user_message:
                        # Thu thập tool calls nếu có
                        tool_calls = None
                        if hasattr(result, 'tool_calls') and result.tool_calls:
                            tool_calls = [
                                {
                                    "name": tool_call.get("name", ""),
                                    "args": json.dumps(tool_call.get("args", {})) if isinstance(tool_call.get("args"), dict) else tool_call.get("args", "{}"),
                                    "id": tool_call.get("id", "")
                                }
                                for tool_call in result.tool_calls
                            ]

                        # Add better error handling for save_message_history
                        try:
                            save_message_history.invoke({
                                "user_message": last_user_message,
                                "bot_response": result.content or "Tool call executed",
                                "tool_calls": tool_calls,
                                "customer_id": customer_id  # Explicitly pass customer_id
                            }, config)
                        except Exception as e:
                            import logging
                            logging.error(f"Error saving conversation history: {str(e)}")
                except Exception as e:
                    import logging
                    logging.error(f"Error preparing message history: {str(e)}")

            # If the LLM happens to return an empty response, we will re-prompt it
            # for an actual response.
            if not result.tool_calls and (
                not result.content
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                messages = state["messages"] + [("user", "Respond with a real output.")]
                state = {**state, "messages": messages}
            else:
                break
        return {"messages": result}


llm = ChatOpenAI(model="gpt-4o-mini")

assistant_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Bạn là một trợ lý bán hàng ảo thân thiện cho cửa hàng trực tuyến của chúng tôi. Mục tiêu của bạn là cung cấp dịch vụ khách hàng xuất sắc bằng cách giúp khách hàng tìm sản phẩm, mua hàng và theo dõi đơn hàng.

Sử dụng các công cụ được cung cấp để:
- Trả lời các câu hỏi chung chung của khách hàng
- Tìm kiếm sản phẩm và đưa ra những đề xuất phù hợp
- Xem các danh mục sản phẩm có sẵn
- Xử lý đơn hàng của khách hàng một cách hiệu quả
- Theo dõi trạng thái đơn hàng và cung cấp thông tin cập nhật
- Hướng dẫn khách hàng trong trải nghiệm mua sắm

Khi tìm kiếm sản phẩm:
- Hãy hiểu rõ nhu cầu và sở thích của khách hàng
- Nếu người dùng chỉ hỏi sản phẩm(query) mà không cung cấp thêm thông tin gì về thể loại thì bạn hãy tự chọn category_name. category_name chỉ bao gồm 4 loại: thoi-trang, do-dung-nha-cua, games-toys, phu-kien.
- Sử dụng tính linh hoạt về danh mục và khoảng giá để tìm các lựa chọn phù hợp nếu khách hàng cung cấp thông tin này
- Cung cấp thông tin sản phẩm chi tiết bao gồm tên sản phẩm, giá cả, mô tả ngắn gọn, link sản phẩm và link ảnh sản phẩm dưới dạng markdown, mỗi dữ liệu là 1 dòng.
- Khi trả về sản phẩm, nếu có trường 'image_url', hãy hiển thị hình ảnh sản phẩm cho người dùng bằng cú pháp markdown: ![Tên sản phẩm](image_url)
- Trả lời chính xác những gì mà hệ thống trả về bao gồm tên sản phẩm, giá, link sản phẩm, link ảnh. Không được bịa đặt thông tin sản phẩm.
- Nếu sản phẩm không có sẵn thì trả lời rằng sản phẩm này cửa hàng không có sẵn.

Khi đưa ra đề xuất:
- Xem xét các giao dịch mua và sở thích trước đây của khách hàng
- Đề xuất sản phẩm bổ sung khi thích hợp
- Tập trung vào các sản phẩm còn hàng
- Giải thích tại sao bạn đề xuất những sản phẩm cụ thể

Khi khách hàng muốn đặt hàng:
- Xác minh xem sản phẩm có tồn tại trong hệ thống không bằng cách sử dụng search_products
- Nếu không tìm thấy sản phẩm, hãy hỏi khách hàng cung cấp thêm chi tiết hoặc kiểm tra lại tên sản phẩm
- Sau khi tìm thấy sản phẩm, hiển thị chi tiết và hỏi xác nhận từ khách hàng
- Nếu khách hàng xác nhận đúng sản phẩm, hãy hỏi số lượng họ muốn đặt và cho phép điều chỉnh số lượng bất cứ lúc nào
- Tính và hiển thị tổng giá trị đơn hàng (số lượng x giá sản phẩm)
- Hiển thị thông tin tài khoản của khách hàng (tên, số điện thoại, địa chỉ) theo định dạng rõ ràng, dễ đọc
- Cung cấp cho khách hàng lựa chọn rõ ràng để cập nhật thông tin cá nhân nếu cần
- Khi khách hàng muốn thay đổi thông tin cá nhân, hướng dẫn họ cụ thể về cách cập nhật (ví dụ: "Cập nhật SĐT: 0912345678")
- Xác nhận lại thông tin đã cập nhật và tiếp tục quy trình đặt hàng
- Khi khách hàng xác nhận thông tin và đơn hàng, thông báo rằng họ sẽ được liên hệ sớm nhất có thể

Khi xử lý đơn hàng:
- Xác minh tình trạng sản phẩm trước khi xác nhận đơn hàng
- Thông báo rõ ràng chi tiết đơn hàng và tổng chi phí
- Cung cấp thông tin theo dõi đơn hàng
- Cập nhật thông tin về trạng thái đơn hàng cho khách hàng

Nếu bạn không thể tìm thấy chính xác những gì khách hàng đang tìm kiếm, hãy khám phá các lựa chọn thay thế và đưa ra những gợi ý hữu ích trước khi kết luận rằng một mặt hàng không có sẵn.

Hãy trả lời bằng tiếng Việt một cách tự nhiên và thân thiện. Sử dụng các cụm từ lịch sự như "xin chào", "cảm ơn", "xin lỗi" khi phù hợp.

{conversation_history_text}

\n\nKhách hàng hiện tại:\n<User>\n{user_info}\n</User>
\nThời gian hiện tại: {time}.""",
        ),
        ("placeholder", "{messages}"),
    ]
).partial(
    time=datetime.now,
    conversation_history_text=lambda **kwargs: (
        f"\n\nLịch sử 3 cuộc trò chuyện gần nhất (bao gồm tools đã sử dụng):\n{kwargs.get('conversation_history', '')}\n" 
        if kwargs.get('conversation_history') 
        else ""
    )
)

# "Read"-only tools
safe_tools = [
    # get_available_categories,
    search_products,
    # search_products_recommendations,
    check_order_status,
    chitchat,
    get_customer_info,  # Add this tool to safe tools
    # search_products_by_image
]

# Sensitive tools (confirmation needed)
sensitive_tools = [
    create_order,
    update_order,
    cancel_order,
    # delete_order,
    update_customer_info,  # Thêm tool cập nhật thông tin khách hàng
]

sensitive_tool_names = {tool.name for tool in sensitive_tools}

assistant_runnable = assistant_prompt | llm.bind_tools(safe_tools + sensitive_tools)

builder = StateGraph(State)


class OrderPreparation:
    def __init__(self, runnable: Runnable):
        self.runnable = runnable
        
    def __call__(self, state: State, config: RunnableConfig):
        # Kiểm tra xem đây có phải là lệnh tạo đơn hàng không
        messages = state.get("messages", [])
        verified_product = state.get("verified_product", None)
        configuration = config.get("configurable", {})
        customer_id = configuration.get("customer_id", None)
        
        import logging
        
        for msg in reversed(messages):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if tool_call.get("name") == "create_order":
                        # Đây là lệnh tạo đơn hàng
                        try:
                            args = json.loads(tool_call.get("args", "{}")) if isinstance(tool_call.get("args"), str) else tool_call.get("args", {})
                            product_name = args.get("product_name", "")
                            quantity = args.get("quantity", 1)
                            
                            logging.info(f"Processing create_order with args: {args}")
                            
                            if not verified_product:
                                # Tìm kiếm sản phẩm trong database
                                search_result = search_products.invoke({"query": product_name, "category": ""}, config)
                                
                                if search_result and "products" in search_result and len(search_result["products"]) > 0:
                                    # Đã tìm thấy sản phẩm, cập nhật state với thông tin sản phẩm
                                    product = search_result["products"][0]
                                    logging.info(f"Found product: {product}")
                                    
                                    # Tạo tin nhắn xác nhận với người dùng - UI thân thiện hơn
                                    confirmation_message = f"""
📦 **Sản phẩm được tìm thấy:**

• **Tên:** {product.get('name')}
• **Giá:** {product.get('price'):,.0f}đ
• **Mô tả:** {product.get('description', 'Không có mô tả')}

Đây có phải là sản phẩm bạn muốn đặt không? 

Nếu đúng, vui lòng cho tôi biết số lượng bạn muốn đặt (hoặc điều chỉnh số lượng nếu cần).
"""
                                    
                                    if product.get('image_url'):
                                        confirmation_message += f"\n\n![{product.get('name')}]({product.get('image_url')})"
                                    
                                    # Cập nhật state với thông tin sản phẩm đã xác minh
                                    return {
                                        "messages": [{"type": "ai", "content": confirmation_message}],
                                        "verified_product": product
                                    }
                                else:
                                    # Không tìm thấy sản phẩm, yêu cầu người dùng cung cấp thêm thông tin - UI thân thiện
                                    search_message = f"""
❓ **Sản phẩm không tìm thấy**

Xin lỗi, tôi không tìm thấy sản phẩm "*{product_name}*" trong hệ thống của chúng tôi. 

Bạn có thể:
• Kiểm tra lại tên sản phẩm
• Cung cấp thêm chi tiết về sản phẩm bạn đang tìm
• Mô tả sản phẩm bằng từ khóa khác
"""
                                    return {
                                        "messages": [{"type": "ai", "content": search_message}]
                                    }
                            else:
                                # Đã có sản phẩm trong state, xem đây là lệnh xác nhận đặt hàng
                                logging.info(f"Creating order with verified_product: {verified_product}")
                                
                                # Kiểm tra xem có product_id không - đây là phần quan trọng để khắc phục lỗi
                                if "id" not in verified_product:
                                    error_message = f"""
❌ **Không thể tạo đơn hàng**

Có lỗi xảy ra: Không tìm thấy ID sản phẩm.

Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
"""
                                    return {
                                        "messages": [{"type": "ai", "content": error_message}],
                                        "verified_product": None
                                    }
                                
                                # Tạo args mới với product_id thay vì product_name
                                new_args = {
                                    "product_id": verified_product["id"],  # Use product ID explicitly
                                    "quantity": args.get("quantity", 1),
                                    "customer_id": customer_id if customer_id and customer_id != "123456789" else None
                                }
                                
                                logging.info(f"Creating order with args: {new_args}")
                                
                                # Kiểm tra customer_id
                                if not new_args["customer_id"]:
                                    error_message = f"""
⚠️ **Thiếu thông tin đặt hàng**

Để hoàn tất đơn hàng, bạn cần đăng nhập trước.

Vui lòng đăng nhập để tiếp tục.
"""
                                    return {
                                        "messages": [{"type": "ai", "content": error_message}],
                                        "verified_product": verified_product
                                    }
                                
                                # Đủ thông tin, thực hiện đặt hàng
                                try:
                                    # Thay đổi ở đây - gửi danh sách products thay vì args đơn lẻ
                                    order_data = {
                                        "products": [
                                            {
                                                "product_id": str(verified_product["id"]),  # Ensure it's a string
                                                "quantity": args.get("quantity", 1)
                                            }
                                        ]
                                    }
                                    logging.info(f"Final create_order payload: {order_data}")
                                    
                                    result = create_order.invoke(order_data, config)
                                    
                                    if "error" in result or result.get("status") == "error":
                                        error_message = f"""
❌ **Không thể tạo đơn hàng**

Có lỗi xảy ra: {result.get("error") or result.get("message", "Unknown error")}

Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
"""
                                        return {
                                            "messages": [{"type": "ai", "content": error_message}],
                                            "verified_product": verified_product
                                        }
                                    else:
                                        success_message = f"""
✅ **Đặt hàng thành công!**

Đơn hàng của bạn đã được tạo:
• Mã đơn hàng: {result.get("order_id")}
• Sản phẩm: {verified_product.get("name")}
• Số lượng: {args.get("quantity", 1)}
• Tổng thanh toán: {float(verified_product.get("price", 0)) * int(args.get("quantity", 1)):,.0f}đ

Cảm ơn bạn đã mua sắm cùng chúng tôi! Đơn hàng sẽ được xử lý và giao đến bạn trong thời gian sớm nhất.
"""
                                        # Reset verified_product sau khi đặt hàng thành công
                                        return {
                                            "messages": [{"type": "ai", "content": success_message}],
                                            "verified_product": None
                                        }
                                except Exception as e:
                                    logging.error(f"Error creating order: {str(e)}")
                                    error_message = f"""
❌ **Không thể tạo đơn hàng**

Có lỗi xảy ra: {str(e)}

Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
"""
                                    return {
                                        "messages": [{"type": "ai", "content": error_message}],
                                        "verified_product": verified_product
                                    }
                        except Exception as e:
                            # Lỗi khi xử lý tham số
                            logging.error(f"Error processing order parameters: {str(e)}")
                            error_message = f"""
❌ **Không thể xử lý thông tin đặt hàng**

Có lỗi xảy ra: {str(e)}

Vui lòng cung cấp thông tin đặt hàng theo định dạng:
• Tên sản phẩm: [tên sản phẩm]
• Số lượng: [số lượng]
"""
                            return {
                                "messages": [{"type": "ai", "content": error_message}]
                            }
                            
        # Xử lý phản hồi của người dùng khi đã có verified_product
        if verified_product:
            last_user_message = ""
            for msg in reversed(messages):
                if hasattr(msg, 'type') and msg.type == "human":
                    last_user_message = msg.content.lower()
                    break

            if "xác nhận" in last_user_message or "đồng ý" in last_user_message or "mua" in last_user_message or "đặt hàng" in last_user_message or "ok" in last_user_message:
                # Người dùng xác nhận đặt hàng
                try:
                    quantity = 1  # Mặc định
                    # Tìm số lượng trong tin nhắn của user
                    import re
                    qty_match = re.search(r'số lượng.*?(\d+)', last_user_message)
                    if qty_match:
                        quantity = int(qty_match.group(1))
                    
                    logging.info(f"User confirmed order with product: {verified_product}")
                    
                    # Kiểm tra xem có product_id không
                    if "id" not in verified_product:
                        logging.error("Product ID missing in verified_product")
                        error_message = "❌ Lỗi: Không tìm thấy ID sản phẩm. Vui lòng thử lại."
                        return {
                            "messages": [{"type": "ai", "content": error_message}],
                            "verified_product": None
                        }
                    
                    # Thay đổi ở đây - gửi danh sách products thay vì args đơn lẻ
                    order_data = {
                        "products": [
                            {
                                "product_id": str(verified_product["id"]),  # Ensure it's a string
                                "quantity": quantity
                            }
                        ]
                    }
                    print("11111111111111111111111111111111111: ", order_data)
                    
                    logging.info(f"Creating order with data: {order_data}")
                    result = create_order.invoke(order_data, config)
                    
                    if "error" in result or result.get("status") == "error":
                        error_message = f"""
❌ **Không thể tạo đơn hàng**

Có lỗi xảy ra: {result.get("error") or result.get("message", "Unknown error")}

Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
"""
                        return {
                            "messages": [{"type": "ai", "content": error_message}],
                            "verified_product": verified_product
                        }
                    else:
                        success_message = f"""
✅ **Đặt hàng thành công!**

Đơn hàng của bạn đã được tạo:
• Mã đơn hàng: {result.get("order_id")}
• Sản phẩm: {verified_product.get("name")}
• Số lượng: {quantity}
• Tổng thanh toán: {float(verified_product.get("price", 0)) * quantity:,.0f}đ

Cảm ơn bạn đã mua sắm cùng chúng tôi! Đơn hàng sẽ được xử lý và giao đến bạn trong thời gian sớm nhất.
"""
                        # Reset verified_product sau khi đặt hàng thành công
                        return {
                            "messages": [{"type": "ai", "content": success_message}],
                            "verified_product": None
                        }
                except Exception as e:
                    logging.error(f"Error processing confirmed order: {str(e)}")
                    error_message = f"""
❌ **Không thể tạo đơn hàng**

Có lỗi xảy ra: {str(e)}

Vui lòng thử lại sau hoặc liên hệ hỗ trợ.
"""
                    return {
                        "messages": [{"type": "ai", "content": error_message}],
                        "verified_product": verified_product
                    }
                
            elif "thay đổi số lượng" in last_user_message:
                # Người dùng muốn thay đổi số lượng
                try:
                    import re
                    qty_match = re.search(r'thành\s+(\d+)', last_user_message)
                    new_quantity = int(qty_match.group(1)) if qty_match else 1
                    
                    # Tính tổng giá tiền mới
                    unit_price = float(verified_product.get('price', 0))
                    total_price = unit_price * new_quantity
                    
                    confirmation_message = f"""
🔄 **Đã cập nhật số lượng**

• Sản phẩm: {verified_product.get('name')}
• Đơn giá: {unit_price:,.0f}đ
• Số lượng mới: {new_quantity}
• **Tổng cộng mới: {total_price:,.0f}đ**

Bạn có muốn xác nhận đặt hàng không?
"""
                    return {
                        "messages": [{"type": "ai", "content": confirmation_message}],
                        "verified_product": verified_product
                    }
                except Exception as e:
                    logging.error(f"Error updating quantity: {str(e)}")
                    error_message = "❌ Không thể cập nhật số lượng. Vui lòng thử lại bằng cú pháp: Thay đổi số lượng thành [số lượng mới]"
                    return {
                        "messages": [{"type": "ai", "content": error_message}],
                        "verified_product": verified_product
                    }
                    
        return state


# Define nodes: these do the work
builder.add_node("assistant", Assistant(assistant_runnable))
builder.add_node("order_preparation", OrderPreparation(assistant_runnable))
builder.add_node("safe_tools", create_tool_node_with_fallback(safe_tools))
builder.add_node("sensitive_tools", create_tool_node_with_fallback(sensitive_tools))


def route_tools(state: State):
    next_node = tools_condition(state)
    # If no tools are invoked, return to the user
    if next_node == END:
        return END
    ai_message = state["messages"][-1]
    # This assumes single tool calls. To handle parallel tool calling, you'd want to
    # use an ANY condition
    first_tool_call = ai_message.tool_calls[0]
    if first_tool_call["name"] == "create_order":
        return "order_preparation"
    elif first_tool_call["name"] in sensitive_tool_names:
        return "sensitive_tools"
    return "safe_tools"


# Define edges: these determine how the control flow moves
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant", route_tools, ["safe_tools", "sensitive_tools", "order_preparation", END]
)
builder.add_edge("safe_tools", "assistant")
builder.add_edge("sensitive_tools", "assistant")
builder.add_edge("order_preparation", END)

# Compile the graph
memory = MemorySaver()
graph = builder.compile(checkpointer=memory, interrupt_before=["sensitive_tools", "order_preparation"])
