# /usr/local/lib/timebot/lib/shared/config.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.



"""Configuration settings for the application."""

import os
from dotenv import load_dotenv

# --- Default Config Vars ---
# These can be overridden by environment variables or dotenv files
_CONFIG = {
    "VERBOSE": False,
    "DRY_RUN": False
}

# --- Load dotenv files with warnings and override for secrets ---
CONFIG_PATH = "/etc/timebot/config"
SECRETS_PATH = "/etc/timebot/secrets"

if not os.path.exists(CONFIG_PATH):
    print(f"Warning: Config file {CONFIG_PATH} not found.")
load_dotenv(CONFIG_PATH)

if not os.path.exists(SECRETS_PATH):
    print(f"Warning: Secrets file {SECRETS_PATH} not found.")
load_dotenv(SECRETS_PATH, override=True)

# Update _CONFIG with environment variables (dotenv will populate os.environ)
_CONFIG.update(os.environ)

# --- Normalize and convert config values in a single pass ---
for key, value in list(_CONFIG.items()):
    if isinstance(value, str):
        # Remove trailing slash (but not if value is just "/")
        if value != '/' and value.endswith('/'):
            value = value.rstrip('/')
        # Remove surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        # Try to convert to int
        try:
            value = int(value)
        except ValueError:
            # Try to convert to bool
            lower_value = value.lower()
            if lower_value in ("true", "yes", "on"):
                value = True
            elif lower_value in ("false", "no", "off"):
                value = False
        _CONFIG[key] = value
    except ValueError:
        # Check if the value is quoted; if so, remove the quotes
        if value.startswith('"') and value.endswith('"'):
            _CONFIG[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            _CONFIG[key] = value[1:-1]


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

