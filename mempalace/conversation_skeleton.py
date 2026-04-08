from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import re
from typing import Dict, List, Sequence, Tuple

FILE_PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+|[\w.-]+\.(?:py|js|ts|tsx|jsx|go|rs|rb|java|json|yaml|yml|toml|md|sh|sql|css|html)")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "agent",
    "already",
    "and",
    "assistant",
    "autosave",
    "because",
    "before",
    "between",
    "change",
    "claude",
    "code",
    "could",
    "current",
    "decision",
    "discussed",
    "done",
    "each",
    "file",
    "files",
    "for",
    "from",
    "good",
    "have",
    "into",
    "its",
    "just",
    "keep",
    "keeps",
    "let",
    "like",
    "maybe",
    "memory",
    "messages",
    "need",
    "our",
    "problem",
    "project",
    "references",
    "relationship",
    "repeated",
    "save",
    "saved",
    "session",
    "should",
    "show",
    "sounds",
    "stay",
    "store",
    "summary",
    "system",
    "task",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "through",
    "topic",
    "topics",
    "user",
    "using",
    "visible",
    "want",
    "with",
}


def _extract_files(text: str) -> List[str]:
    return sorted({match.rstrip('.,:;)]}') for match in FILE_PATH_RE.findall(text)})


def _extract_tokens(text: str) -> List[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        if token.isdigit() or len(token) < 4:
            continue
        if token in {"jsonl", "yaml", "yml", "toml", "html", "css", "sql"}:
            continue
        tokens.append(token)
    return tokens


def _topic_priority(token: str) -> tuple[int, int, str]:
    preferred = 0
    if "/" in token or "_" in token or "-" in token:
        preferred -= 1
    if token.endswith(("ing", "tion", "ment", "ity", "ship")):
        preferred -= 1
    return (preferred, -len(token), token)




def _memory_topics(memory: Dict[str, object]) -> List[str]:
    content = str(memory.get("content", ""))
    token_counts = Counter(_extract_tokens(content))
    ranked = sorted(token_counts.items(), key=lambda item: (-item[1], _topic_priority(item[0])))
    return [token for token, _ in ranked[:3]]


def _topic_groups(memories: Sequence[Dict[str, object]]) -> List[dict]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, memory in enumerate(memories):
        for topic in _memory_topics(memory):
            groups[topic].append(idx)
    return [
        {"name": topic, "memory_indexes": indexes}
        for topic, indexes in sorted(groups.items())
        if len(indexes) >= 2
    ]


def _file_groups(memories: Sequence[Dict[str, object]]) -> List[dict]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, memory in enumerate(memories):
        for path in _extract_files(str(memory.get("content", ""))):
            groups[path].append(idx)
    return [
        {"path": path, "memory_indexes": indexes}
        for path, indexes in sorted(groups.items())
        if len(indexes) >= 2
    ]


def _pattern_groups(memories: Sequence[Dict[str, object]]) -> List[dict]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, memory in enumerate(memories):
        groups[str(memory.get("memory_type", "general"))].append(idx)
    return [
        {"name": pattern, "memory_indexes": indexes}
        for pattern, indexes in sorted(groups.items())
        if len(indexes) >= 2
    ]


def _co_occurrences(memories: Sequence[Dict[str, object]]) -> List[dict]:
    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for memory in memories:
        topics = sorted(set(_memory_topics(memory)))
        for pair in combinations(topics, 2):
            pair_counts[pair] += 1
    return [
        {"left": pair[0], "right": pair[1], "count": count}
        for pair, count in sorted(pair_counts.items())
        if count >= 2
    ]


def _hard_edges(memories: Sequence[Dict[str, object]]) -> List[dict]:
    edges = []
    for idx in range(len(memories) - 1):
        left = str(memories[idx].get("memory_type", "general"))
        right = str(memories[idx + 1].get("memory_type", "general"))
        if left == right:
            edges.append({"source": idx, "target": idx + 1, "relation": "follows_from", "label": None})
    return edges


def _quoted(value: str) -> str:
    return repr(value)


def build_relationship_skeleton(memories: Sequence[Dict[str, object]]) -> Tuple[str, dict]:
    topic_groups = _topic_groups(memories)
    file_groups = _file_groups(memories)
    pattern_groups = _pattern_groups(memories)
    co_occurrences = _co_occurrences(memories)
    hard_edges = _hard_edges(memories)

    init_lines = [
        "from .nodes import MemoryNode",
        "from .topics import TopicCluster",
        "from .files import FileReference",
        "from .patterns import PatternGroup",
        "from .edges import RelationGraph",
        "",
        "graph = RelationGraph()",
        "",
    ]

    nodes_lines = [
        "from __future__ import annotations",
        "",
        "class MemoryNode:",
        "    def __init__(self, index: int, memory_type: str, preview: str) -> None:",
        "        self.index = index",
        "        self.memory_type = memory_type",
        "        self.preview = preview",
        "",
        "NODES = [",
    ]
    for idx, memory in enumerate(memories):
        preview = str(memory.get("content", "")).replace("\n", " ").strip()[:120]
        nodes_lines.append(
            f"    MemoryNode(index={idx}, memory_type={_quoted(str(memory.get('memory_type', 'general')))}, preview={_quoted(preview)}),"
        )
    nodes_lines.append("]")
    nodes_lines.append("")

    topics_lines = [
        "from __future__ import annotations",
        "",
        "class TopicCluster:",
        "    def __init__(self, name: str, members: list[int]) -> None:",
        "        self.name = name",
        "        self.members = members",
        "",
        "    def references(self) -> list[int]:",
        "        return list(self.members)",
        "",
        "TOPIC_CLUSTERS = [",
    ]
    for group in topic_groups:
        topics_lines.append(f"    TopicCluster(name={_quoted(group['name'])}, members={group['memory_indexes']!r}),")
    topics_lines.append("]")
    topics_lines.append("")

    files_lines = [
        "from __future__ import annotations",
        "",
        "class FileReference:",
        "    def __init__(self, path: str, members: list[int]) -> None:",
        "        self.path = path",
        "        self.members = members",
        "",
        "    def touches(self) -> list[int]:",
        "        return list(self.members)",
        "",
        "FILE_REFERENCES = [",
    ]
    for group in file_groups:
        files_lines.append(f"    FileReference(path={_quoted(group['path'])}, members={group['memory_indexes']!r}),")
    files_lines.append("]")
    files_lines.append("")

    patterns_lines = [
        "from __future__ import annotations",
        "",
        "class PatternGroup:",
        "    def __init__(self, name: str, members: list[int]) -> None:",
        "        self.name = name",
        "        self.members = members",
        "",
        "    def repeats(self) -> list[int]:",
        "        return list(self.members)",
        "",
        "REPEATED_PATTERNS = [",
    ]
    for group in pattern_groups:
        patterns_lines.append(f"    PatternGroup(name={_quoted(group['name'])}, members={group['memory_indexes']!r}),")
    patterns_lines.append("]")
    patterns_lines.append("")

    edges_lines = [
        "from __future__ import annotations",
        "",
        "from .nodes import NODES",
        "from .topics import TOPIC_CLUSTERS",
        "from .files import FILE_REFERENCES",
        "from .patterns import REPEATED_PATTERNS",
        "",
        "class RelationGraph:",
        f"    memory_count = {len(memories)}",
        "",
        "    topic_clusters = TOPIC_CLUSTERS",
        "    file_references = FILE_REFERENCES",
        "    repeated_patterns = REPEATED_PATTERNS",
        "",
        f"    co_occurrences = {co_occurrences!r}",
        f"    hard_edges = {hard_edges!r}",
        "",
        "    def same_topic_neighbors(self, node_index: int) -> list[tuple[int, str]]:",
        "        neighbors: list[tuple[int, str]] = []",
        "        seen: set[tuple[int, str]] = set()",
        "        for cluster in self.topic_clusters:",
        "            if node_index not in cluster.members:",
        "                continue",
        "            for member in cluster.members:",
        "                if member == node_index:",
        "                    continue",
        "                item = (member, cluster.name)",
        "                if item in seen:",
        "                    continue",
        "                seen.add(item)",
        "                neighbors.append(item)",
        "        return neighbors",
        "",
        "    def same_file_neighbors(self, node_index: int) -> list[tuple[int, str]]:",
        "        neighbors: list[tuple[int, str]] = []",
        "        seen: set[tuple[int, str]] = set()",
        "        for reference in self.file_references:",
        "            if node_index not in reference.members:",
        "                continue",
        "            for member in reference.members:",
        "                if member == node_index:",
        "                    continue",
        "                item = (member, reference.path)",
        "                if item in seen:",
        "                    continue",
        "                seen.add(item)",
        "                neighbors.append(item)",
        "        return neighbors",
        "",
        "    def same_pattern_neighbors(self, node_index: int) -> list[tuple[int, str]]:",
        "        neighbors: list[tuple[int, str]] = []",
        "        seen: set[tuple[int, str]] = set()",
        "        for pattern in self.repeated_patterns:",
        "            if node_index not in pattern.members:",
        "                continue",
        "            for member in pattern.members:",
        "                if member == node_index:",
        "                    continue",
        "                item = (member, pattern.name)",
        "                if item in seen:",
        "                    continue",
        "                seen.add(item)",
        "                neighbors.append(item)",
        "        return neighbors",
        "",
        "    def neighbors(self, node_index: int) -> list[tuple[int, str, str | None]]:",
        "        merged: list[tuple[int, str, str | None]] = []",
        "        seen: set[tuple[int, str, str | None]] = set()",
        "        for edge in self.hard_edges:",
        "            if edge['source'] == node_index:",
        "                item = (edge['target'], edge['relation'], edge['label'])",
        "                if item not in seen:",
        "                    seen.add(item)",
        "                    merged.append(item)",
        "            elif edge['target'] == node_index:",
        "                item = (edge['source'], edge['relation'], edge['label'])",
        "                if item not in seen:",
        "                    seen.add(item)",
        "                    merged.append(item)",
        "        for neighbor, label in self.same_topic_neighbors(node_index):",
        "            item = (neighbor, 'same_topic_as', label)",
        "            if item not in seen:",
        "                seen.add(item)",
        "                merged.append(item)",
        "        for neighbor, label in self.same_file_neighbors(node_index):",
        "            item = (neighbor, 'mentions_same_file', label)",
        "            if item not in seen:",
        "                seen.add(item)",
        "                merged.append(item)",
        "        for neighbor, label in self.same_pattern_neighbors(node_index):",
        "            item = (neighbor, 'repeats_pattern', label)",
        "            if item not in seen:",
        "                seen.add(item)",
        "                merged.append(item)",
        "        return merged",
        "",
        "    def topics_for(self, node_index: int) -> list[str]:",
        "        return [cluster.name for cluster in self.topic_clusters if node_index in cluster.members]",
        "",
        "    def files_for(self, node_index: int) -> list[str]:",
        "        return [reference.path for reference in self.file_references if node_index in reference.members]",
        "",
        "    def repeated_types(self) -> list[str]:",
        "        return [pattern.name for pattern in self.repeated_patterns]",
        "",
    ]

    package_text = {
        "__init__.py": "\n".join(init_lines),
        "nodes.py": "\n".join(nodes_lines),
        "topics.py": "\n".join(topics_lines),
        "files.py": "\n".join(files_lines),
        "patterns.py": "\n".join(patterns_lines),
        "edges.py": "\n".join(edges_lines),
    }

    preview = "\n\n".join(f"# {name}\n{text}" for name, text in package_text.items())
    stats = {
        "memory_count": len(memories),
        "topic_count": len(topic_groups),
        "file_group_count": len(file_groups),
        "pattern_count": len(pattern_groups),
        "co_occurrence_count": len(co_occurrences),
        "edge_count": len(hard_edges),
    }
    return preview, stats


def skeleton_output_path(workspace_root: str, snapshot_file: str) -> Path:
    snapshot_name = Path(snapshot_file).stem
    return Path(workspace_root) / ".mempalace" / "skeleton" / snapshot_name


def write_relationship_skeleton(workspace_root: str, snapshot_file: str, memories: Sequence[Dict[str, object]]) -> Tuple[Path, dict]:
    output_dir = skeleton_output_path(workspace_root, snapshot_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview, stats = build_relationship_skeleton(memories)
    package = {}
    current_name = None
    current_lines: List[str] = []
    for line in preview.splitlines():
        if line.startswith("# ") and line.endswith(".py"):
            if current_name is not None:
                package[current_name] = "\n".join(current_lines).strip() + "\n"
            current_name = line[2:]
            current_lines = []
            continue
        current_lines.append(line)
    if current_name is not None:
        package[current_name] = "\n".join(current_lines).strip() + "\n"
    for name, content in package.items():
        (output_dir / name).write_text(content, encoding="utf-8")
    return output_dir, stats
