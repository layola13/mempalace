#!/usr/bin/env python3
"""
MemPalace MCP Server — read/write palace access for Claude Code
================================================================
Install: claude mcp add mempalace -- python /path/to/mcp_server.py
"""

import hashlib
import json
import logging
import sys
from datetime import datetime

from .config import MempalaceConfig
from .knowledge_graph import KnowledgeGraph
from .palace_graph import find_tunnels, graph_stats, traverse
from .qdrant_store import QdrantClientAdapter, get_store
from .searcher import search_memories

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
logger = logging.getLogger("mempalace_mcp")

_config = MempalaceConfig()
_store = get_store(_config)
_kg = KnowledgeGraph()


PALACE_PROTOCOL = """IMPORTANT — MemPalace Memory Protocol:
1. ON WAKE-UP: Call mempalace_status to load palace overview + AAAK spec.
2. BEFORE RESPONDING about any person, project, or past event: call mempalace_kg_query or mempalace_search FIRST. Never guess — verify.
3. IF UNSURE about a fact (name, gender, age, relationship): say \"let me check\" and query the palace. Wrong is worse than slow.
4. AFTER EACH SESSION: call mempalace_diary_write to record what happened, what you learned, what matters.
5. WHEN FACTS CHANGE: call mempalace_kg_invalidate on the old fact, mempalace_kg_add for the new one.

This protocol ensures the AI KNOWS before it speaks. Storage is not memory — but storage + this protocol = memory."""

AAAK_SPEC = """AAAK is a compressed memory dialect that MemPalace uses for efficient storage.
It is designed to be readable by both humans and LLMs without decoding.

FORMAT:
  ENTITIES: 3-letter uppercase codes. ALC=Alice, JOR=Jordan, RIL=Riley, MAX=Max, BEN=Ben.
  EMOTIONS: *action markers* before/during text. *warm*=joy, *fierce*=determined, *raw*=vulnerable, *bloom*=tenderness.
  STRUCTURE: Pipe-separated fields. FAM: family | PROJ: projects | ⚠: warnings/reminders.
  DATES: ISO format (2026-03-31). COUNTS: Nx = N mentions (e.g., 570x).
  IMPORTANCE: ★ to ★★★★★ (1-5 scale).
  HALLS: hall_facts, hall_events, hall_discoveries, hall_preferences, hall_advice.
  WINGS: wing_user, wing_agent, wing_team, wing_code, wing_myproject, wing_hardware, wing_ue5, wing_ai_research.
  ROOMS: Hyphenated slugs representing named ideas (e.g., chromadb-setup, gpu-pricing).

EXAMPLE:
  FAM: ALC→♡JOR | 2D(kids): RIL(18,sports) MAX(11,chess+swimming) | BEN(contributor)

Read AAAK naturally — expand codes mentally, treat *markers* as emotional context.
When WRITING AAAK: use entity codes, mark emotions, keep structure tight."""


def _get_collection(create: bool = False):
    try:
        client = QdrantClientAdapter(_config)
        return client.get_or_create_collection(_config.collection_name)
    except Exception:
        return None


def _require_collection(create: bool = False):
    col = _get_collection(create=create)
    if not col:
        raise RuntimeError("Palace collection unavailable")
    return col


def _all_metadatas(wing: str = None, room: str = None):
    return [record["metadata"] for record in _store.scroll(wing=wing, room=room, limit=10000)]


def tool_status():
    count = _store.count()
    wings = {}
    rooms = {}
    for m in _all_metadatas():
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        wings[w] = wings.get(w, 0) + 1
        rooms[r] = rooms.get(r, 0) + 1
    return {
        "total_drawers": count,
        "wings": wings,
        "rooms": rooms,
        "palace_path": _config.palace_path,
        "protocol": PALACE_PROTOCOL,
        "aaak_dialect": AAAK_SPEC,
    }


def tool_list_wings():
    wings = {}
    for m in _all_metadatas():
        w = m.get("wing", "unknown")
        wings[w] = wings.get(w, 0) + 1
    return {"wings": wings}


def tool_list_rooms(wing: str = None):
    rooms = {}
    for m in _all_metadatas(wing=wing):
        r = m.get("room", "unknown")
        rooms[r] = rooms.get(r, 0) + 1
    return {"wing": wing or "all", "rooms": rooms}


def tool_get_taxonomy():
    taxonomy = {}
    for m in _all_metadatas():
        w = m.get("wing", "unknown")
        r = m.get("room", "unknown")
        taxonomy.setdefault(w, {})
        taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
    return {"taxonomy": taxonomy}


def tool_search(query: str, limit: int = 5, wing: str = None, room: str = None):
    return search_memories(
        query=query,
        palace_path=_config.palace_path,
        wing=wing,
        room=room,
        n_results=limit,
    )


