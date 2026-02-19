"""
Biological pathway and causal subnetwork queries against INDRA CoGex.
"""

import logging
from typing import Any

from .client import parse_id, indra_post, cap_results

logger = logging.getLogger(__name__)


async def query_pathways(
    gene_ids: list[str],
    max_results: int = 50,
) -> dict[str, Any]:
    """Query biological pathways for genes from the INDRA knowledge graph.

    For a single gene, returns all pathways containing that gene.
    For multiple genes, returns shared pathways across all of them.

    Args:
        gene_ids: One or more gene identifiers in "HGNC:id" format.
            Single: ["HGNC:6407"] for KRAS pathways.
            Multiple: ["HGNC:6407", "HGNC:1097"] for shared KRAS/BRAF pathways.
        max_results: Max pathways to return (default 50).

    Returns:
        Dict with pathways and metadata.
    """
    try:
        curies = [parse_id(gid) for gid in gene_ids]
        mode = "shared" if len(curies) > 1 else "single"

        if len(curies) == 1:
            raw = await indra_post(
                "/api/get_pathways_for_gene", {"gene": curies[0]},
            )
        else:
            raw = await indra_post(
                "/api/get_shared_pathways_for_genes", {"genes": curies},
            )

        pathways, total = cap_results(raw, max_results)
        return {
            "pathways": pathways,
            "total_pathways": total,
            "query": {"gene_ids": gene_ids, "mode": mode},
        }

    except Exception as e:
        logger.error(f"query_pathways failed: {e}")
        return {"error": str(e), "query": {"gene_ids": gene_ids}}


async def query_causal_subnetwork(
    node_ids: list[str],
    find_mediators: bool = True,
    max_results: int = 50,
) -> dict[str, Any]:
    """Query causal subnetwork between biological entities from INDRA.

    Find mechanistic connections between entities. When find_mediators is True,
    discovers intermediate nodes X such that A -> X -> B, revealing indirect
    regulatory pathways.

    Args:
        node_ids: Two or more entity identifiers in "NAMESPACE:id" format.
            E.g. ["HGNC:6407", "HGNC:5173"] to find paths between KRAS and HRAS.
            Supports genes (HGNC), protein families (FPLX), etc.
        find_mediators: If True (default), find mediated pathways (A -> X -> B).
            If False, return direct relations between the given nodes.
        max_results: Max relations to return (default 50).

    Returns:
        Dict with subnetwork relations and metadata.
    """
    try:
        curies = [parse_id(nid) for nid in node_ids]

        if find_mediators:
            raw = await indra_post("/api/indra_mediated_subnetwork", {
                "nodes": curies,
                "order_by_ev_count": True,
            })
        else:
            raw = await indra_post("/api/indra_subnetwork_relations", {
                "nodes": curies,
                "include_db_evidence": True,
            })

        items, total = cap_results(raw, max_results)
        return {
            "subnetwork": items,
            "total_relations": total,
            "query": {"node_ids": node_ids, "find_mediators": find_mediators},
        }

    except Exception as e:
        logger.error(f"query_causal_subnetwork failed: {e}")
        return {"error": str(e), "query": {"node_ids": node_ids}}
