"""
palace_graph.py — Graph traversal layer for MemPalace
======================================================
"""

from collections import defaultdict, Counter

from .config import MempalaceConfig
from .qdrant_store import get_store


class _StoreCollectionAdapter:
    def __init__(self, store):
        self.store = store

    def count(self):
        return self.store.count()

    def get(self, limit=1000, offset=0, include=None, where=None):
        include = include or []
        wing = where.get("wing") if where else None
        room = where.get("room") if where else None
        records = self.store.scroll(wing=wing, room=room, limit=limit + offset)
        if offset:
            records = records[offset:]
        records = records[:limit]
        return {
            "ids": [record["id"] for record in records],
            "documents": [record["text"] for record in records] if "documents" in include else [],
            "metadatas": [record["metadata"] for record in records] if "metadatas" in include else [],
        }


def _get_collection(config=None):
    try:
        return _StoreCollectionAdapter(get_store(config or MempalaceConfig()))
    except Exception:
        return None


def build_graph(col=None, config=None):
    if col is None:
        col = _get_collection(config)
    if not col:
        return {}, []

    total = col.count()
    room_data = defaultdict(lambda: {"wings": set(), "halls": set(), "count": 0, "dates": set()})

    offset = 0
    while offset < total:
        batch = col.get(limit=1000, offset=offset, include=["metadatas"])
        for meta in batch["metadatas"]:
            room = meta.get("room", "")
            wing = meta.get("wing", "")
            hall = meta.get("hall", "")
            date = meta.get("date", "")
            if room and room != "general" and wing:
                room_data[room]["wings"].add(wing)
                if hall:
                    room_data[room]["halls"].add(hall)
                if date:
                    room_data[room]["dates"].add(date)
                room_data[room]["count"] += 1
        if not batch["ids"]:
            break
        offset += len(batch["ids"])

    edges = []
    for room, data in room_data.items():
        wings = sorted(data["wings"])
        if len(wings) >= 2:
            for i, wa in enumerate(wings):
                for wb in wings[i + 1 :]:
                    halls = data["halls"] or {""}
                    for hall in halls:
                        edges.append(
                            {
                                "room": room,
                                "wing_a": wa,
                                "wing_b": wb,
                                "hall": hall,
                                "count": data["count"],
                            }
                        )

    nodes = {}
    for room, data in room_data.items():
        nodes[room] = {
            "wings": sorted(data["wings"]),
            "halls": sorted(data["halls"]),
            "count": data["count"],
            "dates": sorted(data["dates"])[-5:] if data["dates"] else [],
        }

    return nodes, edges


def traverse(start_room: str, col=None, config=None, max_hops: int = 2):
    nodes, edges = build_graph(col, config)

    if start_room not in nodes:
        return {"error": f"Room '{start_room}' not found", "suggestions": _fuzzy_match(start_room, nodes)}

    start = nodes[start_room]
    visited = {start_room}
    results = [
        {
            "room": start_room,
            "wings": start["wings"],
            "halls": start["halls"],
            "count": start["count"],
            "hop": 0,
        }
    ]

    frontier = [(start_room, 0)]
    while frontier:
        current_room, depth = frontier.pop(0)
        if depth >= max_hops:
            continue

        current = nodes.get(current_room, {})
        current_wings = set(current.get("wings", []))

        for room, data in nodes.items():
            if room in visited:
                continue
            shared_wings = current_wings & set(data["wings"])
            if shared_wings:
                visited.add(room)
                results.append(
                    {
                        "room": room,
                        "wings": data["wings"],
                        "halls": data["halls"],
                        "count": data["count"],
                        "hop": depth + 1,
                        "connected_via": sorted(shared_wings),
                    }
                )
                if depth + 1 < max_hops:
                    frontier.append((room, depth + 1))

    results.sort(key=lambda x: (x["hop"], -x["count"]))
    return results[:50]


def find_tunnels(wing_a: str = None, wing_b: str = None, col=None, config=None):
    nodes, edges = build_graph(col, config)

    tunnels = []
    for room, data in nodes.items():
        wings = data["wings"]
        if len(wings) < 2:
            continue
        if wing_a and wing_a not in wings:
            continue
        if wing_b and wing_b not in wings:
            continue
        tunnels.append(
            {
                "room": room,
                "wings": wings,
                "halls": data["halls"],
                "count": data["count"],
                "recent": data["dates"][-1] if data["dates"] else "",
            }
        )

    tunnels.sort(key=lambda x: -x["count"])
    return tunnels[:50]


def graph_stats(col=None, config=None):
    nodes, edges = build_graph(col, config)

    tunnel_rooms = sum(1 for n in nodes.values() if len(n["wings"]) >= 2)
    wing_counts = Counter()
    for data in nodes.values():
        for w in data["wings"]:
            wing_counts[w] += 1

    return {
        "total_rooms": len(nodes),
        "tunnel_rooms": tunnel_rooms,
        "total_edges": len(edges),
        "rooms_per_wing": dict(wing_counts.most_common()),
        "top_tunnels": [
            {"room": r, "wings": d["wings"], "count": d["count"]}
            for r, d in sorted(nodes.items(), key=lambda x: -len(x[1]["wings"]))[:10]
            if len(d["wings"]) >= 2
        ],
    }


def _fuzzy_match(query: str, nodes: dict, n: int = 5):
    query_lower = query.lower()
    scored = []
    for room in nodes:
        if query_lower in room:
            scored.append((room, 1.0))
        elif any(word in room for word in query_lower.split("-")):
            scored.append((room, 0.5))
    scored.sort(key=lambda x: -x[1])
    return [r for r, _ in scored[:n]]
