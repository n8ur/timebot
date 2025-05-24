# /usr/local/lib/timebot/lib/chat/info_page.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# info_page.py - Information page for the Timebot application

import streamlit as st
import json
import os
import logging
from chat.ui import create_sidebar, set_font_size

logger = logging.getLogger(__name__)


def tuple_to_string(my_tuple):
    """Safely converts a tuple of strings to a string.
    Handles the case of the key missing and avoids IndexError.
    """
    if not my_tuple:  # Key missing or tuple is empty
        return ""
    else:
        return "".join(my_tuple)  # Join only if the tuple exists and isn't empty


def display_info_page(config):
    """
    Display the Information and Sources page

    Args:
        config: Dictionary containing application configuration
    """
    # Set font size
    set_font_size()

    # Add the sidebar to the info page
    create_sidebar()

    st.title("About Timebot")

    st.markdown(
        """
    Timebot is an AI assistant specialized in time and frequency measurement 
    topics.  It draws its specialized knowledge from three primary collections:

    1.  **Time-Nuts Mailing List Archive:** The complete public archive of 
    the [time-nuts](http://leapsecond.com/time-nuts.htm) mailing list, 
    encompassing over 20 years and currently including nearly 110,000 messages. 
    All messages were publicly posted to the list.
    2.  **Technical Document Collection:** A curated set of currently 
    over 3000 relevant technical publications, application notes, 
    equipment manuals, and other reference materials.
    3.  **Selected Web Sites:** Pages from several web sites devoted to
    time-and-frequency topics.  Currently, relevant portions of the
    febo.com, leapsecond.com, ke5fx.com, and wriley.com sites are
    included.

    **Document Sources:**
    The bulk of the technical document collection comes from two 
    publicly-available sources:
    *   The **NIST publications archive**, currently covering roughly 
    2010-2024.
    *   The **PTTI (Precise Time and Time Interval) proceedings**, 
    currently covering papers from 1969-2018 (most papers since 2012 
    are unavailable due to copyright).
    
    The document collection also includes numerous application notes
    and manuals from Hewlett-Packard and other manufacturers, as well
    as over 100 papers from the wriley.com (Stable32) web site.


    ### How Timebot Answers Queries (Retrieval-Augmented Generation - RAG)
    Timebot uses RAG to provide expert responses.  Your query first goes
    to the database where the most relevant documents (default number 10) 
    are returned.  The server then sends your query, along with those
    results, to the AI (a large language model), essentially saying,
    "Here's a question, and here is some context that might help you
    answer it."

    If you're interested in more detail, these are the steps that occur:

    1.  **Retrieval:** This is now a multi-step process.

    1a. Your query is sent to an LLM that is instructed to review and
    enhance it to generate more relevant results from the database search.
    It does things like expand abbreviations and provide additional content
    for the semantic search to work with.

    1b. The enhanced query is run against both the vector database 
    (for semantic relevance) and the full-text index (for keyword matches) 
    to find potentially relevant emails and document chunks from the 
    knowledge base.

    2.  **Reranking:** The initial results from both indexes are combined and 
    then re-evaluated by a separate reranking model. This model scores and 
    reorders the results to prioritize the most relevant items for your 
    specific query.

    3.  **Context Assembly:** The 10 highest-ranked results (a mix of 
    email, document, and web chunks) are selected as context for your query.

    4.  **LLM Prompting:** Your original query *and* the context documents
    are sent to a Large Language Model (LLM). Timebot currently uses Google's 
    `Gemini-2.0-Flash` LLM.  (NOTE: your *original* query is sent, not the
    enhanced version used for the RAG retrieval step above.)

    5.  **Generation:** The LLM synthesizes an answer based *both* on the 
    provided context from the knowledge base *and* its own general knowledge. 
    Citations linking back to the source emails or documents are included 
    where possible.

    6.  **Follow-up queries:** If you submit a follow up query, that query is
    enhanced to clarify ambiguities (e.g., if the follow-up refers to "it", that
    is expanded to tie back to the subject of the prior query), a new database 
    search is run, and the enhanced query, chat history, and new context documents 
    are all sent to the LLM for processing.

    **Important Note:** This RAG process uses the knowledge base only for 
    the current query. The LLM is not permanently "trained" on this data; 
    the retrieved information is provided temporarily for each specific 
    question and then discarded.

    ### Data Processing and Indexing
    To make the knowledge base searchable, it went through several
    processing steps:

    *   **OCR Conversion:** Documents originally in PDF format were converted 
    to plain text using Google's Vision AI service (Optical Character 
    Recognition). OCR quality can vary, especially with older scans, 
    potentially introducing errors.
    *   **Content Structuring:**
        *   Emails from the `time-nuts` archive are treated as 
        single, complete items.
        *   Technical documents and web pages are segmented into 
        overlapping "chunks" of approximately 400 words each. Chunking 
        helps isolate relevant passages within longer documents.
    *   **Indexing:**
        Both the `time-nuts` emails and the document/web chunks are 
        indexed in two ways to facilitate effective retrieval:
        *   **Vector Index:** Content is converted into numerical 
        representations (embeddings) using an embedding model, and
        those embeddings are added to a Chroma vector database.
        This allows for semantic search (finding content based on 
        meaning and context, not just keywords).
        *   **Full-Text Index:** A traditional keyword-based index is 
        also created for fast lexical searches.  The Whoosh database
        library is used for that.

    ## Traceability
    I think it's very important that all the references Timebot uses
    are traceable back to the original documents.  For each reference
    cited in an answer, the metadata are provided, along with a link
    to the original source.  For emails the links are to the original
    message in the febo.com archive.  For documents, the original PDF
    is stored on febo.com and there is a link to its location.  For web
    pages, the URL of the page is linked.

    ## Metadata

    Metadata associated with the documents (like titles, authors, 
    and subjects) was extracted using OCR or entered manually and may 
    contain transcription errors. For definitive information or the full 
    original context, please refer to the original source document via
    the link referred to above.

    ## Code Availability

    The Python source code for Timebot will be publicly available
    as soon as it's been tested a bit better.  At that time I'll 
    add a link here to the github repo where it may be downloaded.  
    All components used in the system are open source and royalty 
    free, except the LLM which uses a paid-for API key.

    ## Limitations
    
    While Timebot strives for accuracy, please note:
    
    - It may not have access to the most recent publications or developments
    - The OCR process may result in errors
    - Complex technical questions might require simplification
    - For critical applications, always verify information with primary sources
    
    ## Contact
    For questions, feedback, or suggestions, please contact:
    John Ackermann -- jra at febo dot com
    """
    )
