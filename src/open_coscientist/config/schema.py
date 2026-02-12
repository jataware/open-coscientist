"""
Schema definitions for tool configuration.

Uses dataclasses to match existing codebase patterns.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


def resolve_content_params(
    params: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Resolve content params by substituting {placeholders} with context values.

    Supports:
        - {research_goal} - the current research goal
        - {focus_areas} - list of focus areas (from hypothesis categories, etc.)
        - Any other context key

    Args:
        params: Content params dict with potential {placeholder} values
        context: Runtime context containing values to substitute

    Returns:
        Resolved params dict with placeholders replaced
    """
    if not params:
        return {}

    resolved = {}
    placeholder_pattern = re.compile(r'\{(\w+)\}')

    for key, value in params.items():
        if isinstance(value, str):
            # check for placeholders like {research_goal}
            matches = placeholder_pattern.findall(value)
            if matches:
                resolved_value = value
                for match in matches:
                    if match in context:
                        context_val = context[match]
                        # handle full replacement vs partial
                        if value == f"{{{match}}}":
                            resolved_value = context_val
                        else:
                            resolved_value = resolved_value.replace(
                                f"{{{match}}}",
                                str(context_val) if not isinstance(context_val, str) else context_val
                            )
                resolved[key] = resolved_value
            else:
                resolved[key] = value
        elif isinstance(value, list):
            # resolve each item in list
            resolved_list = []
            for item in value:
                if isinstance(item, str) and placeholder_pattern.search(item):
                    matches = placeholder_pattern.findall(item)
                    resolved_item = item
                    for match in matches:
                        if match in context:
                            resolved_item = resolved_item.replace(f"{{{match}}}", str(context[match]))
                    resolved_list.append(resolved_item)
                else:
                    resolved_list.append(item)
            resolved[key] = resolved_list
        else:
            resolved[key] = value

    return resolved


@dataclass
class ServerConfig:
    """Configuration for an MCP server connection."""

    url: str
    transport: str = "streamable_http"
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerConfig":
        """Create ServerConfig from dictionary."""
        return cls(
            url=data.get("url", ""),
            transport=data.get("transport", "streamable_http"),
            enabled=data.get("enabled", True),
        )


@dataclass
class ResponseFormat:
    """
    Configuration for parsing tool responses.

    Attributes:
        type: Response type (json, boolean_string, etc.)
        results_path: JSONPath-like path to results (e.g., "." for root, "results" for nested)
        is_dict: Whether results are a dict (True) or list (False)
        field_mapping: Maps Article fields to response fields with optional transforms
    """

    type: str = "json"
    results_path: str = "."
    is_dict: bool = False
    field_mapping: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseFormat":
        """Create ResponseFormat from dictionary."""
        if not data:
            return cls()
        return cls(
            type=data.get("type", "json"),
            results_path=data.get("results_path", "."),
            is_dict=data.get("is_dict", False),
            field_mapping=data.get("field_mapping", {}),
        )


@dataclass
class ParameterConfig:
    """Configuration for a tool parameter."""

    type: str = "string"
    default: Optional[Any] = None
    required: bool = False
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterConfig":
        """Create ParameterConfig from dictionary."""
        if not data:
            return cls()
        return cls(
            type=data.get("type", "string"),
            default=data.get("default"),
            required=data.get("required", False),
            description=data.get("description", ""),
        )


