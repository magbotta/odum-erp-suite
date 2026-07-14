"""
Minimal MCP consumer client.

Calls external MCP tool servers as one of the agent's allowed action types.
Responses are treated as untrusted external data — never as instructions.

See ADR-0001 §MCP Consumer Design for the security model.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MCPToolError(Exception):
    pass


class MCPToolNotAllowed(MCPToolError):
    pass


class MCPClient:
    """Calls an external MCP server's tool and returns the response as data."""

    CALL_TIMEOUT = 30  # seconds

    def __init__(self, allowed_tools: List[Dict[str, Any]]):
        """
        allowed_tools: list of {server_url, tool_name, description} from AgentDefinition.
        Only tools in this list can be called — any other call raises MCPToolNotAllowed.
        """
        self._allowed = {
            (t["server_url"].rstrip("/"), t["tool_name"]): t
            for t in (allowed_tools or [])
        }

    def call(self, server_url: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an MCP tool and return its output tagged as untrusted.

        Returns:
            {"source": "mcp", "trusted": False, "server_url": ..., "tool_name": ...,
             "output": <tool output>, "error": None}

        Never raises on MCP-server errors — returns {"error": "..."} instead
        so the executor can decide whether to handoff.
        """
        key = (server_url.rstrip("/"), tool_name)
        if key not in self._allowed:
            raise MCPToolNotAllowed(
                "Tool {0}::{1} is not in the agent's allowed_mcp_tools".format(
                    server_url, tool_name
                )
            )

        payload = json.dumps({
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }).encode()

        req = urllib.request.Request(
            server_url.rstrip("/") + "/mcp",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        result: Dict[str, Any] = {
            "source": "mcp",
            "trusted": False,
            "server_url": server_url,
            "tool_name": tool_name,
            "output": None,
            "error": None,
        }

        try:
            with urllib.request.urlopen(req, timeout=self.CALL_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                # MCP protocol wraps results; we surface content only
                result["output"] = data.get("result", {}).get("content", data)
        except urllib.error.HTTPError as exc:
            result["error"] = "HTTP {0}: {1}".format(exc.code, exc.reason)
            logger.warning("MCPClient: HTTP error from %s::%s — %s", server_url, tool_name, exc)
        except urllib.error.URLError as exc:
            result["error"] = "Connection error: {0}".format(exc.reason)
            logger.warning("MCPClient: connection error from %s::%s — %s", server_url, tool_name, exc)
        except Exception as exc:
            result["error"] = "Unexpected error: {0}".format(exc)
            logger.exception("MCPClient: unexpected error calling %s::%s", server_url, tool_name)

        return result
