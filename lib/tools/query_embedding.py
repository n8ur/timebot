#!/bin/env python3

import requests
import json
import pprint

def query_embedding_server(
    query,
    mode="combined",
    fuzzy=True,
    similarity_threshold=0.5,
    use_reranking=True,
    top_k=3,
    collection_filter="all",
    weights=None
):
    """
    Query the embedding server with the given parameters.

    Args:
        query (str): The search query
        mode (str): Search mode (combined, semantic, keyword)
        fuzzy (bool): Whether to use fuzzy search
        similarity_threshold (float): Threshold for similarity matching
        use_reranking (bool): Whether to use reranking
        top_k (int): Number of results to return
        collection_filter (str): Filter for collections
        weights (dict): Optional weights configuration

    Returns:
        dict: The server response
    """
    url = "http://localhost:8100/api/query"

    # Prepare the request payload
    payload = {
        "query": query,
        "mode": mode,
        "fuzzy": fuzzy,
        "similarity_threshold": similarity_threshold,
        "use_reranking": use_reranking,
        "top_k": top_k,
        "collection_filter": collection_filter
    }

    # Add weights if provided
    if weights:
        payload["weights"] = weights

    # Make the request
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error querying embedding server: {e}")
        return None

def query_rag_endpoint(
    query,
    mode="combined",
    fuzzy=True,
    similarity_threshold=0.5,
    use_reranking=True,
    top_k=3,
    collection_filter="all",
    weights=None
):
    """
    Query the RAG endpoint of the embedding server.

    Args:
        query (str): The search query
        mode (str): Search mode (combined, semantic, keyword)
        fuzzy (bool): Whether to use fuzzy search
        similarity_threshold (float): Threshold for similarity matching
        use_reranking (bool): Whether to use reranking
        top_k (int): Number of results to return
        collection_filter (str): Filter for collections
        weights (dict): Optional weights configuration

    Returns:
        dict: The server response
    """
    url = "http://localhost:8100/api/rag"

    # Prepare the request payload
    payload = {
        "query": query,
        "mode": mode,
        "fuzzy": fuzzy,
        "similarity_threshold": similarity_threshold,
        "use_reranking": use_reranking,
        "top_k": top_k,
        "collection_filter": collection_filter
    }

    # Add weights if provided
    if weights:
        payload["weights"] = weights

    # Make the request
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error querying RAG endpoint: {e}")
        return None

def print_results(results, endpoint_type):
    """
    Pretty print the results from the server.

    Args:
        results (dict): The server response
        endpoint_type (str): The type of endpoint queried
    """
    print(f"\n===== {endpoint_type} Results =====\n")

    if results is None:
        print("No results received from server.")
        return

    # Use pprint for nicely formatted output
    pp = pprint.PrettyPrinter(indent=2, width=100)
    pp.pprint(results)

def main():
    # Example query
    query = "What are the latest updates on the project?"

    # Example weights configuration
    weights = {
        "document_collection_weight": 1.2,
        "email_collection_weight": 1.0,
        "recency_weight": 0.8,
        "recency_decay_days": 30,
        "chromadb_weight": 1.0,
        "whoosh_weight": 0.7,
        "reranker_weight": 1.5
    }

    # Query the standard API endpoint
    api_results = query_embedding_server(
        query=query,
        mode="combined",
        fuzzy=True,
        similarity_threshold=0.6,
        use_reranking=True,
        top_k=5,
        collection_filter="all",
        weights=weights
    )
    print_results(api_results, "API Query")

    # Query the RAG endpoint
    rag_results = query_rag_endpoint(
        query=query,
        mode="combined",
        fuzzy=True,
        similarity_threshold=0.6,
        use_reranking=True,
        top_k=5,
        collection_filter="all",
        weights=weights
    )
    print_results(rag_results, "RAG Query")

if __name__ == "__main__":
    main()

