# /usr/local/lib/timebot/lib/chat/ui.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# ui.py - UI components for the Timebot chat application

import streamlit as st
import datetime
import logging
from typing import Callable
from shared.config import config
from chat.prompts import SYSTEM_PROMPT
# Use config["TOP_K"], etc. directly below.
from chat.rag_service import clear_rag_cache

logger = logging.getLogger(__name__)


def set_font_size(font_size: str = "18px"):  # Set desired font size here
    """Sets the base font size for the Streamlit app."""
    st.markdown(
        f"""
    <style>
    html, body, .stApp {{
        font-size: {font_size};
    }}

    /* Style for the text input area */
    .stTextArea textarea {{
        border-radius: 10px;
        border: 1px solid #ddd;
        padding: 10px;
        font-size: 18px;  /* Increase this value to make the text larger */
    }}

    /* Style for the send button */
    .stButton button {{
        border-radius: 10px;
    }}

    /* Style for the chat button */
    .sidebar .stButton button {{
        width: 100%;
        text-align: left;
        margin-bottom: 10px;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )


def initialize_session_state():
    """Initialize all necessary session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "chat_id" not in st.session_state:
        st.session_state.chat_id = datetime.datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )

    if "top_k" not in st.session_state:
        st.session_state.top_k = config["TOP_K"]

    # Initialize rule-based query enhancement toggle if not present
    if "enable_query_enhancement" not in st.session_state:
        st.session_state.enable_query_enhancement = (
            config["ENABLE_RULES_QUERY_ENHANCEMENT"]
        )

    # Initialize RAG cache with new detailed structure
    if "rag_cache" not in st.session_state:
        st.session_state.rag_cache = {
            "original_query": None,
            "query_after_llm_enhancement": None,
            "final_query_for_rag": None,
            "llm_enhancement_applied_flag": False,
            "rule_enhancement_applied_flag": False,
            "results": None,
            "timestamp": None,
            # For backward compatibility if any part still uses these exact old keys
            "last_query": None,
            "enhanced_query": None,
        }



def display_introduction():
    st.markdown(
        """
    Welcome to Timebot, an expert assistant for questions about
    time and frequency measurement.  Timebot combines specialized 
    knowledge with general AI capabilities to provide accurate and 
    helpful information.  Learn more by clicking the "About Timebot" 
    button at the left.

    Type your question in the box below to get started, or use 
    the "Search Database" button to query the database directly,
    like a traditional web search.
    """
    )


def render_footer():
    """Render the footer with contact information"""
    if "footer_rendered" not in st.session_state:
        st.session_state.footer_rendered = True
        st.markdown(
            """
        <style>
        .footer {
            margin-top: 50px;
            text-align: center;
            padding: 10px;
            font-size: 14px;
            border-top: 1px solid rgba(128, 128, 128, 0.2);
        }
        </style>
        <div class="footer"><i><b>Service provided by John Ackermann -- jra at febo dot com</i></b></div>
        """,
            unsafe_allow_html=True,
        )   



def initialize_chat_history():
    """Initialize chat history in session state if it doesn't exist"""
    # This function's content is largely duplicated by initialize_session_state.
    # Calling initialize_session_state() at the start of display_chat_interface
    # or other entry points is sufficient.
    initialize_session_state() # Ensure all states are initialized


def handle_new_chat():
    """Reset the chat history and generate a new chat ID"""
    st.session_state.messages = []
    st.session_state.chat_id = datetime.datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )
    # Clear the RAG cache with the new structure
    st.session_state.rag_cache = {
        "original_query": None,
        "query_after_llm_enhancement": None,
        "final_query_for_rag": None,
        "llm_enhancement_applied_flag": False,
        "rule_enhancement_applied_flag": False,
        "results": None,
        "timestamp": None,
        "last_query": None, # maintain for compatibility if needed
        "enhanced_query": None, # maintain for compatibility if needed
    }
    logger.info(f"New chat started with ID: {st.session_state.chat_id}")


def handle_refresh_context():
    """Clear the RAG cache to force a new search on the next query"""
    if clear_rag_cache():
        st.success("Context refreshed! The next query will perform a new search.")
        logger.info(f"Chat ID: {st.session_state.chat_id} - Context refreshed manually")
    else:
        st.warning("No context to refresh.")


