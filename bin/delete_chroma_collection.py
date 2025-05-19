#!/usr/bin/env python3
import os
import sys
import argparse
import chromadb
from typing import List

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config

# Import the ChromaDB utilities
from shared.chromadb_utils import (
    db_manager, close_collection
)

def list_collections(db_path: str) -> List[str]:
    """List all collections in the ChromaDB database."""
    try:
        client = chromadb.PersistentClient(path=db_path)
        return client.list_collections()
    except Exception as e:
        print(f"Error listing collections: {e}")
        sys.exit(1)

def delete_collection(db_path: str, collection_name: str, force: bool = False) -> bool:
    """
    Delete a collection from ChromaDB with verification.
    
    Args:
        db_path: Path to the ChromaDB directory
        collection_name: Name of the collection to delete
        force: Skip verification if True
        
    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(path=db_path)
        
        # Check if collection exists
        collections = client.list_collections()
        if collection_name not in collections:
            print(f"Error: Collection '{collection_name}' not found.")
            return False
        
        # Get collection info for verification
        try:
            # We need to get the collection to check its count
            # We don't need an embedding function for this operation
            collection = client.get_collection(name=collection_name)
            doc_count = collection.count()
        except Exception as e:
            print(f"Warning: Could not get collection details: {e}")
            doc_count = "unknown"
        
        # Verification step
        if not force:
            print(f"\nWARNING: You are about to delete collection '{collection_name}'")
            print(f"This collection contains {doc_count} documents.")
            print("This action CANNOT be undone!")
            
            confirmation = input(f"\nTo confirm, type the collection name '{collection_name}': ")
            
            if confirmation != collection_name:
                print("Deletion cancelled: Collection name did not match.")
                return False
        
        # Delete the collection
        client.delete_collection(name=collection_name)
        print(f"Collection '{collection_name}' has been deleted.")
        return True
        
    except Exception as e:
        print(f"Error deleting collection: {e}")
        return False
    finally:
        # Close all collections
        close_collection()

def main():
    parser = argparse.ArgumentParser(description="ChromaDB Collection Deletion Utility")
    parser.add_argument("--db-path", required=True, help="Path to the ChromaDB directory")
    parser.add_argument("--collection", help="Name of the collection to delete")
    parser.add_argument("--force", action="store_true", help="Skip verification (DANGEROUS)")
    parser.add_argument("--list", action="store_true", help="List all collections and exit")
    
    args = parser.parse_args()
    
    # List collections if requested
    if args.list:
        collections = list_collections(args.db_path)
        if collections:
            print("\nAvailable collections:")
            for i, collection in enumerate(collections, 1):
                print(f"{i}. {collection}")
        else:
            print("No collections found.")
        sys.exit(0)
    
    # Check if collection name is provided
    if not args.collection:
        print("Error: Please specify a collection name with --collection")
        print("Use --list to see available collections")
        sys.exit(1)
    
    # Delete the collection
    success = delete_collection(args.db_path, args.collection, args.force)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

