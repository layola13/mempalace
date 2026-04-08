from __future__ import annotations

import ast
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .conversation_skeleton import _extract_tokens, index_output_path, skeleton_output_path

_MODULE_CACHE: dict[tuple[str, int, int], ast.Module | None] = {}
_LITERAL_CACHE: dict[tuple[str, int, int, str], object] = {}
_CONSTRUCTOR_LIST_CACHE: dict[tuple[str, int, int, str], List[dict]] = {}
_SNAPSHOT_RECORD_CACHE: dict[tuple[str, str], List[dict]] = {}
_ALL_RECORDS_CACHE: dict[tuple[str, tuple[str, ...]], List[dict]] = {}
_GRAPH_COUNTS_CACHE: dict[tuple[str, str], dict] = {}


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _path_cache_key(file_path: Path) -> tuple[str, int, int] | None:
    try:
        stat = file_path.stat()
    except FileNotFoundError:
        return None
    return (str(file_path), stat.st_mtime_ns, stat.st_size)


def _parse_module(file_path: Path) -> ast.Module | None:
    cache_key = _path_cache_key(file_path)
    if cache_key is None:
        return None
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]
    try:
        parsed = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        parsed = None
    _MODULE_CACHE[cache_key] = parsed
    return parsed


def _read_literal_assignment(file_path: Path, name: str, fallback):
    path_key = _path_cache_key(file_path)
    if path_key is None:
        return fallback
    cache_key = (*path_key, name)
    if cache_key in _LITERAL_CACHE:
        return _LITERAL_CACHE[cache_key]
    module = _parse_module(file_path)
    if module is None:
        return fallback
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    return fallback
                _LITERAL_CACHE[cache_key] = value
                return value
    return fallback


def _read_constructor_list(file_path: Path, name: str) -> List[dict]:
    path_key = _path_cache_key(file_path)
    if path_key is None:
        return []
    cache_key = (*path_key, name)
    if cache_key in _CONSTRUCTOR_LIST_CACHE:
        return list(_CONSTRUCTOR_LIST_CACHE[cache_key])
    module = _parse_module(file_path)
    if module is None:
        return []
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != name:
                continue
            if not isinstance(node.value, ast.List):
                return []
            items = []
            for element in node.value.elts:
                if not isinstance(element, ast.Call):
                    continue
                payload = {}
                for keyword in element.keywords:
                    try:
                        payload[keyword.arg] = ast.literal_eval(keyword.value)
                    except (ValueError, SyntaxError):
                        payload = {}
                        break
                if payload:
                    items.append(payload)
            _CONSTRUCTOR_LIST_CACHE[cache_key] = list(items)
            return items
    return []


def _snapshot_dir(workspace_root: str, snapshot: str) -> Path:
    return skeleton_output_path(workspace_root) / snapshot


def _index_path(workspace_root: str) -> Path:
    return index_output_path(workspace_root)


def _load_index_summary(workspace_root: str) -> dict:
    index_path = _index_path(workspace_root)
    if not index_path.exists():
        return {
            "exists": False,
            "index_path": str(index_path),
            "snapshots": [],
            "snapshot_summaries": [],
            "global_top_topics": [],
            "global_top_files": [],
            "global_task_topics": [],
            "latest_snapshot": None,
            "snapshot_count": 0,
            "total_memory_count": 0,
            "index_text": "",
        }
    return {
        "exists": True,
        "index_path": str(index_path),
        "snapshots": _read_literal_assignment(index_path, "SNAPSHOTS", []),
        "snapshot_summaries": _read_literal_assignment(index_path, "SNAPSHOT_SUMMARIES", []),
        "global_top_topics": _read_literal_assignment(index_path, "GLOBAL_TOP_TOPICS", []),
        "global_top_files": _read_literal_assignment(index_path, "GLOBAL_TOP_FILES", []),
        "global_task_topics": _read_literal_assignment(index_path, "GLOBAL_TASK_TOPICS", []),
        "latest_snapshot": _read_literal_assignment(index_path, "LATEST_SNAPSHOT", None),
        "snapshot_count": _read_literal_assignment(index_path, "SNAPSHOT_COUNT", 0),
        "total_memory_count": _read_literal_assignment(index_path, "TOTAL_MEMORY_COUNT", 0),
        "index_text": index_path.read_text(encoding="utf-8"),
    }


def load_index(workspace_root: str) -> dict:
    start = time.perf_counter()
    result = _load_index_summary(workspace_root)
    result.update({"backend": "skeleton", "elapsed_ms": _elapsed_ms(start)})
    return result


