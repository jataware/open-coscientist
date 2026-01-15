"""
Hybrid tool provider for unified access to MCP and Python tools

Provides composition pattern wrapping MCPToolClient and PythonToolRegistry
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..mcp_client import MCPToolClient
from .registry import PythonToolRegistry

logger = logging.getLogger(__name__)


class HybridToolProvider:
    """
    Unified interface for MCP and Python tools.

    Routes tool calls to appropriate executor based on tool source

    example usage:
        provider = HybridToolProvider(
            mcp_client=mcp_client,
            python_registry=literature_tools
        )

        tools_dict, openai_tools = provider.get_tools(
            mcp_whitelist=["pubmed_search_with_fulltext"],
            python_whitelist=["rank_papers_by_quality"]
        )

        result = await provider.execute_tool_call(tool_call)
    """

    def __init__(
        self,
        mcp_client: Optional[MCPToolClient] = None,
        python_registry: Optional[PythonToolRegistry] = None,
    ):
        """
        Initialize hybrid tool provider

        args:
            mcp_client: optional MCP client for MCP tools
            python_registry: optional Python tool registry
        """
        self.mcp_client = mcp_client
        self.python_registry = python_registry

        # track tool sources for routing
        self._tool_sources: Dict[str, str] = {}  # tool_name → "mcp" or "python"

    def get_tools(
        self,
        mcp_whitelist: Optional[List[str]] = None,
        python_whitelist: Optional[List[str]] = None,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Get merged tools from MCP and Python sources

        args:
            mcp_whitelist: optional list of MCP tool names to include
            python_whitelist: optional list of Python tool names to include

        returns:
            tuple of (tools_dict, openai_tools_list)
            tools_dict is combined {tool_name: tool_object} for both sources
            openai_tools_list is combined list of OpenAI-format tools
        """
        merged_tools_dict = {}
        merged_openai_tools = []

        # get MCP tools
        if self.mcp_client is not None and mcp_whitelist is not None:
            try:
                mcp_tools_dict, mcp_openai_tools = self.mcp_client.get_tools(
                    whitelist=mcp_whitelist
                )

                # track tool sources
                for tool_name in mcp_tools_dict.keys():
                    self._tool_sources[tool_name] = "mcp"

                merged_tools_dict.update(mcp_tools_dict)
                merged_openai_tools.extend(mcp_openai_tools)

                logger.debug(f"added {len(mcp_tools_dict)} MCP tools")
            except Exception as e:
                logger.warning(f"Failed to get MCP tools: {e}")

        # get Python tools
        if self.python_registry is not None and python_whitelist is not None:
            try:
                python_functions, python_openai_tools = self.python_registry.get_tools(
                    whitelist=python_whitelist
                )

                # track tool sources
                for tool_name in python_functions.keys():
                    self._tool_sources[tool_name] = "python"

                # Python tools stored as functions, not tool objects
                # store them in merged dict for tracking
                merged_tools_dict.update(python_functions)
                merged_openai_tools.extend(python_openai_tools)

                logger.debug(f"added {len(python_functions)} Python tools")
            except Exception as e:
                logger.warning(f"Failed to get Python tools: {e}")

        logger.info(
            f"hybrid provider ready: {len(merged_tools_dict)} total tools "
            f"({len([s for s in self._tool_sources.values() if s == 'mcp'])} MCP, "
            f"{len([s for s in self._tool_sources.values() if s == 'python'])} Python)"
        )

        return merged_tools_dict, merged_openai_tools

    async def execute_tool_call(self, tool_call: Any) -> Dict[str, Any]:
        """
        Execute a tool call by routing to appropriate executor

        args:
            tool_call: LiteLLM tool call object with .id, .function.name, .function.arguments

        returns:
            tool response message dict: {role: "tool", name: ..., tool_call_id: ..., content: ...}
        """
        tool_name = tool_call.function.name
        tool_call_id = tool_call.id

        # check tool source
        tool_source = self._tool_sources.get(tool_name)

        if tool_source is None:
            error_msg = f"unknown tool: {tool_name}"
            logger.error(error_msg)
            return self._create_error_response(tool_name, tool_call_id, error_msg)

        # route to appropriate executor
        try:
            if tool_source == "mcp":
                return await self._execute_mcp_tool(tool_call)
            elif tool_source == "python":
                return await self._execute_python_tool(tool_call)
            else:
                error_msg = f"invalid tool source: {tool_source}"
                logger.error(error_msg)
                return self._create_error_response(tool_name, tool_call_id, error_msg)

        except Exception as e:
            error_msg = f"tool execution failed: {str(e)}"
            logger.error(f"{tool_name} error: {error_msg}")
            return self._create_error_response(tool_name, tool_call_id, error_msg)

    async def _execute_mcp_tool(self, tool_call: Any) -> Dict[str, Any]:
        """
        Execute MCP tool call

        args:
            tool_call: LiteLLM tool call object

        returns:
            tool response message dict
        """
        if self.mcp_client is None:
            raise ValueError("MCP client not configured")

        # delegate to MCP client
        return await self.mcp_client.execute_tool_call(tool_call)

    async def _execute_python_tool(self, tool_call: Any) -> Dict[str, Any]:
        """
        Execute Python tool call

        args:
            tool_call: LiteLLM tool call object

        returns:
            tool response message dict
        """
        if self.python_registry is None:
            raise ValueError("Python registry not configured")

        tool_name = tool_call.function.name
        tool_call_id = tool_call.id

        # get function
        func = self.python_registry.get_function(tool_name)
        if func is None:
            raise ValueError(f"Python function not found: {tool_name}")

        # parse arguments
        try:
            args_dict = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON arguments: {e}")

        logger.debug(f"calling Python tool: {tool_name} with args: {args_dict}")

        # call function
        result = await func(**args_dict)

        # serialize result
        result_json = json.dumps(result)

        # return tool message
        return {
            "role": "tool",
            "name": tool_name,
            "tool_call_id": tool_call_id,
            "content": result_json,
        }

    def _create_error_response(
        self, tool_name: str, tool_call_id: str, error_msg: str
    ) -> Dict[str, Any]:
        """
        Create error response message for failed tool call

        args:
            tool_name: name of tool that failed
            tool_call_id: tool call ID
            error_msg: error message

        returns:
            tool response message dict with error
        """
        return {
            "role": "tool",
            "name": tool_name,
            "tool_call_id": tool_call_id,
            "content": json.dumps({"error": error_msg}),
        }
