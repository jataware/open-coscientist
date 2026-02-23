"""
helpers for INDRA knowledge graph integration in the reflection node.

Pre-fetches structured mechanistic evidence from INDRA CoGex to augment
reflection analysis. Extracts likely gene/protein names from hypothesis
text and queries INDRA for known causal relationships.
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# matches hyphenated bio names first (IL-6, YKL-40, IL-1B), then standalone (KRAS, TREM2)
# hyphenated suffix is 1-2 digits + optional letter — avoids pathway notation like RAGE-JAK2
_HYPHENATED_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,5}-[0-9]{1,2}[A-Z]?)\b")
_STANDALONE_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,5})\b")

# common false positives: english words, non-gene abbreviations, protein families
_STOP = frozenset({
    # english
    "THE", "AND", "FOR", "WITH", "THIS", "THAT", "FROM", "INTO",
    "BUT", "NOT", "HAS", "CAN", "MAY", "WILL", "ARE", "WAS",
    "TWO", "ONE", "USE", "NEW", "ALL", "HOW", "ANY", "ITS",
    "VIA", "WHO", "WHY", "YET", "SET", "OUR", "OUT", "WAY",
    "TRY", "LET", "PUT", "GET", "END", "DID", "HIS", "HER",
    "BEEN", "ALSO", "SHOW", "THAN", "DOES", "SUCH", "HAVE",
    "BEEN", "MORE", "WELL", "MOST", "ONLY", "BOTH", "SOME",
    # tech/science abbreviations (not genes)
    "MCP", "LLM", "API", "PDF", "URL", "PCT", "KEY", "RED",
    "DNA", "RNA", "ATP", "ADP", "GDP", "GTP", "USA", "NIH",
    # biomedical non-gene abbreviations
    "CSF", "CNS", "BBB", "PPI", "PET", "MRI", "CVE", "ROS",
    "iPSC", "CRISPR", "ELISA", "GWAS", "SNP", "DOID", "MESH",
    "HGNC", "CHEBI",
    # protein families/classes (too broad for INDRA single-agent queries)
    "CYP450", "CSPG", "CSPGS",
})

# known informal → canonical mappings for common biomedical abbreviations
_ALIAS_MAP: dict[str, str] = {
    "RAGE": "AGER",
    "MK2": "MAPKAPK2",
    "P38": "MAPK14",
    "P53": "TP53",
    "BACE": "BACE1",
    "YKL40": "CHI3L1",
    "MCP1": "CCL2",
    "ABETA": "APP",
    "APOE4": "APOE",
}


def _normalize_entity(raw: str) -> str:
    """Normalize an extracted entity name for INDRA queries.

    Strips hyphens from bio names (IL-6 → IL6, YKL-40 → YKL40),
    applies known alias mappings (RAGE → AGER).
    """
    # strip hyphen for names like IL-6, IL-15, YKL-40
    normalized = raw.replace("-", "")
    upper = normalized.upper()
    return _ALIAS_MAP.get(upper, normalized)


def extract_entity_names(text: str, max_entities: int = 3) -> list[str]:
    """Extract likely gene/protein names from hypothesis text.

    Uses two-pass heuristic: first captures hyphenated bio names (IL-6, YKL-40),
    then standalone uppercase tokens (KRAS, TREM2). Normalizes and deduplicates.
    """
    hyphenated = _HYPHENATED_RE.findall(text)
    standalone = _STANDALONE_RE.findall(text)

    seen: set[str] = set()
    result: list[str] = []

    # pass 1: hyphenated names first (higher signal)
    # also mark the prefix as seen so "YKL" doesn't re-match after "YKL-40"
    for raw in hyphenated:
        prefix = raw.split("-")[0].upper()
        seen.add(prefix)
        normalized = _normalize_entity(raw)
        upper = normalized.upper()
        if upper in _STOP or upper in seen:
            continue
        seen.add(upper)
        result.append(normalized)

    # pass 2: standalone uppercase words
    for raw in standalone:
        if len(result) >= max_entities:
            break
        # skip mutation notations like G12C, V600E, L858R (single letter + digit)
        if len(raw) >= 2 and raw[0].isupper() and raw[1].isdigit():
            continue
        normalized = _normalize_entity(raw)
        upper = normalized.upper()
        if upper in _STOP or upper in seen:
            continue
        seen.add(upper)
        result.append(normalized)

    return result[:max_entities]


def get_kg_tools_for_workflow(tool_registry: Optional[Any], workflow_name: str) -> list[str]:
    """Resolve which MCP tool names the yaml config assigned to a workflow's search_tools.

    Returns an empty list when:
    - no tool_registry is configured
    - no workflow entry exists in the yaml
    - the workflow lists no enabled tools

    This is the gate: if the list is empty, no tool calls happen for that workflow.
    """
    if tool_registry is None:
        return []
    try:
        tool_ids = tool_registry.get_tools_for_workflow(workflow_name)
        if not tool_ids:
            return []
        return tool_registry.get_mcp_tool_names(tool_ids)
    except Exception:
        return []


async def fetch_indra_evidence(
    hypothesis_text: str,
    tool_registry: Optional[Any] = None,
    max_statements: int = 5,
    workflow_name: str = "reflection",
) -> dict[str, Any]:
    """Pre-fetch mechanistic statements relevant to a hypothesis.

    Only runs if the yaml config explicitly opts in via a workflow section
    listing the tools to use. No workflow entry → no calls, even if the MCP
    server happens to have the tools registered.

    Returns dict with:
        - "prompt_text": formatted string for LLM prompt injection
        - "enrichment_items": structured list of dicts for UI rendering
    Both empty when skipped or on any failure.
    """
    empty = {"prompt_text": "", "enrichment_items": []}

    mcp_names = get_kg_tools_for_workflow(tool_registry, workflow_name)
    if not mcp_names:
        return empty

    entities = extract_entity_names(hypothesis_text)
    if not entities:
        return empty

    try:
        from ..mcp_client import get_mcp_client

        client = await get_mcp_client(tool_registry=tool_registry)

        tool_name = _pick_available_tool(client, mcp_names)
        if not tool_name:
            return empty

        all_stmts = await _query_entities(client, tool_name, entities, max_statements)
        if not all_stmts:
            return empty

        capped = all_stmts[:max_statements]
        return {
            "prompt_text": _format_evidence(capped, entities),
            "enrichment_items": _build_enrichment_items(capped, entities),
        }

    except Exception as e:
        logger.debug(f"reflection evidence fetch skipped: {e}")
        return empty


def _pick_available_tool(client: Any, mcp_names: list[str]) -> str:
    """Return the first tool from the workflow list that exists on the MCP server."""
    for name in mcp_names:
        if client.has_tool(name):
            return name
    return ""


_EVIDENCE_LIMIT = 25


async def _query_single_entity(
    client: Any, tool_name: str, entity: str, max_per_entity: int,
) -> list[dict]:
    """Query a knowledge graph tool for one entity; returns its statements."""
    try:
        raw = await client.call_tool(
            tool_name, agent=entity, limit=max_per_entity, evidence_limit=_EVIDENCE_LIMIT,
        )
        result = _parse_tool_result(raw)
        return result.get("statements", [])
    except Exception as e:
        logger.debug(f"entity query failed for '{entity}' via {tool_name}: {e}")
        return []


async def _query_entities(
    client: Any, tool_name: str, entities: list[str], max_per_entity: int,
) -> list[dict]:
    """Query a knowledge graph tool for all entities in parallel."""
    tasks = [
        _query_single_entity(client, tool_name, entity, max_per_entity)
        for entity in entities[:2]
    ]
    results = await asyncio.gather(*tasks)
    return [stmt for stmts in results for stmt in stmts]


def _parse_tool_result(raw: Any) -> dict:
    """Parse MCP tool result which may be string JSON or already a dict."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _format_evidence(statements: list[dict], queried_entities: list[str]) -> str:
    """Format INDRA statements concisely for prompt injection.

    Target: ~200-300 tokens for 5 statements. Each line is one relationship.
    """
    header = (
        "Structured knowledge from the INDRA biomedical knowledge graph "
        f"(queried for: {', '.join(queried_entities)}):"
    )
    lines = [header]

    for stmt in statements:
        line = _format_single_statement(stmt)
        if line:
            lines.append(line)

    return "\n".join(lines) if len(lines) > 1 else ""


