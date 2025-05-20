#!/bin/env python3

import os
import sys
import argparse
import hashlib
import torch
from pathlib import Path

import shutil
import time
import atexit
from typing import List, Dict, Any, Optional

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
from shared.utils import compute_hash
from shared.whoosh_utils import (
    initialize_whoosh_index,
    document_exists_in_whoosh,
    add_document_to_whoosh
)

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
    """Extract metadata (Subject, From, Date, URL) and content from a cleaned email text file."""
    from shared.email_parser import parse_email_message

    with open(file_path, "r", encoding="utf-8") as f:
        raw_message = f.read()

    # Use the specialized parser to extract metadata and content
    metadata, content = parse_email_message(raw_message)

    # Add the file name to metadata
    metadata["file_name"] = str(file_path)

    # Compute hash
    hash_value = compute_hash(content, metadata)
    metadata["hash"] = hash_value

    return content, metadata


def process_files(
    input_dir,
    processed_dir,
    db_path,
    collection_name,
    index_dir,
    embedding_model_name,
    dry_run=False,
    verbose=False,
    force_recreate_collection=False
):
    """Process files for both ChromaDB and Whoosh, then move them to the processed directory."""
    input_path = Path(input_dir)
    processed_path = Path(processed_dir)

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
    ix = initialize_whoosh_index(index_dir, schema_type="email")
    writer = ix.writer()

    # Process files
    total_files = 0
    total_ingested = 0
    total_skipped = 0
    total_errors = 0
    batch_size = 250
    current_batch = 0

    print("Processing files...")
    for txt_file in txt_files:
        total_files += 1
        try:
            content, metadata = extract_metadata_and_content(txt_file)
            # Note: file_name is now added in extract_metadata_and_content

            # Check for duplicates in ChromaDB
            try:
                if document_exists(collection_name, metadata["hash"]):
                    sys.stderr.write(
                        f"Skipping (already indexed in ChromaDB): {txt_file}\n"
                        f"  Current file hash: {metadata['hash']}\n"
                        f"  Current file metadata: From: {metadata['from_']}, Date: {metadata['date']}, "
                        f"  Subject: {metadata['subject']}, URL: {metadata['url']}\n"
                    )
                    total_skipped += 1
                    continue
            except Exception as e:
                sys.stderr.write(
                    f"Error checking ChromaDB for duplicates: {e}\n"
                )
                total_errors += 1
                continue

            # Check if the file is already indexed in Whoosh using the new utility function
            try:
                if document_exists_in_whoosh(ix, metadata["hash"]):
                    sys.stderr.write(
                        f"Skipping (already indexed in Whoosh): {txt_file}\n"
                        f"  Hash: {metadata['hash']}\n"
                    )
                    total_skipped += 1
                    continue
            except Exception as e:
                sys.stderr.write(
                    f"Error checking Whoosh index for {txt_file}: {e}\n"
                )
                total_errors += 1
                continue

            if dry_run:
                print(f"Would process: {txt_file}")
                continue

            # Ingest into ChromaDB using the new function
            try:
                add_document(collection_name, content, metadata, verbose)
                current_batch += 1
            except Exception as e:
                sys.stderr.write(f"Error ingesting into ChromaDB: {e}\n")
                total_errors += 1
                continue

            # Ingest into Whoosh using the new utility function
            add_document_to_whoosh(writer, content, metadata, schema_type="email", verbose=verbose)

            # Move file to processed directory
            destination = processed_path / txt_file.name
            txt_file.rename(destination)

            # Print only if verbose is enabled
            if verbose:
                print(f"Processed and moved: {txt_file} -> {destination}")

            total_ingested += 1

            # Commit in batches to ensure persistence
            if current_batch >= batch_size:
                print(".", end="",flush=True)
                # Sleep briefly to allow persistence
                time.sleep(1)
                current_batch = 0

        except Exception as e:
            sys.stderr.write(f"Error processing {txt_file}: {e}\n")
            if 'metadata' in locals():
                sys.stderr.write(f"  Metadata at time of error: {metadata}\n")
            else:
                sys.stderr.write("  Metadata was not defined at time of error.\n")
            total_errors += 1

    # Commit Whoosh changes
    writer.commit()

    # Print summary
    print("\n**Ingestion Summary**")
    print(f"Total files scanned: {total_files}")
    print(f"Total ingested: {total_ingested}")
    print(f"Total skipped: {total_skipped}")
    print(f"Total errors encountered: {total_errors}")


if __name__ == "__main__":
    # Define ChromaDB path for cleanup
    EMAIL_TEXT_UNPROCESSED_DIR = config["EMAIL_TEXT_UNPROCESSED_DIR"]
    EMAIL_TEXT_PROCESSED_DIR = config["EMAIL_TEXT_PROCESSED_DIR"]
    CHROMADB_PATH = config["CHROMADB_PATH"]
    CHROMADB_EMAIL_COLLECTION = config["CHROMADB_EMAIL_COLLECTION"]
    WHOOSHDB_EMAIL_PATH = config["WHOOSHDB_EMAIL_PATH"]
    EMBEDDING_MODEL = config["EMBEDDING_MODEL"]
    DRY_RUN = config["DRY_RUN"]
    VERBOSE = config["VERBOSE"]

    # Call the processing function with parsed arguments
    process_files(
        EMAIL_TEXT_UNPROCESSED_DIR,
        EMAIL_TEXT_PROCESSED_DIR,
        CHROMADB_PATH,
        CHROMADB_EMAIL_COLLECTION,
        WHOOSHDB_EMAIL_PATH,
        EMBEDDING_MODEL,
        DRY_RUN,
        VERBOSE,
    )

