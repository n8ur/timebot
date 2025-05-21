#!/usr/bin/env python3
# /usr/local/lib/timebot/bin/pipermail2text.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import re
import sys
import logging
import html2text
import argparse
import textwrap
from bs4 import BeautifulSoup
from pathlib import Path

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

sys.pycache_prefix = "/var/cache/timebot/embedding_service"
from shared.config import config
from rag.search_utils import init_search_module

# Set up logging
logger = logging.getLogger()
log_file_path = config["PIPERMAIL2TEXT_LOG"]
log_directory = os.path.dirname(log_file_path)
Path(log_directory).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()  # Also log to console
    ]
)


# Email directories
EMAIL_HTML_UNPROCESSED_DIR = config["EMAIL_HTML_UNPROCESSED_DIR"]
EMAIL_HTML_PROCESSED_DIR = config["EMAIL_HTML_PROCESSED_DIR"]
EMAIL_TEXT_UNPROCESSED_DIR = config["EMAIL_TEXT_UNPROCESSED_DIR"]
EMAIL_TEXT_PROCESSED_DIR = config["EMAIL_TEXT_PROCESSED_DIR"]
# Database paths
CHROMADB_PATH = config["CHROMADB_PATH"]
# Base URL for the archive
ARCHIVE_BASE_URL = config["ARCHIVE_BASE_URL"]


def wrap_text_with_quote_prefix(text, prefix, width=80):
    """
    Wrap text while preserving the quote prefix at the beginning of each line.
    """
    # Calculate available width for text after prefix
    available_width = width - len(prefix)
    if available_width <= 10:  # Ensure we have reasonable space for text
        available_width = 40
    
    # Wrap the text
    wrapped_lines = textwrap.wrap(text, width=available_width)
    
    # Add prefix to each line
    return [f"{prefix} {line}" for line in wrapped_lines]

def wrap_all_lines(text, width=80):
    """
    Wrap all lines, including quoted lines, to the specified width.
    Preserves quote prefixes (>, >>, >>>, etc.) at the beginning of each line.
    """
    lines = text.split('\n')
    result = []
    
    # Track paragraph building
    current_paragraph = []
    current_prefix = ""
    
    for i, line in enumerate(lines):
        # Check if this is a quoted line
        quote_match = re.match(r'^(>+)\s*(.*)', line)
        
        # Check if this is a blank line
        is_blank = not line.strip()
        
        # Check if this is a special line that shouldn't be wrapped
        is_special = re.match(r'On .+? wrote:', line.strip())
        
        # If we're starting a new paragraph or changing quote level
        if is_blank or is_special or (quote_match and quote_match.group(1) != current_prefix):
            # Process any accumulated paragraph
            if current_paragraph:
                paragraph_text = ' '.join(current_paragraph)
                if current_prefix:
                    # This is a quoted paragraph
                    wrapped_lines = wrap_text_with_quote_prefix(paragraph_text, current_prefix, width)
                    result.extend(wrapped_lines)
                else:
                    # This is a regular paragraph
                    wrapped = textwrap.fill(paragraph_text, width=width)
                    result.extend(wrapped.split('\n'))
                current_paragraph = []
            
            # Add blank line or special line as is
            if is_blank or is_special:
                result.append(line)
                current_prefix = ""
            else:
                # Start a new quoted paragraph
                current_prefix = quote_match.group(1)
                current_paragraph = [quote_match.group(2).strip()]
        else:
            # Continue current paragraph
            if quote_match:
                # This is a quoted line continuing the current paragraph
                if quote_match.group(1) == current_prefix:
                    current_paragraph.append(quote_match.group(2).strip())
                else:
                    # Different quote level, process the current paragraph first
                    if current_paragraph:
                        paragraph_text = ' '.join(current_paragraph)
                        if current_prefix:
                            wrapped_lines = wrap_text_with_quote_prefix(paragraph_text, current_prefix, width)
                            result.extend(wrapped_lines)
                        else:
                            wrapped = textwrap.fill(paragraph_text, width=width)
                            result.extend(wrapped.split('\n'))
                    
                    # Start a new paragraph with the new quote level
                    current_prefix = quote_match.group(1)
                    current_paragraph = [quote_match.group(2).strip()]
            else:
                # This is a regular line continuing the current paragraph
                if not current_prefix:
                    current_paragraph.append(line.strip())
                else:
                    # We were in a quoted paragraph but now we're not
                    if current_paragraph:
                        paragraph_text = ' '.join(current_paragraph)
                        wrapped_lines = wrap_text_with_quote_prefix(paragraph_text, current_prefix, width)
                        result.extend(wrapped_lines)
                        # Add a blank line after quoted text before starting unquoted text
                        result.append('')
                    
                    # Start a new regular paragraph
                    current_prefix = ""
                    current_paragraph = [line.strip()]
    
    # Process any final paragraph
    if current_paragraph:
        paragraph_text = ' '.join(current_paragraph)
        if current_prefix:
            wrapped_lines = wrap_text_with_quote_prefix(paragraph_text, current_prefix, width)
            result.extend(wrapped_lines)
        else:
            wrapped = textwrap.fill(paragraph_text, width=width)
            result.extend(wrapped.split('\n'))
    
    # Ensure blank line after quoted blocks
    processed_result = []
    i = 0
    while i < len(result):
        processed_result.append(result[i])
        
        # If this is the end of a quoted block and not already followed by a blank line
        if (i < len(result) - 1 and 
            result[i].strip().startswith('>') and 
            not result[i+1].strip().startswith('>') and 
            result[i+1].strip()):
            processed_result.append('')
        
        i += 1
    
    # Add blank line at the end if the last line is quoted
    if processed_result and processed_result[-1].strip().startswith('>'):
        processed_result.append('')
    
    return '\n'.join(processed_result)

