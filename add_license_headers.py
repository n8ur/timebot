#!/usr/bin/env python3
# /usr/local/lib/timebot/add_license_headers.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Bulk-add copyright and MIT license headers to all eligible files in a directory tree.
- Adds a comment with the full file path at the top.
- Preserves #! (shebang) lines at the top of scripts.
- Supports Python, Shell, HTML, JS, CSS, and TXT files.
- Skips files that already have the copyright header.
"""
import os
import sys
import re
from pathlib import Path

# --- Configurable ---
ROOT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
HEADER_LINES = {
    '.py': [
        '# Copyright 2025 John Ackermann',
        '# Licensed under the MIT License. See LICENSE.TXT for details.'
    ],
    '.sh': [
        '# Copyright 2025 John Ackermann',
        '# Licensed under the MIT License. See LICENSE.TXT for details.'
    ],
    '.js': [
        '/* Copyright 2025 John Ackermann',
        '   Licensed under the MIT License. See LICENSE.TXT for details. */'
    ],
    '.css': [
        '/* Copyright 2025 John Ackermann',
        '   Licensed under the MIT License. See LICENSE.TXT for details. */'
    ],
    '.html': [
        '<!-- Copyright 2025 John Ackermann',
        '     Licensed under the MIT License. See LICENSE.TXT for details. -->'
    ],
    '.txt': [
        'Copyright 2025 John Ackermann',
        'Licensed under the MIT License. See LICENSE.TXT for details.'
    ]
}

SUPPORTED_EXTS = set(HEADER_LINES.keys())

COPYRIGHT_RE = re.compile(r'Copyright 2025 John Ackermann', re.IGNORECASE)


def get_comment_block(ext, filepath):
    header = HEADER_LINES[ext]
    if ext in ['.js', '.css']:
        path_comment = f'/* {filepath} */'
    elif ext == '.html':
        path_comment = f'<!-- {filepath} -->'
    elif ext == '.txt':
        path_comment = f'{filepath}'
    else:
        path_comment = f'# {filepath}'
    return [path_comment] + header + ['']

# Regex to match a possible existing path comment (for all supported types)
PATH_COMMENT_PATTERNS = {
    '.py': re.compile(r'^#\s*/.*'),
    '.sh': re.compile(r'^#\s*/.*'),
    '.js': re.compile(r'^/\*\s*/.*\s*\*/'),
    '.css': re.compile(r'^/\*\s*/.*\s*\*/'),
    '.html': re.compile(r'^<!--\s*/.*\s*-->'),
    '.txt': re.compile(r'^/.*'),
}

def file_needs_header(filepath, ext):
    # Always return True now, since we always want to update the path comment
    return True


def insert_header(filepath, ext):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[SKIP] Could not read {filepath}: {e}")
        return

    # Preserve shebang
    shebang = ''
    start_idx = 0
    if lines and lines[0].startswith('#!'):
        shebang = lines[0]
        start_idx = 1

    # Remove any existing path comment (immediately after shebang or at top)
    if len(lines) > start_idx:
        path_pat = PATH_COMMENT_PATTERNS.get(ext)
        if path_pat and path_pat.match(lines[start_idx]):
            start_idx += 1

    # Remove any existing copyright/license header (next lines)
    # Only remove if the header is present and matches our format
    header_lines = HEADER_LINES[ext]
    for hline in header_lines:
        if len(lines) > start_idx and hline in lines[start_idx]:
            start_idx += 1

    # Remove trailing empty line after header if present
    if len(lines) > start_idx and lines[start_idx].strip() == '':
        start_idx += 1

    header_block = get_comment_block(ext, filepath)
    new_lines = []
    if shebang:
        new_lines.append(shebang.rstrip('\n'))
    new_lines.extend(header_block)
    new_lines.extend([line.rstrip('\n') for line in lines[start_idx:]])

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')
        print(f"[UPDATED] {filepath}")
    except Exception as e:
        print(f"[FAIL] Could not write {filepath}: {e}")


def should_skip_file(path):
    # Skip hidden, backup, compiled, or ignored files
    basename = os.path.basename(path)
    if basename.startswith('.') or basename.endswith('~') or basename.endswith('.bak'):
        return True
    if basename.endswith('.pyc') or basename.endswith('.pyo'):
        return True
    return False


def main():
    for dirpath, _, filenames in os.walk(ROOT_DIR):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_EXTS and not should_skip_file(fpath):
                if file_needs_header(fpath, ext):
                    insert_header(fpath, ext)
                else:
                    print(f"[SKIP] {fpath} (already has header)")

if __name__ == '__main__':
    main()
