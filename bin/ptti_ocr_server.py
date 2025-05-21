#!/usr/bin/env python3
# /usr/local/lib/timebot/bin/ptti_ocr_server.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# Standard imports
import os
import sys
import threading
import shutil
import logging
import uuid
import tempfile
import time
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config
from shared.utils import ensure_timebot_prefix, make_timebot_filename

# FastAPI imports
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

# Local imports
from ocr.ocr_processor import OCRProcessor
from ocr.file_manager import FileManager
from ocr.log_manager import LogManager

# Initialize FastAPI app
app = FastAPI(title="Batch OCR Server", description="Batch OCR Server for processing PDF documents from directories")

# Define the middleware class
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Check if we're behind a proxy and should be using https
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        if forwarded_proto == "https":
            request.scope["scheme"] = "https"
        
        response = await call_next(request)
        return response
app.add_middleware(HTTPSRedirectMiddleware)

# Add session middleware for flash messages
app.add_middleware(
    SessionMiddleware,
    secret_key=config["OCR_SECRET_KEY"],
    max_age=3600        # default 1 hour timeout
)

# Mount static files directory
static_dir = config["PYTHON_STATIC_DIR"]
app.mount(
    "/static",
    StaticFiles(directory=static_dir),
    name="static",
)

# Set up templates
template_dir = config["PYTHON_TEMPLATE_DIR"]
templates = Jinja2Templates(directory=template_dir)

# Create a config dictionary for services
app_config = dict(config)

# Initialize services
file_manager = FileManager(config)
ocr_processor = OCRProcessor(config)
log_manager = LogManager(config)

# Simple semaphore to track active processing jobs
processing_jobs = 0
processing_lock = threading.Lock()

# Semaphore to limit concurrent processing jobs
max_concurrent_jobs = 2  # Reduced from 4 to 2 for batch processing
job_semaphore = threading.Semaphore(max_concurrent_jobs)

# Dictionary to store document queue and processing state
document_queue = []
current_document = None
queue_lock = threading.Lock()

# Helper function to get flash messages from session
def get_flash_messages(request: Request):
    flash_messages = request.session.pop("flash_messages", [])
    return flash_messages

# Helper function to add flash messages
def flash(request: Request, message: str):
    if "flash_messages" not in request.session:
        request.session["flash_messages"] = []
    request.session["flash_messages"].append(message)

# Helper function to load CSS and JS resources
def load_template_resources() -> Tuple[str, str]:
    """Load CSS and JS resources for templates"""
    # Read the CSS file
    css_path = os.path.join(config["PYTHON_STATIC_DIR"], "css/ptti_tool/styles.css")
    css_content = ""
    if os.path.exists(css_path):
        try:
            with open(css_path, 'r') as f:
                css_content = f.read()
        except Exception as e:
            print(f"Error reading CSS file: {e}")

    # Read the JS file
    js_path = os.path.join(config["PYTHON_STATIC_DIR"], "js/ptti_tool/main.js")
    js_content = ""
    if os.path.exists(js_path):
        try:
            with open(js_path, 'r') as f:
                js_content = f.read()
        except Exception as e:
            print(f"Error reading JS file: {e}")
            
    return css_content, js_content

# Function to find PDF files in a directory recursively
def find_pdf_files(root_dir: str) -> List[Dict[str, Any]]:
    """Find all PDF files in the given directory and its subdirectories, excluding the 'processed' and 'skipped' directories"""
    pdf_files = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip the 'processed' directory
        if "processed" in dirpath.split(os.path.sep) or "skipped" in dirpath.split(os.path.sep):
            continue

        # Extract year from directory name if possible
        year_match = re.search(r'(\d{4})', os.path.basename(dirpath))
        year = year_match.group(1) if year_match else ""

        for filename in filenames:
            if filename.lower().endswith('.pdf'):
                # Extract volume and number if possible
                vol_match = re.search(r'Vol\s*(\d+)', filename)
                num_match = re.search(r'[_\s](\d+)\.pdf', filename)

                vol = vol_match.group(1) if vol_match else ""
                num = num_match.group(1) if num_match else ""

                # Create publisher and publisher_id based on available info
                publisher = f"PTTI {year}" if year else "PTTI"
                publisher_id = ""

                if vol and num:
                    publisher_id = f"{publisher} Vol. {vol} No. {num}"
                elif vol:
                    publisher_id = f"{publisher} Vol. {vol}"

                pdf_files.append({
                    "path": os.path.join(dirpath, filename),
                    "filename": filename,
                    "year": year,
                    "volume": vol,
                    "number": num,
                    "publisher": publisher,
                    "publisher_id": publisher_id,
                    "publication_date": year,
                    "source": "Attila_PDF_Files"
                })

    return pdf_files


