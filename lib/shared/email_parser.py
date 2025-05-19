#!/bin/env python3

from typing import Dict, Any, Tuple

def parse_email_message(raw_message: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse an email message with a specific format where the first four lines contain metadata:
    Line 1: Subject
    Line 2: From
    Line 3: Date
    Line 4: URL
    
    Args:
        raw_message: Raw email message text
        
    Returns:
        Tuple of (metadata dict, content text)
    """
    lines = raw_message.split('\n')
    
    # Extract metadata from the first four lines
    metadata = {}
    
    if len(lines) >= 1 and lines[0].startswith('Subject:'):
        metadata['subject'] = lines[0][len('Subject:'):].strip()
    else:
        metadata['subject'] = 'Unknown'
        
    if len(lines) >= 2 and lines[1].startswith('From:'):
        metadata['from_'] = lines[1][len('From:'):].strip()
    else:
        metadata['from_'] = 'Unknown'
        
    if len(lines) >= 3 and lines[2].startswith('Date:'):
        metadata['date'] = lines[2][len('Date:'):].strip()
    else:
        metadata['date'] = 'Unknown'
        
    if len(lines) >= 4 and lines[3].startswith('URL:'):
        metadata['url'] = lines[3][len('URL:'):].strip()
    else:
        metadata['url'] = ''
    
    # Content is everything after the first four lines
    content = '\n'.join(lines[4:]) if len(lines) > 4 else ''
    
    return metadata, content

