from mempalace.autosave import persist_autosave, _summarize_file_changes
from mempalace.conversation_skeleton import build_relationship_skeleton, skeleton_output_path
import importlib.util
import sys


class DummyStore:
    def __init__(self, captured):
        self.captured = captured

    def upsert_drawer(self, drawer_id, text, metadata, collection_name=None):
        self.captured.append((drawer_id, text, metadata))


def _patch_store(monkeypatch, captured):
    monkeypatch.setattr("mempalace.autosave.get_store", lambda: DummyStore(captured))


def _patch_memories(monkeypatch, memories):
    monkeypatch.setattr("mempalace.autosave.extract_memories", lambda normalized: memories)


def _sample_memories():
    return [
        {
            "content": "We should keep a relationship skeleton for mempalace/autosave.py.",
            "memory_type": "decision",
            "chunk_index": 0,
        },
        {
            "content": "The relationship skeleton should link repeated mentions of mempalace/autosave.py.",
            "memory_type": "decision",
            "chunk_index": 1,
        },
    ]


def _rooms(captured):
    return [item[2]["room"] for item in captured]


def test_non_git_file_summary_extraction():
    text = "Created src/new_feature.py\nEdited mempalace/normalize.py\nDeleted old_notes.md\n"
    summary = _summarize_file_changes(text)
    assert "created:" in summary
    assert "- src/new_feature.py" in summary
    assert "edited:" in summary
    assert "- mempalace/normalize.py" in summary
    assert "deleted:" in summary
    assert "- old_notes.md" in summary


def test_persist_autosave_non_git_returns_code_summary_and_writes_skeleton_package(tmp_path, monkeypatch):
    snapshot = tmp_path / "session.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "Created src/new_feature.py because we need autosave relationship tracking"}}\n'
        '{"message": {"role": "assistant", "content": "Sounds good, let us keep a skeleton"}}\n',
        encoding="utf-8",
    )

    captured = []
    _patch_store(monkeypatch, captured)
    _patch_memories(monkeypatch, _sample_memories())
    monkeypatch.setattr("mempalace.autosave._git_repo_root", lambda workspace_root: None)

    memory_count, code_saved = persist_autosave(
        snapshot_file=str(snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
    )

    skeleton_dir = skeleton_output_path(str(tmp_path), str(snapshot))
    assert memory_count == 2
    assert code_saved is True
    assert "code-summary" in _rooms(captured)
    assert skeleton_dir.exists()
    assert (skeleton_dir / "__init__.py").exists()
    assert (skeleton_dir / "nodes.py").exists()
    assert (skeleton_dir / "topics.py").exists()
    assert (skeleton_dir / "files.py").exists()
    assert (skeleton_dir / "patterns.py").exists()
    assert (skeleton_dir / "edges.py").exists()
    edges_text = (skeleton_dir / "edges.py").read_text(encoding="utf-8")
    assert "RelationGraph" in edges_text
    assert "hard_edges" in edges_text
    assert "same_topic_neighbors" in edges_text
    assert "same_file_neighbors" in edges_text
    assert "same_pattern_neighbors" in edges_text
    assert "mempalace/autosave.py" in (skeleton_dir / "nodes.py").read_text(encoding="utf-8")


def test_persist_autosave_git_uses_diff_and_writes_skeleton_package(tmp_path, monkeypatch):
    snapshot = tmp_path / "session.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "We updated normalize.py to fix autosave and keep the relationship skeleton"}}\n'
        '{"message": {"role": "assistant", "content": "Done"}}\n',
        encoding="utf-8",
    )

    captured = []
    _patch_store(monkeypatch, captured)
    _patch_memories(monkeypatch, _sample_memories())
    monkeypatch.setattr("mempalace.autosave._git_repo_root", lambda workspace_root: str(tmp_path))
    monkeypatch.setattr("mempalace.autosave._git_diff", lambda repo_root: "diff --git a/a.py b/a.py\n+print('hi')")

    memory_count, code_saved = persist_autosave(
        snapshot_file=str(snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
    )

    skeleton_dir = skeleton_output_path(str(tmp_path), str(snapshot))
    assert memory_count == 2
    assert code_saved is True
    assert "code-diff" in _rooms(captured)
    assert any("diff --git" in item[1] for item in captured)
    assert skeleton_dir.exists()
    assert "hard_edges" in (skeleton_dir / "edges.py").read_text(encoding="utf-8")




def test_generated_skeleton_package_methods_are_callable(tmp_path, monkeypatch):
    snapshot = tmp_path / "session.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "Created src/new_feature.py because we need autosave relationship tracking"}}\n'
        '{"message": {"role": "assistant", "content": "Sounds good, let us keep a skeleton"}}\n',
        encoding="utf-8",
    )

    captured = []
    _patch_store(monkeypatch, captured)
    _patch_memories(monkeypatch, _sample_memories())
    monkeypatch.setattr("mempalace.autosave._git_repo_root", lambda workspace_root: None)

    persist_autosave(
        snapshot_file=str(snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
    )

    skeleton_dir = skeleton_output_path(str(tmp_path), str(snapshot))
    package_name = "generated_skeleton_test"
    spec = importlib.util.spec_from_file_location(package_name, skeleton_dir / "__init__.py", submodule_search_locations=[str(skeleton_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

    graph = module.graph
    assert graph.topics_for(0)
    assert graph.files_for(0) == ["mempalace/autosave.py"]
    assert graph.repeated_types() == ["decision"]
    neighbors = graph.neighbors(0)
    assert any(item[1] == "same_topic_as" for item in neighbors)
    assert any(item[1] == "mentions_same_file" for item in neighbors)
    assert any(item[1] == "repeats_pattern" for item in neighbors)