# Function to move processed files
def move_to_processed_directory(file_path, top_dir):
    """
    Move a file to a 'processed' subdirectory within the top directory
    while maintaining subdirectory structure

    Args:
        file_path: Path to the file to move
        top_dir: Top-level directory where 'processed' will be created

    Returns:
        str: New file path
    """
    # Create the processed directory
    processed_dir = os.path.join(top_dir, "processed")

    # Get the relative path from the top directory
    rel_path = os.path.relpath(file_path, top_dir)

    # Create the destination path
    # Use the sequence number if available to rename the file
    seq_num = None
    try:
        # Try to extract sequence number from the filename or metadata if available
        base = os.path.basename(file_path)
        if base.startswith("timebot-"):
            seq_num = base.split('-')[1].split('.')[0]
    except Exception:
        pass

    if seq_num:
        new_filename = make_timebot_filename(seq_num, "pdf")
        destination_path = os.path.join(processed_dir, new_filename)
    else:
        destination_path = os.path.join(processed_dir, ensure_timebot_prefix(os.path.basename(file_path)))

    # Ensure the destination directory exists
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    # Move the file
    shutil.move(file_path, destination_path)

    return destination_path


# Function to move skipped files
def move_to_skipped_directory(file_path, top_dir):
    """
    Move a file to a 'skipped' subdirectory within the top directory
    while maintaining subdirectory structure

    Args:
        file_path: Path to the file to move
        top_dir: Top-level directory where 'skipped' will be created

    Returns:
        str: New file path
    """
    # Create the skipped directory
    skipped_dir = os.path.join(top_dir, "skipped")

    # Get the relative path from the top directory
    rel_path = os.path.relpath(file_path, top_dir)

    # Create the destination path
    destination_path = os.path.join(skipped_dir, rel_path)

    # Ensure the destination directory exists
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)

    # Move the file
    shutil.move(file_path, destination_path)

    return destination_path



# Function to extract text from the first few pages of a PDF
def extract_first_pages(pdf_path: str, num_pages: int = 2) -> str:
    """Extract text from the first few pages of a PDF using OCR"""
    try:
        # Create a temporary processor just for this extraction
        temp_processor = OCRProcessor(config)
        
        # Process only the first few pages
        images = temp_processor.convert_pdf_to_images(pdf_path, first_page=1, last_page=num_pages)
        
        full_text = []
        for i, image in enumerate(images):
            page_text = temp_processor.process_image(image)
            if page_text:
                full_text.append(page_text)
        
        return "\n\n".join(full_text)
    except Exception as e:
        logging.error(f"Error extracting first pages: {str(e)}")
        return f"Error extracting text: {str(e)}"

