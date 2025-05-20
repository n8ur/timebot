# utils.py

import hashlib
from typing import List, Dict, Any, Tuple
import re
import copy

# Configurable file prefix for document filenames
FILE_PREFIX = "timebot-"

from config import DOC_BASE_URL

def make_prefixed_document_url(file_name: str) -> str:
    """
    Ensure the filename is prefixed and return the correct download URL for documents using DOC_BASE_URL.
    Args:
        file_name: The raw filename from metadata
    Returns:
        The formatted download URL (e.g., 'https://febo.com/timebot_docs/timebot-foo.pdf')
    """
    if not file_name:
        return "#"
    if not file_name.startswith(FILE_PREFIX):
        file_name = f"{FILE_PREFIX}{file_name}"
    # Remove any leading slash from file_name
    file_name = file_name.lstrip("/")
    base_url = DOC_BASE_URL.rstrip('/')
    return f"{base_url}/{file_name}"

def ensure_timebot_prefix(filename: str) -> str:
    """
    Ensure the filename starts with the configured FILE_PREFIX.
    If it already does, return as-is. Otherwise, prepend FILE_PREFIX.
    """
    if filename.startswith(FILE_PREFIX):
        return filename
    return f"{FILE_PREFIX}{filename}"

def strip_timebot_prefix(filename: str) -> str:
    """
    Remove FILE_PREFIX from filename if present.
    """
    if filename.startswith(FILE_PREFIX):
        return filename[len(FILE_PREFIX) :]
    return filename

def make_timebot_filename(seq_num: int, ext: str) -> str:
    """
    Generate a filename in the format '<FILE_PREFIX><seq_num>.<ext>'
    """
    return f"{FILE_PREFIX}{seq_num}.{ext.lstrip('.')}"


def compute_hash(content, metadata):
    """
    Generate a SHA256 hash for a given content string and metadata.
    This ensures uniqueness even if the content is empty.
    """
    # Normalize content and metadata fields
    normalized_content = content.strip() if content else ""
    from_field = metadata.get('from_', '').strip()
    date_field = metadata.get('date', '').strip()
    subject_field = metadata.get('subject', '').strip()
    url_field = metadata.get('url', '').strip()
    file_name = metadata.get('file_name', '').strip()

    # Create hash input with all available fields
    hash_input = f"{normalized_content}|{from_field}|{date_field}|{subject_field}|{url_field}|{file_name}"

    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

def compute_chunk_hash(chunk_text: str, chunk_metadata: Dict[str, Any]) -> str:
    """
    Generate a SHA256 hash for a document chunk.

    Args:
        chunk_text: The text content of the chunk
        chunk_metadata: The metadata for the chunk

    Returns:
        A SHA256 hash string
    """
    # Normalize content
    normalized_content = chunk_text.strip() if chunk_text else ""

    # Get chunk-specific identifiers
    parent_hash = chunk_metadata.get('parent_hash', '')
    chunk_number = chunk_metadata.get('chunk_number', 0)

    # Create hash input with chunk-specific information
    hash_input = f"{normalized_content}|{parent_hash}|{chunk_number}"

    # Add other relevant metadata fields if available
    for field in ['title', 'author', 'date', 'file_name']:
        if field in chunk_metadata:
            hash_input += f"|{chunk_metadata.get(field, '').strip()}"

    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

