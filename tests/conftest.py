import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "test.db")