def extract_metadata_from_text(text: str) -> Dict[str, str]:
    """Extract title and author from OCR text with improved multi-line title handling"""
    metadata = {
        "title": "",
        "author": ""
    }

    # Split text into lines
    lines = text.split('\n')

    # Clean lines (remove empty lines and excessive whitespace)
    clean_lines = [line.strip() for line in lines if line.strip()]

    # Title extraction strategy:
    # 1. Look for centered text at the beginning (often titles)
    # 2. Continue collecting lines until we hit what appears to be author information

    title_lines = []
    author_lines = []
    title_end_index = 0  # Track where the title ends

    # Start with the first few non-empty lines
    title_candidate_range = min(10, len(clean_lines))

    # First pass: identify potential title lines
    # Titles are often in ALL CAPS or have few lowercase letters
    for i in range(title_candidate_range):
        line = clean_lines[i]

        # Skip very short lines or lines that are likely page numbers
        if len(line) < 3 or line.isdigit():
            continue

        # Check if line is centered or all caps (common for titles)
        is_centered = line.startswith(' ') and line.endswith(' ')
        is_mostly_caps = sum(1 for c in line if c.isupper()) > sum(1 for c in line if c.islower())

        # If line looks like a title component, check if it's not a conference header
        if is_mostly_caps or is_centered:
            # Create a normalized version of the line for pattern matching
            normalized_line = line.strip().lower()

            # Skip if it looks like a conference header
            if (re.search(r'\d+(st|nd|rd|th)\s+annual', normalized_line) and
                ('ptti' in normalized_line or 'time' in normalized_line or 'interval' in normalized_line)):
                continue

            if ('proceedings' in normalized_line or 'conference' in normalized_line or
                'meeting' in normalized_line or 'symposium' in normalized_line) and 'of the' in normalized_line:
                continue

            if 'ptti' in normalized_line and any(word in normalized_line for word in
                                               ['annual', 'meeting', 'systems', 'applications']):
                continue

            # If we got here, it's a valid title line
            title_lines.append(line)
            title_end_index = i + 1  # Update where the title ends
        # If we've already found some title lines and hit text that looks like regular content, stop
        elif title_lines and len(line) > 20 and not line.isupper():
            title_end_index = i  # Update where the title ends
            break

    # If we didn't find any title lines, use a simpler approach - just take the first substantial line
    if not title_lines and len(clean_lines) > 0:
        for i, line in enumerate(clean_lines[:5]):
            if len(line) > 15:
                # Check if it's not a conference header
                normalized_line = line.strip().lower()
                if not (re.search(r'\d+(st|nd|rd|th)\s+annual', normalized_line) and
                       ('ptti' in normalized_line or 'time' in normalized_line or 'interval' in normalized_line)) and \
                   not ('ptti' in normalized_line and any(word in normalized_line for word in
                                                        ['annual', 'meeting', 'systems', 'applications'])):
                    title_lines.append(line)
                    title_end_index = i + 1  # Update where the title ends
                    break

    # CRITICAL FIX: Check for the specific pattern we're seeing in the example
    # If we have a title followed by what looks like a person's name followed by an organization,
    # make sure we use the person's name as the author
    if (title_end_index < len(clean_lines) - 1 and
        re.search(r'\b[A-Z][a-z]+ [A-Z]\.? [A-Z][a-z]+\b', clean_lines[title_end_index - 1]) and
        any(word in clean_lines[title_end_index].lower() for word in
            ['university', 'institute', 'laboratory', 'corporation', 'inc', 'ltd'])):
        # We have the pattern: Title, then Person Name, then Organization
        # Use the person's name as the author
        author_lines = [clean_lines[title_end_index - 1]]
    else:
        # Normal author detection
        # First check the line immediately after the title
        if title_end_index < len(clean_lines):
            first_line_after_title = clean_lines[title_end_index]

            # Check if this line looks like an author name (not too long, contains a name pattern)
            if len(first_line_after_title) < 50 and re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', first_line_after_title):
                author_lines.append(first_line_after_title)

                # Look for additional author lines or affiliations
                for j in range(title_end_index + 1, min(title_end_index + 5, len(clean_lines))):
                    next_line = clean_lines[j]
                    # Check if it's an affiliation (contains keywords) but not an abstract
                    if (any(word in next_line.lower() for word in ['university', 'institute', 'laboratory', 'dept', 'department']) and
                        not next_line.lower().startswith('abstract')):
                        # Don't include organization as part of author
                        break
                    # Check if it might be another author
                    elif len(next_line) < 50 and re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', next_line):
                        author_lines.append(next_line)
                    # Stop if we hit the abstract
                    elif next_line.lower().startswith('abstract'):
                        break
                    else:
                        break

        # Second pass: if we didn't find an author in the first line after title, look more broadly
        if not author_lines:
            for i in range(title_end_index, min(title_end_index + 15, len(clean_lines))):
                line = clean_lines[i]

                # Skip very short lines
                if len(line) < 3:
                    continue

                # Skip lines that are likely to be section headers
                if line.startswith('Abstract') or line.startswith('ABSTRACT'):
                    continue

                # Author lines often contain names (First Last format)
                has_name_pattern = re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', line)

                # Author lines might mention affiliations
                has_affiliation = any(word in line.lower() for word in ['university', 'institute', 'laboratory', 'dept', 'department'])

                # Author lines might have "by" or similar
                is_by_line = line.lower().startswith('by ') or 'presented by' in line.lower()

                if has_name_pattern or has_affiliation or is_by_line:
                    author_lines.append(line)
                    # If we find multiple consecutive author lines, collect them
                    for j in range(i+1, min(i+5, len(clean_lines))):
                        next_line = clean_lines[j]
                        if len(next_line) < 50 and (re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', next_line) or
                                                   any(word in next_line.lower() for word in ['university', 'institute', 'laboratory'])):
                            author_lines.append(next_line)
                        else:
                            break
                    break

    # Combine title lines and author lines
    if title_lines:
        # Join with spaces for title lines that appear to be part of the same sentence
        combined_title = ""
        for i, line in enumerate(title_lines):
            if i > 0 and not (line.startswith('AND') or line.startswith('OR') or
                             line.startswith('WITH') or line.startswith('THE') or
                             title_lines[i-1].endswith(',') or title_lines[i-1].endswith('-')):
                combined_title += " "
            combined_title += line

        metadata["title"] = combined_title

    if author_lines:
        metadata["author"] = " ".join(author_lines)

    return metadata