def fix_quoted_text(text):
    """
    Fix quoted text formatting to ensure each quoted line has proper line breaks.
    """
    lines = text.split('\n')
    result = []
    
    for line in lines:
        # Remove leading spaces from "On ... wrote" lines
        if re.match(r'\s+On .+? wrote:', line):
            line = line.strip()
        
        # Check if this is a quoted line with multiple quotes run together
        if '>' in line:
            # Find all segments that start with '>'
            segments = re.findall(r'(>+[^>]*?)(?=>|$)', line)
            if len(segments) > 1:
                # Add each segment as a separate line
                for segment in segments:
                    result.append(segment.strip())
            else:
                result.append(line)
        else:
            result.append(line)
    
    # Collapse multiple blank lines to just one
    collapsed_result = []
    prev_blank = False
    
    for line in result:
        if not line.strip():
            if not prev_blank:
                collapsed_result.append(line)
                prev_blank = True
        else:
            collapsed_result.append(line)
            prev_blank = False
    
    return '\n'.join(collapsed_result)

def strip_mailman_urls(text):
    """
    Strip URLs like (http://febo.com/cgi-bin/mailman/listinfo/time-nutslists.febo.com)
    from quoted text lines.
    """
    # Pattern to match email addresses followed by URLs in parentheses
    pattern = r'(\S+@\S+)\s+\(http://[^)]+\)'
    # Replace with just the email address
    text = re.sub(pattern, r'\1', text)
    
    # Pattern to match "mailto:" URLs in parentheses
    pattern = r'\(http://[^)]+\)\s+mailto:\[([^]]+)\]\s+\(http://[^)]+\)'
    # Replace with just the email address
    text = re.sub(pattern, r'\1', text)
    
    # Catch any remaining URLs in parentheses
    pattern = r'\(http://[^)]+\)'
    text = re.sub(pattern, '', text)
    
    return text

def ensure_quote_transitions(text):
    """
    Ensure there's always a blank line when transitioning from quoted to unquoted text.
    """
    lines = text.split('\n')
    result = []
    
    for i in range(len(lines)):
        result.append(lines[i])
        
        # If this line is quoted and the next line is not quoted and not blank
        if (i < len(lines) - 1 and 
            lines[i].strip().startswith('>') and 
            not lines[i+1].strip().startswith('>') and 
            lines[i+1].strip()):
            result.append('')  # Add a blank line
    
    return '\n'.join(result)

