# /usr/local/lib/timebot/lib/chat/help_page.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# help_page.py - Help page for the Timebot chat application

import streamlit as st
import logging
from chat.ui import set_font_size, create_sidebar, render_footer

logger = logging.getLogger(__name__)


def display_help_page():
    """Display the help page with instructions on using Timebot"""
    # Set font size
    set_font_size()

    # Add the sidebar
    create_sidebar()

    # Main content
    st.title("Timebot Help")

    # Introduction
    st.markdown(
        """
    Welcome to the Timebot help page. This guide will help you
    understand how to use Timebot effectively.
    """
    )

    # Basic usage
    st.header("Basic Usage")
    st.markdown(
        """
    Timebot is designed to answer questions about time and frequency
    measurement and related topics. Here's how to use it:
    
    1. **Ask a question**: Type your question in the chat box and
    press "Send".
    2. **Start a new chat**: Click the "New Chat" button in the sidebar
    to start a fresh conversation.
    3. **View information sources**: Click "About Timebot" to
    learn about the knowledge base behind Timebot.
    4. **Search the database**: Use the "Search Database" button to
    directly search the knowledge base without AI assistance.
    """
    )

    # Advanced features
    st.header("Advanced Features")
    st.markdown(
        """
    ### Search Settings
    
    In the main chat interface, you can adjust search settings in the
    sidebar:
    
    - **Number of context documents**: Adjust how many documents are
    retrieved for each query.
    - **Refresh Context**: Clear the current context to force a new
    search on your next query.
    - **Rerun last query**: Apply new settings to your previous question.
    
    ### Direct Database Search
    
    The "Search Database" page allows you to:
    
    1. Search for specific terms in the knowledge base
    2. Filter results by collection
    3. View document details
    4. Ask the AI about specific documents

    You can search for content with a natural language query,
    search metadata such as title, author, etc., or do a combined
    search for both.

    Content searches work better with real questions rather than just a word or two.
    Metadata searches by default use "fuzzy matching" which will try to work around
    typos or similar words.
    """
    )

    # Tips for effective queries
    st.header("Tips for Effective Queries")
    st.markdown(
        """
    - **Be specific**: The more specific your question, the more accurate
    the response.
    - **Ask follow-up questions**: Timebot remembers your conversation
    history.
    - **Provide context**: If you're asking about a specific concept,
    include relevant details.
    - **Request clarification**: If a response is unclear, ask Timebot toi
    explain further.
    """
    )

    # Troubleshooting
    st.header("Troubleshooting")
    st.markdown(
        """
    - **No relevant documents found**: Try rephrasing your question or
    using different terminology.
    - **Response seems incorrect**: Click "Refresh Context" and try
    again, or start a new chat.
    - **System errors**: If you encounter persistent errors, please
    contact the administrator.
    """
    )

    # Contact information
    st.header("Contact Information")
    st.markdown(
        """
    If you need further assistance or want to provide feedback,
    please contact:
    
    John Ackermann -- jra at febo dot com
    """
    )

    # Add the footer
    render_footer()


if __name__ == "__main__":
    display_help_page()