@app.get("/status")
async def processing_status():
    """Return the current processing status"""
    global processing_jobs, document_queue, current_document
    with processing_lock:
        current_jobs = processing_jobs
    
    with queue_lock:
        queue_length = len(document_queue)
        current_doc = current_document
    
    return {
        "active_jobs": current_jobs, 
        "max_concurrent_jobs": max_concurrent_jobs,
        "queue_length": queue_length,
        "current_document": current_doc
    }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the index page with embedded CSS and JS"""
    global processing_jobs, document_queue, current_document
    with processing_lock:
        current_jobs = processing_jobs
    
    with queue_lock:
        queue_length = len(document_queue)
        current_doc = current_document
    
    # Load CSS and JS resources
    css_content, js_content = load_template_resources()

    # Pass the CSS and JS content to the template
    return templates.TemplateResponse(
        "ptti_tool/index.html",
        {
            "request": request,
            "processing_jobs": current_jobs,
            "queue_length": queue_length,
            "current_document": current_doc,
            "max_jobs": max_concurrent_jobs,
            "flash_messages": get_flash_messages(request),
            "config": app_config,
            "css_content": css_content,
            "js_content": js_content,
        },
    )

@app.post("/scan-directory")
async def scan_directory(request: Request, directory_path: str = Form(...)):
    """Scan a directory for PDF files and add them to the queue"""
    if not os.path.exists(directory_path):
        flash(request, f"Directory not found: {directory_path}")
        return RedirectResponse(url="/", status_code=303)

    try:
        # Find all PDF files in the directory
        pdf_files = find_pdf_files(directory_path)

        if not pdf_files:
            flash(request, f"No PDF files found in {directory_path}")
            return RedirectResponse(url="/", status_code=303)

        # Add files to the queue
        with queue_lock:
            document_queue.extend(pdf_files)

        flash(request, f"Added {len(pdf_files)} PDF files to the processing queue")

        # Process the first document to make it ready for review
        # but don't start the full OCR processing
        if pdf_files:
            # Get the first document
            pdf_path = pdf_files[0]["path"]

            try:
                # Extract text from first few pages
                first_pages_text = extract_first_pages(pdf_path, num_pages=2)

                # Extract metadata from text
                extracted_metadata = extract_metadata_from_text(first_pages_text)

                # Combine extracted metadata with file-based metadata
                metadata = {
                    "title": extracted_metadata["title"],
                    "author": extracted_metadata["author"],
                    "publisher": pdf_files[0]["publisher"],
                    "publisher_id": pdf_files[0]["publisher_id"],
                    "publication_date": pdf_files[0]["publication_date"],
                    "source": pdf_files[0]["source"],
                    "original_filename": pdf_files[0]["filename"],
                    "first_pages_text": first_pages_text,
                    "pdf_path": pdf_path
                }

                # Store the metadata for the document
                with queue_lock:
                    if document_queue:
                        document_queue[0]["metadata"] = metadata
                        document_queue[0]["status"] = "ready_for_review"

            except Exception as e:
                logging.error(f"Error preparing first document: {str(e)}")
                with queue_lock:
                    if document_queue:
                        document_queue[0]["error"] = str(e)
                        document_queue[0]["status"] = "error"

        # Just redirect to the queue page
        return RedirectResponse(url="/queue", status_code=303)

    except Exception as e:
        flash(request, f"Error scanning directory: {str(e)}")
        return RedirectResponse(url="/", status_code=303)



@app.get("/queue", response_class=HTMLResponse)
async def view_queue(request: Request):
    """View the current document queue"""
    global document_queue, current_document
    
    with queue_lock:
        queue = document_queue.copy()
        current_doc = current_document
    
    # Load CSS and JS resources
    css_content, js_content = load_template_resources()
    
    return templates.TemplateResponse(
        "ptti_tool/queue.html",
        {
            "request": request,
            "queue": queue,
            "queue_length": len(queue),
            "current_document": current_doc,
            "flash_messages": get_flash_messages(request),
            "config": app_config,
            "css_content": css_content,
            "js_content": js_content,
        },
    )

@app.get("/process-next", response_class=HTMLResponse)
async def get_next_document(request: Request, background_tasks: BackgroundTasks):
    """Process the next document in the queue"""
    background_tasks.add_task(process_next_document)
    return RedirectResponse(url="/queue", status_code=303)

async def process_next_document():
    """Process the next document in the queue"""
    global document_queue, current_document, processing_jobs
    
    # Check if we're already at max capacity
    if not job_semaphore.acquire(blocking=False):
        logging.info("Max concurrent jobs reached, waiting...")
        return
    
    try:
        # Get the next document from the queue
        with queue_lock:
            if not document_queue:
                job_semaphore.release()
                return
            
            # Check if the first document is already processed or being processed
            if document_queue[0].get("status") in ["ready_for_review", "processing", "error"]:
                logging.info(f"First document already has status: {document_queue[0].get('status')}")
                job_semaphore.release()
                return
            
            # Mark the document as being processed
            document_queue[0]["status"] = "processing"
            next_doc = document_queue[0]
            current_document = next_doc
        
        # Increment active jobs counter
        with processing_lock:
            processing_jobs += 1
        
        # Process the document
        pdf_path = next_doc["path"]
        
        try:
            # Extract text from first few pages
            first_pages_text = extract_first_pages(pdf_path, num_pages=2)
            
            # Extract metadata from text
            extracted_metadata = extract_metadata_from_text(first_pages_text)
            
            # Combine extracted metadata with file-based metadata
            metadata = {
                "title": extracted_metadata["title"],
                "author": extracted_metadata["author"],
                "publisher": next_doc["publisher"],
                "publisher_id": next_doc["publisher_id"],
                "publication_date": next_doc["publication_date"],
                "source": next_doc["source"],
                "original_filename": next_doc["filename"],
                "first_pages_text": first_pages_text,
                "pdf_path": pdf_path
            }
            
            # Store the metadata for the document
            with queue_lock:
                if document_queue and document_queue[0] == next_doc:
                    document_queue[0]["metadata"] = metadata
                    document_queue[0]["status"] = "ready_for_review"
        
        except Exception as e:
            logging.error(f"Error processing document: {str(e)}")
            with queue_lock:
                if document_queue and document_queue[0] == next_doc:
                    document_queue[0]["error"] = str(e)
                    document_queue[0]["status"] = "error"
        
        finally:
            # Decrement active jobs counter
            with processing_lock:
                processing_jobs -= 1
            
            # Release the semaphore
            job_semaphore.release()
    
    except Exception as e:
        logging.error(f"Error in process_next_document: {str(e)}")
        # Make sure to release the semaphore in case of error
        job_semaphore.release()
        with processing_lock:
            processing_jobs -= 1

@app.get("/review/{index}", response_class=HTMLResponse)
async def review_document(request: Request, index: int):
    """Review a document before finalizing"""
    global document_queue

    with queue_lock:
        if index >= len(document_queue):
            flash(request, "Document not found in queue")
            return RedirectResponse(url="/queue", status_code=303)

        document = document_queue[index]

        # If document hasn't been prepared yet, prepare it now
        if "metadata" not in document or document.get("status") == "pending":
            # Mark as processing
            document["status"] = "processing"

    # If document needs preparation, do it now
    if document.get("status") == "processing" and "metadata" not in document:
        try:
            # Extract text from first few pages
            pdf_path = document["path"]
            first_pages_text = extract_first_pages(pdf_path, num_pages=2)

            # Extract metadata from text
            extracted_metadata = extract_metadata_from_text(first_pages_text)

            # Combine extracted metadata with file-based metadata
            metadata = {
                "title": extracted_metadata["title"],
                "author": extracted_metadata["author"],
                "publisher": document["publisher"],
                "publisher_id": document["publisher_id"],
                "publication_date": document["publication_date"],
                "source": document["source"],
                "original_filename": document["filename"],
                "first_pages_text": first_pages_text,
                "pdf_path": pdf_path
            }

            # Store the metadata for the document
            with queue_lock:
                if index < len(document_queue) and document_queue[index] == document:
                    document_queue[index]["metadata"] = metadata
                    document_queue[index]["status"] = "ready_for_review"
                    document = document_queue[index]  # Update our local copy

        except Exception as e:
            logging.error(f"Error preparing document for review: {str(e)}")
            with queue_lock:
                if index < len(document_queue) and document_queue[index] == document:
                    document_queue[index]["error"] = str(e)
                    document_queue[index]["status"] = "error"
                    document = document_queue[index]  # Update our local copy

            flash(request, f"Error preparing document: {str(e)}")
            return RedirectResponse(url="/queue", status_code=303)

    # Load CSS and JS resources
    css_content, js_content = load_template_resources()

    return templates.TemplateResponse(
        "ptti_tool/review.html",
        {
            "request": request,
            "document": document,
            "index": index,
            "flash_messages": get_flash_messages(request),
            "config": app_config,
            "css_content": css_content,
            "js_content": js_content,
        },
    )


@app.post("/finalize/{index}")
async def finalize_document(
    request: Request,
    index: int,
    title: str = Form(...),
    author: str = Form(""),
    publisher: str = Form(...),
    publisher_id: str = Form(""),
    publication_date: str = Form(""),
    source: str = Form(...),
):
    """Finalize a document with user-verified metadata"""
    global document_queue, current_document, processing_jobs
    
    # Validate required fields
    if not title or not publisher or not source:
        flash(request, "Title, publisher, and source are required fields")
        return RedirectResponse(url=f"/review/{index}", status_code=303)
    
    with queue_lock:
        if index >= len(document_queue):
            flash(request, "Document not found in queue")
            return RedirectResponse(url="/queue", status_code=303)
        
        document = document_queue[index]
        
        if "metadata" not in document:
            flash(request, "Document metadata not found")
            return RedirectResponse(url="/queue", status_code=303)
    
    # Update metadata with user-verified values
    document["metadata"]["title"] = title
    document["metadata"]["author"] = author
    document["metadata"]["publisher"] = publisher
    document["metadata"]["publisher_id"] = publisher_id
    document["metadata"]["publication_date"] = publication_date
    document["metadata"]["source"] = source
    
    # Check if we're already at max capacity
    if not job_semaphore.acquire(blocking=False):
        flash(request, f"Server is currently processing the maximum number of documents ({max_concurrent_jobs}). Please try again later.")
        return RedirectResponse(url="/queue", status_code=303)
    
    try:
        # Increment active jobs counter
        with processing_lock:
            processing_jobs += 1
        
        # Process the document with OCR
        # Process the document with OCR
        pdf_path = document["path"]
        processed_metadata = {  # Renamed from 'metadata' to 'processed_metadata'
            "title": title,
            "author": author,
            "publisher": publisher,
            "publisher_id": publisher_id,
            "publication_date": publication_date,
            "source": source,
            "original_filename": document["filename"],
        }   

        # Process the PDF
        result = ocr_processor.process_pdf(pdf_path, processed_metadata)

        # Save the original PDF with the sequence number
        pdf_destination = os.path.join(
            app_config["DOC_PDF_DIR"], f"{result['sequence_number']}.pdf"
        )

        # Ensure directory exists
        os.makedirs(os.path.dirname(pdf_destination), exist_ok=True)
        # Copy file to destination
        shutil.copy2(pdf_path, pdf_destination)

        # Upload PDF and text to public server
        success, message = ocr_processor.upload_pdf_to_server(
            result["sequence_number"], app_config
        )
        if not success:
            logging.warning(message)

        # Log the processed document
        log_manager.log_processed_document(
            result["sequence_number"], processed_metadata, pdf_destination
        )

        
        # Move the original file to the processed directory
        try:
            # Determine the top-level directory
            # This assumes the structure is /root/ptti/1987papers/paper.pdf
            # and we want to get /root/ptti/
            file_dir = os.path.dirname(pdf_path)  # /root/ptti/1987papers
            top_dir = os.path.dirname(file_dir)   # /root/ptti
    
            # Move the file to the processed directory
            new_path = move_to_processed_directory(pdf_path, top_dir)
            logging.info(f"Moved processed file to: {new_path}")
        except Exception as e:
            logging.error(f"Error moving file to processed directory: {str(e)}")

        # Remove the document from the queue
        with queue_lock:
            # Remove the document from the queue
            document_queue.pop(index)

            # IMPORTANT CHANGE: Set current_document to None instead of the next document
            if index == 0:
                current_document = None

                # If there are more documents, prepare the next one for review
                if document_queue:
                    try:
                        next_doc = document_queue[0]
                        pdf_path = next_doc["path"]

                        # Extract text from first few pages
                        first_pages_text = extract_first_pages(pdf_path, num_pages=2)

                        # Extract metadata from text
                        extracted_metadata = extract_metadata_from_text(first_pages_text)

                        # Combine extracted metadata with file-based metadata
                        next_metadata = {
                            "title": extracted_metadata["title"],
                            "author": extracted_metadata["author"],
                            "publisher": next_doc["publisher"],
                            "publisher_id": next_doc["publisher_id"],
                            "publication_date": next_doc["publication_date"],
                            "source": next_doc["source"],
                            "original_filename": next_doc["filename"],
                            "first_pages_text": first_pages_text,
                            "pdf_path": pdf_path
                        }

                        # Store the metadata for the document
                        document_queue[0]["metadata"] = next_metadata
                        document_queue[0]["status"] = "ready_for_review"

                    except Exception as e:
                        logging.error(f"Error preparing next document: {str(e)}")
                        document_queue[0]["error"] = str(e)
                        document_queue[0]["status"] = "error"


        
        # Load CSS and JS resources
        css_content, js_content = load_template_resources()
        
        # Redirect to success page
        return templates.TemplateResponse(
            "ptti_tool/success.html",
            {
                "request": request,
                "sequence_number": result["sequence_number"],
                "url": result["url"],
                "title": processed_metadata["title"],
                "flash_messages": get_flash_messages(request),
                "css_content": css_content,
                "js_content": js_content,
                "queue_length": len(document_queue),
            },
        )
    
    except Exception as e:
        flash(request, f"Error processing document: {str(e)}")
        return RedirectResponse(url="/queue", status_code=303)
    
    finally:
        # Decrement active jobs counter
        with processing_lock:
            processing_jobs -= 1
        
        # Release the semaphore
        job_semaphore.release()


@app.post("/skip/{index}")
async def skip_document(request: Request, index: int):
    """Skip a document in the queue and move it to the skipped directory"""
    global document_queue, current_document

    logging.info(f"Attempting to skip document at index {index}")

    with queue_lock:
        if index >= len(document_queue):
            logging.warning(f"Document index {index} not found in queue of length {len(document_queue)}")
            flash(request, "Document not found in queue")
            return RedirectResponse(url="/queue", status_code=303)

        document = document_queue[index]
        pdf_path = document["path"]
        logging.info(f"Skipping document: {pdf_path}")

        # Check if the file exists before trying to move it
        if not os.path.exists(pdf_path):
            logging.warning(f"File not found at path: {pdf_path}")
            flash(request, f"File not found: {pdf_path}")
            # Still remove it from the queue since it doesn't exist
            document_queue.pop(index)
            if index == 0:
                current_document = document_queue[0] if document_queue else None
            return RedirectResponse(url="/queue", status_code=303)

        try:
            # Determine the top-level directory
            file_dir = os.path.dirname(pdf_path)
            top_dir = os.path.dirname(file_dir)

            # Move the file to the skipped directory
            new_path = move_to_skipped_directory(pdf_path, top_dir)
            logging.info(f"Successfully moved skipped file to: {new_path}")
        except Exception as e:
            logging.error(f"Error moving file to skipped directory: {str(e)}")
            flash(request, f"Error skipping document: {str(e)}")
            return RedirectResponse(url="/queue", status_code=303)

        # Remove the document from the queue
        document_queue.pop(index)

        # Update current_document if we skipped the first document
        if index == 0:
            # If there are more documents in the queue, set the next one as current
            if document_queue:
                current_document = document_queue[0]

                # If the next document isn't ready for review, prepare it
                if document_queue[0].get("status") != "ready_for_review" and "metadata" not in document_queue[0]:
                    try:
                        next_doc = document_queue[0]
                        next_pdf_path = next_doc["path"]

                        # Extract text from first few pages
                        first_pages_text = extract_first_pages(next_pdf_path, num_pages=2)

                        # Extract metadata from text
                        extracted_metadata = extract_metadata_from_text(first_pages_text)

                        # Combine extracted metadata with file-based metadata
                        metadata = {
                            "title": extracted_metadata["title"],
                            "author": extracted_metadata["author"],
                            "publisher": next_doc["publisher"],
                            "publisher_id": next_doc["publisher_id"],
                            "publication_date": next_doc["publication_date"],
                            "source": next_doc["source"],
                            "original_filename": next_doc["filename"],
                            "first_pages_text": first_pages_text,
                            "pdf_path": next_pdf_path
                        }

                        # Store the metadata for the document
                        document_queue[0]["metadata"] = metadata
                        document_queue[0]["status"] = "ready_for_review"
                    except Exception as e:
                        logging.error(f"Error preparing next document: {str(e)}")
                        document_queue[0]["error"] = str(e)
                        document_queue[0]["status"] = "error"
            else:
                # No more documents in the queue
                current_document = None

    flash(request, "Document skipped")
    return RedirectResponse(url="/queue", status_code=303)




@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request):
    """Display the document processing log"""
    log_entries = log_manager.get_log_entries()
    
    # Load CSS and JS resources
    css_content, js_content = load_template_resources()

    return templates.TemplateResponse(
        "ocr/logs.html",  # Reuse the existing logs template
        {
            "request": request,
            "log_entries": log_entries,
            "config": app_config,
            "flash_messages": get_flash_messages(request),
            "css_content": css_content,
            "js_content": js_content,
        },
    )

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn

    # Check and recover critical files if needed
    recovery_needed, recovery_success = log_manager.recover_from_backup()
    if recovery_needed:
        if recovery_success:
            logging.info("Successfully recovered critical files from backup")
        else:
            logging.error("Failed to recover some critical files from backup")

    # Put us where the support files are
    original_dir = os.getcwd()
    os.chdir(config["SERVER_DIR"])

    host = config["PTTI_OCR_SERVER_LISTEN_ADDR"]
    port = config["PTTI_OCR_SERVER_PORT"]
    try:
        uvicorn.run("ptti_ocr_server:app", 
            host=host, 
            port=port, 
            reload=True,
            timeout_keep_alive=120,
            timeout_graceful_shutdown=30
            )
    finally:
        os.chdir(original_dir)

