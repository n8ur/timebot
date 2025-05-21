# /usr/local/lib/timebot/lib/ocr/ocr_processor.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

#!/bin/env python3

import os
import io
import re
import gc
import datetime
import tempfile
import subprocess
import logging
import fcntl  # For file locking
import psutil
import time
import shutil
from pdf2image import convert_from_path
from pathlib import Path
from google.cloud import vision
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable, GatewayTimeout

debug = False

class OCRProcessor:
    def __init__(self, config):
        self.config = config
        
        # Set up Google Vision client with credentials from config
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = \
            self.config["GOOGLE_APPLICATION_CREDENTIALS"]
        
        print("google application credentials:", os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
        # Create client
        self.client = vision.ImageAnnotatorClient()
        
        # Track last usage time
        self.last_client_use = time.time()
        self.client_idle_timeout = 300  # 5 minutes
    
    def ensure_fresh_client(self):
        """Ensure the Vision client is fresh by recreating it if idle too long"""
        current_time = time.time()
        
        # If client has been idle for too long, recreate it
        if current_time - self.last_client_use > self.client_idle_timeout:
            logging.info("Vision client idle too long, recreating...")
            
            # Create a new client
            self.client = vision.ImageAnnotatorClient()
        
        # Update last use time
        self.last_client_use = current_time
    
    def log_memory_usage(self, message):
        """Log current memory usage with a custom message."""
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logging.info(f"{message}: Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")
    
    def get_next_sequence_number(self):
        """
        Get the next sequence number without incrementing it.
        """
        sequence_file = os.path.join(self.config["DOC_SEQUENCE_FILE"])
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(sequence_file), exist_ok=True)
        
        # Create the file if it doesn't exist
        if not os.path.exists(sequence_file):
            with open(sequence_file, 'w') as f:
                f.write("1")
        
        # Open the file for reading
        with open(sequence_file, 'r') as f:
            # Acquire a shared lock (read-only)
            fcntl.flock(f, fcntl.LOCK_SH)
            
            try:
                # Read the current sequence number
                seq_num = int(f.read().strip() or "0")
                return seq_num
            finally:
                # Release the lock
                fcntl.flock(f, fcntl.LOCK_UN)
    
    def update_sequence_number(self, seq_num):
        """
        Update the sequence number file with the next number and create a backup.
        """
        sequence_file = os.path.join(self.config["DOC_SEQUENCE_FILE"])
        
        # Open the file for writing
        with open(sequence_file, 'r+') as f:
            # Acquire an exclusive lock
            fcntl.flock(f, fcntl.LOCK_EX)
            
            try:
                # Read the current value to verify it hasn't changed
                current = int(f.read().strip() or "0")
                
                # Only update if the current value matches what we expect
                # This prevents race conditions if multiple processes are running
                if current == seq_num:
                    # Go back to the beginning of the file
                    f.seek(0)
                    
                    # Write the incremented sequence number
                    f.write(str(seq_num + 1))
                    
                    # Truncate the file to the current position
                    f.truncate()
                    
                    # Create a backup in the root directory
                    backup_dir = "/root/ocr_history"
                    if not os.path.exists(backup_dir):
                        os.makedirs(backup_dir)
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = os.path.join(backup_dir, f"sequence_{timestamp}.txt")
                    
                    # Copy the updated sequence file to the backup location
                    shutil.copy2(sequence_file, backup_path)
                    
                    # Keep only the 10 most recent backups
                    seq_backups = sorted(Path(backup_dir).glob("sequence_*.txt"))
                    if len(seq_backups) > 10:
                        for old_backup in seq_backups[:-10]:
                            os.remove(old_backup)
                else:
                    logging.warning(f"Sequence number changed during processing: expected {seq_num}, found {current}")
            finally:
                # Release the lock
                fcntl.flock(f, fcntl.LOCK_UN)
    
    def clean_ocr_text(self, text):
        """
        Cleans OCR text by preserving paragraphs, 
        fixing line breaks, and removing artifacts.
        """
        # Fix hyphenated words that are split across lines
        text = re.sub(r"(\w+)-\s*\n(\w+)", r"\1\2", text)
        
        # Remove extra spaces
        text = re.sub(r"\s+", " ", text).strip()
        
        # Insert paragraph breaks after sentence endings
        text = re.sub(r'([.!?]) (\w)', r'\1\n\n\2', text)
        
        return text.strip()
    
    def convert_pdf_to_images(self, pdf_path, first_page=1, last_page=None):
        """Convert PDF pages to images"""
        return convert_from_path(pdf_path, first_page=first_page, last_page=last_page)
    
    def process_image(self, image):
        """Process an image with Google Vision AI"""
        return self._process_image_with_vision(image)
    
    def _process_image_with_vision(self, image):
        """Process an image with Google Vision AI"""
        import io
        
        # Convert to grayscale
        grayscale_image = image.convert('L')
        
        # Save image to temporary file as PNG
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
            grayscale_image.save(temp.name, 'PNG')
            temp_name = temp.name
        
        try:
            # Process with Vision AI
            with io.open(temp_name, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            
            # Ensure client is fresh
            self.ensure_fresh_client()
            
            response = self.client.document_text_detection(
                image=image,
                timeout=120  # 2 minutes timeout
            )
            
            if response.error.message:
                return f"Error: {response.error.message}"
            
            # Extract text
            if response.full_text_annotation:
                return response.full_text_annotation.text
            else:
                return ""
        
        except Exception as e:
            return f"Error: {str(e)}"
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    
    def process_pdf(self, pdf_path, metadata):
        """
        Process a PDF file with Google Vision AI OCR with batch processing.
        """
        # Get sequence number for this document (without incrementing)
        seq_num = self.get_next_sequence_number()
        
        # Generate URL
        base = self.config['DOC_BASE_URL'].rstrip('/')
        document_url = f"{base}/{seq_num}.pdf"
        
        # Create progress file
        if debug:
            progress_dir = os.path.dirname(self.config['DOC_TEXT_UNPROCESSED_DIR'])
            os.makedirs(progress_dir, exist_ok=True)
            progress_path = os.path.join(progress_dir, f"{seq_num}.progress")
        
            with open(progress_path, 'w') as f:
                f.write(f"Started processing at {datetime.datetime.now()}\n")
                f.write(f"PDF path: {pdf_path}\n")
                f.write(f"Title: {metadata['title']}\n")
        
        try:
            # Get total page count first
            self.log_memory_usage("Before getting page count")
            info = subprocess.run(
                ["pdfinfo", pdf_path], 
                capture_output=True, 
                text=True, 
                check=True
            )
            pages_match = re.search(r'Pages:\s+(\d+)', info.stdout)
            total_pages = int(pages_match.group(1)) if pages_match else 0
            
            logging.info(f"Processing PDF with {total_pages} pages")
            if debug:
                with open(progress_path, 'a') as f:
                    f.write(f"Total pages: {total_pages}\n")
            
            # Process in batches of 50 pages
            batch_size = 50
            full_text = []
            
            for batch_start in range(0, total_pages, batch_size):
                batch_end = min(batch_start + batch_size, total_pages)
                logging.info(f"Processing batch: pages {batch_start+1}-{batch_end}")
                
                if debug:
                    with open(progress_path, 'a') as f:
                        f.write(f"Starting batch {batch_start+1}-{batch_end} at {datetime.datetime.now()}\n")
                
                self.log_memory_usage(f"Before processing batch {batch_start+1}-{batch_end}")
                
                # Convert specific pages to images
                images = convert_from_path(
                    pdf_path,
                    first_page=batch_start+1,
                    last_page=batch_end
                )
                
                # Process each page in this batch
                for i, image in enumerate(images):
                    page_num = batch_start + i + 1
                    logging.info(f"Processing page {page_num}/{total_pages}")
                    
                    if debug:
                        with open(progress_path, 'a') as f:
                            f.write(f"Processing page {page_num}/{total_pages} at {datetime.datetime.now()}\n")
                    
                    # Convert to grayscale
                    grayscale_image = image.convert('L')
                    
                    # Save image to temporary file as PNG
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                        grayscale_image.save(temp.name, 'PNG')
                        temp_name = temp.name
                    
                    try:
                        # Process with Vision AI
                        with io.open(temp_name, 'rb') as image_file:
                            content = image_file.read()
                        
                        image = vision.Image(content=content)
                        
                        # Try up to 3 times with timeout and connection errors
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                # Ensure client is fresh
                                self.ensure_fresh_client()
                                
                                response = self.client.document_text_detection(
                                    image=image,
                                    timeout=120  # 2 minutes timeout
                                )
                                break
                            except (DeadlineExceeded, ServiceUnavailable, GatewayTimeout, ConnectionError) as e:
                                if retry < max_retries - 1:
                                    # Exponential backoff: wait longer between retries
                                    wait_time = (2 ** retry) * 2  # 2, 4, 8 seconds
                                    logging.warning(f"Connection error processing page {page_num}, retry {retry+1}/{max_retries} after {wait_time}s: {str(e)}")
                                    if debug:
                                        with open(progress_path, 'a') as f:
                                            f.write(f"Connection error on page {page_num}, retry {retry+1}/{max_retries} after {wait_time}s\n")
                                    
                                    # Wait before retrying
                                    time.sleep(wait_time)
                                    
                                    # Force recreation of client on connection errors
                                    client_options = ClientOptions(
                                        api_endpoint="vision.googleapis.com:443",
                                        api_connection_timeout=120.0
                                    )
                                    self.client = vision.ImageAnnotatorClient()
                                else:
                                    if debug:
                                        with open(progress_path, 'a') as f:
                                            f.write(f"Failed after {max_retries} retries on page {page_num}: {str(e)}\n")
                                    raise Exception(f"Error processing page {page_num} after {max_retries} retries: {str(e)}")
                        
                        if response.error.message:
                            if debug:
                                with open(progress_path, 'a') as f:
                                    f.write(f"Error on page {page_num}: {response.error.message}\n")
                            raise Exception(f"Error processing page {page_num}: {response.error.message}")
                        
                        # Extract text
                        if response.full_text_annotation:
                            page_text = response.full_text_annotation.text
                            full_text.append(page_text)
                        else:
                            logging.warning(f"No text found on page {page_num}")
                            if debug:
                                    with open(progress_path, 'a') as f:
                                        f.write(f"No text found on page {page_num}\n")
                    finally:
                        # Clean up temp file
                        if os.path.exists(temp_name):
                            os.unlink(temp_name)
                
                # Free memory after each batch
                images = None
                gc.collect()
                self.log_memory_usage(f"After processing batch {batch_start+1}-{batch_end}")
                
                if debug:
                    with open(progress_path, 'a') as f:
                        f.write(f"Completed batch {batch_start+1}-{batch_end} at {datetime.datetime.now()}\n")
            
            # Combine all text
            if debug:
                with open(progress_path, 'a') as f:
                    f.write(f"Combining and cleaning text at {datetime.datetime.now()}\n")
            
            combined_text = "\n\n".join(full_text)
            
            # Clean the OCR text
            logging.info("Cleaning OCR text...")
            cleaned_text = self.clean_ocr_text(combined_text)
            
            # Add metadata header
            processing_date = datetime.datetime.now().strftime("%Y-%m-%d")
            
            metadata_header = f"""
Title: {metadata['title']}
Author: {metadata['author'] or 'Unknown'}
Publisher: {metadata['publisher']}
Publisher ID: {metadata['publisher_id'] or 'N/A'}
Publication Date: {metadata['publication_date'] or 'Unknown'}
Source: {metadata['source']}
Original Filename: {metadata['original_filename']}
Sequence Number: {seq_num}
URL: {document_url}
Processing Date: {processing_date}

-----------------------------------------

"""
            
            final_text = metadata_header + cleaned_text
            
            # Save to file in the text folder
            output_path = os.path.join(self.config['DOC_TEXT_UNPROCESSED_DIR'], f"{seq_num}.txt")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_text)
            
            if debug:
                with open(progress_path, 'a') as f:
                    f.write(f"Text saved to {output_path} at {datetime.datetime.now()}\n")
                    f.write(f"Processing complete at {datetime.datetime.now()}\n")
            
            # Only update the sequence number after successful processing
            self.update_sequence_number(seq_num)
            
            return {
                'sequence_number': seq_num,
                'url': document_url,
                'output_path': output_path
            }
        except Exception as e:
            # Log the error but don't update sequence number
            error_msg = f"Error processing PDF: {str(e)}"
            logging.error(error_msg)
            if debug:
                with open(progress_path, 'a') as f:
                    f.write(f"ERROR: {error_msg} at {datetime.datetime.now()}\n")
            # Re-raise the exception to be handled by the caller
            raise

    def upload_pdf_to_server(self, sequence_number, config):
        """
        Upload PDF and text files to the remote server using SCP
        
        Args:
            sequence_number: Document sequence number
            config: Configuration object with paths and SSH settings
    
        Returns:
            tuple: (success, message)
        """

        # Get file paths from config
        pdf_dir = config['DOC_PDF_DIR']
        text_dir = config['DOC_TEXT_UNPROCESSED_DIR']
        remote_server = config['REMOTE_SERVER']
        if '@' not in remote_server:
            user = config['OCR_UPLOAD_USER']
            remote_server = f"{user}@{remote_server}"
        remote_pdf_dir = config['TIMEBOT_PDF_DIR'].rstrip('/')

        # Get configurable timeout (default to 10 seconds if not specified)
        connect_timeout = config.get('OCR_UPLOAD_TIMEOUT', 10)

        # Construct local file paths
        local_pdf_path = os.path.join(pdf_dir, f"{sequence_number}.pdf")
        local_text_path = os.path.join(text_dir, f"{sequence_number}.txt")

        remote_pdf_path = f"{remote_pdf_dir}/{sequence_number}.pdf"
        remote_text_path = f"{remote_pdf_dir}/text/{sequence_number}.txt"

        # Check if files exist
        if not os.path.exists(local_pdf_path):
            return False, f"PDF file not found: {local_pdf_path}"
    
        if not os.path.exists(local_text_path):
            logging.warning(f"Text file not found: {local_text_path}")
    
        # Prepare SCP command options
        scp_options = [
            "-o", "BatchMode=yes",  # Non-interactive mode
            "-o", "StrictHostKeyChecking=accept-new",  # Auto-add new host keys
            "-o", f"ConnectTimeout={connect_timeout}"  # Configurable timeout
        ]   

        # Define SSH options (similar to SCP options)
        ssh_options = [
            "-o", "BatchMode=yes",  # Non-interactive mode
            "-o", "StrictHostKeyChecking=accept-new",  # Auto-add new host keys
            "-o", f"ConnectTimeout={connect_timeout}"  # Configurable timeout
        ]
    
        # Add identity file if specified
        if config.get('OCR_UPLOAD_KEY'):
            scp_options.extend(["-i", config['OCR_UPLOAD_KEY']])
            ssh_options.extend(["-i", config['OCR_UPLOAD_KEY']])
    
        # upload commands
        pdf_cmd = ["scp"] + scp_options + [local_pdf_path, 
                f"{remote_server}:{remote_pdf_path}"]
        txt_cmd = ["scp"] + scp_options + [local_text_path,
                f"{remote_server}:{remote_text_path}"]

        try:
            # Upload PDF file
            subprocess.run(pdf_cmd, check=True, capture_output=True)
            # change permissions
            ssh_cmd = ["ssh"] + ssh_options + \
                [remote_server, f"chmod 664 {remote_pdf_path}"]
            subprocess.run(ssh_cmd, check=True, capture_output=True)
            # Upload text file
            subprocess.run(txt_cmd, check=True, capture_output=True)
            # change permissions
            ssh_cmd = ["ssh"] + ssh_options + \
                [remote_server, f"chmod 664 {remote_text_path}"]
        
            return True, f"Successfully uploaded document {sequence_number} to remote server"
    
        except subprocess.CalledProcessError as e:
            error_msg = f"SCP upload failed: {e.stderr.decode() if e.stderr else str(e)}"
            logging.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logging.error(error_msg)
            return False, error_msg