def setup_rag_controls():
    """Set up controls for RAG settings in the sidebar"""
    # Ensure session state values are initialized (should be by initialize_session_state)
    if "top_k" not in st.session_state: # Should be handled by initialize_session_state
        st.session_state.top_k = TOP_K

    if "enable_query_enhancement" not in st.session_state: # Should be handled by initialize_session_state
        st.session_state.enable_query_enhancement = (
            config["ENABLE_RULES_QUERY_ENHANCEMENT"]
        )

    with st.sidebar:
        st.divider()
        st.subheader("Search Settings")

        st.session_state.top_k = st.slider(
            "Number of context documents",
            min_value=1,
            max_value=20,
            value=st.session_state.top_k,
            help="Adjust how many documents are retrieved for each query",
        )

        # Toggle for RULE-BASED query enhancement for follow-ups
        st.session_state.enable_query_enhancement = st.toggle(
            "Enable follow-up query enhancement", # Clarified label
            value=st.session_state.enable_query_enhancement,
            help=(
                "When enabled, short follow-up questions will be enhanced "
                "with context from previous conversation turns (rule-based)."
            ),
        )
        # Log the current state of the toggle from session_state
        logger.debug(
            "UI DEBUG - Rule-based follow-up query enhancement toggle is"
            f" {st.session_state.enable_query_enhancement}"
        )
        # REMOVED: Block for modifying chat_config module and reloading rag_service.
        # Setting st.session_state.enable_query_enhancement is sufficient as
        # rag_service.py reads this value from session_state.

        if st.button("🔄 Refresh Context", key="refresh_context"):
            # handle_refresh_context itself was not modified in this file,
            # but its underlying clear_rag_cache in rag_service.py was.
            from .rag_service import clear_rag_cache # Ensure using updated one
            if clear_rag_cache():
                st.success(
                    "Context refreshed! The next query will perform a new search."
                )
                logger.info(
                    f"Chat ID: {st.session_state.chat_id} - Context refreshed manually"
                )
            else:
                st.warning("No context to refresh.")


        if st.button("Rerun last query with new settings"):
            if (
                "messages" in st.session_state
                and len(st.session_state.messages) > 0
            ):
                # Find the last user message
                for i in range(len(st.session_state.messages) - 1, -1, -1):
                    if st.session_state.messages[i]["role"] == "user":
                        last_user_query = st.session_state.messages[i][
                            "content"
                        ]
                        # Remove the last assistant message if it exists
                        if (
                            i + 1 < len(st.session_state.messages)
                            and st.session_state.messages[i + 1]["role"]
                            == "assistant"
                        ):
                            st.session_state.messages.pop(i + 1)
                        # Set a flag to reprocess this query
                        st.session_state.rerun_query = last_user_query
                        break


def create_sidebar(current_page="main"):
    """Create the sidebar with navigation buttons

    Args:
        current_page: The current active page (main, info, search, help)
    """
    with st.sidebar:
        button_container = st.container()
        with button_container:
            if st.button("🔄 New Chat", key="new_chat"):
                handle_new_chat()
                st.query_params.clear() # Use new API for query params
                st.rerun()

            if st.button("🔍 Search Database", key="search_button"):
                st.query_params["page"] = "search" # Use new API
                st.rerun()

            if st.button("ℹ️About Timebot", key="info_button"):
                st.query_params["page"] = "info" # Use new API
                st.rerun()

            if st.button("❓ Help", key="help_button"):
                st.query_params["page"] = "help" # Use new API
                st.rerun()

            if "logout_button" in st.session_state:
                st.session_state.logout_button()

        if current_page == "main":
            setup_rag_controls()

