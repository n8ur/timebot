# Modified log_manager.py

import os
import datetime
import json
import difflib
import shutil
import logging
from pathlib import Path

class LogManager:
    def __init__(self, config):
        self.log_file_path = config["OCR_LOG_FILE"]
        self.sequence_file_path = config["DOC_SEQUENCE_FILE"]
        
        # Define backup directory in root
        self.backup_dir = "/root/ocr_history"
        
        # Ensure main files and backup directory exist
        self.ensure_file_exists()
        self.ensure_backup_dir_exists()
        
    def ensure_file_exists(self):
        """Make sure the file exists, create it if it doesn't"""
        log_dir = os.path.dirname(self.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        if not os.path.exists(self.log_file_path):
            # Create the file with a header
            with open(self.log_file_path, 'w') as f:
                f.write("# Document Processing Log\n")
    
    def ensure_backup_dir_exists(self):
        """Ensure the backup directory exists"""
        if not os.path.exists(self.backup_dir):
            try:
                os.makedirs(self.backup_dir)
                logging.info(f"Created backup directory at {self.backup_dir}")
            except Exception as e:
                logging.error(f"Failed to create backup directory: {str(e)}")
    
    def backup_critical_files(self):
        """Create incremental backups of log and sequence files"""
        # Generate timestamp for the backup files
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Define backup file paths
        log_backup_path = os.path.join(self.backup_dir, f"document_log_{timestamp}.txt")
        seq_backup_path = os.path.join(self.backup_dir, f"sequence_{timestamp}.txt")
        
        # Create backups if the original files exist
        backup_success = True
        
        # Backup log file
        if os.path.exists(self.log_file_path):
            try:
                shutil.copy2(self.log_file_path, log_backup_path)
                logging.info(f"Backed up log file to {log_backup_path}")
            except Exception as e:
                logging.error(f"Failed to backup log file: {str(e)}")
                backup_success = False
        
        # Backup sequence file
        if os.path.exists(self.sequence_file_path):
            try:
                shutil.copy2(self.sequence_file_path, seq_backup_path)
                logging.info(f"Backed up sequence file to {seq_backup_path}")
            except Exception as e:
                logging.error(f"Failed to backup sequence file: {str(e)}")
                backup_success = False
        
        # Cleanup old backups (keep last 10)
        self.cleanup_old_backups()
        
        return backup_success
    
    def cleanup_old_backups(self):
        """Keep only the 10 most recent backups of each file type"""
        try:
            # Get all log backups
            log_backups = sorted(Path(self.backup_dir).glob("document_log_*.txt"))
            
            # Remove older log backups if we have more than 10
            if len(log_backups) > 10:
                for old_backup in log_backups[:-10]:
                    os.remove(old_backup)
                    logging.info(f"Removed old log backup: {old_backup}")
            
            # Get all sequence backups
            seq_backups = sorted(Path(self.backup_dir).glob("sequence_*.txt"))
            
            # Remove older sequence backups if we have more than 10
            if len(seq_backups) > 10:
                for old_backup in seq_backups[:-10]:
                    os.remove(old_backup)
                    logging.info(f"Removed old sequence backup: {old_backup}")
        
        except Exception as e:
            logging.error(f"Error during backup cleanup: {str(e)}")
    
    def recover_from_backup(self):
        """Attempt to recover files from the most recent backup if needed"""
        recovery_needed = False
        recovery_success = True
        
        # Check if log file is missing or empty
        if not os.path.exists(self.log_file_path) or os.path.getsize(self.log_file_path) == 0:
            recovery_needed = True
            logging.warning("Log file is missing or empty, attempting recovery")
            
            # Find the most recent log backup
            log_backups = sorted(Path(self.backup_dir).glob("document_log_*.txt"))
            if log_backups:
                latest_log_backup = log_backups[-1]
                try:
                    shutil.copy2(latest_log_backup, self.log_file_path)
                    logging.info(f"Recovered log file from {latest_log_backup}")
                except Exception as e:
                    logging.error(f"Failed to recover log file: {str(e)}")
                    recovery_success = False
            else:
                logging.error("No log backups found for recovery")
                recovery_success = False
        
        # Check if sequence file is missing or invalid
        seq_file_valid = False
        if os.path.exists(self.sequence_file_path):
            try:
                with open(self.sequence_file_path, 'r') as f:
                    int(f.read().strip())
                    seq_file_valid = True
            except (ValueError, IOError):
                seq_file_valid = False
        
        if not seq_file_valid:
            recovery_needed = True
            logging.warning("Sequence file is missing or invalid, attempting recovery")
            
            # Find the most recent sequence backup
            seq_backups = sorted(Path(self.backup_dir).glob("sequence_*.txt"))
            if seq_backups:
                latest_seq_backup = seq_backups[-1]
                try:
                    shutil.copy2(latest_seq_backup, self.sequence_file_path)
                    logging.info(f"Recovered sequence file from {latest_seq_backup}")
                except Exception as e:
                    logging.error(f"Failed to recover sequence file: {str(e)}")
                    recovery_success = False
            else:
                logging.error("No sequence backups found for recovery")
                recovery_success = False
        
        return recovery_needed, recovery_success
    
    def log_processed_document(self, sequence_number, metadata, file_path=None):
        """
        Log a processed document to the log file and create a backup
        
        Args:
            sequence_number: The assigned sequence number
            metadata: Dictionary containing document metadata
            file_path: Original file path (optional)
        """
        timestamp = datetime.datetime.now().isoformat()
        
        # Create a log entry with timestamp, sequence number and metadata
        log_data = {
            "timestamp": timestamp,
            "sequence_number": sequence_number,
            "metadata": metadata
        }
        
        if file_path:
            log_data["processed_pdf_name"] = os.path.basename(file_path)
        
        # Write the log entry as a single line
        with open(self.log_file_path, 'a') as f:
            f.write(f"{json.dumps(log_data)}\n")
        
        # Create a backup after adding a new entry
        self.backup_critical_files()
        
        return True

    def get_log_entries(self):
        """
        Read and parse the log file, returning a list of log entries
    
        Returns:
            List of dictionaries containing log entries
        """
        entries = []
        
        # Try to recover files if needed
        recovery_needed, recovery_success = self.recover_from_backup()
        if recovery_needed and not recovery_success:
            logging.error("Failed to recover log file, returning empty log entries")
            return entries
    
        if not os.path.exists(self.log_file_path):
            return entries
    
        with open(self.log_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # Skip comments and empty lines
                    try:
                        entry = json.loads(line)
                        # Convert ISO timestamp to a more readable format
                        if 'timestamp' in entry:
                            try:
                                dt = datetime.datetime.fromisoformat(entry['timestamp'])
                                entry['formatted_timestamp'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                entry['formatted_timestamp'] = entry['timestamp']
                        entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
        
        # Sort entries by timestamp (newest first)
        entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return entries
    
    def find_similar_titles(self, title, threshold=0.7):
        """
        Find documents with similar titles in the log
        
        Args:
            title: The title to compare against
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            List of log entries with similar titles
        """
        similar_entries = []
        entries = self.get_log_entries()
        
        # Normalize the input title
        title_lower = title.lower().strip()
        
        for entry in entries:
            if 'metadata' in entry and 'title' in entry['metadata']:
                entry_title = entry['metadata']['title'].lower().strip()
                
                # Calculate similarity ratio using difflib
                similarity = difflib.SequenceMatcher(None, title_lower, entry_title).ratio()
                
                if similarity >= threshold:
                    # Add similarity score to the entry
                    entry['similarity'] = round(similarity * 100)
                    similar_entries.append(entry)
        
        # Sort by similarity (highest first)
        similar_entries.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        
        return similar_entries

