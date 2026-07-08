# /// script
# requires-python = ">=3.9,<3.13"
# dependencies = [
#   "chromadb>=1.5.0",
#   "onnxruntime>=1.14.1,<1.20.0",
# ]
# ///
"""Local-dev Chroma HTTP server.

Run with:
    uv run run_chroma.py

Starts a persistent Chroma server on port 8001, storing data in
./.chroma (repo-local). Override via env vars:
    CHROMA_DATA_PATH   default: ./.chroma
    CHROMA_PORT        default: 8001

Remove this file (and the chroma service in docker-compose.yml) if the
project does not need a vector store.
"""

import os
import sys

chroma_path = os.environ.get(
    "CHROMA_DATA_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chroma"),
)
port = os.environ.get("CHROMA_PORT", "8001")

os.makedirs(chroma_path, exist_ok=True)

sys.argv = ["chroma", "run", "--path", chroma_path, "--port", port]

from chromadb.cli.cli import app  # noqa: E402

app()
