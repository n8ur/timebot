#!/usr/bin/env python3

# Standard imports
import os
import sys
import threading
import shutil
import logging
import uuid
import tempfile
import time
from typing import Optional, Dict, Any, Tuple

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")

# Import the config module
from shared.config import config
from shared.utils import ensure_timebot_prefix, make_timebot_filename

# FastAPI imports
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
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
app = FastAPI(title="OCR Server", description="OCR Server for processing PDF documents")

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
max_concurrent_jobs = 4  # Adjust based on your server's capacity
job_semaphore = threading.Semaphore(max_concurrent_jobs)

# Dictionary to store temporary uploaded files
temp_files = {}


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
    css_path = os.path.join(config["PYTHON_STATIC_DIR"], "css/ocr/styles.css")
    css_content = ""
    if os.path.exists(css_path):
        try:
            with open(css_path, 'r') as f:
                css_content = f.read()
        except Exception as e:
            print(f"Error reading CSS file: {e}")

    # Read the JS file
    js_path = os.path.join(config["PYTHON_STATIC_DIR"], "js/ocr/main.js")
    js_content = ""
    if os.path.exists(js_path):
        try:
            with open(js_path, 'r') as f:
                js_content = f.read()
        except Exception as e:
            print(f"Error reading JS file: {e}")
            
    return css_content, js_content


@app.get("/status")
async def processing_status():
    """Return the current processing status"""
    global processing_jobs
    with processing_lock:
        return {"active_jobs": processing_jobs, "max_concurrent_jobs": max_concurrent_jobs}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the index page with embedded CSS and JS"""
    global processing_jobs
    with processing_lock:
        current_jobs = processing_jobs

    # Load CSS and JS resources
    css_content, js_content = load_template_resources()

    # Pass the CSS and JS content to the template
    return templates.TemplateResponse(
        "ocr/index.html",
        {
            "request": request,
            "processing_jobs": current_jobs,
            "max_jobs": max_concurrent_jobs,
            "flash_messages": get_flash_messages(request),
            "config": app_config,
            "css_content": css_content,
            "js_content": js_content,
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def view_logs(request: Request):
    """Display the document processing log"""
    log_entries = log_manager.get_log_entries()
    
    # Load CSS and JS resources
    css_content, js_content = load_template_resources()

    return templates.TemplateResponse(
        "ocr/logs.html",
        {
            "request": request,
            "log_entries": log_entries,
            "config": app_config,
            "flash_messages": get_flash_messages(request),
            "css_content": css_content,
            "js_content": js_content,
        },
    )


@app.post("/")
async def upload_file(
    request: Request,
    pdf_file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(""),
    publisher: str = Form(...),
    publisher_id: str = Form(""),
    publication_date: str = Form(""),
    source: str = Form(...),
):
    """Handle file upload and processing"""
    # Validate required fields
    if not title or not publisher or not source:
        flash(request, "Title, publisher, and source are required fields")
        return RedirectResponse(url="/", status_code=303)

    # Check if file is provided and valid
    if not pdf_file.filename:
        flash(request, "No selected file")
        return RedirectResponse(url="/", status_code=303)

    # Check if we're already at max capacity
    global job_semaphore
    if not job_semaphore.acquire(blocking=False):
        flash(request, f"Server is currently processing the maximum number of documents ({max_concurrent_jobs}). Please try again later.")
        return RedirectResponse(url="/", status_code=303)
    
    try:
        # Process the file
        if file_manager.allowed_file(pdf_file.filename):
            try:
                # Save the uploaded file in temp location
                contents = await pdf_file.read()
                temp_file_path = file_manager.save_uploaded_file_content(
                    contents, pdf_file.filename
                )

                if not temp_file_path:
                    flash(request, "Error saving file")
                    return RedirectResponse(url="/", status_code=303)

                # Collect metadata
                metadata = {
                    "title": title,
                    "author": author,
                    "publisher": publisher,
                    "publisher_id": publisher_id,
                    "publication_date": publication_date,
                    "source": source,
                    "original_filename": pdf_file.filename,
                }
                
                # Check for similar titles before processing
                similar_entries = log_manager.find_similar_titles(title, threshold=0.7)
                
                if similar_entries:
                    # Generate a unique ID for this temporary file
                    temp_file_id = str(uuid.uuid4())
                    
                    # Store the temp file path and metadata in the temp_files dictionary
                    temp_files[temp_file_id] = {
                        "temp_file_path": temp_file_path,
                        "metadata": metadata
                    }
                    
                    # Load CSS and JS resources
                    css_content, js_content = load_template_resources()
                    
                    # Show the duplicate check page
                    return templates.TemplateResponse(
                        "ocr/duplicate_check.html",
                        {
                            "request": request,
                            "title": title,
                            "similar_entries": similar_entries,
                            "temp_file_id": temp_file_id,
                            "config": app_config,
                            "flash_messages": get_flash_messages(request),
                            "css_content": css_content,
                            "js_content": js_content,
                        },
                    )
                
                # If no similar titles found, proceed with processing
                return await process_uploaded_file(request, temp_file_path, metadata)

            except Exception as e:
                flash(request, f"Error processing file: {str(e)}")
                return RedirectResponse(url="/", status_code=303)
        else:
            flash(request, "File type not allowed. Please upload a PDF.")
            return RedirectResponse(url="/", status_code=303)
    finally:
        # If we didn't proceed to processing, release the semaphore
        if "temp_file_id" in locals() or "return" in locals():
            job_semaphore.release()


@app.post("/proceed-with-upload")
async def proceed_with_upload(
    request: Request,
    temp_file_id: str = Form(...),
):
    """Process the file after user confirms it's not a duplicate"""
    # Check if the temp file ID exists
    if temp_file_id not in temp_files:
        flash(request, "Upload session expired. Please try again.")
        return RedirectResponse(url="/", status_code=303)
    
    # Get the temp file path and metadata
    temp_file_data = temp_files.pop(temp_file_id)
    temp_file_path = temp_file_data["temp_file_path"]
    metadata = temp_file_data["metadata"]
    
    # Try to acquire the semaphore
    global job_semaphore
    if not job_semaphore.acquire(blocking=False):
        flash(request, f"Server is currently processing the maximum number of documents ({max_concurrent_jobs}). Please try again later.")
        return RedirectResponse(url="/", status_code=303)
    
    # Process the file
    return await process_uploaded_file(request, temp_file_path, metadata)