def list_snapshots(workspace_root: str) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    return {
        "backend": "skeleton",
        "snapshots": list(index_data["snapshots"]),
        "latest_snapshot": index_data["latest_snapshot"],
        "elapsed_ms": _elapsed_ms(start),
    }


def summary_for_snapshot(workspace_root: str, snapshot: str) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    for summary in index_data["snapshot_summaries"]:
        if summary.get("name") == snapshot:
            return {
                "backend": "skeleton",
                "summary": dict(summary),
                "elapsed_ms": _elapsed_ms(start),
            }
    return {
        "backend": "skeleton",
        "error": f"Snapshot not found: {snapshot}",
        "snapshot": snapshot,
        "elapsed_ms": _elapsed_ms(start),
    }


def read_snapshot_module(workspace_root: str, snapshot: str, module: str) -> dict:
    start = time.perf_counter()
    allowed_modules = {"__init__", "summary", "nodes", "topics", "files", "patterns", "edges"}
    if module not in allowed_modules:
        return {
            "backend": "skeleton",
            "success": False,
            "error": f"Unsupported module: {module}",
            "allowed_modules": sorted(allowed_modules),
            "elapsed_ms": _elapsed_ms(start),
        }

    snapshot_dir = _snapshot_dir(workspace_root, snapshot)
    file_name = "__init__.py" if module == "__init__" else f"{module}.py"
    file_path = snapshot_dir / file_name
    if not file_path.exists():
        return {
            "backend": "skeleton",
            "success": False,
            "error": f"Module file not found: {file_name}",
            "snapshot": snapshot,
            "module": module,
            "file_path": str(file_path),
            "elapsed_ms": _elapsed_ms(start),
        }
    return {
        "backend": "skeleton",
        "success": True,
        "snapshot": snapshot,
        "module": module,
        "file_path": str(file_path),
        "content": file_path.read_text(encoding="utf-8"),
        "elapsed_ms": _elapsed_ms(start),
    }


def _parse_nodes(snapshot_dir: Path) -> List[dict]:
    return _read_constructor_list(snapshot_dir / "nodes.py", "NODES")


def _parse_topic_clusters(snapshot_dir: Path) -> List[dict]:
    return _read_constructor_list(snapshot_dir / "topics.py", "TOPIC_CLUSTERS")


def _parse_file_references(snapshot_dir: Path) -> List[dict]:
    return _read_constructor_list(snapshot_dir / "files.py", "FILE_REFERENCES")


def _parse_hard_edges(snapshot_dir: Path) -> List[dict]:
    edges_path = snapshot_dir / "edges.py"
    hard_edges = _read_literal_assignment(edges_path, "hard_edges", None)
    if hard_edges is not None:
        return hard_edges
    return _read_literal_assignment(edges_path, "    hard_edges", [])


def _snapshot_records(workspace_root: str, snapshot: str) -> List[dict]:
    cache_key = (workspace_root, snapshot)
    if cache_key in _SNAPSHOT_RECORD_CACHE:
        return list(_SNAPSHOT_RECORD_CACHE[cache_key])
    summary = summary_for_snapshot(workspace_root, snapshot)
    if summary.get("error"):
        return []
    summary_data = summary.get("summary", {})
    task_description = str(summary_data.get("task_description", ""))
    task_topics = list(summary_data.get("task_topics", []))
    snapshot_dir = _snapshot_dir(workspace_root, snapshot)
    nodes = _parse_nodes(snapshot_dir)
    records = []
    for node in nodes:
        records.append(
            {
                "snapshot": snapshot,
                "index": node.get("index"),
                "memory_type": node.get("memory_type", "general"),
                "preview": node.get("preview", ""),
                "topics": list(node.get("topics", [])),
                "files": list(node.get("files", [])),
                "task_description": task_description,
                "task_topics": task_topics,
                "wing": "conversation-skeleton",
                "room": f"nodes:{node.get('memory_type', 'general')}",
                "source_file": f"{snapshot}/nodes.py",
                "drawer_id": f"{snapshot}:{node.get('index')}",
            }
        )
    _SNAPSHOT_RECORD_CACHE[cache_key] = list(records)
    return records


def _all_records(workspace_root: str) -> List[dict]:
    index_data = _load_index_summary(workspace_root)
    snapshots = tuple(index_data["snapshots"])
    cache_key = (workspace_root, snapshots)
    if cache_key in _ALL_RECORDS_CACHE:
        return list(_ALL_RECORDS_CACHE[cache_key])
    records: List[dict] = []
    for snapshot in snapshots:
        records.extend(_snapshot_records(workspace_root, snapshot))
    _ALL_RECORDS_CACHE[cache_key] = list(records)
    return records


