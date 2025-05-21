#!/usr/bin/env python3
# /usr/local/lib/timebot/bin/whoosh_check.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import sys
import random
import argparse
import json
from typing import Dict, Any, List, Optional

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config

# Import the Whoosh utilities
from shared.whoosh_utils import (
    open_whoosh_index,
    get_index_stats
)
from whoosh.index import open_dir

def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0 or unit == 'TB':
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

def pretty_print_metadata(metadata: Dict[str, Any], indent: int = 0) -> None:
    """Pretty print metadata with proper indentation for nested structures."""
    for key, value in metadata.items():
        if isinstance(value, dict):
            print(f"{' ' * indent}{key}:")
            pretty_print_metadata(value, indent + 2)
        elif isinstance(value, list):
            print(f"{' ' * indent}{key}: [")
            for item in value:
                if isinstance(item, dict):
                    pretty_print_metadata(item, indent + 2)
                else:
                    print(f"{' ' * indent}  {item}")
            print(f"{' ' * indent}]")
        else:
            print(f"{' ' * indent}{key}: {value}")

def get_all_documents_custom(index_dir: str, max_docs: int = 1000) -> List[Dict[str, Any]]:
    """
    Custom implementation to retrieve documents from the index up to the specified limit.
    
    Args:
        index_dir: Directory path for the Whoosh index
        max_docs: Maximum number of documents to retrieve
        
    Returns:
        List of documents as dictionaries
    """
    ix = open_dir(index_dir)
    results = []
    
    with ix.searcher() as searcher:
        # Get all document IDs
        doc_count = 0
        for doc in searcher.all_stored_fields():
            results.append(dict(doc))
            doc_count += 1
            if doc_count >= max_docs:
                break
    
    return results

def get_whoosh_stats(index_dir: str) -> Dict[str, Any]:
    """Get detailed statistics for a Whoosh index."""
    try:
        # Open the index
        ix = open_whoosh_index(index_dir)
        
        # Get basic stats
        stats = get_index_stats(index_dir)
        
        # Get schema information
        schema_info = {}
        for field_name in ix.schema.names():
            field = ix.schema[field_name]
            schema_info[field_name] = {
                "type": field.__class__.__name__,
                "stored": getattr(field, "stored", False),
                "indexed": getattr(field, "indexed", False),
                "unique": getattr(field, "unique", False),
                "sortable": getattr(field, "sortable", False)
            }
        
        # Get a sample of documents to estimate average size
        sample_size = min(100, stats["doc_count"])
        total_size = 0
        
        if sample_size > 0:
            # Use our custom function instead of get_all_documents
            sample_docs = get_all_documents_custom(index_dir, max_docs=sample_size)
            
            # Calculate total size of documents
            for doc in sample_docs:
                # Estimate size by converting to string and measuring bytes
                doc_str = str(doc)
                total_size += len(doc_str.encode('utf-8'))
            
            avg_doc_size = total_size / sample_size if sample_size > 0 else 0
            estimated_total_size = avg_doc_size * stats["doc_count"]
        else:
            avg_doc_size = 0
            estimated_total_size = 0
        
        # Add to stats
        stats["schema_details"] = schema_info
        stats["avg_document_size"] = avg_doc_size
        stats["estimated_total_size"] = estimated_total_size
        
        # Get index directory size on disk
        index_size = sum(
            os.path.getsize(os.path.join(index_dir, f)) 
            for f in os.listdir(index_dir) 
            if os.path.isfile(os.path.join(index_dir, f))
        )
        stats["index_size_on_disk"] = index_size
        
        # Determine schema type based on fields
        schema_fields = set(stats["schema_fields"])
        
        if "from_" in schema_fields and "subject" in schema_fields:
            stats["schema_type"] = "email"
        elif "title" in schema_fields and "author" in schema_fields and "publisher" in schema_fields:
            stats["schema_type"] = "technical"
        elif "source_url" in schema_fields and "domain" in schema_fields:
            stats["schema_type"] = "web"
        elif "title" in schema_fields and "author" in schema_fields:
            stats["schema_type"] = "document"
        else:
            stats["schema_type"] = "unknown"
        
        return stats
    
    except Exception as e:
        return {
            "error": str(e),
            "index_dir": index_dir
        }

def get_random_record(index_dir: str) -> Optional[Dict[str, Any]]:
    """Get a random record from the Whoosh index."""
    try:
        # Open the index
        ix = open_whoosh_index(index_dir)
        
        # Get document count
        doc_count = ix.doc_count()
        
        if doc_count == 0:
            print(f"Index '{index_dir}' is empty.")
            return None
        
        # Get all documents (limited to a reasonable number)
        max_docs = min(1000, doc_count)  # Limit to 1000 docs for performance
        all_docs = get_all_documents_custom(index_dir, max_docs=max_docs)
        
        if not all_docs:
            print(f"Could not retrieve documents from index '{index_dir}'.")
            return None
        
        # Select a random document
        random_doc = random.choice(all_docs)
        
        return random_doc
    
    except Exception as e:
        print(f"Error getting random record: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Whoosh Index Statistics Utility")
    parser.add_argument("--index-dir", required=True, help="Path to the Whoosh index directory")
    parser.add_argument("--random-record", action="store_true", help="Show a random record from the index")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    
    args = parser.parse_args()
    
    try:
        # Check if index directory exists
        if not os.path.exists(args.index_dir):
            print(f"Error: Index directory '{args.index_dir}' does not exist.")
            sys.exit(1)
        
        # Get index statistics
        stats = get_whoosh_stats(args.index_dir)
        
        if "error" in stats:
            print(f"Error: {stats['error']}")
            sys.exit(1)
        
        if not args.json:
            print(f"\n{'=' * 50}")
            print(f"Whoosh Index: {args.index_dir}")
            print(f"{'=' * 50}")
            print(f"Document count: {stats['doc_count']:,}")
            print(f"Schema type: {stats['schema_type']}")
            print(f"Last modified: {stats['last_modified']}")
            print(f"Index version: {stats['index_version']}")
            print(f"Average document size: {format_size(stats['avg_document_size'])}")
            print(f"Estimated total size: {format_size(stats['estimated_total_size'])}")
            print(f"Index size on disk: {format_size(stats['index_size_on_disk'])}")
            
            print("\nSchema fields:")
            for field_name, field_info in stats["schema_details"].items():
                print(f"  {field_name}: {field_info['type']} (stored: {field_info['stored']}, indexed: {field_info['indexed']})")
            
            if args.random_record and stats['doc_count'] > 0:
                random_record = get_random_record(args.index_dir)
                if random_record:
                    print(f"\n{'-' * 50}")
                    print(f"Random Record (ID: {random_record.get('doc_id', 'Unknown')})")
                    print(f"{'-' * 50}")
                    
                    # Print all fields except content (which can be large)
                    content = random_record.pop('content', None)
                    print("\nMetadata:")
                    pretty_print_metadata(random_record, 2)
                    
                    # Print a preview of the content
                    if content:
                        content_preview = content[:500]
                        if len(content) > 500:
                            content_preview += "..."
                        print(f"\nContent preview:")
                        print(f"  {content_preview}")
                        
                        # Put content back for JSON output
                        random_record['content'] = content
        
        if args.json:
            result = {"stats": stats}
            
            if args.random_record and stats['doc_count'] > 0:
                random_record = get_random_record(args.index_dir)
                if random_record:
                    result["random_record"] = random_record
            
            print(json.dumps(result, indent=2, default=str))
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

