#!/usr/bin/env python3
import os
import sys
from whoosh.index import open_dir
from whoosh.query import Term, And, Or, Wildcard
from whoosh.qparser import QueryParser
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search_web_url(index_dir, url):
    """Search for a URL in the web collection using various methods."""
    logger.info(f"Searching for URL: {url}")
    
    # Parse the URL to get components
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path.strip('/')
    
    logger.info(f"Parsed URL - Domain: {domain}, Path: {path}")
    
    # Open the index
    ix = open_dir(index_dir)
    
    results = []
    with ix.searcher() as searcher:
        # Method 1: Exact source_url match
        logger.info("Method 1: Exact source_url match")
        query1 = Term("source_url", url)
        results1 = searcher.search(query1, limit=5)
        
        if results1:
            logger.info(f"Found {len(results1)} results with exact URL match")
            for i, hit in enumerate(results1):
                logger.info(f"Result {i+1}: {hit['doc_id']}")
                logger.info(f"  Title: {hit.get('title', 'Unknown')}")
                logger.info(f"  Domain: {hit.get('domain', 'Unknown')}")
                logger.info(f"  Source URL: {hit.get('source_url', 'Unknown')}")
            results.extend([dict(hit) for hit in results1])
        else:
            logger.info("No exact URL matches found")
        
        # Method 2: Domain match
        logger.info("Method 2: Domain match")
        query2 = Term("domain", domain)
        results2 = searcher.search(query2, limit=10)
        
        if results2:
            logger.info(f"Found {len(results2)} results with domain match")
            for i, hit in enumerate(results2):
                logger.info(f"Result {i+1}: {hit['doc_id']}")
                logger.info(f"  Title: {hit.get('title', 'Unknown')}")
                logger.info(f"  Domain: {hit.get('domain', 'Unknown')}")
                logger.info(f"  Source URL: {hit.get('source_url', 'Unknown')}")
            
            # Only add if we didn't find exact matches
            if not results:
                results.extend([dict(hit) for hit in results2])
        else:
            logger.info("No domain matches found")
        
        # Method 3: Content search for URL or path
        logger.info("Method 3: Content search")
        content_parser = QueryParser("content", ix.schema)
        
        # Try full URL first
        query3a = content_parser.parse(url)
        results3a = searcher.search(query3a, limit=5)
        
        if results3a:
            logger.info(f"Found {len(results3a)} results with URL in content")
            for i, hit in enumerate(results3a):
                logger.info(f"Result {i+1}: {hit['doc_id']}")
                logger.info(f"  Title: {hit.get('title', 'Unknown')}")
                logger.info(f"  Domain: {hit.get('domain', 'Unknown')}")
                logger.info(f"  Source URL: {hit.get('source_url', 'Unknown')}")
            
            # Only add if we didn't find matches with methods 1 or 2
            if not results:
                results.extend([dict(hit) for hit in results3a])
        else:
            logger.info("No content matches for full URL")
            
            # Try just the path
            if path:
                query3b = content_parser.parse(path)
                results3b = searcher.search(query3b, limit=5)
                
                if results3b:
                    logger.info(f"Found {len(results3b)} results with path in content")
                    for i, hit in enumerate(results3b):
                        logger.info(f"Result {i+1}: {hit['doc_id']}")
                        logger.info(f"  Title: {hit.get('title', 'Unknown')}")
                        logger.info(f"  Domain: {hit.get('domain', 'Unknown')}")
                        logger.info(f"  Source URL: {hit.get('source_url', 'Unknown')}")
                    
                    # Only add if we didn't find matches with methods 1 or 2
                    if not results:
                        results.extend([dict(hit) for hit in results3b])
                else:
                    logger.info("No content matches for path")
    
    return results

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: search_web_url.py <index_dir> <url>")
        sys.exit(1)
    
    index_dir = sys.argv[1]
    url = sys.argv[2]
    
    results = search_web_url(index_dir, url)
    
    print(f"\nFound {len(results)} total results")
    if results:
        print("\nFirst result details:")
        result = results[0]
        for key, value in result.items():
            if key != "content":  # Skip content for brevity
                print(f"{key}: {value}")

