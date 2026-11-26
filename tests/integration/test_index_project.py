import pytest
import os
import shutil
import tempfile
from pathlib import Path

from map.mcp.handlers import MCPHandler
from map.mcp.tools import IndexProjectParams, GetProjectOverviewParams

@pytest.fixture
def test_repo():
    temp_dir = tempfile.mkdtemp(prefix="mindmap_idx_")
    f1 = Path(temp_dir) / "core.py"
    f1.write_text("class Engine:\n    def start(self):\n        return True\n", encoding="utf-8")
    os.system(f"git -C {temp_dir} init && git -C {temp_dir} config user.email 'test@test.com' && git -C {temp_dir} config user.name 'Test' && git -C {temp_dir} add . && git -C {temp_dir} commit -m 'init'")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.mark.asyncio
async def test_index_project_flow(test_repo):
    handler = MCPHandler()
    res = await handler.index_project(IndexProjectParams(repo_url=test_repo, repo_type="local"))
    assert res.get("ok") is True
    assert res.get("status") == "indexed"
    assert res.get("nodes", 0) > 0

    overview = await handler.get_project_overview(GetProjectOverviewParams(project_id=test_repo))
    assert overview.get("ok") is True
    assert overview.get("classes", 0) >= 1

