#!/bin/bash
# /usr/local/lib/timebot/bin/email_archive_update.sh
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

set -e  # Exit immediately if any command fails

LOG_FILE="/var/log/timebot/archive-process.log"
ADMIN_EMAIL="jra@febo.com"

echo "Starting job at $(date)" >> $LOG_FILE

# --- Step 1: Download ---
echo "Running update_from_archive.py..." >> $LOG_FILE
# Run the first program and handle success/failure
if ! /usr/local/bin/update_from_archive.py; then
    # Failure case
    ERROR_MSG="First program (update_from_archive.py) failed at $(date)"
    echo "$ERROR_MSG" >> $LOG_FILE
    echo "$ERROR_MSG" | mail -s "Timebot email archive download failure" $ADMIN_EMAIL
    exit 1
else
    # Success case for the first program
    echo "First program (update_from_archive.py) completed successfully at $(date)" >> $LOG_FILE
fi

# --- Step 2: Convert ---
# Step 2 only runs if Step 1 succeeded
echo "Running pipermail2text.py..." >> $LOG_FILE
# Run the second program, redirecting stdout and stderr to the log file
/usr/local/bin/pipermail2text.py >> $LOG_FILE 2>&1

# --- Step 3: Ingest ---
echo "Running email_ingest.py..." >> $LOG_FILE
# Run the third program, redirecting stdout and stderr to the log file
/usr/local/bin/email_ingest.py >> $LOG_FILE 2>&1

echo "Timebot email archive processing completed successfully at $(date)" >> $LOG_FILE

# write a blank line
echo "" >> $LOG_FILE

exit 0 # Explicitly exit with success status

