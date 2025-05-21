#!/usr/bin/env python3
# /usr/local/lib/timebot/lib/tools/debug.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Email Sender Field Debugger

This script specifically focuses on finding email sender information
in the embedding server's response.
"""

import requests
import json
import sys
import re
from typing import Dict, Any, List, Optional

def query_embedding_server(
    server_url: str,
    query: str,
    similarity_threshold: float = 0.5,
    top_k: int = 10,
    use_reranking: bool = True,
    mode: str = "combined"
) -> Dict[str, Any]:
    """Query the embedding server using the same approach as the chat application."""
    
    # Ensure URL has proper format
    if not server_url.startswith(('http://', 'https://')):
        server_url = f"http://{server_url}"
    
    # Prepare the query payload - match the chat application's parameters
    payload = {
        "query": query,
        "similarity_threshold": similarity_threshold,
        "top_k": top_k,
        "use_reranking": use_reranking,
        "mode": mode
    }
    
    print(f"Connecting to embedding server at: {server_url}/api/query")
    print(f"Query: '{query}'")
    
    try:
        response = requests.post(f"{server_url}/api/query", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {type(e).__name__}: {e}")
        return {"error": str(e)}

def find_email_addresses(text: str) -> List[str]:
    """Find all email addresses in a text string."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(email_pattern, text)

def find_all_email_fields(obj, path="", results=None):
    """
    Recursively find all fields that might contain email addresses or sender information.
    """
    if results is None:
        results = []
    
    if isinstance(obj, dict):
        # Check if this is an email document
        is_email = obj.get("doc_type") == "email" if "doc_type" in obj else False
        if "metadata" in obj and "doc_type" in obj["metadata"]:
            is_email = is_email or obj["metadata"]["doc_type"] == "email"
        
        # If this is an email document, record the path and all fields
        if is_email:
            email_info = {
                "path": path,
                "fields": {},
                "email_addresses": []
            }
            
            # Check all string fields for email addresses
            for key, value in obj.items():
                if isinstance(value, str):
                    email_addresses = find_email_addresses(value)
                    if email_addresses:
                        email_info["email_addresses"].extend(email_addresses)
                    
                    # Record fields that might be related to sender
                    if key.lower() in ["from", "from_", "from_field", "sender", "author"]:
                        email_info["fields"][key] = value
                    
                    # Also record subject and date for context
                    if key.lower() in ["subject", "date"]:
                        email_info["fields"][key] = value
            
            # Check content field specifically
            content = obj.get("content", obj.get("text", ""))
            if content and isinstance(content, str):
                # Look for From: lines in the content
                from_lines = re.findall(r'From:.*?(?=\n)', content, re.IGNORECASE)
                if from_lines:
                    email_info["from_lines"] = from_lines
                
                # Find email addresses in content
                content_emails = find_email_addresses(content)
                if content_emails:
                    email_info["content_emails"] = content_emails
            
            # If we found any useful information, add it to results
            if email_info["fields"] or email_info.get("from_lines") or email_info.get("content_emails"):
                results.append(email_info)
        
        # Continue recursion
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            find_all_email_fields(value, new_path, results)
    
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            find_all_email_fields(item, new_path, results)
    
    return results

def main():
    # Get server URL from command line or use default
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    else:
        server_url = "http://localhost:8100"  # Default embedding server URL
    
    # Get query from command line or use default
    if len(sys.argv) > 2:
        query = sys.argv[2]
    else:
        query = "email"  # Default query that should return emails
    
    # Query the embedding server
    response = query_embedding_server(server_url, query)
    
    if "error" in response:
        print("Failed to get response from embedding server.")
        return
    
    # Extract results based on response format
    results = []
    if isinstance(response, list):
        results = response
    elif isinstance(response, dict):
        if "results" in response:
            results = response.get("results", [])
        elif "documents" in response:
            results = response.get("documents", [])
    
    print(f"\nFound {len(results)} results")
    
    # Find all email-related fields
    email_fields = find_all_email_fields(results)
    
    print(f"\nFound {len(email_fields)} email documents with sender information")
    
    # Display the email information
    for i, info in enumerate(email_fields):
        print(f"\nEmail #{i+1} at {info['path']}:")
        
        # Print fields
        if info["fields"]:
            print("  Fields:")
            for key, value in info["fields"].items():
                print(f"    {key}: {value}")
        
        # Print From: lines found in content
        if "from_lines" in info:
            print("  From lines in content:")
            for line in info["from_lines"]:
                print(f"    {line}")
        
        # Print email addresses found in content
        if "content_emails" in info:
            print("  Email addresses in content:")
            for email in info["content_emails"]:
                print(f"    {email}")
    
    # Save full response to file for reference
    with open("embedding_server_email_response.json", "w") as f:
        json.dump(response, f, indent=2)
    print("\nFull response saved to 'embedding_server_email_response.json'")
    
    # Print a summary of what we found
    print("\nSummary:")
    print(f"  Total results: {len(results)}")
    print(f"  Email documents with sender info: {len(email_fields)}")
    
    # Check if we found any From: lines or email addresses
    from_lines_count = sum(1 for info in email_fields if "from_lines" in info)
    content_emails_count = sum(1 for info in email_fields if "content_emails" in info)
    print(f"  Documents with From: lines in content: {from_lines_count}")
    print(f"  Documents with email addresses in content: {content_emails_count}")

if __name__ == "__main__":
    main()

