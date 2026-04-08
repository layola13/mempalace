from mempalace.autosave import persist_autosave, _summarize_file_changes
from mempalace.conversation_skeleton import index_output_path, snapshot_skeleton_output_path
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


def test_persist_autosave_non_git_returns_code_summary_and_writes_single_skeleton_package(tmp_path, monkeypatch):
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
        session_id="session-123",
    )

    skeleton_dir = snapshot_skeleton_output_path(str(tmp_path), str(snapshot))
    index_file = index_output_path(str(tmp_path))
    assert memory_count == 2
    assert code_saved is True
    assert "code-summary" in _rooms(captured)
    assert skeleton_dir.exists()
    assert index_file.exists()
    assert not (skeleton_dir.parent / "latest").exists()
    assert (skeleton_dir / "__init__.py").exists()
    assert (skeleton_dir / "summary.py").exists()
    assert (skeleton_dir / "nodes.py").exists()
    assert (skeleton_dir / "topics.py").exists()
    assert (skeleton_dir / "files.py").exists()
    assert (skeleton_dir / "patterns.py").exists()
    assert (skeleton_dir / "edges.py").exists()
    summary_text = (skeleton_dir / "summary.py").read_text(encoding="utf-8")
    assert "TASK_DESCRIPTION = 'Created src/new_feature.py because we need autosave relationship tracking'" in summary_text
    assert "TASK_TOPICS = ['tracking', 'created', 'new_feature']" not in summary_text
    assert "TASK_TOPICS = " in summary_text
    assert "tracking" in summary_text
    assert "created" in summary_text
    assert "new_feature" in summary_text
    assert "snapshot_overview" in summary_text
    edges_text = (skeleton_dir / "edges.py").read_text(encoding="utf-8")
    assert "RelationGraph" in edges_text
    assert "hard_edges" in edges_text
    assert "same_topic_neighbors" in edges_text
    assert "same_file_neighbors" in edges_text
    assert "same_pattern_neighbors" in edges_text
    assert "mempalace/autosave.py" in (skeleton_dir / "nodes.py").read_text(encoding="utf-8")
    index_text = index_file.read_text(encoding="utf-8")
    assert f"snapshot_{snapshot.stem}" in index_text
    assert "SNAPSHOT_SUMMARIES" in index_text
    assert "LATEST_SNAPSHOT" in index_text
    assert "SNAPSHOT_COUNT" in index_text
    assert "TOTAL_MEMORY_COUNT" in index_text
    assert "GLOBAL_TOP_TOPICS" in index_text
    assert "GLOBAL_TOP_FILES" in index_text
    assert "GLOBAL_TASK_TOPICS" in index_text
    assert "summary_module_for" in index_text
    assert "nodes_module_for" in index_text
    assert "edges_module_for" in index_text
    assert "task_topics" in index_text
    assert "task_description" in index_text
    assert "global_overview" in index_text
    assert "top_topics" in index_text
    assert "top_files" in index_text


