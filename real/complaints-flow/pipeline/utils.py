"""
Utility functions for the pipeline:
- Language detection
- Arabic/English text processing
- Embedding helpers (for guidebook chunking)
"""

import re
from typing import Tuple, List


def is_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    if not text:
        return False
    arabic_pattern = r'[\u0600-\u06FF]'
    return bool(re.search(arabic_pattern, str(text)))


def detect_language(text: str) -> str:
    """
    Detect language of text.

    Returns: 'ar', 'en', or 'mixed'
    """
    if not text:
        return 'unknown'

    text_str = str(text)
    arabic_count = len(re.findall(r'[\u0600-\u06FF]', text_str))
    english_count = len(re.findall(r'[a-zA-Z]', text_str))

    if arabic_count > 0 and english_count == 0:
        return 'ar'
    elif english_count > 0 and arabic_count == 0:
        return 'en'
    elif arabic_count > 0 and english_count > 0:
        return 'mixed'
    else:
        return 'unknown'


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for comparison (remove diacritics, extra spaces)."""
    if not text:
        return ""

    # Remove diacritics
    text = re.sub(r'[\u064B-\u065F]', '', text)
    # Normalize alef variants
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    # Remove leading/trailing spaces
    text = text.strip()

    return text.lower()


def extract_arabic_words(text: str) -> List[str]:
    """Extract Arabic words from text."""
    if not text:
        return []
    # Match sequences of Arabic characters
    pattern = r'[\u0600-\u06FF]+'
    return re.findall(pattern, str(text))


def extract_english_words(text: str) -> List[str]:
    """Extract English words from text."""
    if not text:
        return []
    # Match word boundaries for English
    pattern = r'\b[a-zA-Z]+\b'
    return re.findall(pattern, str(text), re.IGNORECASE)


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """
    Chunk text for embedding (guidebook PDF chunks).

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
        # Find chunk end
        end = min(start + chunk_size, len(text))

        # Try to break at a sentence boundary if not at end
        if end < len(text):
            # Look for last period, question mark, or exclamation within chunk
            search_end = max(start + chunk_size - 100, start)
            last_boundary = max(
                text.rfind('.', start, end),
                text.rfind('؟', start, end),
                text.rfind('!', start, end),
            )
            if last_boundary > search_end:
                end = last_boundary + 1

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c]  # Filter out empty chunks


def extract_numbers(text: str) -> List[str]:
    """Extract numbers from text."""
    if not text:
        return []
    return re.findall(r'\d+(?:[.,]\d+)?', str(text))


def format_arabic_number(num: int) -> str:
    """Format number with Arabic numerals if needed."""
    # For now, just return string of number
    # Can be extended to use Arabic-Indic numerals if needed
    return str(num)


def arabic_case_count(n) -> str:
    """Return grammatically correct Arabic count string for 'case(s)'.

    Arabic rules:
      n == 0          → "لا حالات"
      n == 1          → "حالة واحدة"
      2 <= n <= 10    → "{n} حالات"   (plural)
      n > 10          → "{n} حالة"    (singular — Arabic grammar for 11+)
      n is "4+" etc.  → "{n} حالات"   (treat as plural)
    """
    if isinstance(n, str) and '+' in n:
        return f"{n} حالات"
    try:
        n = int(n)
    except (ValueError, TypeError):
        return f"{n} حالة"
    if n == 0:
        return "لا حالات"
    if n == 1:
        return "حالة واحدة"
    if 2 <= n <= 10:
        return f"{n} حالات"
    return f"{n} حالة"


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Simple similarity metric using word overlap.
    For production, use proper embeddings with chromadb.

    Returns: Float between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0

    words1 = set(normalize_arabic(text1).split())
    words2 = set(normalize_arabic(text2).split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0