def _record_score(record: dict, query: str) -> dict:
    query_lower = query.lower()
    query_tokens = set(_extract_tokens(query))
    preview = str(record.get("preview", "")).lower()
    topics = [str(item).lower() for item in record.get("topics", [])]
    files = [str(item).lower() for item in record.get("files", [])]
    task_description = str(record.get("task_description", "")).lower()
    task_topics = [str(item).lower() for item in record.get("task_topics", [])]

    preview_hit = 1 if query_lower in preview else 0
    task_description_hit = 1 if query_lower in task_description else 0
    topic_hits = sum(1 for topic in topics if query_lower in topic)
    task_topic_hits = sum(1 for topic in task_topics if query_lower in topic)
    file_hits = sum(1 for path in files if query_lower in path)
    exact_type_hit = 1 if query_lower == str(record.get("memory_type", "")).lower() else 0

    preview_tokens = set(_extract_tokens(preview))
    task_description_tokens = set(_extract_tokens(task_description))
    topic_token_overlap = len(query_tokens.intersection(topics))
    task_token_overlap = len(query_tokens.intersection(task_topics))
    preview_token_overlap = len(query_tokens.intersection(preview_tokens))
    task_description_token_overlap = len(query_tokens.intersection(task_description_tokens))

    score = (
        preview_hit * 4
        + task_description_hit * 4
        + topic_hits * 3
        + task_topic_hits * 3
        + file_hits * 2
        + exact_type_hit * 2
        + topic_token_overlap * 2
        + task_token_overlap * 2
        + preview_token_overlap
        + task_description_token_overlap
    )

    return {
        "score": score,
        "preview_hit": preview_hit,
        "task_description_hit": task_description_hit,
        "topic_hits": topic_hits,
        "task_topic_hits": task_topic_hits,
        "file_hits": file_hits,
        "exact_type_hit": exact_type_hit,
        "topic_token_overlap": topic_token_overlap,
        "task_token_overlap": task_token_overlap,
        "preview_token_overlap": preview_token_overlap,
        "task_description_token_overlap": task_description_token_overlap,
    }


def search_skeleton(
    workspace_root: str,
    query: str,
    wing: Optional[str] = None,
    room: Optional[str] = None,
    limit: int = 5,
) -> dict:
    start = time.perf_counter()
    hits = []
    for record in _all_records(workspace_root):
        if wing and record["wing"] != wing:
            continue
        if room and record["room"] != room:
            continue
        score = _record_score(record, query)
        if score["score"] <= 0:
            continue
        enriched = dict(record)
        enriched["similarity"] = round(score["score"], 3)
        enriched["score_breakdown"] = {
            "preview_hit": score["preview_hit"],
            "task_description_hit": score["task_description_hit"],
            "topic_hits": score["topic_hits"],
            "task_topic_hits": score["task_topic_hits"],
            "file_hits": score["file_hits"],
            "exact_type_hit": score["exact_type_hit"],
            "topic_token_overlap": score["topic_token_overlap"],
            "task_token_overlap": score["task_token_overlap"],
            "preview_token_overlap": score["preview_token_overlap"],
            "task_description_token_overlap": score["task_description_token_overlap"],
        }
        hits.append(enriched)
    hits.sort(
        key=lambda item: (
            -item["similarity"],
            -item["score_breakdown"]["task_description_hit"],
            -item["score_breakdown"]["task_topic_hits"],
            -item["score_breakdown"]["topic_hits"],
            item["snapshot"],
            item["index"],
        )
    )
    return {
        "backend": "skeleton",
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": hits[:limit],
        "elapsed_ms": _elapsed_ms(start),
    }


def check_duplicate_skeleton(workspace_root: str, content: str, threshold: float = 0.9) -> dict:
    start = time.perf_counter()
    query = content.strip().lower()
    matches = []
    for record in _all_records(workspace_root):
        preview = str(record.get("preview", "")).strip().lower()
        if not preview:
            continue
        if query == preview or query in preview or preview in query:
            matches.append(
                {
                    "id": record["drawer_id"],
                    "wing": record["wing"],
                    "room": record["room"],
                    "similarity": 1.0,
                    "content": record["preview"],
                    "snapshot": record["snapshot"],
                }
            )
    return {
        "backend": "skeleton",
        "is_duplicate": bool(matches),
        "matches": matches,
        "threshold": threshold,
        "elapsed_ms": _elapsed_ms(start),
    }


