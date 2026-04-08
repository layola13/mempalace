import os
import tempfile

from mempalace.autosave import persist_autosave, _summarize_file_changes


def test_non_git_file_summary_extraction():
    text = "Created src/new_feature.py\nEdited mempalace/normalize.py\nDeleted old_notes.md\n"
    summary = _summarize_file_changes(text)
    assert "created:" in summary
    assert "- src/new_feature.py" in summary
    assert "edited:" in summary
    assert "- mempalace/normalize.py" in summary
    assert "deleted:" in summary
    assert "- old_notes.md" in summary


def test_persist_autosave_non_git_returns_code_summary(tmp_path, monkeypatch):
    snapshot = tmp_path / "session.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "Created src/new_feature.py because we need autosave"}}\n'
        '{"message": {"role": "assistant", "content": "Sounds good"}}\n',
        encoding="utf-8",
    )

    captured = []

    class DummyStore:
        def upsert_drawer(self, drawer_id, text, metadata, collection_name=None):
            captured.append((drawer_id, text, metadata))

    monkeypatch.setattr("mempalace.autosave.get_store", lambda: DummyStore())
    monkeypatch.setattr("mempalace.autosave._git_repo_root", lambda workspace_root: None)

    memory_count, code_saved = persist_autosave(
        snapshot_file=str(snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
    )

    assert memory_count >= 0
    assert code_saved is True
    assert any(item[2]["room"] == "code-summary" for item in captured)


def test_persist_autosave_git_uses_diff(tmp_path, monkeypatch):
    snapshot = tmp_path / "session.jsonl"
    snapshot.write_text(
        '{"message": {"role": "user", "content": "We updated normalize.py to fix autosave"}}\n'
        '{"message": {"role": "assistant", "content": "Done"}}\n',
        encoding="utf-8",
    )

    captured = []

    class DummyStore:
        def upsert_drawer(self, drawer_id, text, metadata, collection_name=None):
            captured.append((drawer_id, text, metadata))

    monkeypatch.setattr("mempalace.autosave.get_store", lambda: DummyStore())
    monkeypatch.setattr("mempalace.autosave._git_repo_root", lambda workspace_root: str(tmp_path))
    monkeypatch.setattr("mempalace.autosave._git_diff", lambda repo_root: "diff --git a/a.py b/a.py\n+print('hi')")

    memory_count, code_saved = persist_autosave(
        snapshot_file=str(snapshot),
        wing="wing_test",
        agent="tester",
        workspace_root=str(tmp_path),
        trigger="stop",
    )

    assert memory_count >= 0
    assert code_saved is True
    assert any(item[2]["room"] == "code-diff" for item in captured)
    assert any("diff --git" in item[1] for item in captured)
