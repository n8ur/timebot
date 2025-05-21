# /usr/local/lib/timebot/lib/shared/file_utils.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# file_utils.py

import os

def check_or_create_directory(path, create=True):
    """Check if a directory exists and create it if needed."""
    path_exists = os.path.exists(path)
    is_dir = os.path.isdir(path) if path_exists else False

    if path_exists and not is_dir:
        print(f"WARNING: Path exists but is not a directory!")
        return False

    if not path_exists and create:
        try:
            os.makedirs(path, exist_ok=True)
            print(f"Created directory: {path}")
            return True
        except Exception as e:
            print(f"ERROR creating directory: {e}")
            return False

    return path_exists and is_dir

