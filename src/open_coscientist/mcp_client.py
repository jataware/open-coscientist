"""
MCP (Model Context Protocol) client for interacting with MCP servers.

This module provides utilities for connecting to MCP servers and accessing
their tools for use with LiteLLM agents.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class MCPToolClient:
    """
    Client for accessing MCP tools from literature review servers.

    This client connects to an MCP server and provides access to
    literature review and reasoning tools.
    """

    def __init__(self, server_url: Optional[str] = None):
        """
        Initialize the MCP client.

        Args:
            server_url: URL of the MCP server. If None, reads from MCP_SERVER_URL env var,
                       falling back to http://localhost:8888/mcp
        """
        if server_url is None:
            server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")

        self.server_url = server_url
        self._client: Optional[MultiServerMCPClient] = None
        self._tools_dict: Optional[Dict[str, Any]] = None
        self._openai_tools: Optional[List[Dict[str, Any]]] = None

    async def initialize(self):
        """Initialize the client and fetch available tools."""
        if self._client is not None:
            logger.debug("MCP client already initialized")
            return

        logger.info(f"Initializing MCP client for {self.server_url}")

        servers = {
            "mcp_server": {
                "transport": "streamable_http",
                "url": self.server_url
            }
        }

        self._client = MultiServerMCPClient(servers)
        tools = await self._client.get_tools()

        # Create a dict for easy lookup
        self._tools_dict = {tool.name: tool for tool in tools}

        # Convert to OpenAI format for LiteLLM
        self._openai_tools = [convert_to_openai_tool(tool) for tool in tools]

        logger.debug(
            f"MCP client initialized with {len(self._tools_dict)} tools: {list(self._tools_dict.keys())}"
        )

    async def call_tool(self, tool_name: str, **kwargs) -> str:
        """
        Call an MCP tool directly with arguments.

        This is a convenience method for calling tools directly without
        constructing a LiteLLM-style tool call object.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments as keyword arguments

        Returns:
            Tool result as a string (often JSON)

        Raises:
            RuntimeError: If client not initialized
            ValueError: If tool not found
        """
        if self._tools_dict is None:
            raise RuntimeError("mcp client not initialized. call initialize() first.")

        if tool_name not in self._tools_dict:
            raise ValueError(
                f"tool '{tool_name}' not found. "
                f"available tools: {list(self._tools_dict.keys())}"
            )

        logger.debug(f"calling mcp tool: {tool_name} with args: {kwargs}")

        result = await self._tools_dict[tool_name].ainvoke(kwargs)

        # Wrap to support earlier/recent langchain versions
        if isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], dict) and "text" in result[0]:
                result = result[0]["text"]

        logger.debug(
            f"mcp tool result for {tool_name}: "
            f"{str(result)[:200]}{'...' if len(str(result)) > 200 else ''}"
        )

        return result

    async def execute_tool_call(self, tool_call) -> Dict[str, Any]:
        """
        Execute an MCP tool call.

        Args:
            tool_call: Tool call object from LiteLLM with function name and arguments

        Returns:
            Dictionary formatted as a tool response message
        """
        if self._tools_dict is None:
            raise RuntimeError("mcp client not initialized. call initialize() first.")

        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        logger.debug(f"executing mcp tool: {tool_name} with args: {tool_args}")

        # Execute using the original MCP tool
        result = await self._tools_dict[tool_name].ainvoke(tool_args)

        logger.debug(
            f"mcp tool result for {tool_name}: {str(result)[:200]}{'...' if len(str(result)) > 200 else ''}"
        )

        return {
            "role": "tool",
            "name": tool_name,
            "tool_call_id": tool_call.id,
            "content": result,  # MCP tools return strings (often JSON)
        }

    def get_tools(
        self, whitelist: Optional[List[str]] = None
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get MCP tools, optionally filtered by whitelist.

        Args:
            whitelist: Optional list of tool names to include. If None, returns all tools.

        Returns:
            Tuple of (tools_dict, openai_tools) where:
            - tools_dict: Dict mapping tool names to tool objects
            - openai_tools: List of tools in OpenAI format for LiteLLM
        """
        if self._tools_dict is None or self._openai_tools is None:
            raise RuntimeError("MCP client not initialized. Call initialize() first.")

        if whitelist is None:
            return self._tools_dict, self._openai_tools

        # Filter tools by whitelist
        filtered_tools_dict = {k: v for k, v in self._tools_dict.items() if k in whitelist}
        filtered_openai_tools = [
            convert_to_openai_tool(filtered_tools_dict[k])
            for k in whitelist
            if k in filtered_tools_dict
        ]

        logger.debug(
            f"filtered to {len(filtered_tools_dict)} tools: {list(filtered_tools_dict.keys())}"
        )

        return filtered_tools_dict, filtered_openai_tools


