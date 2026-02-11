"""
Response parser for converting MCP tool responses to Article objects.

Supports dynamic field mapping with transformations defined in YAML configs.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from ..config.schema import ResponseFormat, ToolConfig
from ..models import Article

logger = logging.getLogger(__name__)


class ResponseParser:
    """
    Parse MCP tool responses using YAML-defined field mappings.

    Supports:
    - Direct field access: "title" -> item["title"]
    - Dict key as value: "@key" -> dict key
    - URL from key: "@url_from_key" -> constructs URL from dict key
    - Static values: "'pubmed'" -> "pubmed"
    - Transform chains: "date_revised|split:/|index:0|int"
    - Nested paths: "metadata.title" -> item["metadata"]["title"]
    - Default values: "citations|default:0"
    - Wrap in list: "pdf_url|wrap_list" -> [value] if not None
    """

    def __init__(self, tool_config: ToolConfig):
        """
        Initialize parser with tool configuration.

        Args:
            tool_config: Tool configuration containing response_format
        """
        self.tool_config = tool_config
        self.response_format = tool_config.response_format

    def parse_response(self, response: Any) -> Any:
        """
        Parse raw response based on response_format type.

        Args:
            response: Raw response from MCP tool (string or dict/list)

        Returns:
            Parsed response data
        """
        # handle string responses (JSON)
        if isinstance(response, str):
            response = response.strip()
            if self.response_format.type == "boolean_string":
                return response.lower() == "true"
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                logger.warning(f"failed to parse JSON response: {response[:100]}...")
                return response

        return response

    def parse_to_articles(self, response: Any) -> List[Article]:
        """
        Parse tool response into Article objects.

        Args:
            response: Raw response from MCP tool

        Returns:
            List of Article objects
        """
        # parse raw response
        data = self.parse_response(response)

        if data is None:
            return []

        # navigate to results using results_path
        results = self._navigate_path(data, self.response_format.results_path)

        if results is None:
            logger.warning("results_path returned None")
            return []

        articles = []

        if self.response_format.is_dict:
            # results is a dict {key: item}
            if not isinstance(results, dict):
                logger.warning(f"expected dict but got {type(results)}")
                return []

            for key, item in results.items():
                try:
                    article = self._map_item_to_article(item, dict_key=key)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"failed to map item {key}: {e}")
        else:
            # results is a list
            if not isinstance(results, list):
                # try to treat as single item
                results = [results]

            for i, item in enumerate(results):
                try:
                    article = self._map_item_to_article(item)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"failed to map item {i}: {e}")

        logger.debug(f"parsed {len(articles)} articles from response")
        return articles

    def _navigate_path(self, data: Any, path: str) -> Any:
        """
        Navigate to a nested path in data.

        Args:
            data: Data structure to navigate
            path: Dot-separated path (e.g., "results.items" or "." for root)

        Returns:
            Value at path, or None if not found
        """
        if path == "." or not path:
            return data

        parts = path.split(".")
        current = data

        for part in parts:
            if current is None:
                return None

            # handle array index notation
            match = re.match(r"(\w+)\[(\d+)\]", part)
            if match:
                field, index = match.groups()
                if field:
                    current = current.get(field) if isinstance(current, dict) else None
                if current is not None and isinstance(current, list):
                    idx = int(index)
                    current = current[idx] if idx < len(current) else None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    def _map_item_to_article(
        self, item: Dict[str, Any], dict_key: Optional[str] = None
    ) -> Optional[Article]:
        """
        Map a single result item to an Article object.

        Args:
            item: Result item dict
            dict_key: Optional dict key (for is_dict=True results)

        Returns:
            Article object or None if mapping fails
        """
        if not isinstance(item, dict):
            logger.warning(f"expected dict item but got {type(item)}")
            return None

        mapping = self.response_format.field_mapping

        # build kwargs for Article
        kwargs: Dict[str, Any] = {}

        # map each field
        for article_field, expr in mapping.items():
            try:
                value = self._evaluate_expression(expr, item, dict_key)
                kwargs[article_field] = value
            except Exception as e:
                logger.debug(f"failed to evaluate {article_field}={expr}: {e}")
                # use None for failed mappings
                kwargs[article_field] = None

        # ensure required field (title)
        if not kwargs.get("title"):
            logger.warning("article missing title, skipping")
            return None

        # create Article with mapped fields
        return Article(
            title=kwargs.get("title", ""),
            url=kwargs.get("url"),
            authors=kwargs.get("authors", []),
            year=kwargs.get("year"),
            venue=kwargs.get("venue"),
            citations=kwargs.get("citations", 0),
            abstract=kwargs.get("abstract"),
            content=kwargs.get("content"),
            source_id=kwargs.get("source_id"),
            source=kwargs.get("source", self.tool_config.source_type),
            pdf_links=kwargs.get("pdf_links", []),
            used_in_analysis=True,
        )

    def _evaluate_expression(
        self, expr: str, item: Dict[str, Any], dict_key: Optional[str] = None
    ) -> Any:
        """
        Evaluate a field mapping expression.

        Supported expressions:
        - "fieldname" -> item["fieldname"]
        - "@key" -> dict_key
        - "@url_from_key" -> construct PubMed URL from dict_key
        - "'static'" -> "static" (quoted string)
        - "field|transform1|transform2" -> apply transforms

        Transforms:
        - split:DELIM -> split string by delimiter
        - index:N -> get Nth element
        - int -> convert to integer
        - default:VALUE -> use VALUE if None

        Args:
            expr: Expression string
            item: Data item dict
            dict_key: Optional dict key for "@key" expressions

        Returns:
            Evaluated value
        """
        # handle static values (quoted strings)
        if expr.startswith("'") and expr.endswith("'"):
            return expr[1:-1]

        # handle special @key expressions
        if expr == "@key":
            return dict_key

        if expr == "@url_from_key":
            # construct PubMed URL from paper ID
            if dict_key:
                return f"https://pubmed.ncbi.nlm.nih.gov/{dict_key}/"
            return None

        # check for transform chain
        if "|" in expr:
            parts = expr.split("|")
            field_expr = parts[0]
            transforms = parts[1:]

            # get initial value
            value = self._get_field_value(field_expr, item, dict_key)

            # apply transforms
            for transform in transforms:
                value = self._apply_transform(transform, value)

            return value

        # simple field access
        return self._get_field_value(expr, item, dict_key)

    def _get_field_value(
        self, field_expr: str, item: Dict[str, Any], dict_key: Optional[str] = None
    ) -> Any:
        """Get a field value from item, supporting nested paths."""
        if field_expr == "@key":
            return dict_key

        # handle nested paths
        if "." in field_expr:
            return self._navigate_path(item, field_expr)

        return item.get(field_expr)

    def _apply_transform(self, transform: str, value: Any) -> Any:
        """
        Apply a transform to a value.

        Args:
            transform: Transform specification (e.g., "split:/", "index:0", "int")
            value: Value to transform

        Returns:
            Transformed value
        """
        if value is None:
            # check for default transform
            if transform.startswith("default:"):
                default_value = transform[8:]
                # try to parse as int
                try:
                    return int(default_value)
                except ValueError:
                    return default_value
            return None

        # split transform
        if transform.startswith("split:"):
            delimiter = transform[6:]
            if isinstance(value, str):
                return value.split(delimiter)
            return value

        # index transform
        if transform.startswith("index:"):
            index = int(transform[6:])
            if isinstance(value, (list, tuple)) and len(value) > index:
                return value[index]
            return None

        # int transform
        if transform == "int":
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        # float transform
        if transform == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        # default transform
        if transform.startswith("default:"):
            if value is None:
                default_value = transform[8:]
                try:
                    return int(default_value)
                except ValueError:
                    return default_value
            return value

        # wrap_list transform - wrap single value in a list
        if transform == "wrap_list":
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return [value]

        logger.warning(f"unknown transform: {transform}")
        return value


def parse_tool_response(
    response: Any, tool_config: ToolConfig
) -> Union[List[Article], bool, Any]:
    """
    Convenience function to parse a tool response.

    Args:
        response: Raw response from MCP tool
        tool_config: Tool configuration

    Returns:
        Parsed response (List[Article] for search tools, bool for utility, etc.)
    """
    parser = ResponseParser(tool_config)

    # for boolean responses
    if tool_config.response_format.type == "boolean_string":
        return parser.parse_response(response)

    # for search tools, parse to articles
    if tool_config.category in ("search", "search_with_content"):
        return parser.parse_to_articles(response)

    # for other tools, just parse the response
    return parser.parse_response(response)
