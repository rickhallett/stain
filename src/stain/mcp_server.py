"""MCP server — exposes Stain tools for editor integration.

Usage: stain mcp serve
Protocol: JSON-RPC over stdio (MCP standard)
"""

from __future__ import annotations

import json
from typing import Any

from stain.config import load_config
from stain.orchestrator import analyse
from stain.registry import discover_detectors


TOOL_DEFINITIONS = [
    {
        "name": "analyse_text",
        "description": "Analyse text for LLM generation patterns. Returns composite score and per-detector breakdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to analyse"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "analyse_file",
        "description": "Analyse a file for LLM generation patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to text file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_detectors",
        "description": "List all available pattern detectors.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_detector_info",
        "description": "Get detailed info about a specific detector.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "detector_id": {"type": "string", "description": "Detector ID (e.g. D1)"},
            },
            "required": ["detector_id"],
        },
    },
]


def get_tool_definitions() -> list[dict]:
    """Return MCP tool definitions."""
    return TOOL_DEFINITIONS


def handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Handle an MCP tool call. Returns JSON string result."""
    if name == "analyse_text":
        result = analyse(arguments["text"])
        return json.dumps(result.model_dump(), indent=2)

    elif name == "analyse_file":
        from pathlib import Path
        path = Path(arguments["path"])
        if not path.is_file():
            return json.dumps({"error": f"File not found: {path}"})
        result = analyse(path.read_text())
        return json.dumps(result.model_dump(), indent=2)

    elif name == "list_detectors":
        detectors = discover_detectors(enabled_only=False)
        return json.dumps([
            {
                "id": info.id,
                "name": info.name,
                "version": info.version,
                "enabled": info.enabled,
                "weight": info.weight,
                "patterns": len(info.patterns),
            }
            for info in detectors.values()
        ], indent=2)

    elif name == "get_detector_info":
        detectors = discover_detectors(enabled_only=False)
        did = arguments["detector_id"]
        if did not in detectors:
            return json.dumps({"error": f"Detector not found: {did}"})
        info = detectors[did]
        return json.dumps({
            "id": info.id,
            "name": info.name,
            "version": info.version,
            "enabled": info.enabled,
            "weight": info.weight,
            "prompt_hash": info.prompt_hash,
            "patterns": [{"name": p.name, "description": p.description} for p in info.patterns],
        }, indent=2)

    else:
        raise ValueError(f"Unknown tool: {name}")


async def run_mcp_server():
    """Run the MCP server over stdio."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        raise RuntimeError(
            "MCP support requires the mcp package. Install with: "
            "pip install 'stain-cli[mcp]'"
        )

    server = Server("stain")

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = handle_tool_call(name, arguments)
        return [types.TextContent(type="text", text=result)]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
