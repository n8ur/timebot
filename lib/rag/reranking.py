# /usr/local/lib/timebot/lib/rag/reranking.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""Reranking module for search results."""

from typing import List, Dict, Any

# Global variable to store the loaded reranker model
_RERANKER_INSTANCE = None

def get_reranker(model_name_or_path=None):
    """
    Get or initialize the reranker model.
    
    Args:
        model_name_or_path: The name or path of the reranker model
        
    Returns:
        The initialized reranker model
    """
    global _RERANKER_INSTANCE
    
    # If model is already loaded and we're requesting the same one, return it
    if _RERANKER_INSTANCE is not None:
        return _RERANKER_INSTANCE
    
    # Otherwise, load the model
    print("model_name_or_path:",model_name_or_path)
    if model_name_or_path:
        try:
            # Import here to avoid circular imports
            from sentence_transformers import CrossEncoder
            
            print(f"Loading reranker model: {model_name_or_path}")
            _RERANKER_INSTANCE = CrossEncoder(model_name_or_path)
            return _RERANKER_INSTANCE
        except Exception as e:
            print(f"⚠️ Error loading reranker model: {e}")
            return None
    
    return None


def rerank_results(query: str, results: List[Dict[str, Any]], model_name_or_path=None):
    """
    Rerank search results using a cross-encoder reranker model.

    Args:
        query: The search query string
        results: List of search result dictionaries
        model_name_or_path: The name or path of the reranker model

    Returns:
        List of reranked search results
    """
    if not results:
        return results

    # Get or initialize the reranker
    reranker = get_reranker(model_name_or_path)

    if not reranker:
        return results

    try:
        # Prepare pairs of (query, document) for reranking
        pairs = []
        for result in results:
            # Try different field names for content
            content = (
                result.get("content") or
                result.get("snippet") or
                result.get("message") or
                result.get("text", "")
            )
            pairs.append((query, content))

        # Get reranking scores
        rerank_scores = reranker.predict(pairs)

        # Add reranking scores to results
        for i, score in enumerate(rerank_scores):
            results[i]["rerank_score"] = float(score)
            results[i]["original_score"] = results[i].get("score", 0)  # Keep original score
            results[i]["score"] = float(score)  # Replace with reranking score for sorting

        # Sort by reranking score (higher is better)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return results
    except Exception as e:
        print(f"⚠️ Error during reranking: {e}")
        # Add more detailed error logging
        import traceback
        print(f"Reranking error details: {traceback.format_exc()}")
        return results  # Return original results if reranking fails

