"""
Literature review tools for LLM agents

This module kept for backwards compatibility but contains no registered tools.
"""

import logging
from .registry import PythonToolRegistry

logger = logging.getLogger(__name__)

# create empty registry instance for backwards compatibility
# (draft.py and validate.py now use python_whitelist = [])
literature_tools = PythonToolRegistry()