def chunk_document(
    text: str,
    metadata: Dict[str, Any],
    chunk_size: int = 500,
    chunk_overlap: int = 75,
    size_flexibility: float = 0.15
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Split a document into chunks with intelligent boundary detection for technical documents.
    
    Args:
        text: The document text to chunk
        metadata: The document metadata to be included with each chunk
        chunk_size: Target number of tokens per chunk
        chunk_overlap: Number of tokens to overlap between chunks
        size_flexibility: Fraction of chunk_size to allow flexibility (0.15 = ±15%)
        
    Returns:
        List of (chunk_text, chunk_metadata) tuples
    """
    # Simple tokenization by splitting on whitespace
    tokens = re.findall(r'\S+|\n', text)
    
    # If the document is smaller than the chunk size, return it as is
    if len(tokens) <= chunk_size:
        return [(text, metadata)]
    
    # Precompute token properties to avoid repeated analysis
    # Common abbreviations in technical documents
    abbreviations = {
        'fig.', 'eq.', 'ref.', 'no.', 'nos.', 'al.', 'etc.', 'e.g.', 'i.e.',
        'vs.', 'v.', 'ch.', 'sec.', 'pp.', 'ca.', 'approx.', 'app.',
        'min.', 'max.', 'temp.', 'vol.', 'freq.', 'spec.', 'ver.'
    }
    
    token_properties = []
    for i, token in enumerate(tokens):
        is_newline = (token == '\n')
        ends_with_period = token.endswith('.') if not is_newline else False
        ends_with_question = token.endswith('?') if not is_newline else False
        ends_with_exclamation = token.endswith('!') if not is_newline else False
        ends_with_semicolon = token.endswith(';') if not is_newline else False
        ends_with_colon = token.endswith(':') if not is_newline else False
        
        # Check if it's a numbered list item or single letter abbreviation
        is_numbered_list = False
        is_single_letter_abbr = False
        is_abbreviation = False
        
        if ends_with_period:
            is_numbered_list = bool(re.match(r'^\d+\.$', token))
            is_single_letter_abbr = bool(re.match(r'^[A-Za-z]\.$', token))
            is_abbreviation = token.lower() in abbreviations
        
        # Check if it's a section break
        is_section_break = bool(re.match(r'^[-=*]{3,}$', token)) if not is_newline else False
        
        # Store properties
        token_properties.append({
            'is_newline': is_newline,
            'ends_with_period': ends_with_period,
            'ends_with_question': ends_with_question,
            'ends_with_exclamation': ends_with_exclamation,
            'ends_with_semicolon': ends_with_semicolon,
            'ends_with_colon': ends_with_colon,
            'is_numbered_list': is_numbered_list,
            'is_single_letter_abbr': is_single_letter_abbr,
            'is_abbreviation': is_abbreviation,
            'is_section_break': is_section_break
        })
    
    # Function to find the best boundary in a range
    def find_best_boundary(min_idx, max_idx):
        # Ensure min_idx <= max_idx
        if min_idx > max_idx:
            min_idx = max_idx
            
        # Prioritize paragraph breaks
        for i in range(min_idx, min(max_idx, len(tokens) - 1)):
            if (token_properties[i]['is_newline'] and 
                i + 1 < len(tokens) and token_properties[i + 1]['is_newline']):
                return i + 2
        
        # Look for sentence boundaries
        for i in range(min_idx, min(max_idx, len(tokens) - 1)):
            props = token_properties[i]
            if ((props['ends_with_period'] or props['ends_with_question'] or 
                 props['ends_with_exclamation']) and
                not props['is_abbreviation'] and
                not props['is_numbered_list'] and
                not props['is_single_letter_abbr']):
                
                # Check if next token starts with uppercase or is a newline
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    if token_properties[i + 1]['is_newline'] or (next_token and next_token[0:1].isupper()):
                        return i + 1
        
        # Look for other natural breaks
        for i in range(min_idx, min(max_idx, len(tokens))):
            props = token_properties[i]
            if (props['is_newline'] or props['ends_with_semicolon'] or 
                props['ends_with_colon'] or props['is_section_break']):
                return i + 1
        
        # No good boundary found, use target size
        return None
    
    chunks = []
    start_idx = 0
    
    # Create a shallow copy of metadata base to avoid deep copying each time
    metadata_base = metadata.copy()
    if "hash" in metadata_base:
        parent_hash = metadata_base["hash"]
        del metadata_base["hash"]
    else:
        parent_hash = ""
    
    # Safety counter to prevent infinite loops
    max_iterations = len(tokens) * 2  # Should never need more iterations than this
    iteration_count = 0
    
    while start_idx < len(tokens) and iteration_count < max_iterations:
        iteration_count += 1
        
        # Calculate the target end index for this chunk
        target_end_idx = min(start_idx + chunk_size, len(tokens))
        
        # Define the flexibility range
        min_end_idx = max(start_idx + int(chunk_size * (1 - size_flexibility)), start_idx + 1)
        max_end_idx = min(start_idx + int(chunk_size * (1 + size_flexibility)), len(tokens))
        
        # Ensure min_end_idx <= max_end_idx
        min_end_idx = min(min_end_idx, max_end_idx)
        
        # If we're near the end of the document, just include everything remaining
        if target_end_idx >= len(tokens) - chunk_overlap:
            end_idx = len(tokens)
        else:
            # Find the best boundary
            best_boundary = find_best_boundary(min_end_idx, max_end_idx)
            end_idx = best_boundary if best_boundary else target_end_idx
        
        # Ensure end_idx is valid
        end_idx = min(end_idx, len(tokens))
        
        # Get the tokens for this chunk
        chunk_tokens = tokens[start_idx:end_idx]
        
        # Skip empty chunks
        if not chunk_tokens:
            start_idx = min(end_idx + 1, len(tokens))
            continue
        
        # Reconstruct the text from tokens
        chunk_text = " ".join(chunk_tokens).replace(" \n ", "\n").replace("\n ", "\n")
        
        # Create metadata for this chunk
        chunk_metadata = metadata_base.copy()
        
        # Add chunk-specific metadata
        chunk_number = len(chunks) + 1
        chunk_metadata["chunk_number"] = chunk_number
        chunk_metadata["is_chunk"] = True
        chunk_metadata["parent_hash"] = parent_hash
        chunk_metadata["chunk_id"] = f"{parent_hash}_{chunk_number}"
        
        chunks.append((chunk_text, chunk_metadata))
        
        # Move to the next chunk, accounting for overlap
        next_start_idx = end_idx - chunk_overlap
        
        # Ensure we make progress
        if next_start_idx <= start_idx:
            next_start_idx = start_idx + (chunk_size // 2) #  Aggressive Advance!
        
        start_idx = next_start_idx
    
    # Update total_chunks in all chunk metadata
    total_chunks = len(chunks)
    for i in range(len(chunks)):
        chunks[i][1]["total_chunks"] = total_chunks
    
    return chunks