def fast_status(workspace_root: str) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    taxonomy = get_taxonomy_fast(workspace_root)
    return {
        "backend": "skeleton",
        "total_drawers": index_data["total_memory_count"],
        "wings": taxonomy["wings"],
        "rooms": taxonomy["rooms"],
        "palace_path": str(skeleton_output_path(workspace_root)),
        "snapshot_count": index_data["snapshot_count"],
        "elapsed_ms": _elapsed_ms(start),
    }


def get_taxonomy_fast(workspace_root: str) -> dict:
    start = time.perf_counter()
    wings = Counter()
    rooms = Counter()
    taxonomy: Dict[str, Dict[str, int]] = defaultdict(dict)
    for record in _all_records(workspace_root):
        wing = record["wing"]
        room = record["room"]
        wings[wing] += 1
        rooms[room] += 1
        taxonomy.setdefault(wing, {})
        taxonomy[wing][room] = taxonomy[wing].get(room, 0) + 1
    return {
        "backend": "skeleton",
        "taxonomy": {wing: dict(sorted(room_counts.items())) for wing, room_counts in sorted(taxonomy.items())},
        "wings": dict(sorted(wings.items())),
        "rooms": dict(sorted(rooms.items())),
        "elapsed_ms": _elapsed_ms(start),
    }


def list_wings_fast(workspace_root: str) -> dict:
    taxonomy = get_taxonomy_fast(workspace_root)
    return {"backend": "skeleton", "wings": taxonomy["wings"], "elapsed_ms": taxonomy["elapsed_ms"]}


def list_rooms_fast(workspace_root: str, wing: Optional[str] = None) -> dict:
    start = time.perf_counter()
    records = _all_records(workspace_root)
    rooms = Counter()
    for record in records:
        if wing and record["wing"] != wing:
            continue
        rooms[record["room"]] += 1
    return {
        "backend": "skeleton",
        "wing": wing or "all",
        "rooms": dict(sorted(rooms.items())),
        "elapsed_ms": _elapsed_ms(start),
    }


def _snapshot_graph_counts(workspace_root: str, snapshot: str) -> dict:
    cache_key = (workspace_root, snapshot)
    if cache_key in _GRAPH_COUNTS_CACHE:
        return dict(_GRAPH_COUNTS_CACHE[cache_key])
    snapshot_dir = _snapshot_dir(workspace_root, snapshot)
    counts = {
        "topic_cluster_count": len(_parse_topic_clusters(snapshot_dir)),
        "file_reference_count": len(_parse_file_references(snapshot_dir)),
        "hard_edge_count": len(_parse_hard_edges(snapshot_dir)),
    }
    _GRAPH_COUNTS_CACHE[cache_key] = dict(counts)
    return counts


def graph_stats_fast(workspace_root: str) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    topic_count = 0
    file_count = 0
    edge_count = 0
    for snapshot in index_data["snapshots"]:
        counts = _snapshot_graph_counts(workspace_root, snapshot)
        topic_count += counts["topic_cluster_count"]
        file_count += counts["file_reference_count"]
        edge_count += counts["hard_edge_count"]
    return {
        "backend": "skeleton",
        "snapshot_count": len(index_data["snapshots"]),
        "memory_count": index_data["total_memory_count"],
        "topic_cluster_count": topic_count,
        "file_reference_count": file_count,
        "hard_edge_count": edge_count,
        "elapsed_ms": _elapsed_ms(start),
    }


def neighbors_fast(workspace_root: str, snapshot: str, node_index: int) -> dict:
    start = time.perf_counter()
    snapshot_dir = _snapshot_dir(workspace_root, snapshot)
    nodes = _parse_nodes(snapshot_dir)
    if not any(node.get("index") == node_index for node in nodes):
        return {
            "backend": "skeleton",
            "error": f"Node not found: {node_index}",
            "snapshot": snapshot,
            "elapsed_ms": _elapsed_ms(start),
        }

    topics = _read_literal_assignment(snapshot_dir / "nodes.py", "NODE_TOPICS", {})
    files = _read_literal_assignment(snapshot_dir / "nodes.py", "NODE_FILES", {})
    hard_edges = _parse_hard_edges(snapshot_dir)
    neighbors = []
    seen = set()
    for edge in hard_edges:
        if edge.get("source") == node_index:
            item = (edge.get("target"), edge.get("relation"), edge.get("label"))
            if item not in seen:
                seen.add(item)
                neighbors.append(item)
        elif edge.get("target") == node_index:
            item = (edge.get("source"), edge.get("relation"), edge.get("label"))
            if item not in seen:
                seen.add(item)
                neighbors.append(item)
    for topic, indexes in topics.items():
        if node_index not in indexes:
            continue
        for other in indexes:
            if other == node_index:
                continue
            item = (other, "same_topic_as", topic)
            if item not in seen:
                seen.add(item)
                neighbors.append(item)
    for path, indexes in files.items():
        if node_index not in indexes:
            continue
        for other in indexes:
            if other == node_index:
                continue
            item = (other, "mentions_same_file", path)
            if item not in seen:
                seen.add(item)
                neighbors.append(item)
    return {
        "backend": "skeleton",
        "snapshot": snapshot,
        "node_index": node_index,
        "neighbors": neighbors,
        "elapsed_ms": _elapsed_ms(start),
    }


