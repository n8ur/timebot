#!/bin/env python3

import os
import sys
import argparse
import hashlib
import torch
from pathlib import Path
from dotenv import load_dotenv
import shutil
import time
import atexit
from typing import List, Dict, Any, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

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

def extract_metadata_and_content(file_path):
    """Extract metadata and content from a technical document text file."""
    metadata = {
        "title": "Unknown",
        "author": "Unknown",
        "publisher": "Unknown",
        "publisher_id": "Unknown",
        "publication_date": "Unknown",
        "source": "Unknown",
        "sequence_number": "Unknown",
        "url": "Unknown",
        "processing_date": "Unknown",
        "file_name": str(file_path),
    }

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    content_start_index = 0
    separator_found = False

    # Look for the metadata section and the separator line
    for i, line in enumerate(lines):
        line = line.strip()

        if line.startswith("Title: "):
            metadata["title"] = line.replace("Title: ", "").strip()
        elif line.startswith("Author: "):
            metadata["author"] = line.replace("Author: ", "").strip()
        elif line.startswith("Publisher: "):
            metadata["publisher"] = line.replace("Publisher: ", "").strip()
        elif line.startswith("Publisher ID: "):
            metadata["publisher_id"] = line.replace("Publisher ID: ", "").strip()
        elif line.startswith("Publication Date: "):
            metadata["publication_date"] = line.replace("Publication Date: ", "").strip()
        elif line.startswith("Source: "):
            metadata["source"] = line.replace("Source: ", "").strip()
        elif line.startswith("Sequence Number: "):
            metadata["sequence_number"] = line.replace("Sequence Number: ", "").strip()
        elif line.startswith("URL: "):
            metadata["url"] = line.replace("URL: ", "").strip()
        elif line.startswith("Processing Date: "):
            metadata["processing_date"] = line.replace("Processing Date: ", "").strip()
        elif line.startswith("-----------------------------------------"):
            separator_found = True
            content_start_index = i + 1
            break

    # If we found the separator, extract content after it
    if separator_found:
        content = "\n".join(lines[content_start_index:]).strip()
    else:
        # If no separator found, assume all content after metadata fields
        # Find the last metadata field
        last_metadata_index = 0
        for i, line in enumerate(lines):
            if any(line.strip().startswith(prefix) for prefix in [
                "Title:", "Author:", "Publisher:", "Publisher ID:",
                "Publication Date:", "Source:", "Sequence Number:",
                "URL:", "Processing Date:"
            ]):
                last_metadata_index = i

        content = "\n".join(lines[last_metadata_index + 1:]).strip()

    # Compute the hash for the original document
    hash_value = compute_hash(content, metadata)
    metadata["hash"] = hash_value

    return content, metadata


def process_single_file(
    txt_file,
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
    """Process a single file for both ChromaDB and Whoosh, then move it to the processed directory."""
    try:
        content, metadata = extract_metadata_and_content(txt_file)

        # Check for duplicates in ChromaDB
        try:
            chunk_hash = metadata["hash"]
            if document_exists(collection_name, chunk_hash):
                sys.stderr.write(
                    f"Skipping (already indexed in ChromaDB): {txt_file}\n"
                    f"  Current file hash: {metadata['hash']}\n"
                    f"  Current file metadata: Title: {metadata['title']}, Author: {metadata['author']}, "
                    f"  URL: {metadata['url']}\n"
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
            chunk_hash = metadata["hash"]
            with whoosh_lock:
                if document_exists_in_whoosh(ix, chunk_hash):
                    sys.stderr.write(
                        f"Skipping (already indexed in Whoosh): {txt_file}\n"
                        f"  Hash: {metadata['hash']}\n"
                    )
                    with stats_lock:
                        stats['total_skipped'] += 1
                    return
        except Exception as e:
            sys.stderr.write(
                f"Error checking Whoosh index for {txt_file}: {e}\n"
            )
            with stats_lock:
                stats['total_errors'] += 1
            return

        if dry_run:
            print(f"Would process: {txt_file}")
            return

        # Chunk the document
        chunks = chunk_document(content, metadata, chunk_size, chunk_overlap)
        
        # Process each chunk
        chunks_processed = 0
        for chunk_text, chunk_metadata in chunks:
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
            
            # Ingest into Whoosh
            try:
                with whoosh_lock:
                    add_document_to_whoosh(writer, chunk_text, chunk_metadata, schema_type="technical", verbose=verbose)
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
        
        # Move file to processed directory
        with file_lock:
            destination = processed_path / txt_file.name
            txt_file.rename(destination)

        # Print only if verbose is enabled
        if verbose:
            print(f"Processed and moved: {txt_file} -> {destination}")
            print(f"Created {chunks_processed} chunks from document")

        with stats_lock:
            stats['total_ingested'] += 1

    except Exception as e:
        sys.stderr.write(f"Error processing {txt_file}: {e}\n")
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
    """Process technical document files for both ChromaDB and Whoosh, then move them to the processed directory."""
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

    # Get the list of .txt files
    txt_files = list(input_path.rglob("*.txt"))

    # Always print the input directory and number of files to process
    print(f"Input directory: {input_path}")
    print(f"Number of files to process: {len(txt_files)}")
    print(f"Nominal chunk size {chunk_size}, overlap {chunk_overlap} tokens")

    if not txt_files:
        sys.stderr.write(
            f"Error: No .txt files found in directory: {input_path}\n"
        )
        return

    # Open or create the ChromaDB collection
    context = open_collection(
        collection_name, db_path, embedding_model_name, force_recreate=force_recreate_collection)
    if context is None:
        sys.stderr.write("Error: Could not initialize ChromaDB.\n")
        return

    # Initialize Whoosh index using the new utility function
    ix = initialize_whoosh_index(index_dir, schema_type="technical")
    writer = ix.writer()

    # Reset statistics
    with stats_lock:
        stats['total_files'] = len(txt_files)
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
        for txt_file in txt_files:
            future = executor.submit(
                process_single_file,
                txt_file,
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
    DOC_TEXT_UNPROCESSED_DIR = config["DOC_TEXT_UNPROCESSED_DIR"]
    DOC_TEXT_PROCESSED_DIR = config["DOC_TEXT_PROCESSED_DIR"]
    CHROMADB_PATH = config["CHROMADB_PATH"]
    CHROMADB_DOC_COLLECTION = config["CHROMADB_DOC_COLLECTION"]
    WHOOSHDB_DOC_PATH = config["WHOOSHDB_DOC_PATH"]
    DOC_CHUNK_SIZE = config["DOC_CHUNK_SIZE"]
    DOC_CHUNK_OVERLAP = config["DOC_CHUNK_OVERLAP"]
    EMBEDDING_MODEL = config["EMBEDDING_MODEL"]
    DRY_RUN = config["DRY_RUN"]
    VERBOSE = config["VERBOSE"]
    
    # Get number of workers from environment or use default
    NUM_WORKERS = int(os.environ.get("NUM_WORKERS", multiprocessing.cpu_count() - 1))

    # Call the processing function with parsed arguments
    process_files(
        DOC_TEXT_UNPROCESSED_DIR,
        DOC_TEXT_PROCESSED_DIR,
        CHROMADB_PATH,
        CHROMADB_DOC_COLLECTION,
        WHOOSHDB_DOC_PATH,
        EMBEDDING_MODEL,
        DOC_CHUNK_SIZE,
        DOC_CHUNK_OVERLAP,
        DRY_RUN,
        VERBOSE,
        num_workers=NUM_WORKERS
    )