def tool_check_duplicate(content: str, threshold: float = 0.9):
    results = _store.search(query=content, n_results=5)
    duplicates = []
    for hit in results:
        similarity = round(hit.get("similarity", 0.0), 3)
        if similarity >= threshold:
            meta = hit["metadata"]
            doc = hit["text"]
            duplicates.append(
                {
                    "id": hit["id"],
                    "wing": meta.get("wing", "?"),
                    "room": meta.get("room", "?"),
                    "similarity": similarity,
                    "content": doc[:200] + "..." if len(doc) > 200 else doc,
                }
            )
    return {"is_duplicate": len(duplicates) > 0, "matches": duplicates}


def tool_get_aaak_spec():
    return {"aaak_spec": AAAK_SPEC}


def tool_traverse_graph(start_room: str, max_hops: int = 2):
    col = _require_collection()
    return traverse(start_room, col=col, max_hops=max_hops)


def tool_find_tunnels(wing_a: str = None, wing_b: str = None):
    col = _require_collection()
    return find_tunnels(wing_a, wing_b, col=col)


def tool_graph_stats():
    col = _require_collection()
    return graph_stats(col=col)


def tool_add_drawer(
    wing: str, room: str, content: str, source_file: str = None, added_by: str = "mcp"
):
    col = _require_collection(create=True)

    dup = tool_check_duplicate(content, threshold=0.9)
    if dup.get("is_duplicate"):
        return {"success": False, "reason": "duplicate", "matches": dup["matches"]}

    drawer_id = f"drawer_{wing}_{room}_{hashlib.md5((content[:100] + datetime.now().isoformat()).encode()).hexdigest()[:16]}"
    col.add(
        ids=[drawer_id],
        documents=[content],
        metadatas=[
            {
                "wing": wing,
                "room": room,
                "source_file": source_file or "",
                "chunk_index": 0,
                "added_by": added_by,
                "filed_at": datetime.now().isoformat(),
            }
        ],
    )
    logger.info(f"Filed drawer: {drawer_id} → {wing}/{room}")
    return {"success": True, "drawer_id": drawer_id, "wing": wing, "room": room}


def tool_delete_drawer(drawer_id: str):
    col = _require_collection()
    existing = col.get(ids=[drawer_id])
    if not existing["ids"]:
        return {"success": False, "error": f"Drawer not found: {drawer_id}"}
    col.delete(ids=[drawer_id])
    logger.info(f"Deleted drawer: {drawer_id}")
    return {"success": True, "drawer_id": drawer_id}


def tool_kg_query(entity: str, as_of: str = None, direction: str = "both"):
    results = _kg.query_entity(entity, as_of=as_of, direction=direction)
    return {"entity": entity, "as_of": as_of, "facts": results, "count": len(results)}


def tool_kg_add(
    subject: str, predicate: str, object: str, valid_from: str = None, source_closet: str = None
):
    triple_id = _kg.add_triple(
        subject, predicate, object, valid_from=valid_from, source_closet=source_closet
    )
    return {"success": True, "triple_id": triple_id, "fact": f"{subject} → {predicate} → {object}"}


def tool_kg_invalidate(subject: str, predicate: str, object: str, ended: str = None):
    _kg.invalidate(subject, predicate, object, ended=ended)
    return {
        "success": True,
        "fact": f"{subject} → {predicate} → {object}",
        "ended": ended or "today",
    }


def tool_kg_timeline(entity: str = None):
    results = _kg.timeline(entity)
    return {"entity": entity or "all", "timeline": results, "count": len(results)}


def tool_kg_stats():
    return _kg.stats()


def tool_diary_write(agent_name: str, entry: str, topic: str = "general"):
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    room = "diary"
    col = _require_collection(create=True)

    now = datetime.now()
    entry_id = f"diary_{wing}_{now.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(entry[:50].encode()).hexdigest()[:8]}"
    col.add(
        ids=[entry_id],
        documents=[entry],
        metadatas=[
            {
                "wing": wing,
                "room": room,
                "hall": "hall_diary",
                "topic": topic,
                "type": "diary_entry",
                "agent": agent_name,
                "filed_at": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
            }
        ],
    )
    logger.info(f"Diary entry: {entry_id} → {wing}/diary/{topic}")
    return {
        "success": True,
        "entry_id": entry_id,
        "agent": agent_name,
        "topic": topic,
        "timestamp": now.isoformat(),
    }


def tool_diary_read(agent_name: str, last_n: int = 10):
    wing = f"wing_{agent_name.lower().replace(' ', '_')}"
    col = _require_collection()
    results = col.get(
        where={"$and": [{"wing": wing}, {"room": "diary"}]},
        include=["documents", "metadatas"],
    )

    if not results["ids"]:
        return {"agent": agent_name, "entries": [], "message": "No diary entries yet."}

    entries = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        entries.append(
            {
                "date": meta.get("date", ""),
                "timestamp": meta.get("filed_at", ""),
                "topic": meta.get("topic", ""),
                "content": doc,
            }
        )

    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    entries = entries[:last_n]

    return {
        "agent": agent_name,
        "entries": entries,
        "total": len(results["ids"]),
        "showing": len(entries),
    }


