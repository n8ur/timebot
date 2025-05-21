# /usr/local/lib/timebot/lib/shared/chromadb_collections.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# chromadb_collections.py

import os
import sys
from typing import Dict, Any, Optional, List

import chromadb

from .chromadb_core import db_manager, ChromaDBContext
from .file_utils import check_or_create_directory

verbose=False

def open_collection(
    collection_name: str, 
    db_path: str, 
    embedding_model_name: str,
    force_recreate: bool = False
) -> Optional[ChromaDBContext]:
    """
    Open an existing ChromaDB collection or create a new one if it doesn't exist.
    When the collection exists, it will be opened for appending new records.
    Compatible with ChromaDB 0.6.0+
    
    Args:
        collection_name: Name of the collection
        db_path: Path to the ChromaDB directory
        embedding_model_name: Name of the embedding model to use
        force_recreate: If True, recreate the collection even if it exists
    """
    # Check if we already have this collection open in our context cache
    if collection_name in db_manager.contexts and not force_recreate:
        if verbose:
            print(f"Using cached connection to collection: {collection_name}")
        return db_manager.contexts[collection_name]
    
    # Ensure the ChromaDB directory exists
    if not check_or_create_directory(db_path, create=True):
        sys.stderr.write(
            f"⚠️ Error: Could not create or access ChromaDB directory: {db_path}\n"
        )
        return None
    
    try:
        # Initialize the client
        client = chromadb.PersistentClient(path=db_path)
        
        # Get a ChromaDB-compatible embedding function
        embedding_function = db_manager.get_embedding_function(embedding_model_name)
        
        # Load the embedding model (for context)
        embedding_model = db_manager.embedding_models[embedding_model_name]
        
        # Check if collection exists and if we should recreate it
        all_collection_names = client.list_collections()
        collection_exists = collection_name in all_collection_names
        
        if collection_exists:
            if force_recreate:
                print(f"Force recreating collection: {collection_name}")
                client.delete_collection(name=collection_name)
                collection = client.create_collection(
                    name=collection_name,
                    embedding_function=embedding_function,
                    metadata={"hnsw:space": "cosine", "model": embedding_model_name}
                )
            else:
                try:
                    print(f"Attempting to use existing ChromaDB collection: {collection_name}")
                    collection = client.get_collection(
                        name=collection_name,
                        embedding_function=embedding_function
                    )
                    if verbose:
                        print(f"Successfully opened existing collection '{collection_name}' with model: {embedding_model_name}")
                except Exception as e:
                    if "dimension" in str(e).lower():
                        print(f"⚠️ Dimension mismatch detected. Recreating collection: {collection_name}")
                        client.delete_collection(name=collection_name)
                        collection = client.create_collection(
                            name=collection_name,
                            embedding_function=embedding_function,
                            metadata={"hnsw:space": "cosine", "model": embedding_model_name}
                        )
                    else:
                        # Re-raise if it's not a dimension issue
                        raise
        else:
            print(f"Collection '{collection_name}' not found. Creating it.")
            collection = client.create_collection(
                name=collection_name,
                embedding_function=embedding_function,
                metadata={"hnsw:space": "cosine", "model": embedding_model_name}
            )
        
        # Create and store the context
        context = ChromaDBContext(
            client=client,
            collection=collection,
            embedding_model=embedding_model
        )
        db_manager.contexts[collection_name] = context
        return context
            
    except Exception as e:
        sys.stderr.write(f"⚠️ Error initializing ChromaDB: {e}\n")
        return None


def open_existing_collection(
    collection_name: str,
    db_path: str,
    embedding_model_name: str
) -> ChromaDBContext:
    """
    Open an existing ChromaDB collection. Will raise an exception if the collection doesn't exist.
    Compatible with ChromaDB 0.6.0+

    Args:
        collection_name: Name of the collection
        db_path: Path to the ChromaDB directory
        embedding_model_name: Name of the embedding model to use

    Returns:
        ChromaDBContext object with client, collection, and embedding model

    Raises:
        ValueError: If the collection doesn't exist
    """
    # Check if we already have this collection open in our context cache
    if collection_name in db_manager.contexts:
        if verbose:
            print(f"Using cached connection to collection: {collection_name}")
        return db_manager.contexts[collection_name]

    # Ensure the ChromaDB directory exists
    if not os.path.exists(db_path):
        raise ValueError(f"ChromaDB directory does not exist: {db_path}")

    try:
        # Initialize the client
        client = chromadb.PersistentClient(path=db_path)

        # Get a ChromaDB-compatible embedding function
        embedding_function = db_manager.get_embedding_function(embedding_model_name)

        # Load the embedding model (for context)
        embedding_model = db_manager.embedding_models[embedding_model_name]

        # Check if collection exists
        all_collection_names = client.list_collections()

        if collection_name not in all_collection_names:
            raise ValueError(f"Collection '{collection_name}' not found in ChromaDB")

        # Open the existing collection
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        if verbose:
            print(f"Successfully opened existing collection '{collection_name}' with model: {embedding_model_name}")

        # Create and store the context
        context = ChromaDBContext(
            client=client,
            collection=collection,
            embedding_model=embedding_model
        )
        db_manager.contexts[collection_name] = context
        return context

    except Exception as e:
        sys.stderr.write(f"⚠️ Error initializing ChromaDB: {e}\n")
        raise


