#!/usr/bin/env python3
"""
layers.py — 4-Layer Memory Stack for mempalace
===================================================

Load only what you need, when you need it.
"""

import os
from pathlib import Path
from collections import defaultdict

from .config import MempalaceConfig
from .qdrant_store import get_store


class Layer0:
    def __init__(self, identity_path: str = None):
        if identity_path is None:
            identity_path = os.path.expanduser("~/.mempalace/identity.txt")
        self.path = identity_path
        self._text = None

    def render(self) -> str:
        if self._text is not None:
            return self._text

        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self._text = f.read().strip()
        else:
            self._text = "## L0 — IDENTITY\nNo identity configured. Create ~/.mempalace/identity.txt"
        return self._text

    def token_estimate(self) -> int:
        return len(self.render()) // 4


class Layer1:
    MAX_DRAWERS = 15
    MAX_CHARS = 3200

    def __init__(self, palace_path: str = None, wing: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.wing = wing

    def generate(self) -> str:
        try:
            store = get_store()
            records = store.scroll(wing=self.wing, limit=1000)
        except Exception:
            return "## L1 — No palace found. Run: mempalace mine <dir>"

        if not records:
            return "## L1 — No memories yet."

        scored = []
        for record in records:
            meta = record["metadata"]
            importance = 3
            for key in ("importance", "emotional_weight", "weight"):
                val = meta.get(key)
                if val is not None:
                    try:
                        importance = float(val)
                    except (ValueError, TypeError):
                        pass
                    break
            scored.append((importance, meta, record["text"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_DRAWERS]

        by_room = defaultdict(list)
        for imp, meta, doc in top:
            by_room[meta.get("room", "general")].append((imp, meta, doc))

        lines = ["## L1 — ESSENTIAL STORY"]
        total_len = 0
        for room, entries in sorted(by_room.items()):
            room_line = f"\n[{room}]"
            lines.append(room_line)
            total_len += len(room_line)

            for imp, meta, doc in entries:
                source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
                snippet = doc.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                entry_line = f"  - {snippet}"
                if source:
                    entry_line += f"  ({source})"
                if total_len + len(entry_line) > self.MAX_CHARS:
                    lines.append("  ... (more in L3 search)")
                    return "\n".join(lines)
                lines.append(entry_line)
                total_len += len(entry_line)

        return "\n".join(lines)


class Layer2:
    def __init__(self, palace_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path

    def retrieve(self, wing: str = None, room: str = None, n_results: int = 10) -> str:
        try:
            store = get_store()
            records = store.scroll(wing=wing, room=room, limit=n_results)
        except Exception as e:
            return f"Retrieval error: {e}"

        if not records:
            label = f"wing={wing}" if wing else ""
            if room:
                label += f" room={room}" if label else f"room={room}"
            return f"No drawers found for {label}."

        lines = [f"## L2 — ON-DEMAND ({len(records)} drawers)"]
        for record in records[:n_results]:
            meta = record["metadata"]
            snippet = record["text"].strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            entry = f"  [{meta.get('room', '?')}] {snippet}"
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
            if source:
                entry += f"  ({source})"
            lines.append(entry)
        return "\n".join(lines)


class Layer3:
    def __init__(self, palace_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path

    def search(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> str:
        try:
            hits = get_store().search(query=query, wing=wing, room=room, n_results=n_results)
        except Exception as e:
            return f"Search error: {e}"

        if not hits:
            return "No results found."

        lines = [f'## L3 — SEARCH RESULTS for "{query}"']
        for i, hit in enumerate(hits, 1):
            meta = hit["metadata"]
            snippet = hit["text"].strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            lines.append(
                f"  [{i}] {meta.get('wing', '?')}/{meta.get('room', '?')} (sim={hit.get('similarity', 0.0)})"
            )
            lines.append(f"      {snippet}")
            source = Path(meta.get("source_file", "")).name if meta.get("source_file") else ""
            if source:
                lines.append(f"      src: {source}")
        return "\n".join(lines)

    def search_raw(self, query: str, wing: str = None, room: str = None, n_results: int = 5) -> list:
        try:
            hits = get_store().search(query=query, wing=wing, room=room, n_results=n_results)
        except Exception:
            return []

        return [
            {
                "text": hit["text"],
                "wing": hit["metadata"].get("wing", "unknown"),
                "room": hit["metadata"].get("room", "unknown"),
                "source_file": Path(hit["metadata"].get("source_file", "?")).name,
                "similarity": hit.get("similarity", 0.0),
                "metadata": hit["metadata"],
            }
            for hit in hits
        ]


class MemoryStack:
    def __init__(self, palace_path: str = None, identity_path: str = None):
        cfg = MempalaceConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.identity_path = identity_path or os.path.expanduser("~/.mempalace/identity.txt")

        self.l0 = Layer0(self.identity_path)
        self.l1 = Layer1(self.palace_path)
        self.l2 = Layer2(self.palace_path)
        self.l3 = Layer3(self.palace_path)

    def wake_up(self, wing: str = None) -> str:
        parts = [self.l0.render(), ""]
        if wing:
            self.l1.wing = wing
        parts.append(self.l1.generate())
        return "\n".join(parts)
