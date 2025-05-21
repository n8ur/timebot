#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/test1.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import requests
import json
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Test specific web metadata searches')
    parser.add_argument('--host', default='localhost', help='API server hostname')
    parser.add_argument('--port', type=int, default=8100, help='API server port')
    parser.add_argument('--base-path', default='api', help='API base path')
    parser.add_argument('--doc-id', default='c1e0a4b8c185590a315ae0273bc203426c0acfe0cb68e074ffd3e1195fd8686e', 
                        help='Document ID to search for')
    parser.add_argument('--domain', default='febo.com', help='Domain to search for')
    parser.add_argument('--url', default='https://febo.com/pages/hf_stability', help='URL to search for')
    return parser.parse_args()

def print_section(title):
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)

def test_metadata_search(base_url, metadata, collection="web"):
    print_section(f"Testing Metadata Search: {json.dumps(metadata)}")
    
    try:
        payload = {
            "metadata": metadata,
            "query": "",
            "top_k": 3,
            "metadata_fuzzy": True,
            "metadata_threshold": 0.7,
            "collection_filter": collection
        }
        
        print(f"Sending request to {base_url}/metadata_search with payload:")
        print(json.dumps(payload, indent=2))
        
        response = requests.post(f"{base_url}/metadata_search", json=payload)
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        result = response.json()
        
        print(f"Total Results: {len(result.get('results', []))}")
        
        if result.get('results'):
            print("\nResults:")
            for i, item in enumerate(result.get('results')):
                print(f"\nResult #{i+1}:")
                print(f"ID: {item.get('id')}")
                print(f"Score: {item.get('score'):.4f}")
                
                metadata = item.get('metadata', {})
                print(f"Doc Type: {metadata.get('doc_type', 'unknown')}")
                print(f"Domain: {metadata.get('domain', 'Unknown')}")
                print(f"Source URL: {metadata.get('source_url', 'Unknown')}")
                
                # Print content preview
                content = item.get('content', '')
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"Content Preview: {preview}")
        else:
            print("No results found.")
        
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_direct_query(base_url, query, collection="web"):
    print_section(f"Testing Direct Query: '{query}'")
    
    try:
        payload = {
            "query": query,
            "mode": "combined",
            "fuzzy": True,
            "top_k": 3,
            "collection_filter": collection
        }
        
        print(f"Sending request to {base_url}/query with payload:")
        print(json.dumps(payload, indent=2))
        
        response = requests.post(f"{base_url}/query", json=payload)
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        result = response.json()
        
        print(f"Total Results: {len(result.get('results', []))}")
        
        if result.get('results'):
            print("\nResults:")
            for i, item in enumerate(result.get('results')):
                print(f"\nResult #{i+1}:")
                print(f"ID: {item.get('id')}")
                print(f"Score: {item.get('score'):.4f}")
                
                metadata = item.get('metadata', {})
                print(f"Doc Type: {metadata.get('doc_type', 'unknown')}")
                print(f"Domain: {metadata.get('domain', 'Unknown')}")
                print(f"Source URL: {metadata.get('source_url', 'Unknown')}")
                
                # Print content preview
                content = item.get('content', '')
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"Content Preview: {preview}")
        else:
            print("No results found.")
        
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    args = parse_arguments()
    
    # Construct base API URL
    base_url = f"http://{args.host}:{args.port}"
    if args.base_path:
        base_url = f"{base_url}/{args.base_path.lstrip('/')}"
    
    print(f"Testing API at: {base_url}")
    
    # Test 1: Search by doc_id
    test_metadata_search(base_url, {"doc_id": args.doc_id})
    
    # Test 2: Search by domain
    test_metadata_search(base_url, {"domain": args.domain})
    
    # Test 3: Search by full URL
    test_metadata_search(base_url, {"source_url": args.url})
    
    # Test 4: Search by URL path only
    path = args.url.split('/')[-1] if '/' in args.url else args.url
    test_metadata_search(base_url, {"source_url": path})
    
    # Test 5: Direct content query for domain
    test_direct_query(base_url, args.domain)
    
    # Test 6: Direct content query for URL path
    test_direct_query(base_url, path)
    
    # Test 7: Try with "all" collection instead of "web"
    print_section("Testing with 'all' collection filter")
    test_metadata_search(base_url, {"domain": args.domain}, "all")
    test_metadata_search(base_url, {"source_url": args.url}, "all")

if __name__ == "__main__":
    main()

