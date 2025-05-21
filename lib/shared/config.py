# /usr/local/lib/timebot/lib/shared/config.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# config.py

"""Configuration settings for the application."""

import os
import argparse
from dotenv import load_dotenv

load_dotenv("/etc/timebot/config")
load_dotenv("/etc/timebot/secrets")

"""
We're not calling argparse because that messes up gunicorn
parser = argparse.ArgumentParser(
    description="Timebot Configuration Tool"
)

parser.add_argument(
    "--verbose", action="store_true", help="Enable verbose output"
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Perform a dry run without making changes",
)

args = parser.parse_args()
"""

# --- Load Configuration Values ---
# (All values from environment variables, command-line
# arguments take precedence)

# Get all environment variables
_CONFIG = dict(os.environ)  # Use _CONFIG to avoid naming conflicts

# Add command-line arguments to the configuration 
# (overwriting environment variables)
#_CONFIG["VERBOSE"] = args.verbose  # Boolean
#_CONFIG["DRY_RUN"] = args.dry_run
_CONFIG["VERBOSE"] = False
_CONFIG["DRY_RUN"] = False

# Remove any trailing slash froms vars for clean path creation
for key, value in _CONFIG.items():
    if isinstance(value, str):
        if value != '/' and value.endswith('/'):
            _CONFIG[key] = value.rstrip('/')

# Convert String to Numeric Type (If Appropriate)
for key, value in _CONFIG.items():
    try:
        _CONFIG[key] = int(value)
    except ValueError:
        # Check if the value is quoted; if so, remove the quotes
        if value.startswith('"') and value.endswith('"'):
            _CONFIG[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            _CONFIG[key] = value[1:-1]

        # Now see if it's a boolean
        lower_value = value.lower()
        if lower_value in ("true", "yes", "on"):
            _CONFIG[key] = True
            continue
        elif lower_value in ("false", "no", "off"):
            _CONFIG[key] = False
            continue

# --- Create a Dictionary-Like Object (Read-Only Access) ---
class ConfigDict(object):
    """Read-only dictionary-like object for configuration."""
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __getattr__(self, name):
      try:
        return self.__getitem__(name)
      except KeyError:
        raise AttributeError(name)

    def __setattr__(self, key, value):
        # Prevent accidental modification
        if key == '_data':
            super().__setattr__(key, value)
        else:
            raise TypeError("ConfigDict is read-only")

    def __delattr__(self, item):
      raise TypeError("ConfigDict is read-only")

# Create the ConfigDict instance
config = ConfigDict(_CONFIG)

# --- Print Configuration (Optional, for debugging) ---
if config.get("VERBOSE"):
    print("--- Configuration ---")
    for key, value in config.items():
        print(f"{key}: {value}")

