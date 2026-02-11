"""
Tool registry for managing MCP tool configurations.

Handles loading YAML configs, environment variable substitution,
merging user configs with defaults, and providing access to tool definitions.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .schema import ServerConfig, ToolConfig, ToolsConfig, WorkflowConfig

logger = logging.getLogger(__name__)

# default config file location (relative to this module)
DEFAULT_CONFIG_PATH = Path(__file__).parent / "tools.yaml"

# user config locations (in order of precedence)
USER_CONFIG_PATHS = [
    Path.home() / ".coscientist" / "tools.yaml",
    Path.home() / ".config" / "coscientist" / "tools.yaml",
]


def substitute_env_vars(value: Any) -> Any:
    """
    Substitute environment variables in a value.

    Supports formats:
    - ${VAR} - required env var
    - ${VAR:-default} - env var with default

    Args:
        value: Value to process (string, dict, list, or other)

    Returns:
        Value with environment variables substituted
    """
    if isinstance(value, str):
        # pattern: ${VAR} or ${VAR:-default}
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.environ.get(var_name)
            if env_value is not None:
                return env_value
            if default is not None:
                return default
            # return empty string if no env var and no default
            logger.warning(f"environment variable {var_name} not set and no default provided")
            return ""

        return re.sub(pattern, replacer, value)

    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [substitute_env_vars(item) for item in value]

    return value


def parse_bool_env(value: str) -> bool:
    """Parse a string value as boolean."""
    return value.lower() in ("true", "1", "yes", "on")


class ToolRegistry:
    """
    Central registry for tool configurations.

    Loads tool definitions from YAML configs, supports user overrides,
    and provides access methods for nodes and prompt builders.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        disabled_tools: Optional[List[str]] = None,
        skip_user_config: bool = False,
    ):
        """
        Initialize the tool registry.

        Args:
            config_path: Optional path to custom YAML config (overrides defaults)
            disabled_tools: Optional list of tool IDs to disable
            skip_user_config: If True, don't load user config from ~/.coscientist/
        """
        self._config: Optional[ToolsConfig] = None
        self._custom_config_path = config_path
        self._disabled_tools = set(disabled_tools or [])
        self._skip_user_config = skip_user_config

        # load config on init
        self._load_config()

    def _load_config(self) -> None:
        """Load and merge configuration files."""
        # start with default config
        default_data = self._load_yaml_file(DEFAULT_CONFIG_PATH)
        if default_data is None:
            logger.warning(f"default config not found at {DEFAULT_CONFIG_PATH}, using empty config")
            default_data = {}

        # load user config if exists
        user_data = None
        if not self._skip_user_config:
            for user_path in USER_CONFIG_PATHS:
                user_data = self._load_yaml_file(user_path)
                if user_data is not None:
                    logger.info(f"loaded user config from {user_path}")
                    break

        # load custom config if specified
        custom_data = None
        if self._custom_config_path:
            custom_data = self._load_yaml_file(Path(self._custom_config_path))
            if custom_data is not None:
                logger.info(f"loaded custom config from {self._custom_config_path}")
            else:
                logger.warning(f"custom config not found at {self._custom_config_path}")

        # merge configs
        merged_data = self._merge_configs(default_data, user_data, custom_data)

        # substitute environment variables
        merged_data = substitute_env_vars(merged_data)

        # parse enabled values that might be env var strings
        self._parse_enabled_values(merged_data)

        # create config object
        self._config = ToolsConfig.from_dict(merged_data)

        # apply disabled tools
        self._apply_disabled_tools()

        logger.info(
            f"tool registry initialized: {len(self._config.servers)} servers, "
            f"{len(self._config.get_enabled_tools())} enabled tools"
        )

    def _load_yaml_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load a YAML file, returning None if not found."""
        try:
            if path.exists():
                with open(path) as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"failed to load {path}: {e}")
        return None

    def _parse_enabled_values(self, data: Dict[str, Any]) -> None:
        """Parse 'enabled' fields that might be string booleans from env vars."""
        # parse server enabled values
        for server_data in data.get("servers", {}).values():
            if isinstance(server_data.get("enabled"), str):
                server_data["enabled"] = parse_bool_env(server_data["enabled"])

        # parse tool enabled values
        for category_tools in data.get("tools", {}).values():
            for tool_data in category_tools.values():
                if isinstance(tool_data.get("enabled"), str):
                    tool_data["enabled"] = parse_bool_env(tool_data["enabled"])

    def _merge_configs(
        self,
        default: Dict[str, Any],
        user: Optional[Dict[str, Any]],
        custom: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Merge configuration dicts based on merge strategy.

        Priority: custom > user > default
        """
        result = dict(default)

        # determine merge strategy (from user or custom config)
        strategy = "override"
        if custom and "settings" in custom:
            strategy = custom.get("settings", {}).get("merge_strategy", "override")
        elif user and "settings" in user:
            strategy = user.get("settings", {}).get("merge_strategy", "override")

        # apply user config
        if user:
            result = self._merge_dict(result, user, strategy)

        # apply custom config (highest priority)
        if custom:
            result = self._merge_dict(result, custom, strategy)

        return result

    def _merge_dict(
        self, base: Dict[str, Any], overlay: Dict[str, Any], strategy: str
    ) -> Dict[str, Any]:
        """
        Merge overlay dict into base dict.

        Strategies:
        - override: overlay values replace base values for matching keys
        - extend: overlay adds to base, doesn't replace
        - replace: overlay completely replaces base
        """
        if strategy == "replace":
            return dict(overlay)

        result = dict(base)

        for key, value in overlay.items():
            if key not in result:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result[key], dict):
                # recursively merge dicts
                result[key] = self._merge_dict(result[key], value, strategy)
            elif strategy == "override":
                result[key] = value
            elif strategy == "extend":
                if isinstance(value, list) and isinstance(result[key], list):
                    result[key] = result[key] + value
                # for non-lists, extend doesn't replace existing values

        return result

    def _apply_disabled_tools(self) -> None:
        """Apply disabled_tools list to config."""
        if not self._disabled_tools or not self._config:
            return

        for tool_id in self._disabled_tools:
            tool = self._config.get_tool(tool_id)
            if tool:
                tool.enabled = False
                logger.debug(f"disabled tool: {tool_id}")

    @property
    def config(self) -> ToolsConfig:
        """Get the loaded configuration."""
        if self._config is None:
            raise RuntimeError("tool registry not initialized")
        return self._config

    def get_server(self, server_id: str) -> Optional[ServerConfig]:
        """Get a server configuration by ID."""
        return self.config.servers.get(server_id)

    def get_enabled_servers(self) -> Dict[str, ServerConfig]:
        """Get all enabled server configurations."""
        return {
            server_id: server
            for server_id, server in self.config.servers.items()
            if server.enabled
        }

    def get_tool(self, tool_id: str) -> Optional[ToolConfig]:
        """Get a tool configuration by ID."""
        return self.config.get_tool(tool_id)

    def get_enabled_tools(self) -> Dict[str, ToolConfig]:
        """Get all enabled tool configurations."""
        return self.config.get_enabled_tools()

    def get_tools_for_workflow(self, workflow_name: str) -> List[str]:
        """
        Get list of tool IDs for a workflow phase.

        Args:
            workflow_name: Name of workflow (literature_review, draft_generation, validation)

        Returns:
            List of tool IDs configured for this workflow
        """
        workflow = self.config.workflows.get(workflow_name)
        if not workflow:
            logger.warning(f"workflow '{workflow_name}' not found in config")
            return []

        # get all referenced tools, filtering to only enabled ones
        tool_ids = workflow.get_all_tools()
        enabled_ids = []
        for tool_id in tool_ids:
            tool = self.get_tool(tool_id)
            if tool and tool.enabled:
                enabled_ids.append(tool_id)
            elif tool_id:  # only warn if tool_id is not empty
                logger.debug(f"tool '{tool_id}' in workflow '{workflow_name}' is disabled or missing")

        return enabled_ids

    def get_workflow(self, workflow_name: str) -> Optional[WorkflowConfig]:
        """Get a workflow configuration by name."""
        return self.config.workflows.get(workflow_name)

    def get_mcp_tool_names(self, tool_ids: List[str]) -> List[str]:
        """
        Convert tool IDs to MCP tool names.

        Args:
            tool_ids: List of internal tool IDs

        Returns:
            List of actual MCP tool names
        """
        mcp_names = []
        for tool_id in tool_ids:
            tool = self.get_tool(tool_id)
            if tool and tool.enabled:
                mcp_names.append(tool.mcp_tool_name)
        return mcp_names

    def get_tool_by_mcp_name(self, mcp_tool_name: str) -> Optional[ToolConfig]:
        """
        Find a tool config by its MCP tool name.

        Args:
            mcp_tool_name: The actual tool name on the MCP server

        Returns:
            ToolConfig if found, None otherwise
        """
        for tool in self.config.get_all_tools().values():
            if tool.mcp_tool_name == mcp_tool_name:
                return tool
        return None

    def get_server_configs_for_langchain(self) -> Dict[str, Dict[str, str]]:
        """
        Get server configs in format expected by langchain MultiServerMCPClient.

        Returns:
            Dict of {server_id: {"transport": ..., "url": ...}}
        """
        result = {}
        for server_id, server in self.get_enabled_servers().items():
            result[server_id] = {
                "transport": server.transport,
                "url": server.url,
            }
        return result


# global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry(
    config_path: Optional[str] = None,
    disabled_tools: Optional[List[str]] = None,
    force_reload: bool = False,
) -> ToolRegistry:
    """
    Get or create the global tool registry instance.

    Args:
        config_path: Optional path to custom config (only used on first call or force_reload)
        disabled_tools: Optional list of tools to disable (only used on first call or force_reload)
        force_reload: If True, reload configuration even if already initialized

    Returns:
        Initialized ToolRegistry instance
    """
    global _global_registry

    if _global_registry is None or force_reload:
        _global_registry = ToolRegistry(
            config_path=config_path,
            disabled_tools=disabled_tools,
        )

    return _global_registry


def reset_tool_registry() -> None:
    """Reset the global registry (primarily for testing)."""
    global _global_registry
    _global_registry = None
