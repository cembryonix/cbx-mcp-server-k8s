"""
Integration test fixtures.

Provides fixtures for starting and stopping the MCP server.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import httpx
import pytest

# Paths
TEST_DIR = Path(__file__).parent
APP_DIR = TEST_DIR.parent.parent / "app"
CONFIG_DIR = TEST_DIR / "config"

# Add app to path
sys.path.insert(0, str(APP_DIR))

# Test server settings
TEST_HOST = "127.0.0.1"
TEST_PORT = 8765
TEST_URL = f"http://{TEST_HOST}:{TEST_PORT}"


class ServerProcess:
    """Manages the MCP server subprocess for testing."""

    def __init__(self, host: str = TEST_HOST, port: int = TEST_PORT):
        self.host = host
        self.port = port
        self.process: subprocess.Popen | None = None
        self.url = f"http://{host}:{port}"

    def start(self, timeout: float = 10.0) -> None:
        """Start the server and wait for it to be ready."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(APP_DIR)

        self.process = subprocess.Popen(
            [
                sys.executable,
                str(APP_DIR / "main.py"),
                "--transport", "streamable-http",
                "--host", self.host,
                "--port", str(self.port),
                "--config-dir", str(CONFIG_DIR),
                "--skip-tool-validation",  # Skip validation for testing
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"{self.url}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.1)

        # Server didn't start in time
        self.stop()
        raise RuntimeError(f"Server failed to start within {timeout}s")

    def stop(self) -> None:
        """Stop the server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

    def __enter__(self) -> "ServerProcess":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


@pytest.fixture(scope="module")
def server() -> Generator[ServerProcess, None, None]:
    """
    Start the MCP server for the test module.

    Yields:
        ServerProcess instance with running server
    """
    server = ServerProcess()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def client(server: ServerProcess) -> httpx.Client:
    """
    Get HTTP client configured for the test server.

    Args:
        server: Running server process

    Returns:
        httpx.Client instance
    """
    return httpx.Client(base_url=server.url, timeout=10.0)


@pytest.fixture
def async_client(server: ServerProcess) -> httpx.AsyncClient:
    """
    Get async HTTP client configured for the test server.

    Args:
        server: Running server process

    Returns:
        httpx.AsyncClient instance
    """
    return httpx.AsyncClient(base_url=server.url, timeout=10.0)