async def process_uploaded_file(request: Request, temp_file_path: str, metadata: Dict[str, str]):
    """Process the uploaded file with the given metadata"""
    try:
        # Increment active jobs counter
        global processing_jobs
        with processing_lock:
            processing_jobs += 1

        try:
            # Process the PDF
            result = ocr_processor.process_pdf(temp_file_path, metadata)

            # Save the original PDF with the sequence number
            pdf_destination = os.path.join(
                app_config["DOC_PDF_DIR"], make_timebot_filename(result['sequence_number'], "pdf")
            )

            # Ensure directory exists
            os.makedirs(os.path.dirname(pdf_destination), exist_ok=True)
            # Copy file to destination
            shutil.copy2(temp_file_path, pdf_destination)

            # Upload PDF and text to public server
            success, message = ocr_processor.upload_pdf_to_server(
                result["sequence_number"], app_config
            )
            if not success:
                logging.warning(message)

            # Log the processed document
            log_manager.log_processed_document(
                result["sequence_number"], metadata, pdf_destination
            )
        except FileNotFoundError as e:
            flash(request, f"File not found: {str(e)}")
            return RedirectResponse(url="/", status_code=303)
        except OSError as e:
            flash(request, f"OS error: {str(e)}")
            return RedirectResponse(url="/", status_code=303)
        except Exception as e:
            flash(request, f"Error processing file: {str(e)}")
            return RedirectResponse(url="/", status_code=303)
        finally:
            # Decrement active jobs counter
            with processing_lock:
                processing_jobs -= 1
            # Release the semaphore
            job_semaphore.release()

        # Clean up the uploaded file from the temporary location
        file_manager.cleanup_file(temp_file_path)

        # Load CSS and JS resources
        css_content, js_content = load_template_resources()

        # Return success page
        return templates.TemplateResponse(
            "ocr/success.html",
            {
                "request": request,
                "sequence_number": result["sequence_number"],
                "url": result["url"],
                "title": metadata["title"],
                "flash_messages": get_flash_messages(request),
                "css_content": css_content,
                "js_content": js_content,
            },
        )

    except Exception as e:
        flash(request, f"Error processing file: {str(e)}")
        # Make sure to release the semaphore in case of error
        job_semaphore.release()
        return RedirectResponse(url="/", status_code=303)