TOOLS = {
    "mempalace_status": {
        "description": "Palace overview — total drawers, wing and room counts",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_status,
    },
    "mempalace_list_wings": {
        "description": "List all wings with drawer counts",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_list_wings,
    },
    "mempalace_list_rooms": {
        "description": "List rooms within a wing (or all rooms if no wing given)",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string", "description": "Wing to list rooms for (optional)"}
            },
        },
        "handler": tool_list_rooms,
    },
    "mempalace_get_taxonomy": {
        "description": "Full taxonomy: wing → room → drawer count",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_taxonomy,
    },
    "mempalace_get_aaak_spec": {
        "description": "Get the AAAK dialect specification.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_get_aaak_spec,
    },
    "mempalace_kg_query": {
        "description": "Query the knowledge graph for an entity's relationships.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity to query"},
                "as_of": {"type": "string", "description": "Date filter (optional)"},
                "direction": {"type": "string", "description": "outgoing, incoming, or both"},
            },
            "required": ["entity"],
        },
        "handler": tool_kg_query,
    },
    "mempalace_kg_add": {
        "description": "Add a fact to the knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "valid_from": {"type": "string"},
                "source_closet": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_add,
    },
    "mempalace_kg_invalidate": {
        "description": "Mark a fact as no longer true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "ended": {"type": "string"},
            },
            "required": ["subject", "predicate", "object"],
        },
        "handler": tool_kg_invalidate,
    },
    "mempalace_kg_timeline": {
        "description": "Chronological timeline of facts.",
        "input_schema": {"type": "object", "properties": {"entity": {"type": "string"}}},
        "handler": tool_kg_timeline,
    },
    "mempalace_kg_stats": {
        "description": "Knowledge graph overview.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_kg_stats,
    },
    "mempalace_traverse": {
        "description": "Walk the palace graph from a room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_room": {"type": "string"},
                "max_hops": {"type": "integer"},
            },
            "required": ["start_room"],
        },
        "handler": tool_traverse_graph,
    },
    "mempalace_find_tunnels": {
        "description": "Find rooms that bridge two wings.",
        "input_schema": {
            "type": "object",
            "properties": {"wing_a": {"type": "string"}, "wing_b": {"type": "string"}},
        },
        "handler": tool_find_tunnels,
    },
    "mempalace_graph_stats": {
        "description": "Palace graph overview.",
        "input_schema": {"type": "object", "properties": {}},
        "handler": tool_graph_stats,
    },
    "mempalace_search": {
        "description": "Semantic search. Returns verbatim drawer content with similarity scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "wing": {"type": "string"},
                "room": {"type": "string"},
            },
            "required": ["query"],
        },
        "handler": tool_search,
    },
    "mempalace_check_duplicate": {
        "description": "Check if content already exists in the palace before filing",
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}, "threshold": {"type": "number"}},
            "required": ["content"],
        },
        "handler": tool_check_duplicate,
    },
    "mempalace_add_drawer": {
        "description": "File verbatim content into the palace. Checks for duplicates first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wing": {"type": "string"},
                "room": {"type": "string"},
                "content": {"type": "string"},
                "source_file": {"type": "string"},
                "added_by": {"type": "string"},
            },
            "required": ["wing", "room", "content"],
        },
        "handler": tool_add_drawer,
    },
    "mempalace_delete_drawer": {
        "description": "Delete a drawer by ID. Irreversible.",
        "input_schema": {
            "type": "object",
            "properties": {"drawer_id": {"type": "string"}},
            "required": ["drawer_id"],
        },
        "handler": tool_delete_drawer,
    },
    "mempalace_diary_write": {
        "description": "Write to your personal agent diary in AAAK format.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "entry": {"type": "string"},
                "topic": {"type": "string"},
            },
            "required": ["agent_name", "entry"],
        },
        "handler": tool_diary_write,
    },
    "mempalace_diary_read": {
        "description": "Read your recent diary entries (in AAAK).",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "last_n": {"type": "integer"},
            },
            "required": ["agent_name"],
        },
        "handler": tool_diary_read,
    },
}


def handle_request(request):
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mempalace", "version": "2.0.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {"name": n, "description": t["description"], "inputSchema": t["input_schema"]}
                    for n, t in TOOLS.items()
                ]
            },
        }
    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        try:
            result = TOOLS[tool_name]["handler"](**tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        except Exception as e:
            logger.error(f"Tool error in {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(e)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    logger.info("MemPalace MCP Server starting...")
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Server error: {e}")


if __name__ == "__main__":
    main()
