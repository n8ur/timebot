#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/test_dict.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Diagnostic tool to check the SearchResult.to_dict() method.
"""

import sys
import os
from pprint import pprint

# Add the parent directory to the path so we can import shared modules
sys.path.append('/usr/local/lib/timebot/lib')

# Try to import the SearchResult class
try:
    from shared.chromadb_utils import SearchResult
    
    # Create a test SearchResult object with chunk information
    test_metadata = {
        "chunk_id": "test_chunk_123",
        "chunk_number": 5,
        "total_chunks": 10,
        "title": "Test Document",
        "author": "Test Author"
    }
    
    test_result = SearchResult(
        id="test-id",
        content="This is test content",
        metadata=test_metadata,
        score=0.95,
        search_provider="Test Provider"
    )
    
    print("Original SearchResult metadata:")
    pprint(test_result.metadata)
    
    print("\nConverted to dictionary:")
    result_dict = test_result.to_dict()
    pprint(result_dict)
    
    print("\nChecking for chunk information in dictionary:")
    print(f"  chunk_id: {'chunk_id' in result_dict}")
    print(f"  chunk_number: {'chunk_number' in result_dict}")
    print(f"  total_chunks: {'total_chunks' in result_dict}")
    
except ImportError as e:
    print(f"Error importing SearchResult: {e}")
    print("Let's try to find the file that defines SearchResult...")
    
    # Try to locate the file that defines SearchResult
    for root, dirs, files in os.walk('/usr/local/lib/timebot/lib'):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    content = f.read()
                    if 'class SearchResult' in content:
                        print(f"Found SearchResult class in: {file_path}")
                        print("\nClass definition:")
                        start_idx = content.find('class SearchResult')
                        end_idx = content.find('class', start_idx + 1)
                        if end_idx == -1:
                            end_idx = len(content)
                        print(content[start_idx:end_idx])
                        break