@app.get("/download/pdf/{filename}")
async def download_pdf_file(filename: str):
    """Download a PDF file"""
    normalized_filename = ensure_timebot_prefix(filename)
    file_path = os.path.join(app_config["DOC_PDF_DIR"], normalized_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


# Add a new endpoint to check processing progress
@app.get("/progress/{sequence_number}")
async def check_progress(sequence_number: str):
    """Check the progress of a document being processed"""
    progress_dir = os.path.dirname(app_config['DOC_TEXT_UNPROCESSED_DIR'])
    progress_path = os.path.join(progress_dir, f"{sequence_number}.progress")
    
    if not os.path.exists(progress_path):
        return {"status": "not_found", "message": "Progress file not found"}
    
    try:
        with open(progress_path, 'r') as f:
            progress_content = f.read()
        
        # Parse progress content
        lines = progress_content.strip().split('\n')
        last_line = lines[-1] if lines else ""
        
        # Check if processing is complete
        if "Processing complete" in last_line:
            return {"status": "complete", "progress": 100, "details": progress_content}
        
        # Check if there was an error
        if "ERROR:" in last_line:
            return {"status": "error", "message": last_line, "details": progress_content}
        
        # Calculate approximate progress
        total_pages_match = re.search(r'Total pages: (\d+)', progress_content)
        if not total_pages_match:
            return {"status": "in_progress", "progress": 0, "details": progress_content}
        
        total_pages = int(total_pages_match.group(1))
        
        # Find the highest page number processed
        page_matches = re.findall(r'Processing page (\d+)/', progress_content)
        current_page = int(page_matches[-1]) if page_matches else 0
        
        progress_percent = min(int((current_page / total_pages) * 100), 99)
        
        return {
            "status": "in_progress",
            "progress": progress_percent,
            "current_page": current_page,
            "total_pages": total_pages,
            "details": progress_content
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Add a cleanup job for temporary files
def cleanup_temp_files():
    """Periodically clean up expired temporary files"""
    while True:
        try:
            # Get current time
            now = time.time()
            
            # Check temp_files dictionary for entries older than 1 hour
            expired_ids = []
            for temp_id, temp_data in temp_files.items():
                temp_file_path = temp_data["temp_file_path"]
                
                # Check if file exists and when it was created
                if os.path.exists(temp_file_path):
                    file_age = now - os.path.getctime(temp_file_path)
                    if file_age > 3600:  # 1 hour
                        # Delete the file
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass
                        expired_ids.append(temp_id)
                else:
                    # File doesn't exist anymore
                    expired_ids.append(temp_id)
            
            # Remove expired entries from dictionary
            for temp_id in expired_ids:
                temp_files.pop(temp_id, None)
                
        except Exception as e:
            logging.error(f"Error in cleanup job: {str(e)}")
        
        # Sleep for 15 minutes
        time.sleep(900)

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn

    # Start the cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_temp_files, daemon=True)
    cleanup_thread.start()

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

    host = config["OCR_SERVER_LISTEN_ADDR"]
    port = config["OCR_SERVER_PORT"]
    try:
        uvicorn.run("ocr_server:app", 
            host=host, 
            port=port, 
            reload=True,
            timeout_keep_alive=120,
            timeout_graceful_shutdown=30
            )
    finally:
        os.chdir(original_dir)

