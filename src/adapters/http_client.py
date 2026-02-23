from typing import Any, Dict, Optional
import httpx


class HttpClient:
    def __init__(self, *, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def get_json(self, url: str) -> Dict[str, Any]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.json()