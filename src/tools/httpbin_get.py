from typing import Any, Dict

from src.core.models import ToolResult
from src.core.retry import with_retries
from src.adapters.http_client import HttpClient
from src.tools.base import Tool


class HttpbinGetTool(Tool):
    name = "httpbin_get"
    requires_approval = True

    def run(self, *, args: Dict[str, Any]) -> ToolResult:
        url = args.get("url") or "https://httpbin.org/get"

        client = HttpClient(timeout_seconds=4.0)

        try:
            data = with_retries(lambda: client.get_json(url), retries=2, backoff_seconds=0.4)
            # Normalize the output: only keep stable fields
            output = {
                "url": data.get("url"),
                "origin": data.get("origin"),
                "headers_present": bool(data.get("headers")),
            }
            return ToolResult(ok=True, tool=self.name, output=output)
        except Exception as e:
            return ToolResult(ok=False, tool=self.name, output={}, error=str(e))