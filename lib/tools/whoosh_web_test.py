#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/whoosh_web_test.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import sys
import random
from whoosh.index import open_dir
from urllib.parse import urlparse

def format_size(size_bytes):
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0 or unit == 'TB':
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

def get_random_docs(index_dir, count=5):
    """Get several random documents from the index."""
    try:
        ix = open_dir(index_dir)
        
        # Get all document IDs (up to a reasonable limit)
        all_docs = []
        with ix.searcher() as searcher:
            for doc in searcher.all_stored_fields():
                all_docs.append(dict(doc))
                if len(all_docs) >= 1000:  # Limit to 1000 for performance
                    break
        
        if not all_docs:
            print("No documents found in the index.")
            return []
        
        # Select random documents
        if len(all_docs) <= count:
            return all_docs
        else:
            return random.sample(all_docs, count)
    
    except Exception as e:
        print(f"Error getting random documents: {e}")
        return []

def search_for_domain(index_dir, domain):
    """Search for documents containing a specific domain."""
    try:
        ix = open_dir(index_dir)
        results = []
        
        with ix.searcher() as searcher:
            # Check all documents (up to a reasonable limit)
            count = 0
            domain_in_field = 0
            domain_in_content = 0
            
            for doc in searcher.all_stored_fields():
                count += 1
                if count > 1000:  # Limit to 1000 for performance
                    break
                
                # Check domain field
                if doc.get('domain') == domain:
                    domain_in_field += 1
                    results.append(dict(doc))
                    continue
                
                # Check source_url field
                source_url = doc.get('source_url', '')
                if domain in source_url:
                    domain_in_field += 1
                    results.append(dict(doc))
                    continue
                
                # Check content
                content = doc.get('content', '').lower()
                if domain.lower() in content:
                    domain_in_content += 1
                    results.append(dict(doc))
        
        print(f"Searched {count} documents:")
        print(f"- {domain_in_field} documents have '{domain}' in domain or source_url fields")
        print(f"- {domain_in_content} documents have '{domain}' in content")
        print(f"- {len(results)} total matching documents")
        
        return results
    
    except Exception as e:
        print(f"Error searching for domain: {e}")
        return []

def analyze_url_structure(index_dir, sample_size=100):
    """Analyze how URLs are stored in the index."""
    try:
        ix = open_dir(index_dir)
        
        url_stats = {
            "total": 0,
            "empty": 0,
            "with_protocol": 0,
            "without_protocol": 0,
            "with_www": 0,
            "without_www": 0,
            "with_trailing_slash": 0,
            "without_trailing_slash": 0,
            "samples": []
        }
        
        with ix.searcher() as searcher:
            count = 0
            for doc in searcher.all_stored_fields():
                source_url = doc.get('source_url', '')
                if source_url:
                    url_stats["total"] += 1
                    
                    # Check URL structure
                    if source_url.startswith('http'):
                        url_stats["with_protocol"] += 1
                    else:
                        url_stats["without_protocol"] += 1
                    
                    parsed = urlparse(source_url)
                    netloc = parsed.netloc.lower()
                    
                    if netloc.startswith('www.'):
                        url_stats["with_www"] += 1
                    else:
                        url_stats["without_www"] += 1
                    
                    if source_url.endswith('/'):
                        url_stats["with_trailing_slash"] += 1
                    else:
                        url_stats["without_trailing_slash"] += 1
                    
                    # Collect samples
                    if len(url_stats["samples"]) < 10 and source_url:
                        url_stats["samples"].append(source_url)
                else:
                    url_stats["empty"] += 1
                
                count += 1
                if count >= sample_size:
                    break
        
        return url_stats
    
    except Exception as e:
        print(f"Error analyzing URL structure: {e}")
        return {}

