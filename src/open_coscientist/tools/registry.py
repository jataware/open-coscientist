"""
Python tool registry for registering Python functions as LLM-callable tools

Provides decorator-based registration with automatic JSON schema generation
from type hints.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, get_type_hints, get_origin, get_args

logger = logging.getLogger(__name__)


class PythonToolRegistry:
    """
    Registry for Python functions exposed as LLM-callable tools

    Example usage:
        registry = PythonToolRegistry()

        @registry.register(
            name="my_tool",
            description="does something useful"
        )
        async def my_tool(arg1: str, arg2: int = 0) -> Dict[str, Any]:
            return {"result": f"{arg1} {arg2}"}
    """

    def __init__(self):
        self._functions: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._openai_tools: List[Dict[str, Any]] = []

    def register(self, name: Optional[str] = None, description: Optional[str] = None) -> Callable:
        """
        Decorator to register a Python function as a tool

        args:
            name: tool name (defaults to function name)
            description: tool description (defaults to function docstring)

        returns:
            decorator function
        """

        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_description = description or func.__doc__ or f"call {tool_name}"

            # generate JSON schema from type hints
            schema = self._generate_schema(func, tool_name, tool_description)

            # store function and schema
            self._functions[tool_name] = func
            self._schemas[tool_name] = schema

            # convert to OpenAI format
            openai_tool = {"type": "function", "function": schema}
            self._openai_tools.append(openai_tool)

            logger.debug(f"registered Python tool: {tool_name}")

            return func

        return decorator

    def _generate_schema(self, func: Callable, name: str, description: str) -> Dict[str, Any]:
        """
        Generate JSON schema from function signature and type hints

        args:
            func: function to generate schema for
            name: tool name
            description: tool description

        returns:
            JSON schema dict
        """
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        parameters = {"type": "object", "properties": {}, "required": []}

        for param_name, param in sig.parameters.items():
            # get type hint
            param_type = type_hints.get(param_name, Any)

            # convert to JSON schema type
            param_schema = self._type_to_schema(param_type, param_name)

            # add to parameters
            parameters["properties"][param_name] = param_schema

            # add to required if no default
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)

        schema = {"name": name, "description": description, "parameters": parameters}

        return schema

    def _type_to_schema(self, python_type: Any, param_name: str) -> Dict[str, Any]:
        """
        Convert Python type hint to JSON schema

        supports: str, int, float, bool, List, Dict, Optional

        args:
            python_type: Python type annotation
            param_name: parameter name (for logging)

        returns:
            JSON schema dict for the type
        """
        origin = get_origin(python_type)

        # handle Optional[T] (Union[T, None])
        if origin is type(Optional[str]):  # Union type
            args = get_args(python_type)
            # filter out None type
            non_none_types = [arg for arg in args if arg is not type(None)]
            if len(non_none_types) == 1:
                # Optional[T] case - recurse on T
                return self._type_to_schema(non_none_types[0], param_name)
            else:
                logger.warning(f"complex Union type for {param_name}, using string")
                return {"type": "string"}

        # handle List[T]
        if origin is list:
            args = get_args(python_type)
            if args:
                item_schema = self._type_to_schema(args[0], f"{param_name}_item")
                return {"type": "array", "items": item_schema}
            else:
                return {"type": "array", "items": {"type": "string"}}

        # handle Dict[K, V]
        if origin is dict:
            return {"type": "object", "additionalProperties": True}

        # handle basic types
        if python_type == str:
            return {"type": "string"}
        elif python_type == int:
            return {"type": "integer"}
        elif python_type == float:
            return {"type": "number"}
        elif python_type == bool:
            return {"type": "boolean"}
        elif python_type == Any:
            return {"type": "string"}
        else:
            # default to string for unknown types
            logger.debug(f"unknown type {python_type} for {param_name}, using string")
            return {"type": "string"}

    def get_function(self, name: str) -> Optional[Callable]:
        """get registered function by name"""
        return self._functions.get(name)

    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """get JSON schema for registered tool by name"""
        return self._schemas.get(name)

    def get_all_functions(self) -> Dict[str, Callable]:
        """get all registered functions"""
        return self._functions.copy()

    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """get all JSON schemas"""
        return self._schemas.copy()

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """get tools in OpenAI format for LiteLLM"""
        return self._openai_tools.copy()

    def get_tools(
        self, whitelist: Optional[List[str]] = None
    ) -> tuple[Dict[str, Callable], List[Dict[str, Any]]]:
        """
        Get tools filtered by whitelist

        args:
            whitelist: optional list of tool names to include

        returns:
            tuple of (functions_dict, openai_tools_list)
        """
        if whitelist is None:
            return self.get_all_functions(), self.get_openai_tools()

        # filter functions
        filtered_functions = {
            name: func for name, func in self._functions.items() if name in whitelist
        }

        # filter openai tools
        filtered_openai_tools = [
            tool for tool in self._openai_tools if tool["function"]["name"] in whitelist
        ]

        return filtered_functions, filtered_openai_tools
