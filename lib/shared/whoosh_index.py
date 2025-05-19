# whoosh_index.py

import os
from typing import Dict, Any
from .whoosh_schema import define_whoosh_schema
from whoosh.index import create_in, open_dir

def initialize_whoosh_index(index_dir: str, schema_type: str = "email") -> Any:
    """
    Initialize or open a Whoosh index.

    Args:
        index_dir: Directory path for the Whoosh index
        schema_type: Type of schema to use if creating a new index

    Returns:
        A Whoosh index object
    """
    os.makedirs(index_dir, exist_ok=True)

    if not os.listdir(index_dir):
        print(f"Creating new Whoosh index {index_dir}")
        print(f"    with schema type '{schema_type}'")
        schema = define_whoosh_schema(schema_type)
        return create_in(index_dir, schema)
    else:
        return open_dir(index_dir)


def open_whoosh_index(index_dir: str) -> Any:
    """
    Open an existing Whoosh index without creating a new one.

    Args:
        index_dir: Directory path for the Whoosh index

    Returns:
        A Whoosh index object

    Raises:
        FileNotFoundError: If the index directory doesn't exist
        ValueError: If the directory exists but doesn't contain a valid Whoosh index
    """
    if not os.path.exists(index_dir):
        raise FileNotFoundError(f"Index directory '{index_dir}' does not exist")
    
    if not os.listdir(index_dir):
        raise ValueError(f"Index directory '{index_dir}' exists but is empty")
    
    try:
        return open_dir(index_dir)
    except Exception as e:
        raise ValueError(f"Failed to open Whoosh index in '{index_dir}': {str(e)}")


def get_index_stats(index_dir: str) -> Dict[str, Any]:
    """
    Get statistics about the Whoosh index.

    Args:
        index_dir: Directory path for the Whoosh index

    Returns:
        Dictionary containing index statistics
    """
    ix = open_dir(index_dir)
    
    stats = {
        "doc_count": ix.doc_count(),
        "last_modified": ix.last_modified(),
        "schema_fields": list(ix.schema.names()),
        "index_version": ix.version
    }
    
    return stats

