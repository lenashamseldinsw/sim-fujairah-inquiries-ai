#!/usr/bin/env python3
"""
Quick test of guidebook embedder.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    print("1. Testing imports...")
    from pipeline.guidebook import GuidebookEmbedder
    print("   ✓ GuidebookEmbedder imported")

    print("\n2. Checking PDF file...")
    guidebook_path = Path("inquiries-flow/inquiries-supporting-files/customer_services_guidebook.pdf")
    if guidebook_path.exists():
        print(f"   ✓ PDF exists: {guidebook_path}")
        print(f"   Size: {guidebook_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print(f"   ✗ PDF not found: {guidebook_path}")
        sys.exit(1)

    print("\n3. Initializing embedder...")
    embedder = GuidebookEmbedder(str(guidebook_path), persist_dir=".guidebook_cache")
    print("   ✓ Embedder initialized")

    print("\n4. Loading PDF and chunking...")
    chunks = embedder.load_and_chunk_pdf()
    print(f"   ✓ PDF loaded: {len(chunks)} chunks created")
    print(f"   First chunk ({len(chunks[0])} chars): {chunks[0][:100]}...")

    print("\n5. Computing embeddings (this may take 1-2 minutes)...")
    embedder.compute_embeddings()
    print(f"   ✓ Embeddings computed")

    print("\n6. Testing semantic search...")
    results = embedder.query("كيفية التقديم على الخدمة", top_k=2)
    print(f"   ✓ Query returned {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"   Result {i} (similarity: {result['similarity']:.2f})")
        print(f"      {result['text'][:80]}...")

    print("\n✅ All tests passed!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