def top_topics_fast(workspace_root: str, snapshot: Optional[str] = None) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    if snapshot:
        for item in index_data["snapshot_summaries"]:
            if item.get("name") == snapshot:
                return {
                    "backend": "skeleton",
                    "snapshot": snapshot,
                    "top_topics": list(item.get("top_topics", [])),
                    "elapsed_ms": _elapsed_ms(start),
                }
        return {"backend": "skeleton", "snapshot": snapshot, "top_topics": [], "elapsed_ms": _elapsed_ms(start)}
    return {
        "backend": "skeleton",
        "top_topics": list(index_data["global_top_topics"]),
        "elapsed_ms": _elapsed_ms(start),
    }


def top_files_fast(workspace_root: str, snapshot: Optional[str] = None) -> dict:
    start = time.perf_counter()
    index_data = _load_index_summary(workspace_root)
    if snapshot:
        for item in index_data["snapshot_summaries"]:
            if item.get("name") == snapshot:
                return {
                    "backend": "skeleton",
                    "snapshot": snapshot,
                    "top_files": list(item.get("top_files", [])),
                    "elapsed_ms": _elapsed_ms(start),
                }
        return {"backend": "skeleton", "snapshot": snapshot, "top_files": [], "elapsed_ms": _elapsed_ms(start)}
    return {
        "backend": "skeleton",
        "top_files": list(index_data["global_top_files"]),
        "elapsed_ms": _elapsed_ms(start),
    }


def traverse_fast(workspace_root: str, start_room: str, max_hops: int = 2) -> dict:
    start = time.perf_counter()
    room_graph: Dict[str, set[str]] = defaultdict(set)
    for record in _all_records(workspace_root):
        for topic in record.get("topics", []):
            room_graph[record["room"]].add(f"topic:{topic}")
            room_graph[f"topic:{topic}"].add(record["room"])
        for path in record.get("files", []):
            room_graph[record["room"]].add(f"file:{path}")
            room_graph[f"file:{path}"].add(record["room"])
    visited = {start_room}
    frontier = [(start_room, 0)]
    hops = []
    while frontier:
        room, depth = frontier.pop(0)
        if depth >= max_hops:
            continue
        for neighbor in sorted(room_graph.get(room, set())):
            hops.append({"from": room, "to": neighbor, "depth": depth + 1})
            if neighbor in visited:
                continue
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
    return {
        "backend": "skeleton",
        "start_room": start_room,
        "max_hops": max_hops,
        "hops": hops,
        "elapsed_ms": _elapsed_ms(start),
    }


def find_tunnels_fast(workspace_root: str, wing_a: Optional[str] = None, wing_b: Optional[str] = None) -> dict:
    start = time.perf_counter()
    taxonomy = get_taxonomy_fast(workspace_root)
    wings = taxonomy["wings"]
    available_wings = sorted(wings)
    if wing_a and wing_a not in wings:
        return {"backend": "skeleton", "wing_a": wing_a, "wing_b": wing_b, "tunnels": [], "elapsed_ms": _elapsed_ms(start)}
    if wing_b and wing_b not in wings:
        return {"backend": "skeleton", "wing_a": wing_a, "wing_b": wing_b, "tunnels": [], "elapsed_ms": _elapsed_ms(start)}
    chosen_a = wing_a or (available_wings[0] if available_wings else None)
    chosen_b = wing_b or chosen_a
    rooms = taxonomy["taxonomy"].get(chosen_a or "", {})
    tunnels = [{"room": room, "left": chosen_a, "right": chosen_b, "count": count} for room, count in sorted(rooms.items())]
    return {
        "backend": "skeleton",
        "wing_a": chosen_a,
        "wing_b": chosen_b,
        "tunnels": tunnels,
        "elapsed_ms": _elapsed_ms(start),
    }
