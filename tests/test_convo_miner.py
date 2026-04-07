import os
import tempfile
import shutil
from mempalace.convo_miner import mine_convos
from mempalace.qdrant_store import get_store


def test_convo_mining():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "chat.txt"), "w") as f:
        f.write(
            "> What is memory?\nMemory is persistence.\n\n> Why does it matter?\nIt enables continuity.\n\n> How do we build it?\nWith structured storage.\n"
        )

    palace_path = os.path.join(tmpdir, "palace")
    mine_convos(tmpdir, palace_path, wing="test_convos")

    store = get_store()
    assert store.count() >= 2

    results = store.search(query="memory persistence", n_results=1)
    assert len(results) > 0

    shutil.rmtree(tmpdir)
