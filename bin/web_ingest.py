#!/bin/env python3
# /usr/local/lib/timebot/bin/web_ingest.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import sys
import argparse
import hashlib
import torch
import yaml
import datetime
import re
from pathlib import Path
import shutil
import time
import atexit
from typing import List, Dict, Any, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from urllib.parse import urlparse

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config

from shared.file_utils import check_or_create_directory
from shared.chromadb_utils import (
    open_collection,
    document_exists,
    add_document,
    close_collection
)
from shared.utils import compute_hash, chunk_document, compute_chunk_hash
from shared.whoosh_utils import (
    initialize_whoosh_index,
    document_exists_in_whoosh,
    add_document_to_whoosh
)

# Global locks and counters for thread safety
whoosh_lock = threading.Lock()
file_lock = threading.Lock()
stats_lock = threading.Lock()

# Shared statistics dictionary
stats = {
    'total_files': 0,
    'total_ingested': 0,
    'total_skipped': 0,
    'total_errors': 0,
    'total_chunks': 0,
    'current_batch': 0
}

# Register cleanup function to run at exit
def cleanup():
    """Ensure proper cleanup when the script exits."""
    print("Running cleanup...")
    
    # Close all ChromaDB collections
    close_collection()
    
    # Check if ChromaDB directory still exists
    if not os.path.exists(CHROMADB_PATH):
        print(f"WARNING: ChromaDB directory no longer exists: {CHROMADB_PATH}")

atexit.register(cleanup)

def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed_url = urlparse(url)
        return parsed_url.netloc
    except Exception as e:
        sys.stderr.write(f"Error extracting domain from URL '{url}': {e}\n")
        return ""

