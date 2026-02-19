"""
INDRA mechanistic statement queries - the core knowledge retrieval tool.

INDRA statements are machine-readable causal assertions extracted from
biomedical literature (e.g. "KRAS activates RAF1", "Sotorasib inhibits KRAS").
"""

import logging
from typing import Any

from .client import parse_id, maybe_parse_agent, indra_post, cap_results

logger = logging.getLogger(__name__)


async def query_mechanistic_statements(
    agent: str | None = None,
    other_agent: str | None = None,
    relation_types: list[str] | None = None,
    agent_role: str | None = None,
    mesh_term: str | None = None,
    limit: int = 30,
    evidence_limit: int = 5,
) -> dict[str, Any]:
    """Query INDRA mechanistic statements from curated biomedical knowledge.

    INDRA statements are structured causal claims extracted and curated from
    scientific papers. This is the primary tool for accessing INDRA's unique
    mechanistic knowledge about biological interactions.

    Two query modes:
    1. By agent names: find statements about specific genes/proteins/drugs.
       Accepts plain names ("KRAS", "EGFR", "sotorasib") or CURIEs ("HGNC:6407").
    2. By MeSH term: find all statements annotated with a disease/topic.

    Args:
        agent: Gene, protein, or drug name (e.g. "KRAS", "EGFR", "sotorasib").
            Also accepts "NAMESPACE:id" identifiers like "HGNC:6407".
        other_agent: Second entity to find relationships between
            (e.g. agent="KRAS", other_agent="RAF1").
        relation_types: Filter by relationship type(s). Common types:
            Activation, Inhibition, Phosphorylation, IncreaseAmount,
            DecreaseAmount, Complex, Deactivation, Influence
        agent_role: "subject" or "object" to constrain the agent's causal role.
        mesh_term: MeSH disease/topic ID in "MESH:id" format to query statements
            annotated with that term. E.g. "MESH:D002289" (lung neoplasms),
            "MESH:D000544" (Alzheimer disease).
        limit: Max statements to return (default 30).
        evidence_limit: Max evidence entries per statement (default 5).

    Returns:
        Dict with mechanistic statements, evidence, and metadata.
    """
    query_meta = {
        "agent": agent,
        "other_agent": other_agent,
        "mesh_term": mesh_term,
        "relation_types": relation_types,
    }

    try:
        if mesh_term:
            return await _query_by_mesh(
                mesh_term, evidence_limit, limit, query_meta,
            )
        if agent:
            return await _query_by_agents(
                agent, other_agent, relation_types, agent_role,
                limit, evidence_limit, query_meta,
            )
        return {
            "error": "provide either 'agent' or 'mesh_term'",
            "query": query_meta,
        }

    except Exception as e:
        logger.error(f"query_mechanistic_statements failed: {e}")
        return {"error": str(e), "query": query_meta}


async def _query_by_mesh(
    mesh_term: str,
    evidence_limit: int,
    limit: int,
    query_meta: dict,
) -> dict[str, Any]:
    """Query statements by MeSH disease/topic annotation."""
    curie = parse_id(mesh_term)
    raw = await indra_post("/api/get_stmts_for_mesh", {
        "mesh_term": curie,
        "include_child_terms": True,
        "evidence_limit": evidence_limit,
        "include_db_evidence": True,
    })
    stmts, total = cap_results(raw, limit)
    return {
        "statements": stmts,
        "total_statements": total,
        "query": query_meta,
    }


async def _query_by_agents(
    agent: str,
    other_agent: str | None,
    relation_types: list[str] | None,
    agent_role: str | None,
    limit: int,
    evidence_limit: int,
    query_meta: dict,
) -> dict[str, Any]:
    """Query statements by agent name(s) and optional filters."""
    payload: dict[str, Any] = {
        "agent": maybe_parse_agent(agent),
        "limit": limit,
        "evidence_limit": evidence_limit,
    }
    if other_agent:
        payload["other_agent"] = maybe_parse_agent(other_agent)
    if relation_types:
        payload["rel_types"] = relation_types
    if agent_role:
        payload["agent_role"] = agent_role

    raw = await indra_post("/api/get_statements", payload)
    stmts, total = cap_results(raw, limit)
    return {
        "statements": stmts,
        "total_statements": total,
        "query": query_meta,
    }
