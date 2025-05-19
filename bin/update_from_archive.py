#!/usr/bin/env python3
"""
RAG Processor - Downloads new HTML files from an archive URL that aren't already
processed locally.

This script:
1. Finds the last processed HTML file in EMAIL_HTML_PROCESSED_DIR
2. Downloads all newer files from ARCHIVE_BASE_URL by parsing date.html indexes
3. Stores them in EMAIL_HTML_UNPROCESSED_DIR for further processing
"""

import os
import sys
import argparse
import re
import logging
import requests
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timedelta
import calendar
from bs4 import BeautifulSoup
from typing import Tuple, Optional, List, Dict

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

sys.pycache_prefix = "/var/cache/timebot/embedding_service"
from shared.config import config
from rag.search_utils import init_search_module

# Set up logging
logger = logging.getLogger()
log_file_path = config["ARCHIVE_DOWNLOAD_LOG"]
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
    
# Add date range parameters
current_year = datetime.now().year
current_month = datetime.now().month
   
START_YEAR = 2000
START_MONTH = 1
END_YEAR = current_year
END_MONTH = current_month
MAX_FAILURES = 3

def find_last_processed_file(processed_dir: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Find the last processed HTML file and return its directory name and sequence number.
    
    Returns:
        Tuple containing (directory_name, sequence_number) or (None, None) if no files found
    """
    processed_path = Path(processed_dir)
    if not processed_path.exists():
        logger.error(f"Processed directory does not exist: {processed_dir}")
        sys.exit(1)
    
    # Get all year-month directories
    month_dirs = [d for d in processed_path.iterdir() if d.is_dir()]
    if not month_dirs:
        logger.warning("No month directories found in processed directory")
        return None, None
    
    # Sort directories by year and month
    def dir_sort_key(dir_path):
        try:
            year_str, month_str = dir_path.name.split("-")
            year = int(year_str)
            month_num = list(calendar.month_name).index(month_str)
            return (year, month_num)
        except (ValueError, IndexError):
            return (0, 0)  # Invalid directory names go first
    
    month_dirs.sort(key=dir_sort_key, reverse=True)
    
    # Find the highest sequence number across all directories
    highest_seq = -1
    highest_dir = None
    
    for dir_path in month_dirs:
        html_files = list(dir_path.glob("*.html"))
        for file_path in html_files:
            try:
                seq_num = int(file_path.stem)
                if seq_num > highest_seq:
                    highest_seq = seq_num
                    highest_dir = dir_path.name
            except ValueError:
                continue  # Skip files that don't have numeric names
    
    if highest_seq == -1:
        logger.warning("No HTML files found in any month directory")
        return None, None
    
    logger.info(f"Last processed file: {highest_dir}/{highest_seq}.html")
    return highest_dir, highest_seq

def generate_month_directories(start_year: int, start_month: int, 
                              end_year: int, end_month: int, 
                              archive_url: str) -> List[Tuple[str, str]]:
    """
    Generate a list of month directories based on date range.
    
    Returns:
        List of tuples containing (directory_name, full_url)
    """
    directories = []
    
    current_date = datetime(start_year, start_month, 1)
    end_date = datetime(end_year, end_month, 1)
    
    while current_date <= end_date:
        year = current_date.year
        month = current_date.month
        month_name = calendar.month_name[month]
        
        dir_name = f"{year}-{month_name}"
        
        # Make sure the archive_url ends with a slash
        if not archive_url.endswith('/'):
            archive_url += '/'
            
        dir_url = f"{archive_url}{dir_name}/"
        
        directories.append((dir_name, dir_url))
        logger.debug(f"Generated directory URL: {dir_url}")
        
        # Move to next month
        if month == 12:
            current_date = datetime(year + 1, 1, 1)
        else:
            current_date = datetime(year, month + 1, 1)
    
    return directories



def check_directory_exists(dir_url: str) -> bool:
    """Check if a directory exists by trying to access its date.html file."""
    date_index_url = urljoin(dir_url, "date.html")
    
    try:
        logger.debug(f"Checking if directory exists: {dir_url}")
        logger.debug(f"Trying to access: {date_index_url}")
        
        response = requests.get(date_index_url, allow_redirects=True)
        
        if response.status_code == 200:
            logger.debug(f"Successfully accessed {date_index_url}")
            return True
        else:
            logger.debug(f"Failed to access {date_index_url}, status code: {response.status_code}")
            # Try accessing the directory directly as a fallback
            try:
                dir_response = requests.get(dir_url, allow_redirects=True)
                if dir_response.status_code == 200:
                    logger.debug(f"Successfully accessed directory: {dir_url}")
                    return True
            except:
                pass
            return False
            
    except requests.exceptions.RequestException as e:
        logger.debug(f"Error accessing {date_index_url}: {e}")
        return False


def get_html_files_from_date_index(dir_url: str) -> List[Tuple[int, str]]:
    """
    Get all HTML files by parsing the date.html index file for a month.
    
    Returns:
        List of tuples containing (sequence_number, full_url)
    """
    date_index_url = urljoin(dir_url, "date.html")
    
    try:
        logger.debug(f"Fetching date index from: {date_index_url}")
        response = requests.get(date_index_url, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        files = []
        
        # Look for links to numbered HTML files within LI tags
        for li in soup.find_all("li"):
            links = li.find_all("a")
            if links and links[0].get("href"):
                href = links[0].get("href")
                if re.match(r"\d+\.html$", href):
                    try:
                        # Extract the sequence number from the filename
                        seq_num = int(href.split(".")[0])
                        full_url = urljoin(dir_url, href)
                        files.append((seq_num, full_url))
                        logger.debug(f"Found file: {href} (seq: {seq_num})")
                    except ValueError:
                        continue  # Skip files that don't have numeric names
        
        # Sort files by sequence number
        files.sort(key=lambda x: x[0])
        
        if files:
            logger.debug(f"Found {len(files)} HTML files in date.html for {dir_url}")
            logger.debug(f"Sequence numbers range from {files[0][0]} to {files[-1][0]}")
        else:
            logger.warning(f"No HTML files found in date.html for {dir_url}")
            
        return files
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error accessing date.html: {e}")
        return []


def download_file(url: str, output_path: str) -> bool:
    """Download a file from URL to the specified output path."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write the file
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        logger.debug(f"Downloaded: {url} -> {output_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading {url}: {e}")
        return False


def try_sequential_download(dir_url: str, dir_name: str, start_seq: int, 
                           unprocessed_dir: str, max_failures: int) -> int:
    """
    Try sequential downloading of files until too many consecutive failures.
    
    Returns:
        Number of files successfully downloaded
    """
    logger.info(f"Trying sequential download for {dir_name} starting at {start_seq}")
    next_seq = start_seq
    consecutive_failures = 0
    files_downloaded = 0
    
    while consecutive_failures < max_failures:
        file_url = urljoin(dir_url, f"{next_seq}.html")
        output_path = os.path.join(unprocessed_dir, dir_name, f"{next_seq}.html")
        
        if download_file(file_url, output_path):
            files_downloaded += 1
            consecutive_failures = 0  # Reset failure counter on success
        else:
            consecutive_failures += 1
            logger.debug(f"Failed to download {next_seq}.html ({consecutive_failures}/{max_failures})")
        
        next_seq += 1
    
    logger.info(f"Sequential download complete. Downloaded {files_downloaded} files.")
    return files_downloaded


def download_new_files(config: dict):
    """
    Main function to download new files from the archive URL.
    """
    processed_dir = config["EMAIL_HTML_PROCESSED_DIR"]
    unprocessed_dir = config["EMAIL_HTML_UNPROCESSED_DIR"]
    archive_url = config["ARCHIVE_BASE_URL"]
    max_failures = 3
    
    # Find the last processed file
    last_dir, last_seq = find_last_processed_file(processed_dir)
    
    if last_dir is None:
        logger.info("No processed files found. Will download all available files.")
        last_seq = -1
    
    # Extract year and month from last_dir if available
    start_year = START_YEAR
    start_month = START_MONTH
    
    if last_dir:
        try:
            year_str, month_str = last_dir.split("-")
            year = int(year_str)
            month = list(calendar.month_name).index(month_str)
            
            # Start from the last processed directory
            start_year = year
            start_month = month
            
            logger.info(f"Starting from last processed directory: {year}-{month_str}")
        except (ValueError, IndexError):
            logger.warning(f"Could not parse year-month from directory: {last_dir}")
    
    # Generate month directories based on date range
    month_dirs = generate_month_directories(
        start_year, start_month,
        END_YEAR, END_MONTH,
        archive_url
    )
    
    if not month_dirs:
        logger.error("No month directories generated")
        return
    
    logger.info(f"Generated {len(month_dirs)} month directories to check")
    
    total_files_downloaded = 0
    
    # Process each directory
    for dir_name, dir_url in month_dirs:
        # Check if directory exists
        if not check_directory_exists(dir_url):
            logger.info(f"Directory does not exist or is not accessible: {dir_name}")
            continue
        
        logger.info(f"Processing directory: {dir_name}")
        
        # Determine starting sequence number for this directory
        start_seq = last_seq + 1 if dir_name == last_dir else 0
        
        # First approach: Try to get file list from date.html index
        html_files = get_html_files_from_date_index(dir_url)
        
        if html_files:
            # Download files with sequence numbers greater than the last processed
            dir_files_downloaded = 0
            for seq_num, file_url in html_files:
                if dir_name == last_dir and seq_num <= last_seq:
                    continue  # Skip files we've already processed
                
                output_path = os.path.join(unprocessed_dir, dir_name, f"{seq_num}.html")
                if download_file(file_url, output_path):
                    dir_files_downloaded += 1
                    total_files_downloaded += 1
            
            logger.info(f"Downloaded {dir_files_downloaded} files from {dir_name}")
        else:
            # Second approach: Try sequential downloading
            files_downloaded = try_sequential_download(
                dir_url, dir_name, start_seq, unprocessed_dir, max_failures
            )
            total_files_downloaded += files_downloaded
    
    logger.info(f"Download complete. {total_files_downloaded} new files downloaded.")


def main():
    """Main entry point for the script."""
    download_new_files(config)


if __name__ == "__main__":
    main()
