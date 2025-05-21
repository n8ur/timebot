# /usr/local/lib/timebot/lib/rag/text_processing.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Text processing utilities for the RAG application.
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings.
    
    This implementation uses Jaccard similarity on word sets,
    which is simple and effective for detecting near-duplicates.
    
    Args:
        text1: First text string
        text2: Second text string
        
    Returns:
        Similarity score between 0 and 1
    """
    # Convert to lowercase and tokenize by splitting on whitespace
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # Calculate Jaccard similarity: intersection / union
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    if union == 0:
        return 0.0
    
    return intersection / union

def deduplicate_by_content(results: List[Dict[str, Any]], similarity_threshold: float = 0.85) -> List[Dict[str, Any]]:
    """
    Deduplicate results based on content similarity.
    Only deduplicates documents, not emails.

    Args:
        results: List of search results
        similarity_threshold: Threshold above which documents are considered duplicates

    Returns:
        List of deduplicated results
    """
    if not results:
        return []

    # Keep track of which results to include
    include_result = [True] * len(results)

    # Extract only document results (not emails)
    doc_indices = [i for i, result in enumerate(results)
                  if result.get("doc_type") == "document"]

    # For each pair of document results, check if they're duplicates
    for idx, i in enumerate(doc_indices):
        if not include_result[i]:
            continue  # Skip if already marked as duplicate

        content_i = results[i].get("content", "").strip()
        if not content_i:
            continue  # Skip if no content

        for j in doc_indices[idx + 1:]:
            if not include_result[j]:
                continue  # Skip if already marked as duplicate

            content_j = results[j].get("content", "").strip()
            if not content_j:
                continue  # Skip if no content

            # Calculate similarity
            similarity = calculate_text_similarity(content_i, content_j)

            # If similarity is above threshold, mark one as duplicate
            if similarity > similarity_threshold:
                score_i = results[i].get("score", 0)
                score_j = results[j].get("score", 0)

                # Handle score ties by using secondary criteria
                if abs(score_i - score_j) < 0.0001:  # Consider scores equal if very close
                    # In case of a tie, prefer the document with:
                    # 1. More recent date (if available)
                    # 2. Lower chunk number (if from same document)
                    # 3. Otherwise, keep the first one

                    # Try to compare dates
                    date_i = results[i].get("date", "")
                    date_j = results[j].get("date", "")

                    if date_i and date_j and date_i != date_j:
                        # Keep the more recent document
                        if date_i > date_j:
                            include_result[j] = False
                            logger.debug(f"Marked document {j} as duplicate of {i} (tie broken by date)")
                        else:
                            include_result[i] = False
                            logger.debug(f"Marked document {i} as duplicate of {j} (tie broken by date)")
                            break

                    # If dates don't resolve the tie, check if they're chunks from the same document
                    parent_i = results[i].get("parent_hash", "")
                    parent_j = results[j].get("parent_hash", "")

                    if parent_i and parent_j and parent_i == parent_j:
                        # Same document, prefer lower chunk number
                        chunk_i = results[i].get("chunk_number", 0)
                        chunk_j = results[j].get("chunk_number", 0)

                        if chunk_i <= chunk_j:
                            include_result[j] = False
                            logger.debug(f"Marked document {j} as duplicate of {i} (tie broken by chunk number)")
                        else:
                            include_result[i] = False
                            logger.debug(f"Marked document {i} as duplicate of {j} (tie broken by chunk number)")
                            break

                    # If we still have a tie, keep the first one
                    else:
                        include_result[j] = False
                        logger.debug(f"Marked document {j} as duplicate of {i} (tie broken by order)")

                # If scores are different, keep the higher one
                elif score_i >= score_j:
                    include_result[j] = False
                    logger.debug(f"Marked document {j} as duplicate of {i} (similarity: {similarity:.2f})")
                else:
                    include_result[i] = False
                    logger.debug(f"Marked document {i} as duplicate of {j} (similarity: {similarity:.2f})")
                    break  # No need to check more pairs for i

    # Return only the results that weren't marked as duplicates
    return [result for i, result in enumerate(results) if include_result[i]]

def print_ranking_debug(results, stage_name):
    """
    Print a concise summary of document IDs and scores for debugging.
    
    Args:
        results: List of search results
        stage_name: String indicating the current processing stage
    """
    print(f"\n=== {stage_name} ===")
    print(f"{'Type':<8} {'ID':<40} {'Score':<10} {'Collection Weight':<18}")
    print("-" * 80)
    
    # Sort by score descending for consistent display
    sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    
    # Print top results (adjust the number as needed)
    for i, result in enumerate(sorted_results[:10]):  # Show top 10
        doc_type = result.get('doc_type', 'unknown')
        doc_id = result.get('id', '')[:38]  # Truncate long IDs
        score = result.get('score', 0)
        collection_weight = result.get('collection_weight', 'N/A')
        
        print(f"{doc_type:<8} {doc_id:<40} {score:<10.6f} {collection_weight}")
    
    # Print count by type
    email_count = sum(1 for r in sorted_results if r.get('doc_type') == 'email')
    doc_count = sum(1 for r in sorted_results if r.get('doc_type') == 'document')
    print(f"\nTotal: {len(sorted_results)} results ({doc_count} documents, {email_count} emails)")

