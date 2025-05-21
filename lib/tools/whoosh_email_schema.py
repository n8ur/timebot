#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/whoosh_email_schema.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import sys
import argparse
from whoosh.index import open_dir

def display_whoosh_email_schema(index_dir):
    """
    Display the schema and a sample document from a Whoosh email index.
    
    Args:
        index_dir: Directory path for the Whoosh index
    """
    try:
        # Open the index
        ix = open_dir(index_dir)
        
        # Get schema information
        schema = ix.schema
        
        print("=== Whoosh Email Index Schema ===")
        print("\nField Names:")
        for field_name in schema.names():
            field = schema[field_name]
            field_type = type(field).__name__
            stored = "Stored" if field.stored else "Not Stored"
            indexed = "Indexed" if field.indexed else "Not Indexed"
            print(f"  {field_name}: {field_type} ({stored}, {indexed})")
        
        # Get a sample document to show actual data structure
        with ix.searcher() as searcher:
            all_docs = searcher.documents()
            sample_doc = next(all_docs, None)
            
            if sample_doc:
                print("\nSample Document:")
                for field, value in sample_doc.items():
                    print(f"  {field}: {value[:100]}..." if isinstance(value, str) and len(value) > 100 else f"  {field}: {value}")
                    print("\nRaw Field Values:")
                    for field, value in sample_doc.items():
                        print(f"    {field!r}: {value!r}")
            else:
                print("\nNo documents found in the index.")
        
        # Print index statistics
        print("\nIndex Statistics:")
        print(f"  Document Count: {ix.doc_count()}")
        print(f"  Last Modified: {ix.last_modified()}")
        
    except Exception as e:
        print(f"Error examining Whoosh index: {e}")

def main():
    parser = argparse.ArgumentParser(description="Display schema information for a Whoosh email index")
    parser.add_argument("index_dir", help="Directory path for the Whoosh index")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.index_dir):
        print(f"Error: Index directory '{args.index_dir}' does not exist")
        sys.exit(1)
    
    display_whoosh_email_schema(args.index_dir)

if __name__ == "__main__":
    main()

