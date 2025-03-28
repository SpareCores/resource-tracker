from os import environ
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def artifacts_dir():
    """Create and return path to artifacts directory."""
    # use an environment variable that can be set by tox
    base_dir = environ.get("ARTIFACT_DIR", str(Path(__file__).parent / "artifacts"))
    path = Path(base_dir)
    path.mkdir(exist_ok=True)
    return path
