#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the palace.
Returns verbatim text — the actual words, never summaries.
"""

import sys
from pathlib import Path

from .qdrant_store import get_store


def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):
    """
    Search the palace. Returns verbatim drawer content.
    Optionally filter by wing (project) or room (aspect).
    """
    results = search_memories(
        query=query,
        palace_path=palace_path,
        wing=wing,
        room=room,
        n_results=n_results,
    )
    if results.get("error"):
        print(f"\n  {results['error']}")
        sys.exit(1)

    hits = results["results"]
    if not hits:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(hits, 1):
        source = Path(hit.get("source_file", "?")).name
        print(f"  [{i}] {hit.get('wing', '?')} / {hit.get('room', '?')}")
        print(f"      Source: {source}")
        print(f"      Match:  {hit.get('similarity', 0.0)}")
        print()
        for line in hit.get("text", "").strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5
) -> dict:
    """
    Programmatic search — returns a dict instead of printing.
    Used by the MCP server and other callers that need data.
    """
    try:
        store = get_store()
        hits = store.search(query=query, wing=wing, room=room, n_results=n_results)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    return {
        "query": query,
        "filters": {"wing": wing, "room": room, "palace_path": palace_path},
        "results": [
            {
                "text": hit["text"],
                "wing": hit["metadata"].get("wing", "unknown"),
                "room": hit["metadata"].get("room", "unknown"),
                "source_file": Path(hit["metadata"].get("source_file", "?")).name,
                "similarity": hit.get("similarity", 0.0),
                "drawer_id": hit["id"],
            }
            for hit in hits
        ],
    }