def convert_html_to_text(html_content, base_url, dir_name, file_name, width=80):
    """
    Convert HTML email to text format with specific formatting requirements.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract subject from H1 tag
        subject_tag = soup.find('h1')
        subject = subject_tag.text.strip() if subject_tag else "Unknown Subject"
        
        # Extract sender information
        sender_link = None
        for a_tag in soup.find_all('a'):
            if a_tag.get('title') and 'time-nuts' in a_tag.get('title'):
                sender_link = a_tag
                break
                
        sender = sender_link.text.strip() if sender_link else "Unknown Sender"
        
        # Extract date
        date_tag = soup.find('i')
        date = date_tag.text.strip() if date_tag else "Unknown Date"
        
        # Construct URL
        url = f"{base_url}/{dir_name}/{file_name}"
        
        # Extract email body - find the PRE tag that contains the email content
        pre_tag = soup.find('pre')
        if not pre_tag:
            return None
            
        # Use html2text with minimal configuration
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.body_width = 0  # Don't wrap lines - we'll do our own wrapping
        h.unicode_snob = True  # Use Unicode characters instead of ASCII approximations
        
        # Convert only the PRE content to text
        email_body = h.handle(str(pre_tag))
        
        # Fix quoted text formatting
        email_body = fix_quoted_text(email_body)
        
        # Strip mailman URLs from quoted text
        email_body = strip_mailman_urls(email_body)
        
        # Additional post-processing
        
        # 1. Remove the footer
        footer_patterns = [
            r'___+.*time-nuts mailing list.*\n.*',
            r'time-nuts mailing list.*\n.*unsubscribe.*\n.*',
        ]
        
        for pattern in footer_patterns:
            email_body = re.sub(pattern, '', email_body, flags=re.DOTALL)
        
        # 2. Clean up any remaining markdown artifacts
        email_body = email_body.replace('**', '')
        email_body = email_body.replace('__', '')
        email_body = re.sub(r'_([^_]+)_', r'\1', email_body)
        
        # 3. Fix links - preserve the URL instead of removing it
        email_body = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1 (\2)', email_body)
        
        # 4. Wrap all lines, including quoted lines
        email_body = wrap_all_lines(email_body, width=width)
        
        # 5. Additional check to ensure proper transitions from quoted to unquoted text
        email_body = ensure_quote_transitions(email_body)
        
        # Construct the final text output
        output = f"Subject: {subject}\n"
        output += f"From: {sender}\n"
        output += f"Date: {date}\n"
        output += f"URL: {url}\n\n"
        output += email_body.strip()
        
        # Ensure the output ends with a newline
        if not output.endswith('\n'):
            output += '\n'
        
        return output
    except Exception as e:
        print(f"Error converting HTML to text: {e}")
        import traceback
        traceback.print_exc()
        return None

def process_file(html_file, output_path, base_url, width=80):
    """
    Process a single HTML file and convert it to text.
    """
    try:
        # Get the relative path from the base directory
        rel_path = html_file.relative_to(Path(args.input_dir))
        
        # Get directory name for URL construction (last directory in path)
        dir_name = html_file.parent.name
        
        print(f"Processing file: {html_file}")
        
        # Read HTML content
        with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
            html_content = f.read()
        
        # Convert to text
        text_content = convert_html_to_text(html_content, base_url, dir_name, html_file.name, width=width)
        
        if text_content:
            # Write text to output file directly in the output_path (no subdirectories)
            # Just use the original filename since they're all unique
            output_file = output_path / f"{html_file.stem}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            print(f"Converted {html_file} to {output_file}")
            return True
        else:
            print(f"Failed to convert {html_file}")
            return False
    except Exception as e:
        print(f"Error processing file {html_file}: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_directory(input_dir, output_dir, processed_dir, base_url, width=80):
    """
    Recursively process all HTML files in a directory and its subdirectories.
    Move processed files to processed_dir and delete empty source directories.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    processed_path = Path(processed_dir)
    
    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing directory: {input_path}")
    print(f"Output directory: {output_path}")
    print(f"Processed directory: {processed_path}")
    print(f"Base URL: {base_url}")
    print(f"Line width: {width}")
    
    # Skip list for navigation files
    skip_files = ['index.html', 'date.html', 'thread.html', 'subject.html', 'author.html']
    
    # Counters for processed files
    total_files = 0
    processed_files = 0
    
    # Walk through directory tree
    for root, dirs, files in os.walk(input_path):
        root_path = Path(root)
        
        # Get relative path from input directory
        rel_path = root_path.relative_to(input_path)
        
        # Create corresponding directories in processed path only
        if str(rel_path) != '.':
            (processed_path / rel_path).mkdir(parents=True, exist_ok=True)
        
        # Process HTML files in current directory
        html_files = [f for f in files if f.lower().endswith('.html') and f.lower() not in skip_files]
        total_files += len(html_files)
        
        for html_file in html_files:
            source_file = root_path / html_file
            
            # Determine processed file path
            if str(rel_path) == '.':
                processed_file_path = processed_path / html_file
            else:
                processed_file_path = processed_path / rel_path / html_file
            
            # Process the file - passing just output_path for flat structure
            if process_file(source_file, output_path, base_url, width=width):
                processed_files += 1
                
                # Move the processed file to the processed directory
                processed_file_path.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source_file, processed_file_path)
                print(f"Moved {source_file} to {processed_file_path}")
        
        # Check if directory is now empty and delete if it is
        if not any(root_path.iterdir()):
            try:
                root_path.rmdir()
                print(f"Removed empty directory: {root_path}")
            except OSError as e:
                print(f"Could not remove directory {root_path}: {e}")
    
    print(f"Conversion complete. Processed {processed_files} files out of {total_files} HTML files.")
    print(f"Files saved to {output_path}")
    print(f"Original HTML files moved to {processed_path}")


def main():
    parser = argparse.ArgumentParser(description='Convert Mailman HTML archives to text')
    parser.add_argument('--input_dir', default=EMAIL_HTML_UNPROCESSED_DIR,
        help='Directory containing HTML files')
    parser.add_argument('--output_dir', default=EMAIL_TEXT_UNPROCESSED_DIR,
        help='Directory for output text files')
    parser.add_argument('--processed_dir', default=EMAIL_HTML_PROCESSED_DIR,
        help='Directory for output text files')
    parser.add_argument('--base-url', default=ARCHIVE_BASE_URL,
                        help='Base URL for constructing links')
    parser.add_argument('--width', type=int, default=80,
                        help='Maximum line width for text (default: 80)')
    global args
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input directory '{args.input_dir}' does not exist or is not a directory")
        sys.exit(1)
    
    process_directory(args.input_dir, args.output_dir, args.processed_dir, 
        args.base_url, width=args.width)

if __name__ == "__main__":
    main()

