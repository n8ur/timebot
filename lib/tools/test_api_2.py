#!/usr/bin/env python3

# test_api_doc_types.py - Test RAG API for doc_type consistency

import requests
import json
import logging
from collections import Counter

# --- Configuration ---
API_BASE_URL = "http://localhost:8100" # Adjust if your API runs elsewhere
QUERY_ENDPOINT = f"{API_BASE_URL}/api/query"
QUERY_TERM = "hp5065a"
TOP_K = 25 # Number of results to fetch per filter
COLLECTION_FILTERS = ["emails", "documents", "web", "all"]
SIMILARITY_THRESHOLD = 0.1 # Low threshold to get more results
USE_RERANKING = True
MODE = "combined"
FUZZY = True

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Main Test Function ---
def run_tests():
    logger.info(f"--- Starting API doc_type Test for query: '{QUERY_TERM}' ---")

    for collection_filter in COLLECTION_FILTERS:
        logger.info(f"\n--- Testing Collection Filter: '{collection_filter}' ---")

        payload = {
            "query": QUERY_TERM,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "top_k": TOP_K,
            "use_reranking": USE_RERANKING,
            "mode": MODE,
            "collection_filter": collection_filter,
            "fuzzy": FUZZY,
        }

        logger.info(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(QUERY_ENDPOINT, json=payload, timeout=30) # Added timeout
            logger.info(f"Response Status Code: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    results = data.get("results")

                    if isinstance(results, list):
                        logger.info(f"Received {len(results)} results.")
                        doc_type_counts = Counter()
                        found_nested_metadata = False

                        if not results:
                             logger.info("No results returned for this filter.")
                             continue

                        for i, result in enumerate(results):
                            doc_type_value = "STRUCTURE_ERROR" # Default if structure is wrong
                            metadata_top = result.get("metadata")

                            if isinstance(metadata_top, dict):
                                # Check for nested metadata just in case
                                if isinstance(metadata_top.get("metadata"), dict):
                                    found_nested_metadata = True
                                # Get doc_type safely
                                doc_type_value = metadata_top.get("doc_type", "MISSING_OR_NONE")
                            else:
                                logger.warning(f"Result {i} has invalid or missing top-level metadata.")
                                doc_type_value = "METADATA_INVALID_OR_MISSING"

                            doc_type_counts[str(doc_type_value)] += 1 # Use str() for safety

                        logger.info(f"Doc Type Summary for filter '{collection_filter}': {dict(doc_type_counts)}")
                        if found_nested_metadata:
                            logger.warning("Detected nested 'metadata' key within top-level 'metadata' for at least one result.")

                    else:
                        logger.error(f"Error: 'results' key not found or not a list in response.")
                        logger.error(f"Response sample: {str(data)[:500]}")

                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON response: {e}")
                    logger.error(f"Response text: {response.text[:500]}")
                except Exception as e:
                     logger.error(f"Error processing results: {e}", exc_info=True)

            else:
                logger.error(f"API returned error {response.status_code}")
                try:
                    logger.error(f"Response content: {response.text}")
                except Exception:
                    logger.error("Could not read response content.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to API endpoint {QUERY_ENDPOINT}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)


    logger.info("\n--- API doc_type Test Complete ---")

# --- Run Script ---
if __name__ == "__main__":
    run_tests()