def print_doc_metadata(doc, include_content=False):
    """Print document metadata with focus on web-specific fields."""
    print(f"Document ID: {doc.get('doc_id', 'Unknown')}")
    
    # Print web-specific fields first
    web_fields = ['domain', 'source_url', 'title', 'captured_at']
    for field in web_fields:
        if field in doc:
            print(f"  {field}: {doc[field]}")
    
    # Print other metadata fields
    print("  Other metadata:")
    for key, value in doc.items():
        if key not in web_fields and key != 'content':
            print(f"    {key}: {value}")
    
    # Print content preview if requested
    if include_content and 'content' in doc:
        content = doc['content']
        preview = content[:200] + "..." if len(content) > 200 else content
        print(f"  Content preview: {preview}")
    
    print("-" * 50)

def main():
    if len(sys.argv) < 2:
        print("Usage: web_index_check.py <index_dir> [--search-domain <domain>]")
        sys.exit(1)
    
    index_dir = sys.argv[1]
    search_domain = None
    
    # Check for optional search domain parameter
    if len(sys.argv) > 3 and sys.argv[2] == "--search-domain":
        search_domain = sys.argv[3]
    
    # Check if index directory exists
    if not os.path.exists(index_dir):
        print(f"Error: Index directory '{index_dir}' does not exist.")
        sys.exit(1)
    
    # Open the index and get basic info
    try:
        ix = open_dir(index_dir)
        doc_count = ix.doc_count()
        
        print(f"\n{'=' * 50}")
        print(f"Whoosh Web Index: {index_dir}")
        print(f"{'=' * 50}")
        print(f"Document count: {doc_count:,}")
        
        # Get schema information
        schema_fields = []
        for field_name in ix.schema.names():
            field = ix.schema[field_name]
            schema_fields.append(f"{field_name}: {field.__class__.__name__} (stored: {getattr(field, 'stored', False)}, indexed: {getattr(field, 'indexed', False)})")
        
        print("\nSchema fields:")
        for field in schema_fields:
            print(f"  {field}")
        
        # Analyze URL structure
        print("\nAnalyzing URL structure...")
        url_stats = analyze_url_structure(index_dir)
        
        if url_stats:
            print(f"URL statistics (from sample of {url_stats['total'] + url_stats['empty']} documents):")
            print(f"  Documents with source_url: {url_stats['total']}")
            print(f"  Documents without source_url: {url_stats['empty']}")
            
            if url_stats['total'] > 0:
                print(f"  URLs with protocol (http/https): {url_stats['with_protocol']} ({url_stats['with_protocol']/url_stats['total']*100:.1f}%)")
                print(f"  URLs without protocol: {url_stats['without_protocol']} ({url_stats['without_protocol']/url_stats['total']*100:.1f}%)")
                print(f"  URLs with 'www': {url_stats['with_www']} ({url_stats['with_www']/url_stats['total']*100:.1f}%)")
                print(f"  URLs without 'www': {url_stats['without_www']} ({url_stats['without_www']/url_stats['total']*100:.1f}%)")
                print(f"  URLs with trailing slash: {url_stats['with_trailing_slash']} ({url_stats['with_trailing_slash']/url_stats['total']*100:.1f}%)")
                print(f"  URLs without trailing slash: {url_stats['without_trailing_slash']} ({url_stats['without_trailing_slash']/url_stats['total']*100:.1f}%)")
                
                print("\nSample URLs:")
                for url in url_stats["samples"]:
                    print(f"  {url}")
        
        # Search for specific domain if requested
        if search_domain:
            print(f"\nSearching for documents containing '{search_domain}'...")
            domain_docs = search_for_domain(index_dir, search_domain)
            
            if domain_docs:
                print(f"\nFound {len(domain_docs)} documents containing '{search_domain}'")
                print("First 5 matching documents:")
                for i, doc in enumerate(domain_docs[:5]):
                    print(f"\nDocument {i+1}:")
                    print_doc_metadata(doc, include_content=True)
            else:
                print(f"No documents found containing '{search_domain}'")
        
        # Get random documents
        print("\nRetrieving 5 random documents...")
        random_docs = get_random_docs(index_dir, 5)
        
        if random_docs:
            print(f"\nRandom documents from index:")
            for i, doc in enumerate(random_docs):
                print(f"\nRandom Document {i+1}:")
                print_doc_metadata(doc)
        else:
            print("Could not retrieve random documents.")
        
    except Exception as e:
        print(f"Error examining index: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

