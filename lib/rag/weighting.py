# /usr/local/lib/timebot/lib/rag/weighting.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Weighting module for search results.
This module provides functions to apply various weighting factors to search results.
"""

import datetime
from dateutil import parser as date_parser
from typing import List, Dict, Any

from shared.config import config

def calculate_recency_score(date_str, recency_decay_days):
    """
    Calculate a recency score based on document date.
    Newer documents get higher scores.
    
    Args:
        date_str: Date string from document
        recency_decay_days: Number of days after which documents get zero recency score
        
    Returns:
        Recency score between 0 and 1
    """
    try:
        if not date_str:
            print(f"Empty date string received, using default score")
            return 0.5  # Default middle value if no date
        # Parse the date string
        doc_date = date_parser.parse(date_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        if doc_date.tzinfo is None:
            doc_date = doc_date.replace(tzinfo=datetime.timezone.utc)
        
        # Calculate days since document was created
        days_old = (datetime.datetime.now(datetime.timezone.utc) - doc_date).days
        
        # Apply decay function
        if days_old <= 0:
            return 1.0
        elif days_old >= recency_decay_days:
            return 0.0
        else:
            # Linear decay from 1.0 to 0.0 over recency_decay_days
            return 1.0 - (days_old / recency_decay_days)
            
    except Exception as e:
        print(f"Error calculating recency score: {e}")
        return 0.5  # Default middle value if date parsing fails

def apply_weighting(results):
    """
    Apply weighting to search results based on configuration.
    This function is a dispatcher that calls the appropriate weighting function.

    Args:
        results: List of search results
        config: Dictionary of configuration parameters

    Returns:
        List of results with weighted scores
    """
    # Skip if weighting is disabled
    # Strict config policy: missing USE_WEIGHTING is a configuration error
    if not config["USE_WEIGHTING"]:
        return results

    # Check if results have been reranked
    has_reranking = any("rerank_score" in result for result in results)

    if has_reranking:
        # If results have already been reranked, apply final weights
        return apply_final_weights(results, config)
    else:
        # If results haven't been reranked yet, apply diversity weights
        return apply_diversity_weights(results, config)


def apply_diversity_weights(results):
    """
    Apply minimal weighting to ensure diversity before reranking.
    This prevents any single source from dominating the results
    sent to the reranker.
    
    Args:
        results: List of search results
        config: Dictionary of configuration parameters
        
    Returns:
        List of results with minimally adjusted scores
    """
    diversity_results = []
    
    # Extract diversity parameters from config
    # Strict config policy: missing DIVERSITY_FACTOR is a configuration error
    from shared.config import config as global_config
    diversity_factor = float(global_config["DIVERSITY_FACTOR"])
    
    # Group results by source type
    by_source = {}
    for result in results:
        source_type = result.get("doc_type", "unknown")
        provider = result.get("search_provider", "unknown")
        key = f"{source_type}_{provider}"
        
        if key not in by_source:
            by_source[key] = []
        by_source[key].append(result)
    
    # Apply minimal diversity adjustment
    for result in results:
        # Make a copy of the result
        adjusted_result = result.copy()
        
        # Store original score
        original_score = result.get("score", 0.0)
        adjusted_result["original_score"] = original_score
        
        # Get source information
        source_type = result.get("doc_type", "unknown")
        provider = result.get("search_provider", "unknown")
        key = f"{source_type}_{provider}"
        
        # Calculate diversity adjustment
        # This is a small factor to ensure diversity without
        # dramatically changing the ranking
        group_size = len(by_source.get(key, []))
        total_results = len(results)
        
        # If this source is overrepresented, slightly reduce its score
        if group_size > (total_results / len(by_source)):
            diversity_adjustment = 1.0 - (diversity_factor * (group_size / total_results))
        else:
            # If underrepresented, slightly boost its score
            diversity_adjustment = 1.0 + (diversity_factor * (1 - (group_size / total_results)))
        
        # Apply the adjustment
        adjusted_score = original_score * diversity_adjustment
        
        # Update the result
        adjusted_result["diversity_adjustment"] = diversity_adjustment
        adjusted_result["score"] = adjusted_score
        
        diversity_results.append(adjusted_result)
    
    return diversity_results

def apply_final_weights(results):
    """
    Apply final weighting after reranking to balance semantic relevance with business rules.
    This is where the full weighting logic is applied.

    Args:
        results: List of reranked results
        config: Dictionary of configuration parameters

    Returns:
        List of results with final scores
    """
    final_results = []

    # Extract weight parameters from config
    weights = {
        # Strict config policy: all weights must be present in config, missing keys are errors
        "document_collection_weight": float(config["DOCUMENT_COLLECTION_WEIGHT"]),
        "email_collection_weight": float(config["EMAIL_COLLECTION_WEIGHT"]),
        "web_collection_weight": float(config["WEB_COLLECTION_WEIGHT"]),
        "recency_weight": float(config["RECENCY_WEIGHT"]),
        "recency_decay_days": int(config["RECENCY_DECAY_DAYS"]),
        "chromadb_weight": float(config["CHROMADB_WEIGHT"]),
        "whoosh_weight": float(config["WHOOSH_WEIGHT"]),
        "reranker_weight": float(config["RERANKER_WEIGHT"]),
    }

    # Calculate business rules weight as complement of reranker weight
    business_rules_weight = 1.0 - weights["reranker_weight"]

    for result in results:
        # Make a copy of the result
        final_result = result.copy()

        # Get the reranker score (this is the semantic relevance)
        rerank_score = result.get("rerank_score", result.get("score", 0.0))

        # Store original score if not already present
        if "original_score" not in final_result:
            final_result["original_score"] = result.get("score", 0.0)

        # Determine source type (email, document, or web)
        source_type = result.get("doc_type", "email")

        # Apply collection type weight
        if source_type == "email":
            collection_weight = weights["email_collection_weight"]
            # Get date from email
            date_str = result.get("date", "")
        elif source_type == "web":
            collection_weight = weights["web_collection_weight"]
            # Get captured_at date from web document
            date_str = result.get("captured_at", "")
        else:  # document
            collection_weight = weights["document_collection_weight"]
            # Get date from document
            date_str = result.get("publication_date", result.get("date", ""))

        # Calculate recency score
        recency_score = calculate_recency_score(date_str, weights["recency_decay_days"])

        # Apply recency weight
        recency_factor = 1.0 + (recency_score * weights["recency_weight"])

        # Apply source weight (ChromaDB vs Whoosh)
        provider = result.get("search_provider", "").lower()
        source_weight = weights["chromadb_weight"] if "chroma" in provider else weights["whoosh_weight"]

        # Calculate business rules score
        business_score = final_result["original_score"] * collection_weight * recency_factor * source_weight

        # Normalize scores if needed
        normalized_rerank_score = min(max(rerank_score, 0.0), 1.0)

        # Calculate final score as a weighted combination
        # This balances semantic relevance with business rules
        final_score = (normalized_rerank_score * weights["reranker_weight"]) + \
                      (business_score * business_rules_weight)

        # Update the result with all weighting factors for transparency
        final_result["collection_weight"] = collection_weight
        final_result["recency_score"] = recency_score
        final_result["recency_factor"] = recency_factor
        final_result["source_weight"] = source_weight
        final_result["business_score"] = business_score
        final_result["final_score"] = final_score
        final_result["score"] = final_score  # Replace score with final score for sorting

        final_results.append(final_result)

    return final_results

