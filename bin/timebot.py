#!/bin/env python3
# /usr/local/lib/timebot/bin/timebot.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# timebot_chat.py - Main entry point for the Timebot chat application

import sys
import os
import datetime
import logging
from pathlib import Path

# Path to the startup semaphore file
STARTUP_SEMAPHORE = "/var/run/timebot_startup.semaphore"

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

from shared.config import config

# Set where __pycache__ lives
sys.pycache_prefix = "/var/cache/timebot/embedding_service"


# Set up logging
logger = logging.getLogger()
log_file_path = config["TIMEBOT_LOG"]
log_directory = os.path.dirname(log_file_path)
Path(log_directory).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()  # Also log to console
    ]
)


# import streamlit first
import streamlit as st
# Do this first thing
def setup_page():
    """Set up the page configuration"""
    st.set_page_config(
        page_title="Timebot -- A Time and Frequency Expert System",
        page_icon="⏱️",
        layout="wide"
    )

setup_page()  # Call this immediately

# Import the config module
from shared.config import config

# Import other modules
from chat.info_page import display_info_page
from chat.rag_service import query_rag, query_metadata
from chat.llm_service import query_llm, initialize_external_llm_service
from chat.ui import set_font_size, render_footer, display_chat_interface, handle_navigation, display_usage_stats, create_sidebar
from chat.chat_utils import format_context, format_references

# Import authentication service if enabled
USE_FIREBASE_AUTH = config["USE_FIREBASE_AUTH"]
if USE_FIREBASE_AUTH:
    from chat.auth_service import AuthService
    auth_service = AuthService(config)
    
    # Initialize Google AI service with auth service if enabled
    if config["USE_EXTERNAL_LLM"]:
        initialize_external_llm_service(config, auth_service)
else:
    # Initialize Google AI service without auth service
    if config["USE_EXTERNAL_LLM"]:
        initialize_external_llm_service(config)

def main():

    # Log startup (only once)
    if not os.path.exists(STARTUP_SEMAPHORE):
        # Log actual service startup (first time the script runs)
        logger.info("Timebot chat service started")

        # Create the semaphore file
        try:
            with open(STARTUP_SEMAPHORE, 'w') as f:
                f.write(str(datetime.datetime.now()))
        except Exception as e:
            logger.warning(f"Could not create startup semaphore: {str(e)}")

    # Store config in session state for access in other components
    st.session_state["config"] = config

    # set up font size and title
    set_font_size()
    st.title("Timebot -- A Time and Frequency Expert System")

    # Handle navigation between pages
    if not handle_navigation():
        # If we're on the main page, display the chat interface
        user_id = st.session_state.get("user_id") if USE_FIREBASE_AUTH else None
        display_chat_interface(
            query_rag, 
            lambda prompt, model=None, context=None, conversation_history=None: query_llm(
                prompt, model, context, conversation_history, user_id
            ),
            format_context, 
            format_references
        )
        
        # Display usage statistics if Google AI is enabled and user is authenticated
        if config["USE_EXTERNAL_LLM"] and config["USE_FIREBASE_AUTH"] and st.session_state.get("authenticated", False):
            display_usage_stats()

    # Render the footer
    render_footer()

if __name__ == "__main__":
    if config["USE_FIREBASE_AUTH"]:
        # Apply authentication wrapper if enabled
        main = auth_service.auth_required(main)
    main()