def _ev_count_str(ev_count: int) -> str:
    """Format evidence count, appending '+' when truncated at the fetch limit."""
    return f"{ev_count}+" if ev_count >= _EVIDENCE_LIMIT else str(ev_count)


def _format_single_statement(stmt: dict) -> str:
    """Format one INDRA statement as a concise line."""
    rel_type = stmt.get("type", "Unknown")
    belief = stmt.get("belief", 0)
    ev_count = len(stmt.get("evidence", []))
    ev_str = _ev_count_str(ev_count)

    subj = _agent_name(stmt, "subj")
    obj = _agent_name(stmt, "obj")

    if subj and obj:
        return (
            f"- {subj} --[{rel_type}]--> {obj} "
            f"(belief: {belief:.2f}, {ev_str} papers)"
        )

    # complex/family statements have members instead of subj/obj
    members = stmt.get("members", [])
    if members:
        names = [m.get("name", "?") for m in members if isinstance(m, dict)]
        if names:
            return (
                f"- Complex({', '.join(names)}) [{rel_type}] "
                f"(belief: {belief:.2f}, {ev_str} papers)"
            )

    return ""


def _build_enrichment_items(
    statements: list[dict], queried_entities: list[str],
) -> list[dict[str, str]]:
    """Build structured items for hypothesis.enrichments (UI rendering).

    Each item has display-ready string fields that map directly to
    the customFields config in the domain JSON.
    """
    items: list[dict[str, str]] = []
    for stmt in statements:
        item = _statement_to_enrichment_item(stmt)
        if item:
            items.append(item)

    if items:
        items[0]["queried_entities"] = ", ".join(queried_entities)
    return items


def _statement_to_enrichment_item(stmt: dict) -> dict[str, str] | None:
    """Convert one INDRA statement into a flat dict for UI display."""
    rel_type = stmt.get("type", "Unknown")
    belief = stmt.get("belief", 0)
    ev_count = len(stmt.get("evidence", []))

    subj = _agent_name(stmt, "subj")
    obj = _agent_name(stmt, "obj")

    if subj and obj:
        return {
            "relationship": f"{subj} \u2192 {obj}",
            "type": rel_type,
            "belief": f"{belief:.0%}",
            "evidence_count": _ev_count_str(ev_count),
        }

    members = stmt.get("members", [])
    if members:
        names = [m.get("name", "?") for m in members if isinstance(m, dict)]
        if names:
            return {
                "relationship": f"Complex({', '.join(names)})",
                "type": rel_type,
                "belief": f"{belief:.0%}",
                "evidence_count": _ev_count_str(ev_count),
            }

    return None


def _agent_name(stmt: dict, role: str) -> str:
    """Extract agent name from an INDRA statement."""
    agent = stmt.get(role, {})
    if isinstance(agent, dict):
        return agent.get("name", "")
    return ""