def test_persist_autosave_git_uses_diff_and_writes_single_skeleton_package(tmp_path, monkeypatch):
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
        session_id="session-456",
    )

    skeleton_dir = snapshot_skeleton_output_path(str(tmp_path), str(snapshot))
    index_file = index_output_path(str(tmp_path))
    assert memory_count == 2
    assert code_saved is True
    assert "code-diff" in _rooms(captured)
    assert any("diff --git" in item[1] for item in captured)
    assert skeleton_dir.exists()
    assert not (skeleton_dir.parent / "latest").exists()
    assert index_file.exists()
    assert (skeleton_dir / "summary.py").exists()
    assert "hard_edges" in (skeleton_dir / "edges.py").read_text(encoding="utf-8")
    assert f"snapshot_{snapshot.stem}" in index_file.read_text(encoding="utf-8")


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
        session_id="session-789",
    )

    skeleton_dir = snapshot_skeleton_output_path(str(tmp_path), str(snapshot))
    package_name = "generated_skeleton_test"
    spec = importlib.util.spec_from_file_location(package_name, skeleton_dir / "__init__.py", submodule_search_locations=[str(skeleton_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

    graph = module.graph
    assert module.SNAPSHOT_NAME == f"snapshot_{snapshot.stem}"
    assert module.TASK_DESCRIPTION == "Created src/new_feature.py because we need autosave relationship tracking"
    assert set(module.TASK_TOPICS) == {"tracking", "created", "new_feature"}
    assert module.snapshot_overview()["task_description"] == module.TASK_DESCRIPTION
    assert set(module.snapshot_overview()["task_topics"]) == {"tracking", "created", "new_feature"}
    assert graph.topics_for(0)
    assert graph.files_for(0) == ["mempalace/autosave.py"]
    assert graph.repeated_types() == ["decision"]
    neighbors = graph.neighbors(0)
    assert any(item[1] == "same_topic_as" for item in neighbors)
    assert any(item[1] == "mentions_same_file" for item in neighbors)
    assert any(item[1] == "repeats_pattern" for item in neighbors)


def test_index_points_to_most_recent_snapshot_without_duplicate_directory(tmp_path, monkeypatch):
    first_snapshot = tmp_path / "20260101_000000_stop.jsonl"
    second_snapshot = tmp_path / "20260101_000100_stop.jsonl"
    for snapshot in (first_snapshot, second_snapshot):
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
        snapshot_file=str(first_snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
        session_id="session-latest",
    )
    persist_autosave(
        snapshot_file=str(second_snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
        session_id="session-latest",
    )

    first_dir = snapshot_skeleton_output_path(str(tmp_path), str(first_snapshot))
    second_dir = snapshot_skeleton_output_path(str(tmp_path), str(second_snapshot))
    index_file = index_output_path(str(tmp_path))
    index_text = index_file.read_text(encoding="utf-8")
    assert first_dir.exists()
    assert second_dir.exists()
    assert not (second_dir.parent / "latest").exists()
    assert "LATEST_SNAPSHOT = 'snapshot_20260101_000100_stop'" in index_text
    assert f"snapshot_{first_snapshot.stem}" in index_text
    assert f"snapshot_{second_snapshot.stem}" in index_text
    assert "summary_module" in index_text
    assert "task_description" in index_text
    assert "Created src/new_feature.py because we need autosave relationship tracking" in index_text




def test_persist_autosave_filters_local_command_caveat_from_task_description(tmp_path, monkeypatch):
    snapshot = tmp_path / "session_noise.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "<local-command-caveat>Caveat: ignore this.</local-command-caveat>"}}\n'
        '{"message": {"role": "user", "content": "Use the new py skeleton to replace the old palace interface."}}\n'
        '{"message": {"role": "assistant", "content": "Okay"}}\n',
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
        session_id="session-noise",
    )

    skeleton_dir = snapshot_skeleton_output_path(str(tmp_path), str(snapshot))
    summary_text = (skeleton_dir / "summary.py").read_text(encoding="utf-8")
    assert "local-command-caveat" not in summary_text
    assert "TASK_DESCRIPTION = 'Use the new py skeleton to replace the old palace interface.'" in summary_text



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
        session_id="session-mcp",
    )

    monkeypatch.chdir(tmp_path)
    from mempalace import mcp_server

    index_result = mcp_server.tool_skeleton_index()
    assert index_result["exists"] is True
    assert "SNAPSHOT_SUMMARIES" in index_result["index_text"]

    summary_result = mcp_server.tool_skeleton_read(f"snapshot_{snapshot.stem}", "summary")
    assert summary_result["success"] is True
    assert "TASK_DESCRIPTION" in summary_result["content"]
    assert "TASK_TOPICS" in summary_result["content"]



def test_mcp_fast_tools_return_skeleton_results_with_timing(tmp_path, monkeypatch):
    snapshot = tmp_path / "session_fast.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "Use the new py skeleton to replace the old palace interface and benchmark search speed."}}\n'
        '{"message": {"role": "assistant", "content": "Okay"}}\n',
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
        session_id="session-fast",
    )

    monkeypatch.chdir(tmp_path)
    from mempalace import mcp_server

    status_result = mcp_server.tool_fast_status()
    assert status_result["backend"] == "skeleton"
    assert "elapsed_ms" in status_result

    snapshots_result = mcp_server.tool_fast_list_snapshots()
    assert f"snapshot_{snapshot.stem}" in snapshots_result["snapshots"]
    assert "elapsed_ms" in snapshots_result

    summary_result = mcp_server.tool_fast_summary_for(f"snapshot_{snapshot.stem}")
    assert summary_result["summary"]["name"] == f"snapshot_{snapshot.stem}"
    assert "task_description" in summary_result["summary"]
    assert "elapsed_ms" in summary_result

    search_result = mcp_server.tool_fast_search("autosave", limit=5)
    assert search_result["backend"] == "skeleton"
    assert search_result["results"]
    assert "elapsed_ms" in search_result

    task_search_result = mcp_server.tool_fast_search("benchmark", limit=5)
    assert task_search_result["results"]
    assert any(result.get("task_description") for result in task_search_result["results"])
    assert any(result["score_breakdown"]["task_description_hit"] or result["score_breakdown"]["task_topic_hits"] for result in task_search_result["results"])

    neighbors_result = mcp_server.tool_fast_neighbors(f"snapshot_{snapshot.stem}", 0)
    assert neighbors_result["backend"] == "skeleton"
    assert "neighbors" in neighbors_result
    assert "elapsed_ms" in neighbors_result

    graph_result = mcp_server.tool_fast_graph_stats()
    assert graph_result["backend"] == "skeleton"
    assert graph_result["memory_count"] >= 2
    assert "elapsed_ms" in graph_result

    duplicate_result = mcp_server.tool_fast_check_duplicate(
        "We should keep a relationship skeleton for mempalace/autosave.py."
    )
    assert duplicate_result["backend"] == "skeleton"
    assert duplicate_result["is_duplicate"] is True
    assert "elapsed_ms" in duplicate_result
