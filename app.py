import streamlit as st
import logging
import os
import json
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from virtual_sales_agent.graph import graph
from virtual_sales_agent.ui import process_events, create_order_ui, update_order_ui, delete_order_ui

# Configure logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

st.set_page_config(page_title="🛒 Virtual Sales Assistant", page_icon="🛒", layout="wide")
st.title("🛒 Virtual Sales Assistant")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
    
if "customer_id" not in st.session_state:
    st.session_state.customer_id = None
    
if "config" not in st.session_state:
    st.session_state.config = {"configurable": {}}
    
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

# Add sidebar for user configuration
with st.sidebar:
    st.header("Customer Configuration")
    customer_id = st.text_input("Customer ID", value=st.session_state.customer_id or "")
    
    if customer_id:
        if customer_id != st.session_state.customer_id:
            st.session_state.customer_id = customer_id
            st.session_state.config = {"configurable": {"customer_id": customer_id}}
            logging.info(f"Customer ID set to: {customer_id}")
            st.success(f"Customer ID set to: {customer_id}")
            
    # Debug section
    with st.expander("Debug Options"):
        if st.button("Clear Chat History"):
            st.session_state.messages = []
            st.session_state.pending_approval = None
            st.rerun()
            
        if st.button("Show Session Config"):
            st.json(st.session_state.config)
            
        if st.button("Show Pending Approval"):
            if st.session_state.pending_approval:
                last_message, tool_call = st.session_state.pending_approval
                st.write("Tool Name:", tool_call["name"])
                try:
                    args = tool_call["args"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    st.json(args)
                except:
                    st.write("Could not parse args")
            else:
                st.write("No pending approval")

# Display chat messages
for message in st.session_state.messages:
    if message.type == "human":
        with st.chat_message("user"):
            st.write(message.content)
    elif message.type == "ai":
        with st.chat_message("assistant"):
            st.write(message.content)

# Handle pending approval
if st.session_state.pending_approval:
    last_message, tool_call = st.session_state.pending_approval
    
    # Log what we're trying to handle
    logging.info(f"Handling pending approval for {tool_call['name']}")
    
    # Route to the appropriate UI handler based on tool name
    if tool_call["name"] == "create_order":
        create_order_ui(last_message, tool_call)
    elif tool_call["name"] == "update_order":
        update_order_ui(last_message, tool_call)
    elif tool_call["name"] == "delete_order":
        delete_order_ui(last_message, tool_call)
    else:
        # Generic handler for other tools
        st.info(f"Approval needed for: {tool_call['name']}")
        
        # Try to display the arguments
        try:
            args_to_display = tool_call["args"]
            if isinstance(args_to_display, str):
                args_to_display = json.loads(args_to_display)
            st.json(args_to_display)
        except:
            st.write("(Could not parse arguments)")
        
        # Approval buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Approve"):
                with st.spinner("Processing..."):
                    result = graph.invoke(
                        {
                            "messages": [
                                ToolMessage(
                                    tool_call_id=tool_call["id"],
                                    content="Approved by user",
                                )
                            ]
                        },
                        st.session_state.config,
                    )
                    process_events(result)
                    st.session_state.pending_approval = None
                    st.rerun()
        
        with col2:
            if st.button("❌ Deny"):
                with st.spinner("Processing..."):
                    result = graph.invoke(
                        {
                            "messages": [
                                ToolMessage(
                                    tool_call_id=tool_call["id"],
                                    content="Denied by user",
                                )
                            ]
                        },
                        st.session_state.config,
                    )
                    process_events(result)
                    st.session_state.pending_approval = None
                    st.rerun()

# Chat input
if prompt := st.chat_input("Type a message..."):
    # Add user message to chat history
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.write(prompt)
    
    # Get AI response
    with st.spinner("Thinking..."):
        try:
            # Check if we have a customer ID
            if not st.session_state.customer_id:
                with st.chat_message("assistant"):
                    st.write("Please enter a Customer ID in the sidebar before continuing.")
                st.rerun()
            
            # Get response from the graph
            result = graph.invoke(
                {"messages": [HumanMessage(content=prompt)]}, 
                st.session_state.config
            )
            
            # Process normal messages first
            tool_call = process_events(result)
            
            # Check if we need to interrupt for user approval
            if result.get("interrupt_data"):
                try:
                    ai_message = result["interrupt_before_node"]["messages"][-1]
                    # Ensure we get the full tool call
                    if hasattr(ai_message, "tool_calls") and ai_message.tool_calls:
                        tool_call = ai_message.tool_calls[0]
                        logging.info(f"Interrupting for approval: {tool_call['name']}")
                        st.session_state.pending_approval = (ai_message, tool_call)
                        st.rerun()
                except Exception as e:
                    logging.error(f"Error handling interrupt: {e}")
                    # Fallback to showing the message without interaction
                    process_events(result)
        except Exception as e:
            logging.error(f"Error processing request: {e}")
            with st.chat_message("assistant"):
                st.error(f"Sorry, I encountered an error: {str(e)}")
