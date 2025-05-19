#!/usr/bin/env python3
import requests
import json
import sys
import argparse
from typing import Dict, Any, List, Optional

# ============================================================================
# CUSTOMIZABLE QUERY VARIABLES - Edit these to match your data
# ============================================================================
# Number of hits to return
TOP_K = 1
# General queries for each collection type
GENERAL_QUERY = "hp5061a"  # Query that might match content in any collection

# Collection-specific queries
EMAIL_QUERY = "hp5061a"  # Query likely to match email content
DOCUMENT_QUERY = "hp5061a"  # Query likely to match document content
WEB_QUERY = "hp5061a"  # Query likely to match web content

# Metadata search examples
EMAIL_METADATA = {"from": "jra@febo.com"}  # Example email sender
DOCUMENT_METADATA = {"author": "Matsakis"}  # Example document author
WEB_DOMAIN_METADATA = {"domain": "febo.com"}  # Example web domain
WEB_URL_METADATA = {"source_url": "https://febo.com/pages/hf_stability"}  # Example web URL

# Combined metadata and content query
COMBINED_METADATA = {"domain": "febo.com"}  # Metadata for combined search
COMBINED_CONTENT_QUERY = "hp5061a"  # Content query for combined search
# ============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Test RAG API with web collection support')
    parser.add_argument('--host', default='localhost', help='API server hostname')
    parser.add_argument('--port', type=int, default=8100, help='API server port')
    parser.add_argument('--base-path', default='api', help='API base path (if any)')
    return parser.parse_args()

def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)

def print_result(result: Dict[str, Any], detailed: bool = False):
    """Print a search result in a readable format."""
    metadata = result.get("metadata", {})
    doc_type = metadata.get("doc_type", "unknown")
    
    # Print basic info for all document types
    print(f"ID: {result.get('id')}")
    print(f"Score: {result.get('score'):.4f}")
    print(f"Type: {doc_type}")
    
    # Print type-specific information
    if doc_type == "email":
        print(f"From: {metadata.get('from', 'Unknown')}")
        print(f"Subject: {metadata.get('subject', 'Unknown')}")
        print(f"Date: {metadata.get('date', 'Unknown')}")
    elif doc_type == "document":
        print(f"Title: {metadata.get('title', 'Untitled Document')}")
        print(f"Author: {metadata.get('author', 'Unknown Author')}")
        print(f"Publisher: {metadata.get('publisher', 'Unknown Publisher')}")
        print(f"Chunk: {metadata.get('chunk_number', 1)}/{metadata.get('total_chunks', 1)}")
    elif doc_type == "web":
        print(f"Title: {metadata.get('title', 'Untitled Web Page')}")
        print(f"Domain: {metadata.get('domain', 'Unknown Domain')}")
        print(f"Source URL: {metadata.get('source_url', 'Unknown URL')}")
        print(f"Captured At: {metadata.get('captured_at', 'Unknown Date')}")
    elif doc_type == "unknown":
        # For unknown types, check if they have web-specific fields
        if metadata.get('source_url') or metadata.get('domain'):
            print(f"Title: {metadata.get('title', 'Untitled Web Page')}")
            print(f"Domain: {metadata.get('domain', 'Unknown Domain')}")
            print(f"Source URL: {metadata.get('source_url', 'Unknown URL')}")
            print(f"Captured At: {metadata.get('captured_at', 'Unknown Date')}")
            print("Note: This appears to be web content with doc_type='unknown'")
    
    # Print content preview
    content = result.get("content", "")
    preview = content[:150] + "..." if len(content) > 150 else content
    print(f"Content Preview: {preview}")
    
    # Print detailed information if requested
    if detailed:
        print("\nDetailed Metadata:")
        for key, value in metadata.items():
            if key not in ["doc_type", "from", "subject", "date", "title", "author", 
                          "publisher", "chunk_number", "total_chunks", "domain", 
                          "source_url", "captured_at"]:
                print(f"  {key}: {value}")
    
    print("-" * 40)

