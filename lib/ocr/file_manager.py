# /usr/local/lib/timebot/lib/ocr/file_manager.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

import os
import uuid
import tempfile
from pathlib import Path
from typing import Optional, BinaryIO, Union

class FileManager:
    def __init__(self, config):
        self.config = config
    
    def allowed_file(self, filename: str) -> bool:
        """Check if the file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in 'pdf'
    
    def save_uploaded_file(self, file: BinaryIO) -> Optional[str]:
        """
        Save an uploaded file with a secure name.
        This method is kept for backward compatibility with Flask.
        """
        if hasattr(file, 'filename') and self.allowed_file(file.filename):
            # Create a unique filename
            original_filename = self._secure_filename(file.filename)
            extension = original_filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{extension}"
            
            # Ensure upload directory exists
            os.makedirs(self.config['DOC_UPLOAD_FOLDER'], exist_ok=True)
            
            file_path = os.path.join(self.config['DOC_UPLOAD_FOLDER'], 
                unique_filename)
            
            # Save the file
            if hasattr(file, 'save'):  # Flask's FileStorage object
                file.save(file_path)
            else:  # Regular file-like object
                with open(file_path, 'wb') as f:
                    f.write(file.read())
                    
            return file_path
        return None
    
    def save_uploaded_file_content(self, content: bytes, original_filename: str) -> Optional[str]:
        """
        Save file content with a secure name to a temporary location.
        This method is designed for FastAPI's UploadFile handling.
        """
        if self.allowed_file(original_filename):
            # Create a temporary file with the correct extension
            with tempfile.NamedTemporaryFile(suffix='.pdf', 
                    delete=False) as temp_file:
                temp_file.write(content)
                return temp_file.name
        return None


    def cleanup_file(self, file_path: str) -> None:
        """Remove a temporary file after processing."""
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def _secure_filename(self, filename: str) -> str:
        """
        Return a secure version of a filename.
        This replaces werkzeug.utils.secure_filename to remove the dependency.
        """
        # Convert to ASCII
        filename = filename.encode('ascii', 'ignore').decode('ascii')
        
        # Remove characters that aren't alphanumerics, underscores, or hyphens
        filename = ''.join(c for c in filename if c.isalnum() or c in '._-')
        
        # Ensure it doesn't start with a dot
        if filename.startswith('.'):
            filename = 'file' + filename
            
        return filename

