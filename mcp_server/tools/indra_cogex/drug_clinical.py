"""
Drug target, indication, side effect, and clinical trial queries.
"""

import logging
from typing import Any

from .client import parse_id, indra_post, cap_results

logger = logging.getLogger(__name__)

# maps query_type -> (endpoint, param_name, result_key)
_DRUG_ENDPOINTS = {
    "targets": ("/api/get_targets_for_drug", "drug", "targets"),
    "drugs_for_target": ("/api/get_drugs_for_target", "target", "drugs"),
    "indications": ("/api/get_indications_for_drug", "molecule", "indications"),
    "side_effects": ("/api/get_side_effects_for_drug", "drug", "side_effects"),
}


async def query_drug_info(
    identifier: str,
    query_type: str = "targets",
    max_results: int = 50,
) -> dict[str, Any]:
    """Query drug-related information from the INDRA knowledge graph.

    Look up drug targets (proteins), drugs for a protein target,
    therapeutic indications, or known side effects.

    Args:
        identifier: Entity in "NAMESPACE:id" format.
            For drugs: "CHEBI:CHEBI:27690" (metformin), "CHEBI:CHEBI:90227" (sotorasib)
            For protein targets: "HGNC:6407" (KRAS), "HGNC:3236" (EGFR)
        query_type: What to query:
            "targets" - protein targets of this drug (identifier=drug)
            "drugs_for_target" - drugs targeting this protein (identifier=gene)
            "indications" - therapeutic uses of this drug (identifier=drug)
            "side_effects" - known side effects (identifier=drug)
        max_results: Max results to return (default 50).

    Returns:
        Dict with query results and metadata.
    """
    try:
        curie = parse_id(identifier)
        result: dict[str, Any] = {
            "query": {"identifier": identifier, "query_type": query_type},
        }

        if query_type not in _DRUG_ENDPOINTS:
            valid = ", ".join(_DRUG_ENDPOINTS.keys())
            return {"error": f"invalid query_type '{query_type}', use: {valid}"}

        endpoint, param_name, result_key = _DRUG_ENDPOINTS[query_type]
        raw = await indra_post(endpoint, {param_name: curie})
        items, total = cap_results(raw, max_results)
        result[result_key] = items
        result[f"total_{result_key}"] = total
        return result

    except Exception as e:
        logger.error(f"query_drug_info failed: {e}")
        return {
            "error": str(e),
            "query": {"identifier": identifier, "query_type": query_type},
        }


async def query_clinical_trials(
    identifier: str,
    entity_type: str = "disease",
    max_results: int = 50,
) -> dict[str, Any]:
    """Query clinical trial data from the INDRA knowledge graph.

    Find clinical trials associated with a specific disease or drug.

    Args:
        identifier: Entity in "NAMESPACE:id" format.
            Diseases: "DOID:162" (cancer), "MESH:D000544" (Alzheimer disease)
            Drugs: "CHEBI:CHEBI:27690" (metformin)
        entity_type: "disease" or "drug".
        max_results: Max trials to return (default 50).

    Returns:
        Dict with clinical trials and metadata.
    """
    try:
        curie = parse_id(identifier)

        if entity_type == "disease":
            raw = await indra_post(
                "/api/get_trials_for_disease", {"disease": curie},
            )
        elif entity_type == "drug":
            raw = await indra_post(
                "/api/get_trials_for_drug", {"drug": curie},
            )
        else:
            return {"error": f"invalid entity_type '{entity_type}', use 'disease' or 'drug'"}

        trials, total = cap_results(raw, max_results)
        return {
            "trials": trials,
            "total_trials": total,
            "query": {"identifier": identifier, "entity_type": entity_type},
        }

    except Exception as e:
        logger.error(f"query_clinical_trials failed: {e}")
        return {
            "error": str(e),
            "query": {"identifier": identifier, "entity_type": entity_type},
        }
