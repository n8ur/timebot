
import requests
import json
import sys
import argparse

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Test web collection metadata search')
    parser.add_argument('--host', default='localhost', help='API server hostname')
    parser.add_argument('--port', type=int, default=8100, help='API server port')
    parser.add_argument('--base-path', default='api', help='API base path (if any)')
    parser.add_argument('--url', default='https://febo.com/pages/hf_stability', 
                        help='URL to search for')
    parser.add_argument('--domain', default='febo.com', help='Domain to search for')
    parser.add_argument('--top-k', type=int, default=5, help='Number of results to return')
    parser.add_argument('--fuzzy', action='store_true', help='Enable fuzzy matching')
    parser.add_argument('--threshold', type=float, default=0.8, 
                        help='Metadata matching threshold')
    return parser.parse_args()

def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)

def print_result(result):
    """Print a search result in a readable format."""
    metadata = result.get("metadata", {})
    
    print(f"ID: {result.get('id')}")
    print(f"Score: {result.get('score'):.4f}")
    print(f"Type: {metadata.get('doc_type', 'unknown')}")
    print(f"Title: {metadata.get('title', 'Untitled Web Page')}")
    print(f"Domain: {metadata.get('domain', 'Unknown Domain')}")
    print(f"Source URL: {metadata.get('source_url', 'Unknown URL')}")
    print(f"Captured At: {metadata.get('captured_at', 'Unknown Date')}")
    
    # Print content preview
    content = result.get("content", "")
    preview = content[:150] + "..." if len(content) > 150 else content
    print(f"Content Preview: {preview}")
    
    # Print all metadata for debugging
    print("\nAll Metadata:")
    for key, value in metadata.items():
        print(f"  {key}: {value}")
    
    print("-" * 40)

def test_web_metadata_search(api_url, metadata, query="", top_k=5, fuzzy=True, threshold=0.8):
    """Test metadata search for web content."""
    print_section(f"Testing Web Metadata Search: {json.dumps(metadata)}")
    
    try:
        payload = {
            "metadata": metadata,
            "query": query,
            "top_k": top_k,
            "metadata_fuzzy": fuzzy,
            "metadata_threshold": threshold,
            "collection_filter": "web"
        }
        
        print(f"Sending request to {api_url}/metadata_search with payload:")
        print(json.dumps(payload, indent=2))
        
        response = requests.post(f"{api_url}/metadata_search", json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"Query: {result.get('query')}")
        print(f"Total Results: {len(result.get('results', []))}")
        
        # Print top results
        if result.get('results'):
            print("\nResults:")
            for i, item in enumerate(result.get('results')):
                print(f"\nResult #{i+1}:")
                print_result(item)
        else:
            print("\nNo results found.")
        
        return result
    except Exception as e:
        print(f"Error testing metadata search: {e}")
        return None

def main():
    args = parse_arguments()
    
    # Construct base API URL
    base_url = f"http://{args.host}:{args.port}"
    if args.base_path:
        base_url = f"{base_url}/{args.base_path.lstrip('/')}"
    
    print(f"Testing API at: {base_url}")
    
    # Test URL search
    test_web_metadata_search(
        base_url,
        {"source_url": args.url},
        top_k=args.top_k,
        fuzzy=args.fuzzy,
        threshold=args.threshold
    )
    
    # Test domain search
    test_web_metadata_search(
        base_url,
        {"domain": args.domain},
        top_k=args.top_k,
        fuzzy=args.fuzzy,
        threshold=args.threshold
    )
    
    # Test partial URL search (if fuzzy is enabled)
    if args.fuzzy:
        # Extract path from URL
        parts = args.url.split('/')
        if len(parts) > 3:
            path = parts[-1]
            test_web_metadata_search(
                base_url,
                {"source_url": path},
                top_k=args.top_k,
                fuzzy=args.fuzzy,
                threshold=args.threshold
            )
    
    # Test with exact URL but without collection filter
    test_web_metadata_search(
        base_url,
        {"source_url": args.url},
        top_k=args.top_k,
        fuzzy=args.fuzzy,
        threshold=args.threshold
    )

if __name__ == "__main__":
    main()