def test_api_info(api_url: str):
    """Test the /info endpoint."""
    print_section("Testing API Info Endpoint")
    
    try:
        # Try different possible endpoint paths
        endpoints = [
            f"{api_url}/info",
            f"{api_url}/api/info",
            f"{api_url}/v1/info",
            f"{api_url}/api/v1/info"
        ]
        
        response = None
        working_endpoint = None
        
        for endpoint in endpoints:
            try:
                print(f"Trying endpoint: {endpoint}")
                response = requests.get(endpoint, timeout=5)
                response.raise_for_status()
                working_endpoint = endpoint
                break
            except requests.exceptions.RequestException as e:
                print(f"  Failed: {e}")
        
        if not response or not working_endpoint:
            print("Could not find a working API info endpoint")
            return False
        
        print(f"✅ Found working endpoint: {working_endpoint}")
        info = response.json()
        
        print(f"API Name: {info.get('name')}")
        print(f"Version: {info.get('version')}")
        print(f"Description: {info.get('description')}")
        print("\nModels:")
        for model_type, model_name in info.get('models', {}).items():
            print(f"  {model_type}: {model_name}")
        
        print("\nCollections:")
        for collection in info.get('collections', []):
            print(f"  - {collection}")
        
        # Verify web collection is included
        if "web" in info.get('collections', []):
            print("\n✅ Web collection is available in the API")
        else:
            print("\n❌ Web collection is NOT available in the API")
        
        # Return the working endpoint base
        return working_endpoint.replace("/info", "")
    except Exception as e:
        print(f"Error testing API info: {e}")
        return False

def test_query(api_url: str, query: str, collection_filter: str = "all", top_k: int = 5):
    """Test the /query endpoint with the given parameters."""
    print_section(f"Testing Query: '{query}' (Collection: {collection_filter})")
    
    try:
        payload = {
            "query": query,
            "mode": "combined",
            "fuzzy": True,
            "similarity_threshold": 0.7,
            "use_reranking": True,
            "top_k": top_k,
            "collection_filter": collection_filter,
            "metadata_fuzzy": True,
            "metadata_threshold": 0.8,
            "weights": {
                "document_collection_weight": 1.0,
                "email_collection_weight": 1.0,
                "web_collection_weight": 1.0,
                "recency_weight": 0.5,
                "recency_decay_days": 30,
                "chromadb_weight": 0.7,
                "whoosh_weight": 0.3,
                "reranker_weight": 0.8
            }
        }
        
        print(f"Sending request to {api_url}/query with payload:")
        print(json.dumps(payload, indent=2))
        
        response = requests.post(f"{api_url}/query", json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"Query: {result.get('query')}")
        print(f"Total Results: {len(result.get('results', []))}")
        
        # Count results by type
        doc_types = {}
        for item in result.get('results', []):
            doc_type = item.get('metadata', {}).get('doc_type', 'unknown')
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        
        print("\nResults by type:")
        for doc_type, count in doc_types.items():
            print(f"  {doc_type}: {count}")
        
        # Print top results
        if result.get('results'):
            print("\nTop results:")
            for i, item in enumerate(result.get('results')[:5]):
                print(f"\nResult #{i+1}:")
                print_result(item)
        else:
            print("\nNo results found.")
        
        # Check if web results are included when using "all" or "web" filter
        if collection_filter in ["all", "web"]:
            # Look for results that are either explicitly marked as web type
            # or have web-specific metadata fields
            web_results = [r for r in result.get('results', []) 
                          if (r.get('metadata', {}).get('doc_type') == "web" or
                              r.get('metadata', {}).get('source_url') or
                              r.get('metadata', {}).get('domain'))]
            
            if web_results:
                print(f"\n✅ Found {len(web_results)} web results")
                
                # If they're not properly labeled as web, note this as a potential issue
                unlabeled_web = [r for r in web_results if r.get('metadata', {}).get('doc_type') != "web"]
                if unlabeled_web:
                    print(f"⚠️ Note: {len(unlabeled_web)} web results have doc_type = '{unlabeled_web[0].get('metadata', {}).get('doc_type', 'unknown')}' instead of 'web'")
            else:
                print("\n⚠️ No web results found (this might be expected if no web data exists)")
                
                # Add diagnostic information
                if collection_filter == "web" and result.get('results'):
                    print("\nDiagnostic information:")
                    print(f"- Requested collection filter: {collection_filter}")
                    print(f"- Received results of type: {list(doc_types.keys())}")
                    print("- This suggests the collection filter may not be working correctly")
                    
                    # Check if any results might be web content but mislabeled
                    for i, item in enumerate(result.get('results')[:3]):
                        metadata = item.get('metadata', {})
                        if 'source_url' in metadata or 'domain' in metadata:
                            print(f"- Result #{i+1} has web-specific metadata but incorrect doc_type")
        
        return result
    except Exception as e:
        print(f"Error testing query: {e}")
        return None

