# scripts/verify_ingestion.py
"""
Manual smoke test for the ingestion pipeline — no DB, no Celery, just the
raw stages run against a real YouTube URL and your real LLM endpoint.

Usage:
    uv run python scripts/verify_ingestion.py "https://www.youtube.com/watch?v=VIDEO_ID"
"""

import sys

from app.ingestion.analysis import analyze_transcript
from app.ingestion.chunking import chunk_transcript
from app.ingestion.embeddings import embed_chunks
from app.ingestion.youtube import get_transcript


def main(url: str):
    print(f"--- Fetching transcript for {url} ---")
    snippets = get_transcript(url)
    print(f"Got {len(snippets)} snippets")
    print(f"First snippet: {snippets[0]}")
    print(f"Last snippet:  {snippets[-1]}")

    full_text = " ".join(s["text"] for s in snippets)
    print(f"\nTotal transcript length: {len(full_text)} chars")

    print("\n--- Chunking ---")
    chunks = chunk_transcript(snippets)
    print(f"Produced {len(chunks)} chunks")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\nChunk {i}:")
        print(f"  start={chunk['start_timestamp']}  end={chunk['end_timestamp']}")
        print(f"  text: {chunk['text'][:150]}...")
    if len(chunks) > 3:
        print(f"\n... ({len(chunks) - 3} more chunks not shown)")

    print("\n--- Analysis (real LLM call) ---")
    analysis = analyze_transcript(full_text)
    print(f"\nSummary:\n  {analysis.summary}")
    print(f"\nKey teachings ({len(analysis.key_teachings)}):")
    for t in analysis.key_teachings:
        print(f"  - {t}")
    print(f"\nThemes: {analysis.themes}")
    print(f"\nBible references: {analysis.bible_references}")
    print(f"\nAction points ({len(analysis.action_points)}):")
    for a in analysis.action_points:
        print(f"  - {a}")
    print(f"\nReflection questions ({len(analysis.reflection_questions)}):")
    for q in analysis.reflection_questions:
        print(f"  - {q}")

    print("\n--- Embeddings (real LLM call) ---")
    embeddings = embed_chunks([c["text"] for c in chunks])
    print(f"Produced {len(embeddings)} embeddings")
    print(f"Dimension of first embedding: {len(embeddings[0])}")
    print(f"First 5 values: {embeddings[0][:5]}")

    print("\n--- Done. Pipeline ran end-to-end. ---")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/verify_ingestion.py <youtube_url>")
        sys.exit(1)
    main(sys.argv[1])
