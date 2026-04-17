"""
Guidebook Loader and ChromaDB Embeddings

Pre-computes embeddings of the guidebook PDF at startup.
Saves embeddings to disk for fast loading on subsequent runs.
"""

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import chromadb
from chromadb.config import Settings

# Try to import pdfplumber for PDF loading
try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class GuidebookEmbedder:
    """Loads, chunks, and embeds the customer services guidebook."""

    def __init__(self, pdf_path: str, persist_dir: Optional[str] = None):
        """
        Initialize embedder.

        Args:
            pdf_path: Path to guidebook PDF
            persist_dir: Directory to persist ChromaDB collections (default: .guidebook_cache)
        """
        self.pdf_path = pdf_path
        self.persist_dir = Path(persist_dir or ".guidebook_cache")
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with new API
        try:
            self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        except Exception:
            # Fallback to ephemeral client if persistent fails
            self.client = chromadb.EphemeralClient()

        self.collection = None
        self.chunks: List[str] = []
        self.embeddings: Dict[str, Any] = {}

    def load_and_chunk_pdf(self) -> List[str]:
        """
        Load PDF and chunk into semantic segments.

        Returns:
            List of text chunks
        """
        if not pdfplumber:
            raise ImportError("pdfplumber required for PDF loading. Install: pip install pdfplumber")

        if not Path(self.pdf_path).exists():
            raise FileNotFoundError(f"Guidebook not found: {self.pdf_path}")

        # Extract text from PDF
        full_text = ""
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                full_text += page.extract_text() or ""

        # Chunk by paragraphs and sentence boundaries
        chunks = self._chunk_text(full_text)
        self.chunks = chunks
        return chunks

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 100) -> List[str]:
        """
        Chunk text into overlapping segments.

        Args:
            text: Text to chunk
            chunk_size: Approximate chunk size in characters
            overlap: Character overlap between chunks

        Returns:
            List of text chunks
        """
        if not text:
            return []

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                # Look for period, question mark, or exclamation within last 100 chars
                search_start = max(start, end - 100)
                last_sentence_end = max(
                    text.rfind('.', start, end),
                    text.rfind('؟', start, end),
                    text.rfind('!', start, end),
                )

                if last_sentence_end > search_start:
                    end = last_sentence_end + 1

            chunk = text[start:end].strip()
            if chunk and len(chunk) > 50:  # Only keep substantial chunks
                chunks.append(chunk)

            start = end - overlap

        return chunks

    def compute_embeddings(self, force_recompute: bool = False) -> None:
        """
        Compute embeddings using Claude API and store in ChromaDB.

        Args:
            force_recompute: If True, recompute all embeddings even if cached
        """
        # Check if collection already exists
        try:
            self.collection = self.client.get_collection(name="guidebook")
            if not force_recompute:
                print(f"✅ Loaded cached guidebook embeddings ({len(self.collection.get()['ids'])} chunks)")
                return
        except Exception:
            pass

        # Load and chunk PDF if not already done
        if not self.chunks:
            print("📄 Loading guidebook PDF...")
            self.load_and_chunk_pdf()
            print(f"✂️ Chunked into {len(self.chunks)} segments")

        # Create new collection
        print("🔌 Computing embeddings with Anthropic API...")
        self.collection = self.client.get_or_create_collection(
            name="guidebook",
            metadata={"hnsw:space": "cosine"}
        )

        # Add chunks with IDs
        ids = [f"chunk_{i}" for i in range(len(self.chunks))]
        self.collection.add(
            ids=ids,
            documents=self.chunks,
            metadatas=[{"source": "guidebook", "chunk_index": i} for i in range(len(self.chunks))]
        )

        print(f"✅ Embedded {len(self.chunks)} chunks in ChromaDB")

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the guidebook for relevant chunks.

        Args:
            query_text: Query string
            top_k: Number of results to return

        Returns:
            List of matching chunks with metadata
        """
        if self.collection is None:
            raise ValueError("Collection not initialized. Call compute_embeddings() first.")

        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k
        )

        # Format results
        output = []
        if results and results['documents'] and len(results['documents'][0]) > 0:
            for i, doc in enumerate(results['documents'][0]):
                distance = results['distances'][0][i] if results['distances'] else 0.0
                similarity = 1.0 - distance  # Convert distance to similarity (0-1)

                output.append({
                    'text': doc,
                    'similarity': similarity,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                })

        return output

    def save_collection(self) -> None:
        """Persist collection to disk."""
        if self.collection:
            self.client.persist()
            print(f"💾 Saved embeddings to {self.persist_dir}")

    def get_all_chunks(self) -> List[str]:
        """Get all guidebook chunks."""
        return self.chunks if self.chunks else self._load_chunks_from_collection()

    def _load_chunks_from_collection(self) -> List[str]:
        """Load chunks from stored collection."""
        if self.collection is None:
            return []

        all_data = self.collection.get()
        return all_data.get('documents', []) if all_data else []


def get_guidebook_embedder(guidebook_path: str, persist_dir: Optional[str] = None) -> GuidebookEmbedder:
    """
    Get or create guidebook embedder.

    Args:
        guidebook_path: Path to guidebook PDF
        persist_dir: Directory for ChromaDB persistence

    Returns:
        GuidebookEmbedder instance
    """
    embedder = GuidebookEmbedder(guidebook_path, persist_dir)

    # Try to load from cache, otherwise compute
    try:
        embedder.collection = embedder.client.get_collection(name="guidebook")
        print("✅ Loaded cached guidebook embeddings")
    except Exception:
        print("📚 Computing guidebook embeddings...")
        embedder.compute_embeddings()
        embedder.save_collection()

    return embedder