def display_chat_interface(
    query_rag_fn: Callable,
    query_llm_fn: Callable,
    format_context_fn: Callable,
    format_references_fn: Callable,
):
    """Display the chat interface and handle user interactions"""
    initialize_chat_history() # Ensures all session state vars are set

    if not st.session_state.messages:
        display_introduction() # This function was not modified

    create_sidebar(current_page="main") # Modified for st.query_params
    chat_container = st.container()
    input_container = st.container()

    with chat_container:
        for message_idx, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

                if "references" in message and message["references"]:
                    st.markdown("---")
                    st.markdown("**References:**")
                    st.markdown(message["references"])

                if message["role"] == "user":
                    if "rag_cache" in st.session_state:
                        cache = st.session_state.rag_cache
                        # Check if this message's content matches the original_query in the cache
                        # This assumes the cache is relevant to the *last processing* of this query content.
                        if (
                            cache.get("original_query")
                            and message["content"] == cache.get("original_query")
                        ):
                            original_q = cache.get("original_query")
                            llm_enhanced_q = cache.get(
                                "query_after_llm_enhancement"
                            )
                            final_q_for_rag = cache.get("final_query_for_rag")
                            llm_applied = cache.get(
                                "llm_enhancement_applied_flag"
                            )
                            rule_applied = cache.get(
                                "rule_enhancement_applied_flag"
                            )

                            enhancement_msgs = []
                            # Check if LLM enhancement actually changed the query
                            if (
                                llm_applied
                                and llm_enhanced_q
                                and llm_enhanced_q.strip().lower() != original_q.strip().lower()
                            ):
                                enhancement_msgs.append(
                                    f"Refined for context search: **{llm_enhanced_q}**"
                                )

                            # Determine what the input to rule-based enhancement was
                            input_to_rule_enhancer = (
                                llm_enhanced_q
                                if llm_applied and llm_enhanced_q and llm_enhanced_q.strip().lower() != original_q.strip().lower()
                                else original_q
                            )
                            # Check if rule-based enhancement actually changed the query from its input
                            if (
                                rule_applied
                                and final_q_for_rag
                                and final_q_for_rag.strip().lower() != input_to_rule_enhancer.strip().lower()
                            ):
                                # If LLM also enhanced, make the rule message more specific
                                if llm_applied and llm_enhanced_q and llm_enhanced_q.strip().lower() != original_q.strip().lower():
                                    enhancement_msgs.append(
                                        f"Follow-up context added, final RAG query: **{final_q_for_rag}**"
                                    )
                                else: # Only rule-based enhancement (or LLM made no change)
                                     enhancement_msgs.append(
                                        f"Follow-up context added: **{final_q_for_rag}**"
                                    )
                            elif ( # Case where only LLM enhancement happened and rule-based didn't change it further
                                llm_applied and llm_enhanced_q and llm_enhanced_q.strip().lower() != original_q.strip().lower()
                                and final_q_for_rag and final_q_for_rag.strip().lower() == llm_enhanced_q.strip().lower()
                                and len(enhancement_msgs) == 1 # Already have the LLM message
                            ):
                                # LLM message is already there, no need to add "final query" if same
                                pass
                            elif ( # If neither LLM nor rule changed it textually, but flags were true
                                not enhancement_msgs and (llm_applied or rule_applied)
                            ):
                                # This case means enhancement was attempted but made no textual change.
                                # logger.debug("UI: Enhancement processed but no textual change to display.")
                                pass


                            if enhancement_msgs:
                                st.info(
                                    "✨ " + " | ".join(enhancement_msgs)
                                )
    # Prepared question from search page
    if "prepared_question" in st.session_state and st.session_state.prepared_question:
        # user_input = st.session_state.prepared_question # Keep for clarity
        prepared_question_content = st.session_state.prepared_question
        st.session_state.prepared_question = None # Clear it

        st.session_state.messages.append(
            {"role": "user", "content": prepared_question_content}
        )
        # The user message will be displayed on the next rerun by the loop above.
        process_user_query(
            chat_container,
            prepared_question_content,
            query_rag_fn,
            query_llm_fn,
            format_context_fn,
            format_references_fn,
            user_id=st.session_state.get('user_id'),
        )
        st.rerun() # Rerun to display the new user message and assistant response

    # Chat input form
    with input_container:
        with st.form(key="chat_form", clear_on_submit=True):
            col1, col2 = st.columns([6, 1])
            with col1:
                user_input_from_form = st.text_area( # Renamed to avoid conflict
                    "Type your message here...",
                    height=100,
                    key="user_input_area", # Changed key
                    label_visibility="collapsed",
                )
            with col2:
                st.write("") # Vertical alignment
                st.write("")
                submit_button = st.form_submit_button("Send")

    # Rerun last query logic
    if "rerun_query" in st.session_state and st.session_state.rerun_query:
        prompt_to_rerun = st.session_state.rerun_query
        st.session_state.messages.append({"role": "user", "content": prompt_to_rerun})
        st.session_state.rerun_query = None # Clear the flag

        process_user_query(
            chat_container,
            prompt_to_rerun,
            query_rag_fn,
            query_llm_fn,
            format_context_fn,
            format_references_fn,
            user_id=st.session_state.get('user_id'),
        )
        st.rerun()

    # Process new input from form
    elif submit_button and user_input_from_form:
        prompt_from_form = user_input_from_form.strip()
        if prompt_from_form: # Ensure not just whitespace
            tmp_prompt_log = prompt_from_form.replace("\n", " ")
            logger.info(
                f"Chat ID: {st.session_state.chat_id} - User query: '{tmp_prompt_log}'"
            )
            st.session_state.messages.append({"role": "user", "content": prompt_from_form})
            process_user_query(
                chat_container,
                prompt_from_form,
                query_rag_fn,
                query_llm_fn,
                format_context_fn,
                format_references_fn,
                user_id=st.session_state.get('user_id'),
            )
            st.rerun()