def document_exists(collection_name: str, doc_hash: str) -> bool:
    """
    Check if a document with the given hash already exists in the collection.
    Compatible with ChromaDB 0.6.0+
    """
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened")
    
    collection = db_manager.contexts[collection_name].collection
    results = collection.get(ids=[doc_hash], include=[])
    
    # In ChromaDB 0.6.0+, if the document exists, results['ids'] will be non-empty
    return len(results['ids']) > 0


def add_document(
    collection_name: str, 
    content: str, 
    metadata: Dict[str, Any], 
    verbose: bool = False
) -> bool:
    """Add a document to the collection if it doesn't already exist."""
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened")
    
    doc_hash = metadata.get("hash")
    if not doc_hash:
        raise ValueError("Metadata must contain a 'hash' field")
    
    # Check if document already exists
    if document_exists(collection_name, doc_hash):
        if verbose:
            print(f"Document with hash {doc_hash} already exists in collection")
        return False
    
    # Add the document
    collection = db_manager.contexts[collection_name].collection
    collection.add(
        ids=[doc_hash],
        documents=[content],
        metadatas=[metadata]
    )
    
    if verbose:
        url = metadata.get('url', 'Unknown URL')
        print(f"✅ Ingested into ChromaDB: {url}")
    
    return True


def add_documents_batch(
    collection_name: str,
    contents: List[str],
    metadatas: List[Dict[str, Any]],
    batch_size: int = 64,  # Adjustable batch size
    verbose: bool = False
) -> List[bool]:
    """Add multiple documents in optimized batches, skipping those that already exist."""
    if collection_name not in db_manager.contexts:
        raise ValueError(f"Collection '{collection_name}' not opened")
    
    if len(contents) != len(metadatas):
        raise ValueError("Contents and metadatas must have the same length")
    
    results = [False] * len(contents)
    collection = db_manager.contexts[collection_name].collection
    
    # Process in optimized batches
    for i in range(0, len(contents), batch_size):
        batch_contents = contents[i:i+batch_size]
        batch_metadatas = metadatas[i:i+batch_size]
        
        # Get hashes for this batch
        batch_hashes = [m.get("hash") for m in batch_metadatas]
        if None in batch_hashes:
            raise ValueError("All metadata items must contain a 'hash' field")
        
        # Check which documents in this batch already exist
        existing_docs = collection.get(ids=batch_hashes, include=[])
        existing_ids = set(existing_docs['ids'])
        
        # Filter out documents that already exist
        new_contents = []
        new_metadatas = []
        new_ids = []
        
        for j, doc_hash in enumerate(batch_hashes):
            if doc_hash not in existing_ids:
                new_contents.append(batch_contents[j])
                new_metadatas.append(batch_metadatas[j])
                new_ids.append(doc_hash)
                results[i+j] = True
        
        # Add new documents in batch if any
        if new_contents:
            collection.add(
                ids=new_ids,
                documents=new_contents,
                metadatas=new_metadatas
            )
            
            if verbose:
                for j, idx in enumerate(range(i, min(i+batch_size, len(contents)))):
                    if results[idx]:
                        url = metadatas[idx].get('url', 'Unknown URL')
                        print(f"✅ Ingested into ChromaDB: {url}")
    
    return results


# For backward compatibility with existing code
def initialize_chromadb(collection_name, db_path, embedding_model_name):
    """Legacy function for backward compatibility."""
    return open_collection(collection_name, db_path, embedding_model_name)


def ingest_to_chromadb(collection, content, metadata, verbose=False):
    """Legacy function for backward compatibility."""
    # Try to get the collection name
    try:
        collection_name = collection.name
    except AttributeError:
        # If collection is actually a ChromaDBContext
        if hasattr(collection, 'collection'):
            collection_name = collection.collection.name
        else:
            raise ValueError("Cannot determine collection name from provided object")
    
    return add_document(collection_name, content, metadata, verbose)

