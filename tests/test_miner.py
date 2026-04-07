import os
import tempfile
import shutil
import yaml
from mempalace.miner import mine
from mempalace.qdrant_store import get_store


def test_project_mining():
    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, "backend"))
    with open(os.path.join(tmpdir, "backend", "app.py"), "w") as f:
        f.write("def main():\n    print('hello world')\n" * 20)
    with open(os.path.join(tmpdir, "mempalace.yaml"), "w") as f:
        yaml.dump(
            {
                "wing": "test_project",
                "rooms": [
                    {"name": "backend", "description": "Backend code"},
                    {"name": "general", "description": "General"},
                ],
            },
            f,
        )

    palace_path = os.path.join(tmpdir, "palace")
    mine(tmpdir, palace_path)

    store = get_store()
    assert store.count() > 0

    shutil.rmtree(tmpdir)
