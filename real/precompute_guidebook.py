#!/usr/bin/env python3
"""
Pre-compute guidebook embeddings.

Run this once to:
1. Load the guidebook PDF
2. Compute ChromaDB embeddings
3. Save to .guidebook_cache directory

Then commit .guidebook_cache to repo so it loads instantly at runtime.
"""

import sys
from pathlib import Path

# Add real folder to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.guidebook import get_guidebook_embedder


def main():
    """Pre-compute guidebook embeddings."""
    guidebook_path = Path("inquiries-flow/inquiries-supporting-files/customer_services_guidebook.pdf")

    if not guidebook_path.exists():
        print(f"❌ Guidebook not found: {guidebook_path}")
        print(f"   Expected at: {guidebook_path.absolute()}")
        return False

    print(f"📚 Pre-computing guidebook embeddings...")
    print(f"   Input: {guidebook_path}")
    print(f"   Output: .guidebook_cache/")

    try:
        embedder = get_guidebook_embedder(
            str(guidebook_path),
            persist_dir=".guidebook_cache"
        )

        # Test the embedder
        print("\n✅ Embeddings computed successfully!")
        print(f"   Total chunks: {len(embedder.get_all_chunks())}")

        # Test a query
        print("\n🔍 Testing query capability...")
        results = embedder.query("كيفية التقديم على الخدمة", top_k=3)
        print(f"   Sample query returned {len(results)} results")
        for i, result in enumerate(results, 1):
            print(f"   {i}. Similarity: {result['similarity']:.2f}")
            print(f"      {result['text'][:100]}...")

        print("\n💾 Next steps:")
        print("   1. Commit .guidebook_cache/ to your repository")
        print("   2. At runtime, the embeddings will load instantly from disk")
        print("   3. No need to re-ingest the PDF on every pipeline run")

        return True

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
