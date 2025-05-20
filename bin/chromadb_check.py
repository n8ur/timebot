#!/usr/bin/env python3
import sys
import random
import argparse
import json
import chromadb
from typing import Dict, Any, List, Optional

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config
# Import the ChromaDB utilities
from shared.chromadb_utils import (
    db_manager, open_existing_collection, close_collection
)

def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0 or unit == 'TB':
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

def pretty_print_metadata(metadata: Dict[str, Any], indent: int = 0) -> None:
    """Pretty print metadata with proper indentation for nested structures."""
    for key, value in metadata.items():
        if isinstance(value, dict):
            print(f"{' ' * indent}{key}:")
            pretty_print_metadata(value, indent + 2)
        elif isinstance(value, list):
            print(f"{' ' * indent}{key}: [")
            for item in value:
                if isinstance(item, dict):
                    pretty_print_metadata(item, indent + 2)
                else:
                    print(f"{' ' * indent}  {item}")
            print(f"{' ' * indent}]")
        else:
            print(f"{' ' * indent}{key}: {value}")

def get_collection_stats(db_path: str, collection_name: str, embedding_model_name: str) -> Dict[str, Any]:
    """Get statistics for a specific collection."""
    try:
        # Open the collection
        context = open_existing_collection(collection_name, db_path, embedding_model_name)
        collection = context.collection

        # Get collection count
        count = collection.count()

        # Get collection metadata
        collection_metadata = collection.metadata

        # Get a sample of IDs to estimate average document size
        sample_size = min(100, count)
        if sample_size > 0:
            # Get a sample of documents to estimate average size
            sample_results = collection.get(
                limit=sample_size,
                include=["documents", "metadatas"]
            )

            # Calculate average document size
            total_size = sum(len(doc.encode('utf-8')) for doc in sample_results["documents"])
            avg_doc_size = total_size / sample_size if sample_size > 0 else 0

            # Estimate total size
            estimated_total_size = avg_doc_size * count

            # Get unique metadata keys
            metadata_keys = set()
            for metadata in sample_results["metadatas"]:
                metadata_keys.update(metadata.keys())

            return {
                "name": collection_name,
                "count": count,
                "metadata": collection_metadata,
                "avg_document_size": avg_doc_size,
                "estimated_total_size": estimated_total_size,
                "metadata_keys": sorted(list(metadata_keys))
            }
        else:
            return {
                "name": collection_name,
                "count": 0,
                "metadata": collection_metadata,
                "avg_document_size": 0,
                "estimated_total_size": 0,
                "metadata_keys": []
            }
    except Exception as e:
        return {
            "name": collection_name,
            "error": str(e)
        }

def get_random_record(db_path: str, collection_name: str, embedding_model_name: str) -> Optional[Dict[str, Any]]:
    """Get a random record from the collection."""
    try:
        # Open the collection
        context = open_existing_collection(collection_name, db_path, embedding_model_name)
        collection = context.collection

        # Get collection count
        count = collection.count()

        if count == 0:
            print(f"Collection '{collection_name}' is empty.")
            return None

        # Get all IDs (this could be inefficient for very large collections)
        all_ids = collection.get(include=["embeddings"])["ids"]

        # Select a random ID
        random_id = random.choice(all_ids)

        # Get the full record for this ID
        record = collection.get(
            ids=[random_id],
            include=["documents", "metadatas", "embeddings"]
        )

        return {
            "id": record["ids"][0],
            "document": record["documents"][0],
            "metadata": record["metadatas"][0],
            "embedding_length": len(record["embeddings"][0])
        }
    except Exception as e:
        print(f"Error getting random record: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="ChromaDB Collection Statistics Utility")
    parser.add_argument("--db-path", required=True, help="Path to the ChromaDB directory")
    parser.add_argument("--embedding-model", required=True, help="Name of the embedding model")
    parser.add_argument("--collection", help="Specific collection to analyze (default: all collections)")
    parser.add_argument("--random-record", action="store_true", help="Show a random record from the collection")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

    args = parser.parse_args()

    try:
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(path=args.db_path)

        # Get collection names
        collection_names = client.list_collections()

        if args.collection:
            if args.collection not in collection_names:
                print(f"Error: Collection '{args.collection}' not found.")
                sys.exit(1)
            collection_names = [args.collection]

        results = []

        for collection_name in collection_names:
            stats = get_collection_stats(args.db_path, collection_name, args.embedding_model)
            results.append(stats)

            if not args.json:
                print(f"\n{'=' * 50}")
                print(f"Collection: {collection_name}")
                print(f"{'=' * 50}")
                print(f"Document count: {stats['count']:,}")
                print(f"Average document size: {format_size(stats['avg_document_size'])}")
                print(f"Estimated total size: {format_size(stats['estimated_total_size'])}")
                print(f"Collection metadata: {stats['metadata']}")
                print(f"Metadata keys: {', '.join(stats['metadata_keys'])}")

                if args.random_record and stats['count'] > 0:
                    random_record = get_random_record(args.db_path, collection_name, args.embedding_model)
                    if random_record:
                        print(f"\n{'-' * 50}")
                        print(f"Random Record (ID: {random_record['id']})")
                        print(f"{'-' * 50}")
                        print(f"Embedding length: {random_record['embedding_length']}")
                        print(f"\nMetadata:")
                        pretty_print_metadata(random_record['metadata'], 2)

                        # Print a preview of the document content
                        doc_preview = random_record['document'][:500]
                        if len(random_record['document']) > 500:
                            doc_preview += "..."
                        print(f"\nDocument preview:")
                        print(f"  {doc_preview}")

        if args.json:
            if args.random_record and args.collection:
                # Include a random record in the JSON output if requested
                random_record = get_random_record(args.db_path, args.collection, args.embedding_model)
                if random_record:
                    results[0]["random_record"] = random_record

            print(json.dumps(results, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Close all collections using your function
        close_collection()

if __name__ == "__main__":
    main()