# Global client instance
_global_client: Optional[MCPToolClient] = None


async def check_pubmed_available_via_mcp(server_url: Optional[str] = None) -> bool:
    """
    check if PubMed is available by querying the MCP server.

    Args:
        server_url: URL of the MCP server. If None, reads from MCP_SERVER_URL env var,
                   falling back to http://localhost:8888/mcp

    Returns:
        True if PubMed is available and accessible via MCP server, False otherwise
    """
    if server_url is None:
        server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")

    logger.debug(f"checking pubmed availability via mcp at {server_url}")

    try:
        # first check if MCP server is up
        if not await check_mcp_available(server_url):
            logger.debug("mcp server unavailable, pubmed unavailable")
            return False

        # call check_pubmed_available tool on MCP server
        mcp_client = MCPToolClient(server_url)
        await mcp_client.initialize()

        # get available tools
        all_tools_dict, _ = mcp_client.get_tools()
        logger.debug(f"available mcp tools: {list(all_tools_dict.keys())}")

        tools_dict, _ = mcp_client.get_tools(whitelist=["check_pubmed_available"])

        if "check_pubmed_available" not in tools_dict:
            logger.warning(
                f"Tool check_pubmed_available not found on MCP server. Available tools: {list(all_tools_dict.keys())}"
            )
            return False

        logger.debug("check_pubmed_available tool found, executing")

        # call tool directly using new call_tool method
        result = await mcp_client.call_tool("check_pubmed_available")

        # result should be a boolean or "true"/"false" string
        if isinstance(result, bool):
            return result
        elif isinstance(result, str):
            return result.lower() == "true"
        else:
            logger.warning(f"Unexpected result from check_pubmed_available: {result}")
            return False

    except Exception as e:
        logger.warning(f"Error checking pubmed availability via mcp: {type(e).__name__}: {e}")
        logger.debug(f"full traceback: {e}", exc_info=True)
        return False


async def check_mcp_available(server_url: Optional[str] = None) -> bool:
    """
    Check if MCP server is available and responding.

    Args:
        server_url: URL of the MCP server. If None, reads from MCP_SERVER_URL env var,
                   falling back to http://localhost:8888/mcp

    Returns:
        True if MCP server is available and responding, False otherwise
    """
    if server_url is None:
        server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")

    try:
        logger.debug(f"testing mcp server availability at {server_url}")

        test_client = MCPToolClient(server_url)
        await test_client.initialize()

        # check if we got any tools
        if test_client._tools_dict and len(test_client._tools_dict) > 0:
            logger.info(
                f"MCP server available at {server_url} with {len(test_client._tools_dict)} tools"
            )
            return True
        else:
            logger.warning("MCP server responded but provided no tools")
            return False

    except Exception:
        logger.warning(f"MCP server unavailable at {server_url}")
        return False


async def get_mcp_client(server_url: Optional[str] = None) -> MCPToolClient:
    """
    Get or create the global MCP client instance.

    Args:
        server_url: URL of the MCP server. If None, reads from MCP_SERVER_URL env var,
                   falling back to http://localhost:8888/mcp

    Returns:
        Initialized MCPToolClient instance
    """
    global _global_client

    if _global_client is None:
        _global_client = MCPToolClient(server_url)

    # always ensure it's initialized (safe to call multiple times)
    await _global_client.initialize()

    return _global_client