def extract_metadata_and_content(file_path):
    """Extract metadata and content from a web markdown file with YAML frontmatter."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for YAML frontmatter
        frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"No YAML frontmatter found in {file_path}")

        # Parse YAML frontmatter
        yaml_content = frontmatter_match.group(1)
        markdown_content = frontmatter_match.group(2).strip()

        # Process the YAML content line by line to handle problematic quotes
        processed_lines = []
        for line in yaml_content.splitlines():
            # Check if line starts with key: pattern
            key_match = re.match(r'^(\w+):\s*(.*?)$', line)
            if key_match:
                key, value = key_match.groups()
                
                # If value contains quotes, escape them properly
                if '"' in value:
                    # Remove any existing quotes at the beginning and end
                    value = value.strip('"')
                    # Escape any remaining quotes
                    value = value.replace('"', '\\"')
                    # Wrap in quotes
                    processed_lines.append(f'{key}: "{value}"')
                else:
                    # For values without quotes, add quotes to be safe
                    processed_lines.append(f'{key}: "{value}"')
            else:
                processed_lines.append(line)
                
        fixed_yaml = '\n'.join(processed_lines)
        
        try:
            metadata = yaml.safe_load(fixed_yaml)
        except Exception as yaml_error:
            # Fallback to manual parsing if YAML parsing still fails
            metadata = {}
            for line in processed_lines:
                key_match = re.match(r'^(\w+):\s*"(.*?)"$', line)
                if key_match:
                    key, value = key_match.groups()
                    metadata[key] = value

        # Ensure required fields exist
        if 'source_url' not in metadata:
            raise ValueError(f"Missing required field 'source_url' in {file_path}")

        # Convert datetime objects to strings
        for key, value in list(metadata.items()):
            if isinstance(value, datetime.datetime):
                metadata[key] = value.isoformat()

        # Extract domain from source_url if not already in metadata
        if 'domain' not in metadata:
            metadata['domain'] = extract_domain(metadata['source_url'])

        # Add file path to metadata
        metadata["file_name"] = str(file_path)

        # Generate a hash for the document based on source_url and content
        hash_input = f"{metadata['source_url']}|{markdown_content}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
        metadata["hash"] = hash_value

        return markdown_content, metadata

    except Exception as e:
        sys.stderr.write(f"Error extracting metadata from {file_path}: {e}\n")
        raise

def check_and_remove_empty_parents(directory, root_dir, verbose=False):
    """
    Recursively check and remove empty parent directories up to the root directory.
    
    Args:
        directory: The directory to check
        root_dir: The root directory to stop at (won't be removed)
        verbose: Whether to print verbose output
    """
    try:
        # Stop if we've reached the root directory
        if directory.samefile(root_dir):
            return
        
        # Check if directory is empty
        if not any(directory.iterdir()):
            try:
                # Try to remove the directory
                directory.rmdir()
                if verbose:
                    print(f"Removed empty parent directory: {directory}")
                
                # Recursively check the parent
                check_and_remove_empty_parents(directory.parent, root_dir, verbose)
            except OSError as e:
                # Directory might not be empty if another thread added files
                if verbose:
                    print(f"Could not remove parent directory {directory}: {e}")
    except Exception as e:
        sys.stderr.write(f"Error checking/removing parent directory {directory}: {e}\n")

def process_single_file(
    md_file,
    processed_path,
    collection_name,
    ix,
    writer,
    chunk_size,
    chunk_overlap,
    dry_run,
    verbose,
    batch_size
):
    """Process a single markdown file for both ChromaDB and Whoosh, then move it to the processed directory."""
    try:
        content, metadata = extract_metadata_and_content(md_file)
        
        # Set doc_type to "web" for all web documents
        metadata["doc_type"] = "web"  # Add this line to set the document type

        # Check for duplicates in ChromaDB
        try:
            doc_hash = metadata["hash"]
            if document_exists(collection_name, doc_hash):
                # If the document exists, we need to check if it's changed
                # For now, we'll just skip it, but in a future version we could
                # implement a change detection mechanism
                if verbose:
                    sys.stderr.write(
                        f"Skipping (already indexed in ChromaDB): {md_file}\n"
                        f"  Current file hash: {metadata['hash']}\n"
                        f"  Current file metadata: Title: {metadata.get('title', 'Unknown')}, "
                        f"  URL: {metadata.get('source_url', 'Unknown')}\n"
                    )
                with stats_lock:
                    stats['total_skipped'] += 1
                return
        except Exception as e:
            sys.stderr.write(
                f"Error checking ChromaDB for duplicates: {e}\n"
            )
            with stats_lock:
                stats['total_errors'] += 1
            return

        # Check if the file is already indexed in Whoosh
        try:
            doc_hash = metadata["hash"]
            with whoosh_lock:
                if document_exists_in_whoosh(ix, doc_hash):
                    if verbose:
                        sys.stderr.write(
                            f"Skipping (already indexed in Whoosh): {md_file}\n"
                            f"  Hash: {metadata['hash']}\n"
                        )
                    with stats_lock:
                        stats['total_skipped'] += 1
                    return
        except Exception as e:
            sys.stderr.write(
                f"Error checking Whoosh index for {md_file}: {e}\n"
            )
            with stats_lock:
                stats['total_errors'] += 1
            return

        if dry_run:
            print(f"Would process: {md_file}")
            return

        # Chunk the document
        chunks = chunk_document(content, metadata, chunk_size, chunk_overlap)
        
        # Process each chunk
        chunks_processed = 0
        for chunk_text, chunk_metadata in chunks:
            # Ensure each chunk has doc_type set to "web"
            chunk_metadata["doc_type"] = "web"  # Add this line to set the document type for each chunk
            
            # Ensure domain is extracted and set if not already present
            if "domain" not in chunk_metadata and "source_url" in chunk_metadata:
                chunk_metadata["domain"] = extract_domain(chunk_metadata["source_url"])
                if verbose:
                    print(f"Extracted domain '{chunk_metadata['domain']}' from source_url '{chunk_metadata['source_url']}'")
            
            # Compute hash for this chunk
            chunk_hash = compute_chunk_hash(chunk_text, chunk_metadata)
            chunk_metadata["hash"] = chunk_hash
            
            # Check for duplicates in ChromaDB *before* adding
            try:
                if document_exists(collection_name, chunk_hash):
                    if verbose:
                        print(f"ChromaDB Chunk Duplicate Found! Hash: {chunk_hash}")
                    with stats_lock:
                        stats['total_skipped'] += 1
                    continue  # Skip adding the chunk
            except Exception as e:
                sys.stderr.write(f"Error checking ChromaDB for chunk duplicates: {e}\n")
                with stats_lock:
                    stats['total_errors'] += 1
                continue

            # Check for duplicates in Whoosh *before* adding
            try:
                with whoosh_lock:
                    if document_exists_in_whoosh(ix, chunk_hash):
                        if verbose:
                            print(f"Whoosh Chunk Duplicate Found! Hash: {chunk_hash}")
                        with stats_lock:
                            stats['total_skipped'] += 1
                        continue  # Skip adding the chunk
            except Exception as e:
                sys.stderr.write(f"Error checking Whoosh for chunk duplicates: {e}\n")
                with stats_lock:
                    stats['total_errors'] += 1
                continue
            
            # Ingest into ChromaDB
            try:
                add_document(collection_name, chunk_text, chunk_metadata, verbose)
                with stats_lock:
                    stats['current_batch'] += 1
            except Exception as e:
                sys.stderr.write(f"Error ingesting chunk into ChromaDB: {e}\n")
                with stats_lock:
                    stats['total_errors'] += 1
                continue
            
            # Prepare metadata for Whoosh indexing
            # Map the metadata fields to match the Whoosh schema fields
            whoosh_metadata = {
                "hash": chunk_metadata["hash"],  # Use hash as doc_id
                "content": chunk_text,
                "source_url": chunk_metadata.get("source_url", ""),
                "domain": chunk_metadata.get("domain", ""),
                "title": chunk_metadata.get("title", ""),
                "captured_at": chunk_metadata.get("captured_at", "")
            }
            
            # Ingest into Whoosh
            try:
                with whoosh_lock:
                    add_document_to_whoosh(writer, chunk_text, whoosh_metadata, schema_type="web", verbose=verbose)
            except Exception as e:
                sys.stderr.write(f"Error ingesting chunk into Whoosh: {e}\n")
                with stats_lock:
                    stats['total_errors'] += 1
                continue
            
            chunks_processed += 1
            with stats_lock:
                stats['total_chunks'] += 1
                
                # Commit in batches to ensure persistence
                if stats['current_batch'] >= batch_size:
                    print(".", end="", flush=True)
                    # Sleep briefly to allow persistence
                    time.sleep(0.1)
                    stats['current_batch'] = 0
        
        # Create the same directory structure in the processed directory
        relative_path = md_file.relative_to(Path(WEB_TEXT_UNPROCESSED_DIR))
        destination_dir = processed_path / relative_path.parent
        destination_dir.mkdir(parents=True, exist_ok=True)
        
        # Move file to processed directory
        with file_lock:
            destination = destination_dir / md_file.name
            md_file.rename(destination)
            
            # Check if the source directory is now empty and remove it if so
            source_dir = md_file.parent
            try:
                # Check if directory is empty (no files)
                if not any(source_dir.iterdir()):
                    try:
                        # Try to remove the directory
                        source_dir.rmdir()
                        if verbose:
                            print(f"Removed empty directory: {source_dir}")
                        
                        # Check parent directories recursively
                        check_and_remove_empty_parents(source_dir.parent, Path(WEB_TEXT_UNPROCESSED_DIR), verbose)
                    except OSError as e:
                        # Directory might not be empty if another thread added files
                        if verbose:
                            print(f"Could not remove directory {source_dir}: {e}")
            except Exception as dir_e:
                sys.stderr.write(f"Error checking/removing directory {source_dir}: {dir_e}\n")

        # Print only if verbose is enabled
        if verbose:
            print(f"Processed and moved: {md_file} -> {destination}")
            print(f"Created {chunks_processed} chunks from document")

        with stats_lock:
            stats['total_ingested'] += 1

    except Exception as e:
        sys.stderr.write(f"Error processing {md_file}: {e}\n")
        if 'metadata' in locals():
            sys.stderr.write(f"  Metadata at time of error: {metadata}\n")
        else:
            sys.stderr.write("  Metadata was not defined at time of error.\n")
        with stats_lock:
            stats['total_errors'] += 1



def process_files(
    input_dir,
    processed_dir,
    db_path,
    collection_name,
    index_dir,
    embedding_model_name,
    chunk_size=1000,
    chunk_overlap=200,
    dry_run=False,
    verbose=False,
    force_recreate_collection=False,
    num_workers=None
):
    """Process web markdown files for both ChromaDB and Whoosh, then move them to the processed directory."""
    input_path = Path(input_dir)
    processed_path = Path(processed_dir)

    # Determine number of workers if not specified
    if num_workers is None:
        # Use CPU count - 1 to leave one core free for system tasks
        num_workers = max(1, multiprocessing.cpu_count() - 1)
    
    print(f"Using {num_workers} worker threads")

    # Check if the input directory exists
    if not input_path.exists():
        sys.stderr.write(
            f"Error: Input directory does not exist: {input_path}\n"
        )
        return

    # Ensure the processed directory exists
    processed_path.mkdir(parents=True, exist_ok=True)

    # Get the list of .md files
    md_files = list(input_path.rglob("*.md"))

    # Always print the input directory and number of files to process
    print(f"Input directory: {input_path}")
    print(f"Number of files to process: {len(md_files)}")
    print(f"Nominal chunk size {chunk_size}, overlap {chunk_overlap} tokens")

    if not md_files:
        sys.stderr.write(
            f"Error: No .md files found in directory: {input_path}\n"
        )
        return

    # Open or create the ChromaDB collection
    context = open_collection(
        collection_name, db_path, embedding_model_name, force_recreate=force_recreate_collection)
    if context is None:
        sys.stderr.write("Error: Could not initialize ChromaDB.\n")
        return

    # Initialize Whoosh index using the new utility function
    ix = initialize_whoosh_index(index_dir, schema_type="web")
    writer = ix.writer()

    # Reset statistics
    with stats_lock:
        stats['total_files'] = len(md_files)
        stats['total_ingested'] = 0
        stats['total_skipped'] = 0
        stats['total_errors'] = 0
        stats['total_chunks'] = 0
        stats['current_batch'] = 0
    
    batch_size = 250

    print("Processing files...")
    
    # Process files in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all files to the thread pool
        futures = []
        for md_file in md_files:
            future = executor.submit(
                process_single_file,
                md_file,
                processed_path,
                collection_name,
                ix,
                writer,
                chunk_size,
                chunk_overlap,
                dry_run,
                verbose,
                batch_size
            )
            futures.append(future)
        
        # Wait for all tasks to complete and handle any exceptions
        for future in futures:
            try:
                future.result()
            except Exception as e:
                sys.stderr.write(f"Unhandled exception in worker thread: {e}\n")
                with stats_lock:
                    stats['total_errors'] += 1

    # Commit Whoosh changes
    with whoosh_lock:
        writer.commit()

    # Print summary
    print("\n**Ingestion Summary**")
    print(f"Total files scanned: {stats['total_files']}")
    print(f"Total documents ingested: {stats['total_ingested']}")
    print(f"Total chunks created: {stats['total_chunks']}")
    print(f"Total skipped: {stats['total_skipped']}")
    print(f"Total errors encountered: {stats['total_errors']}")


if __name__ == "__main__":
    # Load configuration
    WEB_TEXT_UNPROCESSED_DIR = config["WEB_TEXT_UNPROCESSED_DIR"]
    WEB_TEXT_PROCESSED_DIR = config["WEB_TEXT_PROCESSED_DIR"]
    CHROMADB_PATH = config["CHROMADB_PATH"]
    CHROMADB_WEB_COLLECTION = config["CHROMADB_WEB_COLLECTION"]
    WHOOSHDB_WEB_PATH = config["WHOOSHDB_WEB_PATH"]
    WEB_CHUNK_SIZE = config["WEB_CHUNK_SIZE"]
    WEB_CHUNK_OVERLAP = config["WEB_CHUNK_OVERLAP"]
    EMBEDDING_MODEL = config["EMBEDDING_MODEL"]
    DRY_RUN = config["DRY_RUN"]
    VERBOSE = config["VERBOSE"]
    
    # Get number of workers from environment or use default
    NUM_WORKERS = int(os.environ.get("NUM_WORKERS", multiprocessing.cpu_count() - 1))

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Ingest web markdown files into ChromaDB and Whoosh")
    parser.add_argument("--force-recreate", action="store_true", help="Force recreate the ChromaDB collection")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually ingest, just show what would be done")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--workers", type=int, help="Number of worker threads to use")
    parser.add_argument("--chunk-size", type=int, help="Size of chunks in tokens")
    parser.add_argument("--chunk-overlap", type=int, help="Overlap between chunks in tokens")
    
    args = parser.parse_args()
    
    # Command line args override config
    if args.dry_run:
        DRY_RUN = True
    if args.verbose:
        VERBOSE = True
    if args.workers:
        NUM_WORKERS = args.workers
    if args.chunk_size:
        WEB_CHUNK_SIZE = args.chunk_size
    if args.chunk_overlap:
        WEB_CHUNK_OVERLAP = args.chunk_overlap

    # Call the processing function with parsed arguments
    process_files(
        WEB_TEXT_UNPROCESSED_DIR,
        WEB_TEXT_PROCESSED_DIR,
        CHROMADB_PATH,
        CHROMADB_WEB_COLLECTION,
        WHOOSHDB_WEB_PATH,
        EMBEDDING_MODEL,
        WEB_CHUNK_SIZE,
        WEB_CHUNK_OVERLAP,
        DRY_RUN,
        VERBOSE,
        args.force_recreate,
        num_workers=NUM_WORKERS
    )

