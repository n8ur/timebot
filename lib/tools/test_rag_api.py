#!/usr/bin/env python3
# test_rag_api.py - Test script for the RAG API

import requests
import json
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("test_rag_api")

# Configuration - update these values to match your environment
EMBEDDING_SERVER_URL = "http://localhost"  # Update with your server URL
EMBEDDING_SERVER_PORT = 8100               # Update with your server port

def test_api_info():
    """Test the API info endpoint"""
    try:
        info_url = f"{EMBEDDING_SERVER_URL}:{EMBEDDING_SERVER_PORT}/api/info"
        logger.info(f"Testing API info endpoint: {info_url}")
        
        response = requests.get(info_url)
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            info = response.json()
            logger.info(f"API Info: {json.dumps(info, indent=2)}")
            return True
        else:
            logger.error(f"Failed to get API info: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Error testing API info: {str(e)}")
        return False

def test_query_endpoint(query="test query", collection_filter="all"):
    """Test the query endpoint"""
    try:
        endpoint = "/api/query"
        full_url = f"{EMBEDDING_SERVER_URL}:{EMBEDDING_SERVER_PORT}{endpoint}"
        
        # Create payload
        payload = {
            "query": query,
            "similarity_threshold": 0.1,  # Low threshold to ensure results
            "top_k": 5,
            "use_reranking": True,
            "mode": "combined",
            "collection_filter": collection_filter,
            "fuzzy": True,
        }
        
        logger.info(f"Testing query endpoint: {full_url}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(full_url, json=payload)
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # Log the structure of the response
            logger.info(f"Response type: {type(result)}")
            
            if isinstance(result, dict):
                logger.info(f"Response keys: {list(result.keys())}")
                
                # Check for results field
                if "results" in result:
                    results = result["results"]
                    logger.info(f"Found {len(results)} results in 'results' key")
                    
                    # Log the structure of the first result
                    if results and isinstance(results[0], dict):
                        logger.info(f"First result keys: {list(results[0].keys())}")
                        
                        # Check for metadata
                        if "metadata" in results[0]:
                            logger.info(f"First result metadata keys: {list(results[0]['metadata'].keys())}")
                            
                        # Check for score
                        if "score" in results[0]:
                            logger.info(f"First result score: {results[0]['score']}")
                        
                        # Check for content
                        if "content" in results[0]:
                            content = results[0]["content"]
                            logger.info(f"First result content (sample): {content[:100]}...")
            
            elif isinstance(result, list):
                logger.info(f"Response is a list with {len(result)} items")
                
                # Log the structure of the first item
                if result and isinstance(result[0], dict):
                    logger.info(f"First item keys: {list(result[0].keys())}")
            
            return True
        else:
            logger.error(f"Query request failed with status {response.status_code}")
            return False
    
    except Exception as e:
        logger.error(f"Error testing query endpoint: {str(e)}")
        return False

def test_all_collections():
    """Test queries with different collection filters"""
    collections = ["all", "emails", "documents", "web"]
    
    for collection in collections:
        logger.info(f"\n\n--- Testing collection filter: {collection} ---\n")
        test_query_endpoint(query="time measurement", collection_filter=collection)

def main():
    """Main test function"""
    logger.info("Starting RAG API test")
    
    # Test API info endpoint
    if not test_api_info():
        logger.error("API info test failed. Check if the server is running.")
        return
    
    # Test query endpoint with a simple query
    logger.info("\n\n--- Testing basic query ---\n")
    if not test_query_endpoint():
        logger.error("Basic query test failed.")
        return
    
    # Test all collections
    test_all_collections()
    
    logger.info("RAG API tests completed")

if __name__ == "__main__":
    main()