def process_user_query(
    chat_container,
    prompt: str,
    query_rag_fn: Callable,
    query_llm_fn: Callable,
    format_context_fn: Callable,
    format_references_fn: Callable,
    user_id: str = None,
):
    """Process a user query and display the response.
    Assumes the user message `prompt` has already been added to st.session_state.messages.
    The display of the user message and any enhancement info will be handled
    by display_chat_interface on the next st.rerun().
    """
    with st.chat_message("assistant"):
        conversation_history = []
        for msg in st.session_state.messages: # Includes current user prompt
            conversation_history.append(
                {"role": msg["role"], "content": msg["content"]}
            )

        with st.spinner("Searching knowledge base..."):
            logger.debug(
                f"Chat ID: {st.session_state.chat_id} - Calling RAG with original prompt: '{prompt[:100]}...'"
            )
            logger.debug(
                f"Chat ID: {st.session_state.chat_id} - RAG parameters: top_k={st.session_state.top_k}, mode=combined, collection_filter=all"
            )
            logger.debug(
                "UI DEBUG - Rule-based follow-up query enhancement (from session_state):"
                f" {st.session_state.get('enable_query_enhancement', 'Not Set (using default)')}"
            )

            rag_results = query_rag_fn(
                prompt,
                top_k=st.session_state.top_k,
                conversation_history=conversation_history,
                mode="combined",
                collection_filter="all",
            )

            if rag_results is None:
                st.warning(
                    "Could not retrieve information from the knowledge "
                    "base. Using general knowledge only."
                )
                logger.error(
                    f"Chat ID: {st.session_state.chat_id} - "
                    f"RAG query failed for: '{prompt}'"
                )
                rag_results = []
            elif not rag_results:
                st.info(
                    "No relevant documents found in the knowledge "
                    "base. Using general knowledge."
                )
                logger.info(
                    f"Chat ID: {st.session_state.chat_id} "
                    f"- No relevant documents found for query: '{prompt}'"
                )

        with st.spinner("Generating response..."):
            context_for_llm = format_context_fn(rag_results if rag_results else [])
            final_llm_prompt = SYSTEM_PROMPT.format(
                context=context_for_llm, question=prompt
            )

            llm_result = query_llm_fn(
                final_llm_prompt,
                context=context_for_llm,
                conversation_history=conversation_history,
                user_id=user_id,
            )
            response_content = llm_result.get('response')
            success = llm_result.get('success', False)
            error_msg = llm_result.get('error')

            if success and response_content:
                references_text = format_references_fn(rag_results if rag_results else [])
                st.markdown(response_content)
                if references_text:
                    st.markdown("---")
                    st.markdown("**References:**")
                    st.markdown(references_text)

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response_content,
                        "references": references_text,
                    }
                )
            else:
                error_display = error_msg or "Failed to get a response. Please try again."
                st.error(error_display)
                logger.error(
                    f"Chat ID: {st.session_state.chat_id} "
                    f"- Failed to get LLM response for query: '{prompt}'. Error: {error_display}"
                )
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": "Sorry, I encountered an error trying to respond.",
                        "references": "",
                    }
                )

                logger.info(
                    f"Chat ID: {st.session_state.chat_id} - "
                    f"Query processed successfully. Original prompt: '{prompt[:50]}...'. "
                    f"LLM response: '{str(response_content)[:50]}...'."
                )


def display_usage_stats():
    """Display usage statistics in the sidebar"""
    if "ai_usage" in st.session_state and "ai_limits" in st.session_state:
        with st.sidebar:
            st.divider()
            st.subheader("Usage Statistics")

            # Get usage and limits
            usage = st.session_state.ai_usage
            limits = st.session_state.ai_limits

            # Display daily usage
            daily_usage = usage.get("daily", 0)
            daily_limit = limits.get("daily", 0)
            daily_percentage = (
                min(100, int((daily_usage / daily_limit) * 100))
                if daily_limit > 0
                else 0
            )

            st.markdown(f"**Daily Usage:** {daily_usage}/{daily_limit}")
            st.progress(daily_percentage / 100)

            # Display monthly usage
            monthly_usage = usage.get("monthly", 0)
            monthly_limit = limits.get("monthly", 0)
            monthly_percentage = (
                min(100, int((monthly_usage / monthly_limit) * 100))
                if monthly_limit > 0
                else 0
            )

            st.markdown(f"**Monthly Usage:** {monthly_usage}/{monthly_limit}")
            st.progress(monthly_percentage / 100)


def handle_navigation():
    """Handle navigation between different pages"""

    # Initialize session state variables
    initialize_session_state()

    # Get the current page from query parameters using the new API
    current_page = st.query_params.get("page", "main")

    if current_page == "info":
        from chat.info_page import display_info_page

        display_info_page(st.session_state.get("config", {}))
        return True
    elif current_page == "search":
        from chat.search_page import display_search_page
        from chat.rag_service import query_rag, query_metadata

        display_search_page(query_rag, query_metadata)
        return True
    elif current_page == "help":
        from chat.help_page import display_help_page

        display_help_page()
        return True
    return False

