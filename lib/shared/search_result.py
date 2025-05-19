# search_result.py
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse


def parse_date(date_str: Union[str, None]) -> Optional[datetime]:
    """Parse date string in various formats."""
    if not date_str:
        return None
        
    # Try different date formats
    formats = [
        "%Y-%m-%d",                     # ISO format: 2023-01-01
        "%Y-%m-%dT%H:%M:%S",            # ISO with time: 2023-01-01T12:30:45
        "%Y-%m-%dT%H:%M:%SZ",           # ISO with UTC Z: 2023-01-01T12:30:45Z
        "%a %b %d %H:%M:%S %Z %Y",      # Fri Aug 7 20:14:17 UTC 2015
        "%Y"                            # Just year: 1990
    ]
    
    # If it's already a datetime object, return it
    if isinstance(date_str, datetime):
        return date_str
    
    # Convert to string if it's not already
    if not isinstance(date_str, str):
        date_str = str(date_str)
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
            
    # If all formats fail, try isoformat as a last resort
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
            
    # If all formats fail, return None
    return None


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed_url = urlparse(url)
        return parsed_url.netloc
    except:
        return ""


class SearchResult:
    def __init__(
        self,
        search_provider: str,  # e.g., "ChromaDB-Emails", "Whoosh-Documents"
        doc_type: str,  # "email", "document", or "web"
        doc_id: str,
        snippet: str,
        score: float,
        title: Optional[str] = None,
        author: Optional[str] = None,
        publisher: Optional[str] = None,
        publisher_id: Optional[str] = None,
        from_field: Optional[str] = None,  # Sender for emails
        date: Optional[datetime] = None,
        subject: Optional[str] = None,
        url: Optional[str] = None,
        source_url: Optional[str] = None,  # Original URL for web documents
        captured_at: Optional[datetime] = None,  # Capture timestamp for web documents
        domain: Optional[str] = None,  # Domain for web documents
        additional_metadata: Optional[Dict[str, Any]] = None,
        chunk_id: Optional[str] = None,
        chunk_index: Optional[int] = None,
        total_chunks: Optional[int] = None,
    ):
        self.search_provider = search_provider
        self.doc_type = doc_type
        self.doc_id = doc_id
        self.snippet = snippet
        self.score = score
        self.title = title
        self.author = author
        self.publisher = publisher
        self.publisher_id = publisher_id
        self.from_field = from_field
        self.date = date
        self.subject = subject
        self.url = url
        self.source_url = source_url
        self.captured_at = captured_at
        self.domain = domain
        self.additional_metadata = additional_metadata or {}
        self.chunk_id = chunk_id
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        
    # Property for backward compatibility
    @property
    def source(self):
        """Legacy accessor for backward compatibility"""
        return self.search_provider

    @source.setter
    def source(self, value):
        self.search_provider = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert the SearchResult object to a dictionary."""
        result = {
            "search_provider": self.search_provider,
            "source": self.search_provider,  # For backward compatibility
            "doc_type": self.doc_type,
            "doc_id": self.doc_id,
            "snippet": self.snippet,
            "score": self.score,
            "content": self.snippet,  # For compatibility with existing code
        }
        
        # Add optional fields if they exist
        if self.title:
            result["title"] = self.title
        if self.author:
            result["author"] = self.author
        if self.publisher:
            result["publisher"] = self.publisher
        if self.publisher_id:
            result["publisher_id"] = self.publisher_id
        if self.from_field:
            result["from"] = self.from_field
        if self.date:
            result["date"] = self.date.isoformat()
        if self.subject:
            result["subject"] = self.subject
        if self.url:
            result["url"] = self.url
        if self.source_url:
            result["source_url"] = self.source_url
        if self.captured_at:
            result["captured_at"] = self.captured_at.isoformat()
        if self.domain:
            result["domain"] = self.domain
        if self.chunk_id:
            result["chunk_id"] = self.chunk_id
        if self.chunk_index is not None:
            result["chunk_index"] = self.chunk_index
            result["chunk_number"] = self.chunk_index  # For backward compatibility
        if self.total_chunks is not None:
            result["total_chunks"] = self.total_chunks
        
        # Add any additional metadata
        result.update(self.additional_metadata)
        
        return result

    @classmethod
    def from_whoosh_email(cls, whoosh_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a Whoosh email search result."""
        # Parse date with more robust handling
        date_obj = parse_date(whoosh_result.get("date"))
        
        # Get content and create snippet
        content = whoosh_result.get("content", "")
        snippet = content[:500] if content else ""
        
        return cls(
            search_provider="Whoosh-Emails",
            doc_type="email",
            doc_id=whoosh_result.get("doc_id", ""),
            snippet=snippet,
            score=whoosh_result.get("score", 0.0),
            from_field=whoosh_result.get("from_", ""),
            date=date_obj,
            subject=whoosh_result.get("subject", ""),
            url=whoosh_result.get("url", ""),
            additional_metadata={
                k: v for k, v in whoosh_result.items() 
                if k not in ["doc_id", "content", "score", "from_", "date", "subject", "url"]
            },
        )

    @classmethod
    def from_whoosh_document(cls, whoosh_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a Whoosh document search result."""
        # Get content and create snippet
        content = whoosh_result.get("content", "")
        snippet = content[:500] if content else ""
        
        # Handle chunk information
        chunk_id = whoosh_result.get("chunk_id")
        
        chunk_number = whoosh_result.get("chunk_number")
        if chunk_number is not None:
            try:
                chunk_number = int(chunk_number)
            except (ValueError, TypeError):
                chunk_number = None
                
        total_chunks = whoosh_result.get("total_chunks")
        if total_chunks is not None:
            try:
                total_chunks = int(total_chunks)
            except (ValueError, TypeError):
                total_chunks = None
        
        return cls(
            search_provider="Whoosh-Documents",
            doc_type="document",
            doc_id=whoosh_result.get("doc_id", ""),
            snippet=snippet,
            score=whoosh_result.get("score", 0.0),
            title=whoosh_result.get("title", ""),
            author=whoosh_result.get("author", ""),
            publisher=whoosh_result.get("publisher", ""),
            publisher_id=whoosh_result.get("publisher_id", ""),
            date=parse_date(whoosh_result.get("publication_date")),
            url=whoosh_result.get("url", ""),
            chunk_id=chunk_id,
            chunk_index=chunk_number,
            total_chunks=total_chunks,
            additional_metadata={
                k: v for k, v in whoosh_result.items() 
                if k not in ["doc_id", "content", "score", "title", "author", 
                            "publication_date", "url", "publisher", "publisher_id",
                            "chunk_id", "chunk_number", "total_chunks"]
            },
        )
    
    @classmethod
    def from_whoosh_web(cls, whoosh_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a Whoosh web search result."""
        # Get content and create snippet
        content = whoosh_result.get("content", "")
        snippet = content[:500] if content else ""
        
        # Get source URL and extract domain
        source_url = whoosh_result.get("source_url", "")
        domain = whoosh_result.get("domain", extract_domain(source_url))
        
        # Parse captured_at timestamp
        captured_at = parse_date(whoosh_result.get("captured_at"))
        
        return cls(
            search_provider="Whoosh-Web",
            doc_type="web",
            doc_id=whoosh_result.get("doc_id", ""),
            snippet=snippet,
            score=whoosh_result.get("score", 0.0),
            title=whoosh_result.get("title", ""),
            source_url=source_url,
            url=source_url,  # For compatibility, use source_url as url
            captured_at=captured_at,
            domain=domain,
            date=captured_at,  # For compatibility, use captured_at as date
            additional_metadata={
                k: v for k, v in whoosh_result.items() 
                if k not in ["doc_id", "content", "score", "title", 
                            "source_url", "captured_at", "domain"]
            },
        )
    
    @classmethod
    def from_chroma_email(cls, chroma_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a ChromaDB email search result."""
        metadata = chroma_result.get("metadata", {})
        
        # Parse date with more robust handling
        date_obj = parse_date(metadata.get("date"))
        
        # Handle both "from_" and "from" fields in metadata
        from_field = metadata.get("from_", metadata.get("from", ""))
        
        # Get content/text and create snippet
        content = chroma_result.get("text", chroma_result.get("document", ""))
        snippet = content[:500] if content else ""
        
        # Get hash/id
        doc_id = chroma_result.get("id", metadata.get("hash", ""))
        
        return cls(
            search_provider="ChromaDB-Emails",
            doc_type="email",
            doc_id=doc_id,
            snippet=snippet,
            score=chroma_result.get("score", chroma_result.get("distance", 0.0)),
            from_field=from_field,
            date=date_obj,
            subject=metadata.get("subject", ""),
            url=metadata.get("url", ""),
            additional_metadata={
                k: v for k, v in metadata.items() 
                if k not in ["from_", "from", "date", "subject", "url", "hash"]
            },
        )
    
    @classmethod
    def from_chroma_document(cls, chroma_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a ChromaDB document search result."""
        metadata = chroma_result.get("metadata", {})
        
        # Get content/text and create snippet
        content = chroma_result.get("text", chroma_result.get("document", ""))
        snippet = content[:500] if content else ""
        
        # Parse date with more robust handling
        date_field = metadata.get("publication_date", metadata.get("date", None))
        date_obj = parse_date(date_field)
        
        # Handle chunk information
        chunk_id = metadata.get("chunk_id")
        
        chunk_number = metadata.get("chunk_number")
        if chunk_number is not None:
            try:
                chunk_number = int(chunk_number)
            except (ValueError, TypeError):
                chunk_number = None
                
        total_chunks = metadata.get("total_chunks")
        if total_chunks is not None:
            try:
                total_chunks = int(total_chunks)
            except (ValueError, TypeError):
                total_chunks = None
        
        # Get hash/id
        doc_id = chroma_result.get("id", metadata.get("hash", ""))
        
        return cls(
            search_provider="ChromaDB-Documents",
            doc_type="document",
            doc_id=doc_id,
            snippet=snippet,
            score=chroma_result.get("score", chroma_result.get("distance", 0.0)),
            title=metadata.get("title", ""),
            author=metadata.get("author", ""),
            publisher=metadata.get("publisher", ""),
            publisher_id=metadata.get("publisher_id", ""),
            date=date_obj,
            url=metadata.get("url", ""),
            chunk_id=chunk_id,
            chunk_index=chunk_number,
            total_chunks=total_chunks,
            additional_metadata={
                k: v for k, v in metadata.items() 
                if k not in ["title", "author", "publication_date", "date", 
                            "url", "chunk_id", "chunk_number", "total_chunks",
                            "publisher", "publisher_id", "hash"]
            },
        )
    
    @classmethod
    def from_chroma_web(cls, chroma_result: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a ChromaDB web search result."""
        metadata = chroma_result.get("metadata", {})
        
        # Get content/text and create snippet
        content = chroma_result.get("text", chroma_result.get("document", ""))
        snippet = content[:500] if content else ""
        
        # Get source URL and extract domain
        source_url = metadata.get("source_url", "")
        domain = metadata.get("domain", extract_domain(source_url))
        
        # Parse captured_at timestamp
        captured_at = parse_date(metadata.get("captured_at"))
        
        # Get hash/id
        doc_id = chroma_result.get("id", metadata.get("hash", ""))
        
        return cls(
            search_provider="ChromaDB-Web",
            doc_type="web",
            doc_id=doc_id,
            snippet=snippet,
            score=chroma_result.get("score", chroma_result.get("distance", 0.0)),
            title=metadata.get("title", ""),
            source_url=source_url,
            url=source_url,  # For compatibility, use source_url as url
            captured_at=captured_at,
            domain=domain,
            date=captured_at,  # For compatibility, use captured_at as date
            additional_metadata={
                k: v for k, v in metadata.items() 
                if k not in ["title", "source_url", "captured_at", "domain", "hash"]
            },
        )

    @staticmethod
    def debug_result(result: "SearchResult") -> None:
        """Print detailed information about a search result for debugging."""
        print(f"Provider: {result.search_provider}")
        print(f"Type: {result.doc_type}")
        print(f"ID: {result.doc_id}")
        print(f"Score: {result.score}")
        print(f"Title: {result.title}")
        print(f"Author: {result.author}")
        print(f"Publisher: {result.publisher}")
        print(f"Publisher ID: {result.publisher_id}")
        print(f"From: {result.from_field}")
        print(f"Date: {result.date}")
        print(f"Subject: {result.subject}")
        print(f"URL: {result.url}")
        print(f"Source URL: {result.source_url}")
        print(f"Captured At: {result.captured_at}")
        print(f"Domain: {result.domain}")
        print(f"Chunk ID: {result.chunk_id}")
        print(f"Chunk Index: {result.chunk_index}")
        print(f"Total Chunks: {result.total_chunks}")
        print("Additional Metadata:")
        for k, v in result.additional_metadata.items():
            print(f"  {k}: {v}")
        print(f"Snippet: {result.snippet[:100]}...")
        print("---")

