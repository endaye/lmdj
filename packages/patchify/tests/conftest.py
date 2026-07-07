import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def golden_package(tmp_path: Path) -> Path:
    """真实 demo 输出的副本；错误路径测试在副本上破坏单个字段。"""
    root = tmp_path / "testsong"
    shutil.copytree(FIXTURES / "testsong", root)
    return root