def test_metadata_search(api_url: str, metadata: Dict[str, Any], content_query: str = "", 
                        collection_filter: str = "all", top_k: int = 5):
    """Test the /metadata_search endpoint with the given parameters."""
    print_section(f"Testing Metadata Search: {json.dumps(metadata)} (Collection: {collection_filter})")
    
    try:
        payload = {
            "metadata": metadata,
            "query": content_query,
            "top_k": top_k,
            "metadata_fuzzy": True,
            "metadata_threshold": 0.8,
            "collection_filter": collection_filter
        }
        
        print(f"Sending request to {api_url}/metadata_search with payload:")
        print(json.dumps(payload, indent=2))
        
        response = requests.post(f"{api_url}/metadata_search", json=payload)
        response.raise_for_status()
        result = response.json()
        
        print(f"Query: {result.get('query')}")
        print(f"Total Results: {len(result.get('results', []))}")
        
        # Count results by type
        doc_types = {}
        for item in result.get('results', []):
            doc_type = item.get('metadata', {}).get('doc_type', 'unknown')
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        
        print("\nResults by type:")
        for doc_type, count in doc_types.items():
            print(f"  {doc_type}: {count}")
        
        # Print top results
        if result.get('results'):
            print("\nTop results:")
            for i, item in enumerate(result.get('results')[:5]):
                print(f"\nResult #{i+1}:")
                print_result(item, detailed=True)  # Show detailed metadata
        else:
            print("\nNo results found.")
        
        # Check if web results are included when using web-specific metadata
        if "domain" in metadata or "source_url" in metadata or collection_filter == "web":
            # Look for results that are either explicitly marked as web type
            # or have web-specific metadata fields
            web_results = [r for r in result.get('results', []) 
                          if (r.get('metadata', {}).get('doc_type') == "web" or
                              r.get('metadata', {}).get('source_url') or
                              r.get('metadata', {}).get('domain'))]
            
            if web_results:
                print(f"\n✅ Found {len(web_results)} web results")
                
                # If they're not properly labeled as web, note this as a potential issue
                unlabeled_web = [r for r in web_results if r.get('metadata', {}).get('doc_type') != "web"]
                if unlabeled_web:
                    print(f"⚠️ Note: {len(unlabeled_web)} web results have doc_type = '{unlabeled_web[0].get('metadata', {}).get('doc_type', 'unknown')}' instead of 'web'")
            else:
                print("\n⚠️ No web results found (this might be expected if no matching web data exists)")
                
                # Add diagnostic information
                if collection_filter == "web" and result.get('results'):
                    print("\nDiagnostic information:")
                    print(f"- Requested collection filter: {collection_filter}")
                    print(f"- Received results of type: {list(doc_types.keys())}")
                    print("- This suggests the collection filter may not be working correctly")
                    
                    # Check if any results contain the domain in their content
                    if "domain" in metadata:
                        domain = metadata["domain"]
                        domain_in_content = [r for r in result.get('results', []) 
                                           if domain in r.get('content', '')]
                        if domain_in_content:
                            print(f"- Found {len(domain_in_content)} results containing '{domain}' in content")
                            print("  This suggests the domain might be in the content but not properly indexed as metadata")
        
        return result
    except Exception as e:
        print(f"Error testing metadata search: {e}")
        return None

