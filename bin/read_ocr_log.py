#!/bin/env python3
# /usr/local/lib/timebot/bin/read_ocr_log.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import json
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional


def load_json_records(file_path: str) -> List[Dict[str, Any]]:
    """Load JSON records from a file where each line is a separate JSON object."""
    records = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if line:  # Skip empty lines
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    print(f"Problematic line: {line}")
    return records


def format_record(record: Dict[str, Any]) -> str:
    """Format a single record in a human-friendly way."""
    metadata = record.get("metadata", {})

    # Format author field
    author = metadata.get("author", "")
    if author:
        author = f"by {author}"

    # Format publisher information
    publisher = metadata.get("publisher", "")
    publisher_id = metadata.get("publisher_id", "")
    if publisher and publisher_id:
        publisher_info = f"{publisher}, {publisher_id}"
    elif publisher:
        publisher_info = publisher
    else:
        publisher_info = ""

    # Format publication date
    pub_date = metadata.get("publication_date", "")

    # Build the formatted string
    title = metadata.get("title", "Untitled")
    seq_num = record.get("sequence_number", "N/A")

    formatted = f"[{seq_num}] {title}"
    if author:
        formatted += f" {author}"
    if pub_date:
        formatted += f" ({pub_date})"
    if publisher_info:
        formatted += f"\n    Published by: {publisher_info}"

    original_file = metadata.get("original_filename", "")
    if original_file:
        formatted += f"\n    Original file: {original_file}"

    processed_file = record.get("processed_pdf_name", "")
    if processed_file:
        formatted += f"\n    Processed as: {processed_file}"

    return formatted


def sort_records(records: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
    """Sort records based on the specified criterion."""
    if sort_by == "title":
        return sorted(records, key=lambda x: x.get("metadata", {}).get("title", "").lower())
    elif sort_by == "date":
        # Try to parse publication dates for sorting
        def get_pub_date(record):
            date_str = record.get("metadata", {}).get("publication_date", "")
            # Try to extract a year from the date string
            try:
                # First try to parse as a full date
                return datetime.strptime(date_str, "%Y")
            except ValueError:
                # If that fails, just try to extract a year as an integer
                try:
                    return int(date_str)
                except (ValueError, TypeError):
                    return 0  # Default for sorting if date can't be parsed

        return sorted(records, key=get_pub_date)
    elif sort_by == "sequence":
        return sorted(records, key=lambda x: x.get("sequence_number", 0))
    else:
        return records  # No sorting


def main():
    parser = argparse.ArgumentParser(description="Format JSON library records in a human-friendly way")
    parser.add_argument("file_path", help="Path to the JSON file containing library records")
    parser.add_argument("--sort", choices=["title", "date", "sequence"], default="sequence",
                        help="Sort records by title, publication date, or sequence number (default: sequence)")
    args = parser.parse_args()

    try:
        records = load_json_records(args.file_path)
        sorted_records = sort_records(records, args.sort)

        print(f"Found {len(records)} records, sorted by {args.sort}:\n")
        for record in sorted_records:
            print(format_record(record))
            print()  # Add a blank line between records

    except FileNotFoundError:
        print(f"Error: File '{args.file_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()

