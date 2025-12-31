"""
Pytest configuration for v2 tests.
"""

import sys
from pathlib import Path


# Add app directory to path
APP_DIR = Path(__file__).parent.parent / "app"
sys.path.insert(0, str(APP_DIR))


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an async test"
    )