def test_web_collection_filter(api_url: str):
    """Test if the web collection filter is working properly."""
    print_section("Testing Web Collection Filter")
    
    try:
        # First, get all results to see if web content exists
        all_payload = {
            "query": WEB_QUERY,
            "mode": "combined",
            "fuzzy": True,
            "top_k": 10,
            "collection_filter": "all"
        }
        
        all_response = requests.post(f"{api_url}/query", json=all_payload)
        all_response.raise_for_status()
        all_results = all_response.json()
        
        # Then, filter to just web results
        web_payload = {
            "query": WEB_QUERY,
            "mode": "combined",
            "fuzzy": True,
            "top_k": 10,
            "collection_filter": "web"
        }
        
        web_response = requests.post(f"{api_url}/query", json=web_payload)
        web_response.raise_for_status()
        web_results = web_response.json()
        
        # Count results by type for both queries
        all_doc_types = {}
        for item in all_results.get('results', []):
            doc_type = item.get('metadata', {}).get('doc_type', 'unknown')
            all_doc_types[doc_type] = all_doc_types.get(doc_type, 0) + 1
        
        web_doc_types = {}
        for item in web_results.get('results', []):
            doc_type = item.get('metadata', {}).get('doc_type', 'unknown')
            web_doc_types[doc_type] = web_doc_types.get(doc_type, 0) + 1
        
        print(f"Query: {WEB_QUERY}")
        print(f"All collections - Total Results: {len(all_results.get('results', []))}")
        print("Results by type:")
        for doc_type, count in all_doc_types.items():
            print(f"  {doc_type}: {count}")
        
        print(f"\nWeb collection only - Total Results: {len(web_results.get('results', []))}")
        print("Results by type:")
        for doc_type, count in web_doc_types.items():
            print(f"  {doc_type}: {count}")
        
        # Check if filtering is working
        if "web" in all_doc_types or "unknown" in all_doc_types:
            if web_doc_types:
                print("\n✅ Web collection filter appears to be working")
                
                # Check if the types match expectations
                if "web" not in web_doc_types and "unknown" in web_doc_types:
                    print("⚠️ Web results are labeled as 'unknown' instead of 'web'")
                    print("   This suggests a labeling issue in the indexing process")
            else:
                print("\n❌ Web collection filter does not appear to be working")
                print("   All query returned potential web results, but web filter returned none")
        else:
            print("\n⚠️ No web results found in either query")
            print("   This might be expected if no web data exists or if the query doesn't match web content")
        
        return all_results, web_results
    except Exception as e:
        print(f"Error testing web collection filter: {e}")
        return None, None

def main():
    """Run all tests."""
    args = parse_arguments()
    
    # Construct base API URL
    base_url = f"http://{args.host}:{args.port}"
    if args.base_path:
        base_url = f"{base_url}/{args.base_path.lstrip('/')}"
    
    print(f"Testing API at: {base_url}")
    
    # Test API info and get working endpoint
    working_api_url = test_api_info(base_url)
    if not working_api_url:
        print("Could not find a working API endpoint. Please check if the server is running and the URL is correct.")
        print("You can specify a different host/port with --host and --port options.")
        sys.exit(1)
    
    print(f"Using API URL: {working_api_url}")
    
    # Test web collection filter specifically
    test_web_collection_filter(working_api_url)
    
    # Test general queries
    test_query(working_api_url, GENERAL_QUERY, "all", TOP_K)
    test_query(working_api_url, DOCUMENT_QUERY, "documents", TOP_K)
    test_query(working_api_url, EMAIL_QUERY, "emails", TOP_K)
    test_query(working_api_url, WEB_QUERY, "web",TOP_K)
    
    # Test metadata search for emails
    test_metadata_search(working_api_url, EMAIL_METADATA, EMAIL_QUERY, "emails", TOP_K)
    
    # Test metadata search for documents
    test_metadata_search(working_api_url, DOCUMENT_METADATA, DOCUMENT_QUERY, "documents", TOP_K)
    
    # Test metadata search for web content
    test_metadata_search(working_api_url, WEB_DOMAIN_METADATA, "", "web", TOP_K)
    test_metadata_search(working_api_url, WEB_URL_METADATA, "", "web", TOP_K)
    
    # Test combined metadata search
    test_metadata_search(working_api_url, COMBINED_METADATA, COMBINED_CONTENT_QUERY, "all", TOP_K)
    
    print_section("All Tests Completed")

if __name__ == "__main__":
    main()

