"""
Shared client for INDRA CoGex REST API.

All INDRA CoGex endpoints are POST with JSON body payloads.
Entity identifiers use a 2-element tuple format: [namespace, id].
"""

import os
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

INDRA_BASE_URL = os.getenv("INDRA_COGEX_URL", "https://discovery.indra.bio")
INDRA_TIMEOUT = float(os.getenv("INDRA_COGEX_TIMEOUT", "120"))


def parse_id(identifier: str) -> list[str]:
    """Parse 'NAMESPACE:id' into [namespace, id] for the INDRA API.

    Examples:
        "HGNC:6407" -> ["HGNC", "6407"]
        "MESH:D002289" -> ["MESH", "D002289"]
        "CHEBI:CHEBI:27690" -> ["CHEBI", "CHEBI:27690"]
    """
    parts = identifier.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"invalid identifier: '{identifier}'. "
            f"expected 'NAMESPACE:id' (e.g. 'HGNC:6407')"
        )
    return parts


def maybe_parse_agent(value: str) -> str | list[str]:
    """Parse value as CURIE tuple if it contains ':', otherwise return as-is.

    The INDRA get_statements endpoint accepts both plain names ("KRAS")
    and CURIE tuples (["HGNC", "6407"]).
    """
    if ":" in value and not value.startswith("http"):
        try:
            return parse_id(value)
        except ValueError:
            return value
    return value


async def indra_post(endpoint: str, payload: dict[str, Any]) -> Any:
    """POST to INDRA CoGex API and return parsed JSON."""
    url = f"{INDRA_BASE_URL}{endpoint}"
    logger.debug(f"indra request: {endpoint}")
    async with httpx.AsyncClient(timeout=INDRA_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def cap_results(items: list | Any, limit: int) -> tuple[list, int]:
    """Cap a list at limit, return (capped_list, original_count)."""
    if not isinstance(items, list):
        return items, 0
    total = len(items)
    return items[:limit], total
