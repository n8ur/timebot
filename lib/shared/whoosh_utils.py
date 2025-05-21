# /usr/local/lib/timebot/lib/shared/whoosh_utils.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
from typing import Dict, Any, Optional, List
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import StemmingAnalyzer
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.searching import Searcher
from whoosh.query import Term

# Import from internal implementation modules
from .whoosh_schema import define_whoosh_schema
from .whoosh_index import initialize_whoosh_index, open_whoosh_index, get_index_stats
from .whoosh_document import (
    document_exists_in_whoosh,
    add_document_to_whoosh,
    get_document_by_id,
    get_all_documents,
    delete_document
)
# --- Import from NEW split search modules ---
from .whoosh_search_core import metadata_search, search_whoosh # Keep search_whoosh export for now
from .whoosh_search_helpers import (
    search_sender, search_date_range, search_subject_or_title,
    search_author, search_domain, search_source_url
)
from .whoosh_search_advanced import suggest_corrections, cross_collection_search
# --- End import from NEW split search modules ---

from .email_parser import parse_email_message # Keep this if needed by add_document_to_whoosh

# Define the public interface of this module
__all__ = [
    # Schema
    'define_whoosh_schema',
    # Index
    'initialize_whoosh_index',
    'open_whoosh_index',
    'get_index_stats',
    # Document
    'document_exists_in_whoosh',
    'add_document_to_whoosh',
    'get_document_by_id',
    'get_all_documents',
    'delete_document',
    # Search Core
    'metadata_search',
    'search_whoosh', # Keep deprecated function exported for now
    # Search Helpers
    'search_sender',
    'search_date_range',
    'search_subject_or_title',
    'search_author',
    'search_domain',
    'search_source_url',
    # Search Advanced
    'suggest_corrections',
    'cross_collection_search',
    # Other Utils (if needed by exported functions like add_document_to_whoosh)
    'parse_email_message'
]

