# chromadb_core.py

import sys
import torch
from sentence_transformers import SentenceTransformer
from dataclasses import dataclass
from typing import Dict, Any, Optional

import chromadb

@dataclass
class ChromaDBContext:
    """Context for managing ChromaDB connections and collections."""
    client: chromadb.PersistentClient
    collection: chromadb.Collection
    embedding_model: SentenceTransformer


class DBManager:
    """Manager for ChromaDB operations with proper resource handling."""
    
    def __init__(self):
        self.contexts = {}  # Store multiple contexts by collection name
        self.embedding_models = {}  # Cache for embedding models
        self.embedding_functions = {}  # Cache for embedding functions
    
    def load_embedding_model(self, model_name: str) -> SentenceTransformer:
        """Load an embedding model with CUDA if available, caching for reuse."""
        if model_name in self.embedding_models:
            return self.embedding_models[model_name]
        
        # Set device to CUDA if available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading embedding model '{model_name}' on {device}")
        
        # Optimize CUDA settings if available
        if device == "cuda":
            torch.backends.cudnn.benchmark = True  # Optimize for fixed input sizes
        
        try:
            model = SentenceTransformer(model_name, device=device)
            self.embedding_models[model_name] = model
            return model
        except Exception as e:
            sys.stderr.write(f"⚠️ Error loading embedding model: {e}\n")
            raise
    
    def get_embedding_function(self, model_name: str):
        """Get a ChromaDB-compatible embedding function for the model."""
        if model_name in self.embedding_functions:
            return self.embedding_functions[model_name]
        
        # Load the model first with GPU support
        model = self.load_embedding_model(model_name)
        
        # Create a ChromaDB-compatible embedding function with our pre-loaded model
        class CustomEmbeddingFunction:
            def __init__(self, model):
                self._model = model
                # Optimize for larger batches
                self._batch_size = 64  # Adjust based on your GPU
            
            def __call__(self, input):
                # For smaller inputs, process directly
                if len(input) <= self._batch_size:
                    return self._model.encode(input, show_progress_bar=False).tolist()
                
                # For larger inputs, process in batches to optimize GPU usage
                results = []
                for i in range(0, len(input), self._batch_size):
                    batch = input[i:i+self._batch_size]
                    with torch.no_grad():  # Disable gradient calculation for inference
                        embeddings = self._model.encode(batch, show_progress_bar=False).tolist()
                    results.extend(embeddings)
                return results
        
        embedding_function = CustomEmbeddingFunction(model)
        self.embedding_functions[model_name] = embedding_function
        
        return embedding_function
    
    def close(self, collection_name: Optional[str] = None):
        """Close a specific collection or all collections."""
        if collection_name:
            if collection_name in self.contexts:
                # ChromaDB handles connection closing automatically
                del self.contexts[collection_name]
                print(f"Closed collection: {collection_name}")
        else:
            # Close all collections
            self.contexts.clear()
            print("Closed all collections")
    
    def __del__(self):
        """Ensure all resources are properly released."""
        self.contexts.clear()
        self.embedding_models.clear()
        self.embedding_functions.clear()


# Create a singleton instance for global use
db_manager = DBManager()


# Convenience function for external use
def close_collection(collection_name: Optional[str] = None):
    """Close a specific collection or all collections."""
    db_manager.close(collection_name)

