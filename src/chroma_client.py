"""
chroma_client.py

Singleton ChromaDB client.
Tries HTTP client first (standalone ChromaDB service), then falls back
to embedded PersistentClient (local storage, no external service needed).
This ensures RAG, memory vectors, and tool indexing work even in Docker
deployments without a dedicated ChromaDB container.
"""

import os
import socket
import logging

logger = logging.getLogger(__name__)

_client = None
_mode = None  # "http" or "embedded"

# A short connect probe so an unreachable ChromaDB fails fast instead of
# blocking on the OS connection timeout (~30-60s, WinError 10060 on Windows),
# which otherwise stalls app startup. Tunable via CHROMADB_CONNECT_TIMEOUT.
_CONNECT_TIMEOUT = float(os.getenv("CHROMADB_CONNECT_TIMEOUT", "2.0"))


def _port_open(host: str, port: int, timeout: float = None) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout or _CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def _embedded_path() -> str:
    """Return the local path for embedded ChromaDB storage."""
    from src.constants import DATA_DIR
    return os.path.join(DATA_DIR, "chroma_embedded")


def get_chroma_client():
    """Get or create the singleton ChromaDB client.

    Tries HTTP client first (if CHROMADB_HOST/PORT points at a running
    service), then falls back to embedded PersistentClient so the app
    works standalone without a ChromaDB container.
    """
    global _client, _mode
    if _client is not None:
        return _client

    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError(
            "ChromaDB integration is not installed. Install the optional "
            "dependency with: pip install chromadb"
        ) from e

    # ── Try HTTP client first ──
    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8100"))

    if _port_open(host, port):
        try:
            client = chromadb.HttpClient(host=host, port=port)
            client.heartbeat()
            _client = client
            _mode = "http"
            logger.info(f"ChromaDB connected (HTTP): {host}:{port}")
            return _client
        except Exception as e:
            logger.warning(f"ChromaDB HTTP at {host}:{port} reachable but unhealthy: {e}")

    # ── Fall back to embedded PersistentClient ──
    # This stores data locally in DATA_DIR/chroma_embedded — no external
    # service needed. RAG, memory vectors, and tool indexing all work.
    try:
        path = _embedded_path()
        os.makedirs(path, exist_ok=True)
        client = chromadb.PersistentClient(path=path)
        client.heartbeat()
        _client = client
        _mode = "embedded"
        logger.info(f"ChromaDB connected (embedded): {path}")
        return _client
    except Exception as e:
        raise RuntimeError(
            f"ChromaDB unavailable: HTTP service not at {host}:{port} and "
            f"embedded mode failed: {e}"
        ) from e


def get_chroma_mode() -> str:
    """Return 'http', 'embedded', or None if not yet initialized."""
    return _mode


def reset_client():
    """Reset the singleton (e.g. after config change)."""
    global _client, _mode
    _client = None
    _mode = None
