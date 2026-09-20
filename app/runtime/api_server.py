from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn

from app.main import app


class EmbeddedApiServer:
    """Run the local FastAPI service beside the desktop GUI.

    When an existing StreamingFinder API is already listening on the configured
    address (for example a developer-run Uvicorn process), the desktop app simply
    reuses it instead of trying to bind the port a second time.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        self.host = host
        self.port = port
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self.owns_server = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, timeout_seconds: float = 5.0) -> None:
        if self._streamingfinder_is_running():
            self.owns_server = False
            return

        if self._port_is_in_use():
            raise RuntimeError(
                f"Port {self.port} is already in use by another application. "
                "StreamingFinder's desktop window can still open, but its local API "
                "will be unavailable until that port is free."
            )

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="critical",
            access_log=False,
            loop="asyncio",
            http="h11",
            ws="none",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self.server.run,
            name="StreamingFinderAPI",
            daemon=True,
        )
        self.thread.start()
        self.owns_server = True

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._streamingfinder_is_running():
                return
            if self.thread is not None and not self.thread.is_alive():
                break
            time.sleep(0.05)

        self.stop()
        raise RuntimeError("StreamingFinder's local API did not start successfully.")

    def stop(self) -> None:
        if not self.owns_server:
            return

        if self.server is not None:
            self.server.should_exit = True

        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        self.owns_server = False

    def _streamingfinder_is_running(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/", timeout=0.25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            return False

        return payload.get("name") == "Streaming Finder API"

    def _port_is_in_use(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((self.host, self.port)) == 0
