# /usr/local/lib/timebot/lib/rag/models.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

"""
Pydantic models for search functionality.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, Extra

class WeightConfig(BaseModel):
    """Model for weight configuration."""
    document_collection_weight: Optional[float] = Field(None, description="Weight for document collection results")
    email_collection_weight: Optional[float] = Field(None, description="Weight for email collection results")
    web_collection_weight: Optional[float] = Field(None, description="Weight for web collection results")
    recency_weight: Optional[float] = Field(None, description="Weight for recency factor")
    recency_decay_days: Optional[int] = Field(None, description="Days after which documents get zero recency score")
    chromadb_weight: Optional[float] = Field(None, description="Weight for Whoosh results")
    whoosh_weight: Optional[float] = Field(None, description="Weight for Whoosh results")
    reranker_weight: Optional[float] = Field(None, description="Weight for reranker scores")

class MetadataQuery(BaseModel):
    """Model for metadata search parameters."""
    # Common fields for both emails and documents
    title: Optional[str] = Field(None, description="Search for documents with this title or emails with this subject")
    author: Optional[str] = Field(None, description="Search for documents with this author or emails with this sender")
    date: Optional[str] = Field(None, description="Search for documents/emails from this date or date range (YYYY-MM-DD to YYYY-MM-DD)")
    
    # Document-specific fields
    publisher: Optional[str] = Field(None, description="Search for documents with this publisher")
    
    # Email-specific fields
    subject: Optional[str] = Field(None, description="Search for emails with this subject (alternative to title)")
    from_: Optional[str] = Field(None, alias="from", description="Search for emails from this sender (alternative to author)")
    to: Optional[str] = Field(None, description="Search for emails sent to this recipient")
    
    # Web-specific fields
    source_url: Optional[str] = Field(None, description="Search for web documents with this source URL")
    domain: Optional[str] = Field(None, description="Search for web documents from this domain")
    
    class Config:
        extra = Extra.allow  # Allow additional metadata fields
        json_schema_extra = {
            "example": {
                "title": "Machine Learning",
                "author": "Andrew Ng",
                "publisher": "Stanford",
                "date": "2020-01-01 to 2020-12-31",
                "from": "andrew@example.com",
                "to": "student@example.com",
                "source_url": "https://example.com/article",
                "domain": "example.com"
            }
        }

class QueryRequest(BaseModel):
    """Request model for API query endpoint."""
    query: str
    mode: Optional[str] = "combined"
    fuzzy: Optional[bool] = None  # Will be set from config default
    similarity_threshold: Optional[float] = None  # Will be set from config default
    use_reranking: Optional[bool] = None  # Will be set from config default
    top_k: Optional[int] = 10
    weights: Optional[WeightConfig] = None  # Optional weight configuration
    collection_filter: Optional[str] = "all"  # Options: "all", "emails", "documents", "web"
    metadata: Optional[MetadataQuery] = None  # Optional metadata search parameters
    metadata_fuzzy: Optional[bool] = True  # Whether to use fuzzy matching for metadata
    metadata_threshold: Optional[float] = 0.8  # Similarity threshold for metadata matching
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning algorithms",
                "mode": "combined",
                "fuzzy": True,
                "similarity_threshold": 0.5,
                "use_reranking": True,
                "top_k": 10,
                "collection_filter": "all",
                "metadata": {
                    "title": "Machine Learning",
                    "author": "Andrew Ng",
                    "date": "2020-01-01 to 2020-12-31",
                    "from": "andrew@example.com",
                    "domain": "example.com"
                },
                "metadata_fuzzy": True,
                "metadata_threshold": 0.8,
            }
        }

class Document(BaseModel):
    """Document model for API responses."""
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    
    class Config:
        extra = Extra.allow  # Allow extra fields
        json_schema_extra = {
            "example": {
                "id": "doc-123",
                "content": "Sample document content",
                "metadata": {
                    "doc_type": "email",
                    "from": "sender@example.com",
                    "date": "2023-01-01",
                    "subject": "Sample Subject",
                    "url": "https://example.com/doc/123",
                    "source": "email",
                    "search_provider": "Whoosh-Emails",
                    "rerank_score": 0.95,
                    "original_score": 0.85,
                    "weighting": {
                        "collection_weight": 1.0,
                        "recency_score": 0.8,
                        "recency_factor": 1.08,
                        "source_weight": 1.1,
                        "final_score": 0.92
                    },
                    "metadata_matches": {
                        "title": 0.92,
                        "author": 0.85
                    }
                },
                "score": 0.95
            }
        }

class QueryResponse(BaseModel):
    """Response model for API query endpoint."""
    query: str
    results: List[Document]
    weights: Optional[WeightConfig] = None  # Included if weighting was applied
    
    class Config:
        extra = Extra.allow  # Allow extra fields

