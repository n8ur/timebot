#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/chromadb_email_metadata.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import sys
import argparse
import chromadb
from collections import Counter

def display_chromadb_email_metadata(collection_name, db_path):
    """
    Display the metadata layout and a sample document from a ChromaDB email collection.
    Compatible with ChromaDB v0.6.0
    
    Args:
        collection_name: Name of the ChromaDB collection
        db_path: Path to the ChromaDB directory
    """
    try:
        # Initialize the client
        client = chromadb.PersistentClient(path=db_path)
        
        # Check if collection exists
        all_collections = client.list_collections()
        if collection_name not in all_collections:
            print(f"Collection '{collection_name}' not found. Available collections: {all_collections}")
            return
        
        # Get the collection
        collection = client.get_collection(name=collection_name)
        
        # Get collection info
        print(f"=== ChromaDB Email Collection: {collection_name} ===")
        
        # Get all documents to analyze metadata structure
        results = collection.get(include=["metadatas", "documents"])
        
        if not results["ids"]:
            print("\nNo documents found in the collection.")
            return
        
        # Count total documents
        doc_count = len(results["ids"])
        print(f"\nTotal Documents: {doc_count}")
        
        # Analyze metadata fields across all documents
        all_metadata_fields = set()
        field_counts = Counter()
        
        for metadata in results["metadatas"]:
            fields = set(metadata.keys())
            all_metadata_fields.update(fields)
            field_counts.update(fields)
        
        print("\nMetadata Fields (with occurrence count):")
        for field in sorted(all_metadata_fields):
            count = field_counts[field]
            percentage = (count / doc_count) * 100
            print(f"  {field}: {count} documents ({percentage:.1f}%)")
        
        # Display a sample document
        print("\nSample Document:")
        sample_idx = 0
        print(f"  ID: {results['ids'][sample_idx]}")
        
        print("  Metadata:")
        for key, value in results["metadatas"][sample_idx].items():
            print(f"    {key}: {value[:100]}..." if isinstance(value, str) and len(value) > 100 else f"    {key}: {value}")
        
        print("  Content Preview:")
        content = results["documents"][sample_idx]
        print(f"    {content[:200]}..." if len(content) > 200 else content)
        
    except Exception as e:
        print(f"Error examining ChromaDB collection: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Display metadata layout for a ChromaDB email collection")
    parser.add_argument("collection_name", help="Name of the ChromaDB collection")
    parser.add_argument("db_path", help="Path to the ChromaDB directory")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.db_path):
        print(f"Error: ChromaDB directory '{args.db_path}' does not exist")
        sys.exit(1)
    
    display_chromadb_email_metadata(args.collection_name, args.db_path)

if __name__ == "__main__":
    main()

