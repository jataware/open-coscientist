"""
MCP (Model Context Protocol) client for interacting with MCP servers.

This module provides utilities for connecting to MCP servers and accessing
their tools for use with LiteLLM agents.

Supports both single-server (legacy) and multi-server configurations.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_mcp_adapters.client import MultiServerMCPClient

if TYPE_CHECKING:
    from .config import ToolRegistry

logger = logging.getLogger(__name__)


class MCPToolClient:
    """
    Client for accessing MCP tools from one or more MCP servers.

    Supports both legacy single-server mode and multi-server mode via ToolRegistry.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        server_configs: Optional[Dict[str, Dict[str, str]]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize the MCP client.

        Args:
            server_url: URL of a single MCP server (legacy mode). If None, reads from
                       MCP_SERVER_URL env var, falling back to http://localhost:8888/mcp
            server_configs: Dict of server configs for multi-server mode.
                           Format: {server_id: {"transport": "...", "url": "..."}}
            tool_registry: ToolRegistry instance for config-driven multi-server mode.
                          Takes precedence over server_configs and server_url.

        At least one of server_url, server_configs, or tool_registry must be provided
        (or server_url will default from environment).
        """
        self._tool_registry = tool_registry
        self._server_configs: Dict[str, Dict[str, str]] = {}
        self._client: Optional[MultiServerMCPClient] = None
        self._tools_dict: Optional[Dict[str, Any]] = None
        self._openai_tools: Optional[List[Dict[str, Any]]] = None
        self._tool_to_server: Dict[str, str] = {}  # maps tool_name -> server_id

        # determine server configuration
        if tool_registry is not None:
            # use registry-provided server configs
            self._server_configs = tool_registry.get_server_configs_for_langchain()
            logger.debug(f"using {len(self._server_configs)} servers from tool registry")
        elif server_configs is not None:
            self._server_configs = server_configs
            logger.debug(f"using {len(self._server_configs)} provided server configs")
        else:
            # legacy single-server mode
            if server_url is None:
                server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")
            self._server_configs = {
                "default": {
                    "transport": "streamable_http",
                    "url": server_url,
                }
            }
            logger.debug(f"using single server: {server_url}")

        # store for backwards compatibility
        self.server_url = list(self._server_configs.values())[0].get("url") if self._server_configs else None

    async def initialize(self):
        """Initialize the client and fetch available tools from all servers."""
        if self._client is not None:
            logger.debug("MCP client already initialized")
            return

        if not self._server_configs:
            raise RuntimeError("no server configurations available")

        server_names = list(self._server_configs.keys())
        logger.info(f"initializing MCP client for {len(server_names)} server(s): {server_names}")

        self._client = MultiServerMCPClient(self._server_configs)
        tools = await self._client.get_tools()

        # create dict for easy lookup and track which server provides each tool
        self._tools_dict = {}
        self._tool_to_server = {}

        for tool in tools:
            self._tools_dict[tool.name] = tool
            # infer server from tool metadata if available
            # MultiServerMCPClient prefixes tools with server name in some versions
            # For now, we'll track based on the tool registry if available
            if self._tool_registry:
                tool_config = self._tool_registry.get_tool_by_mcp_name(tool.name)
                if tool_config:
                    self._tool_to_server[tool.name] = tool_config.server

        # convert to OpenAI format for LiteLLM
        self._openai_tools = [convert_to_openai_tool(tool) for tool in tools]

        logger.info(
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

        # wrap to support earlier/recent langchain versions
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

        # execute using the original MCP tool
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

        # filter tools by whitelist
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

    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Get the server ID that provides a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Server ID or None if unknown
        """
        return self._tool_to_server.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is available."""
        if self._tools_dict is None:
            return False
        return tool_name in self._tools_dict

    @property
    def available_tools(self) -> List[str]:
        """Get list of available tool names."""
        if self._tools_dict is None:
            return []
        return list(self._tools_dict.keys())


# global client instance
_global_client: Optional[MCPToolClient] = None


async def check_literature_source_available(
    server_url: Optional[str] = None,
    tool_registry: Optional["ToolRegistry"] = None,
) -> bool:
    """
    Check if the literature source is available via MCP server.

    Queries the configured availability check tool (e.g., check_pubmed_available)
    to verify the literature source is accessible.

    If no availability check tool is configured (availability_check: null in YAML),
    assumes the source is available as long as MCP server responds.

    Args:
        server_url: URL of the MCP server (legacy). If None, reads from MCP_SERVER_URL
        tool_registry: Optional ToolRegistry for config-driven tool lookup

    Returns:
        True if literature source is available via MCP server, False otherwise
    """
    # determine the availability check tool name from registry
    check_tool_name: Optional[str] = None
    skip_availability_check = False

    if tool_registry:
        workflow = tool_registry.get_workflow("literature_review")
        if workflow:
            if workflow.availability_check:
                # explicit check tool configured
                tool_config = tool_registry.get_tool(workflow.availability_check)
                if tool_config:
                    check_tool_name = tool_config.mcp_tool_name
            else:
                # availability_check is null/None - skip the check
                skip_availability_check = True
                logger.debug("availability check disabled in config (availability_check: null)")

    # default for backwards compat when no registry
    if check_tool_name is None and not skip_availability_check and tool_registry is None:
        check_tool_name = "check_pubmed_available"

    if server_url is None and tool_registry is None:
        server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")

    try:
        # first check if MCP server is up
        if not await check_mcp_available(server_url, tool_registry):
            logger.debug("mcp server unavailable, literature source unavailable")
            return False

        # if no availability check configured, assume available since MCP is up
        if skip_availability_check:
            logger.info("MCP server available, skipping source-specific availability check")
            return True

        # if no check tool configured but we have a registry, assume available
        if check_tool_name is None:
            logger.info("no availability check tool configured, assuming source available")
            return True

        logger.debug(f"checking literature source availability (tool: {check_tool_name})")

        # create client
        mcp_client = MCPToolClient(server_url=server_url, tool_registry=tool_registry)
        await mcp_client.initialize()

        # get available tools
        all_tools_dict, _ = mcp_client.get_tools()
        logger.debug(f"available mcp tools: {list(all_tools_dict.keys())}")

        if check_tool_name not in all_tools_dict:
            logger.warning(
                f"availability check tool '{check_tool_name}' not found. "
                f"available tools: {list(all_tools_dict.keys())}"
            )
            return False

        logger.debug(f"{check_tool_name} tool found, executing")

        # call tool directly
        result = await mcp_client.call_tool(check_tool_name)

        # result should be a boolean or "true"/"false" string
        if isinstance(result, bool):
            return result
        elif isinstance(result, str):
            return result.lower() == "true"
        else:
            logger.warning(f"unexpected result from {check_tool_name}: {result}")
            return False

    except Exception as e:
        logger.warning(f"error checking literature source availability: {type(e).__name__}: {e}")
        logger.debug(f"full traceback: {e}", exc_info=True)
        return False


# backwards compatibility alias
async def check_pubmed_available_via_mcp(
    server_url: Optional[str] = None,
    tool_registry: Optional["ToolRegistry"] = None,
) -> bool:
    """Deprecated: use check_literature_source_available instead."""
    return await check_literature_source_available(server_url, tool_registry)


async def check_mcp_available(
    server_url: Optional[str] = None,
    tool_registry: Optional["ToolRegistry"] = None,
) -> bool:
    """
    Check if MCP server is available and responding.

    Args:
        server_url: URL of the MCP server (legacy)
        tool_registry: Optional ToolRegistry for multi-server configs

    Returns:
        True if MCP server is available and responding, False otherwise
    """
    if server_url is None and tool_registry is None:
        server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8888/mcp")

    try:
        if tool_registry:
            logger.debug(f"testing mcp availability for {len(tool_registry.get_enabled_servers())} server(s)")
        else:
            logger.debug(f"testing mcp server availability at {server_url}")

        test_client = MCPToolClient(server_url=server_url, tool_registry=tool_registry)
        await test_client.initialize()

        # check if we got any tools
        if test_client._tools_dict and len(test_client._tools_dict) > 0:
            logger.info(f"MCP server available with {len(test_client._tools_dict)} tools")
            return True
        else:
            logger.warning("MCP server responded but provided no tools")
            return False

    except Exception as e:
        if tool_registry:
            logger.warning(f"MCP servers unavailable: {e}")
        else:
            logger.warning(f"MCP server unavailable at {server_url}")
        return False


async def get_mcp_client(
    server_url: Optional[str] = None,
    tool_registry: Optional["ToolRegistry"] = None,
    force_new: bool = False,
) -> MCPToolClient:
    """
    Get or create the global MCP client instance.

    Args:
        server_url: URL of the MCP server (legacy)
        tool_registry: Optional ToolRegistry for config-driven setup
        force_new: If True, create a new client even if one exists

    Returns:
        Initialized MCPToolClient instance
    """
    global _global_client

    if _global_client is None or force_new:
        _global_client = MCPToolClient(server_url=server_url, tool_registry=tool_registry)

    # always ensure it's initialized (safe to call multiple times)
    await _global_client.initialize()

    return _global_client


def reset_mcp_client() -> None:
    """Reset the global MCP client (primarily for testing)."""
    global _global_client
    _global_client = None