@dataclass
class ToolConfig:
    """
    Configuration for an MCP tool.

    Attributes:
        server: Server ID this tool belongs to
        mcp_tool_name: Actual tool name on the MCP server
        display_name: Human-readable name for prompts
        description: Tool description for prompts
        category: Tool category (search, search_with_content, read, utility)
        source_type: Source type for articles (academic, preprint, etc.)
        enabled: Whether this tool is enabled
        response_format: Configuration for parsing responses
        prompt_snippet: Prompt text to include when this tool is available
        parameters: Tool parameter configurations
        parameter_mapping: Maps canonical parameter names to tool-specific names
        applies_to: Which sources this tool applies to (for generic tools)
    """

    server: str
    mcp_tool_name: str
    display_name: str = ""
    description: str = ""
    category: str = "utility"
    source_type: str = "academic"
    enabled: bool = True
    response_format: ResponseFormat = field(default_factory=ResponseFormat)
    prompt_snippet: str = ""
    parameters: Dict[str, ParameterConfig] = field(default_factory=dict)
    parameter_mapping: Dict[str, Optional[str]] = field(default_factory=dict)
    applies_to: str = "all"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], tool_id: str = "") -> "ToolConfig":
        """Create ToolConfig from dictionary."""
        # parse parameters
        params_data = data.get("parameters", {})
        parameters = {}
        for param_name, param_data in params_data.items():
            if isinstance(param_data, dict):
                parameters[param_name] = ParameterConfig.from_dict(param_data)
            else:
                # simple value (just a default)
                parameters[param_name] = ParameterConfig(default=param_data)

        return cls(
            server=data.get("server", "default"),
            mcp_tool_name=data.get("mcp_tool_name", tool_id),
            display_name=data.get("display_name", tool_id),
            description=data.get("description", ""),
            category=data.get("category", "utility"),
            source_type=data.get("source_type", "academic"),
            enabled=data.get("enabled", True),
            response_format=ResponseFormat.from_dict(data.get("response_format", {})),
            prompt_snippet=data.get("prompt_snippet", ""),
            parameters=parameters,
            parameter_mapping=data.get("parameter_mapping", {}),
            applies_to=data.get("applies_to", "all"),
        )

    def map_parameters(self, canonical_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map canonical parameter names to tool-specific parameter names.

        Args:
            canonical_params: Parameters using canonical names (e.g., max_papers, recency_years)

        Returns:
            Parameters using tool-specific names (e.g., max_results, starting_year)
        """
        if not self.parameter_mapping:
            # no mapping configured, return as-is
            return canonical_params

        mapped = {}
        for canonical_name, value in canonical_params.items():
            # check if mapping exists
            if canonical_name in self.parameter_mapping:
                tool_param_name = self.parameter_mapping[canonical_name]
                if tool_param_name is None:
                    # explicitly ignore this parameter (null in YAML)
                    continue
                # handle special conversions
                if canonical_name == "recency_years" and tool_param_name == "starting_year":
                    # convert recency_years (e.g., 7) to starting_year (e.g., 2019)
                    import datetime
                    current_year = datetime.datetime.now().year
                    mapped[tool_param_name] = current_year - value if value > 0 else None
                else:
                    mapped[tool_param_name] = value
            else:
                # no mapping, use canonical name
                mapped[canonical_name] = value

        return mapped


@dataclass
class SearchSourceConfig:
    """
    Configuration for a single search source in multi-source literature review.

    Attributes:
        tool: Tool ID for this search source (e.g., "pubmed_fulltext", "arxiv_search")
        papers_per_query: Number of papers to fetch per query from this source
        enabled: Whether this source is enabled
        content_tool: Optional tool to fetch content (overrides workflow-level setting)
        content_url_field: Field containing content URL (overrides workflow-level setting)
        content_params: Extra parameters to pass to content tool (supports {research_goal} substitution)
        pdf_discovery_tool: Optional tool to discover PDF links from landing page URL
        pdf_discovery_url_field: Field containing the URL to pass to pdf_discovery_tool
    """

    tool: str
    papers_per_query: int = 3
    enabled: bool = True
    content_tool: Optional[str] = None
    content_url_field: Optional[str] = None
    content_params: Dict[str, Any] = field(default_factory=dict)
    # Two-step content retrieval: first discover PDF links, then fetch content
    pdf_discovery_tool: Optional[str] = None  # e.g., "find_pdf_links"
    pdf_discovery_url_field: Optional[str] = None  # e.g., "url" (landing page)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchSourceConfig":
        """Create SearchSourceConfig from dictionary."""
        if isinstance(data, str):
            # simple format: just tool name
            return cls(tool=data)
        return cls(
            tool=data.get("tool", ""),
            papers_per_query=data.get("papers_per_query", 3),
            enabled=data.get("enabled", True),
            content_tool=data.get("content_tool"),
            content_url_field=data.get("content_url_field"),
            content_params=data.get("content_params", {}),
            pdf_discovery_tool=data.get("pdf_discovery_tool"),
            pdf_discovery_url_field=data.get("pdf_discovery_url_field"),
        )


@dataclass
class WorkflowConfig:
    """
    Configuration for a workflow phase.

    Defines which tools are available in each phase of hypothesis generation.

    For literature review, supports both single-source (primary_search) and
    multi-source (search_sources) configurations.
    """

    # Single-source mode (legacy/simple)
    primary_search: Optional[str] = None
    fallback_search: Optional[str] = None
    availability_check: Optional[str] = None

    # Multi-source mode
    search_sources: List[SearchSourceConfig] = field(default_factory=list)
    multi_source_strategy: str = "parallel"  # parallel, sequential
    deduplicate_across_sources: bool = True

    # General tool lists
    search_tools: List[str] = field(default_factory=list)
    read_tools: List[str] = field(default_factory=list)
    utility_tools: List[str] = field(default_factory=list)

    # Query generation via MCP tool (replaces hardcoded prompts)
    query_generation_tool: Optional[str] = None
    query_format: str = "boolean"  # "boolean" for PubMed, "natural_language" for arXiv/Scholar

    # Content retrieval for sources that don't return fulltext (e.g., arXiv)
    # Can be overridden per-source in search_sources
    content_tool: Optional[str] = None
    content_url_field: str = "pdf_url"
    content_params: Dict[str, Any] = field(default_factory=dict)

    # Two-step content retrieval: first discover PDF links from landing page
    # Used for sources like Google Scholar that return landing page URLs, not direct PDFs
    pdf_discovery_tool: Optional[str] = None  # e.g., "find_pdf_links"
    pdf_discovery_url_field: str = "url"  # field containing landing page URL

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        """Create WorkflowConfig from dictionary."""
        if not data:
            return cls()

        # parse search_sources list
        search_sources = []
        for source_data in data.get("search_sources", []):
            search_sources.append(SearchSourceConfig.from_dict(source_data))

        return cls(
            primary_search=data.get("primary_search"),
            fallback_search=data.get("fallback_search"),
            availability_check=data.get("availability_check"),
            search_sources=search_sources,
            multi_source_strategy=data.get("multi_source_strategy", "parallel"),
            deduplicate_across_sources=data.get("deduplicate_across_sources", True),
            search_tools=data.get("search_tools", []),
            read_tools=data.get("read_tools", []),
            utility_tools=data.get("utility_tools", []),
            query_generation_tool=data.get("query_generation_tool"),
            query_format=data.get("query_format", "boolean"),
            content_tool=data.get("content_tool"),
            content_url_field=data.get("content_url_field", "pdf_url"),
            content_params=data.get("content_params", {}),
            pdf_discovery_tool=data.get("pdf_discovery_tool"),
            pdf_discovery_url_field=data.get("pdf_discovery_url_field", "url"),
        )

    def get_enabled_search_sources(self) -> List[SearchSourceConfig]:
        """Get list of enabled search sources."""
        return [s for s in self.search_sources if s.enabled]

    def is_multi_source(self) -> bool:
        """Check if this workflow uses multi-source configuration."""
        return len(self.search_sources) > 0

    def get_all_tools(self) -> List[str]:
        """Get all tool IDs referenced in this workflow."""
        tools = []
        if self.primary_search:
            tools.append(self.primary_search)
        if self.fallback_search:
            tools.append(self.fallback_search)
        if self.availability_check:
            tools.append(self.availability_check)
        if self.query_generation_tool:
            tools.append(self.query_generation_tool)
        if self.content_tool:
            tools.append(self.content_tool)
        # add tools from search_sources
        for source in self.search_sources:
            tools.append(source.tool)
            if source.content_tool:
                tools.append(source.content_tool)
        tools.extend(self.search_tools)
        tools.extend(self.read_tools)
        tools.extend(self.utility_tools)
        return tools


@dataclass
class Settings:
    """Global settings for tool configuration."""

    auto_discover: bool = True
    merge_strategy: str = "override"  # override, extend, replace
    allow_disable_builtins: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """Create Settings from dictionary."""
        if not data:
            return cls()
        return cls(
            auto_discover=data.get("auto_discover", True),
            merge_strategy=data.get("merge_strategy", "override"),
            allow_disable_builtins=data.get("allow_disable_builtins", True),
        )


@dataclass
class ToolsConfig:
    """
    Root configuration object containing all tool definitions.

    This is the top-level structure parsed from tools.yaml.
    """

    version: str = "1.0"
    servers: Dict[str, ServerConfig] = field(default_factory=dict)
    tools: Dict[str, Dict[str, ToolConfig]] = field(default_factory=dict)
    workflows: Dict[str, WorkflowConfig] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolsConfig":
        """Create ToolsConfig from dictionary (parsed YAML)."""
        # parse servers
        servers = {}
        for server_id, server_data in data.get("servers", {}).items():
            servers[server_id] = ServerConfig.from_dict(server_data)

        # parse tools by category
        tools: Dict[str, Dict[str, ToolConfig]] = {}
        tools_data = data.get("tools", {})
        for category, category_tools in tools_data.items():
            tools[category] = {}
            for tool_id, tool_data in category_tools.items():
                tools[category][tool_id] = ToolConfig.from_dict(tool_data, tool_id)

        # parse workflows
        workflows = {}
        for workflow_id, workflow_data in data.get("workflows", {}).items():
            workflows[workflow_id] = WorkflowConfig.from_dict(workflow_data)

        # parse settings
        settings = Settings.from_dict(data.get("settings", {}))

        return cls(
            version=data.get("version", "1.0"),
            servers=servers,
            tools=tools,
            workflows=workflows,
            settings=settings,
        )

    def get_tool(self, tool_id: str) -> Optional[ToolConfig]:
        """Get a tool config by ID, searching all categories."""
        for category_tools in self.tools.values():
            if tool_id in category_tools:
                return category_tools[tool_id]
        return None

    def get_all_tools(self) -> Dict[str, ToolConfig]:
        """Get all tools as a flat dict."""
        all_tools = {}
        for category_tools in self.tools.values():
            all_tools.update(category_tools)
        return all_tools

    def get_enabled_tools(self) -> Dict[str, ToolConfig]:
        """Get all enabled tools as a flat dict."""
        return {
            tool_id: tool
            for tool_id, tool in self.get_all_tools().items()
            if tool.enabled
        }

    def get_tools_by_category(self, category: str) -> Dict[str, ToolConfig]:
        """Get tools in a specific category."""
        return self.tools.get(category, {})

    def get_tools_for_server(self, server_id: str) -> Dict[str, ToolConfig]:
        """Get all tools belonging to a specific server."""
        return {
            tool_id: tool
            for tool_id, tool in self.get_all_tools().items()
            if tool.server == server_id
        }
