import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        yield str(Path(tmp) / "test.db")
