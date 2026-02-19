"""
Gene-disease-variant and gene codependence queries against INDRA CoGex.
"""

import logging
from typing import Any

from .client import parse_id, indra_post, cap_results

logger = logging.getLogger(__name__)


async def query_gene_disease_network(
    identifier: str,
    entity_type: str = "disease",
    include_variants: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Query gene-disease-variant associations from the INDRA biomedical knowledge graph.

    Given a disease, find associated genes (and optionally genetic variants).
    Given a gene, find associated diseases (and optionally genetic variants).

    Args:
        identifier: Entity in "NAMESPACE:id" format.
            Diseases: "DOID:162" (cancer), "MESH:D000544" (Alzheimer disease),
                "MESH:D002289" (non-small cell lung carcinoma)
            Genes: "HGNC:6407" (KRAS), "HGNC:3236" (EGFR), "HGNC:11730" (TREM2)
        entity_type: "disease" to find genes for a disease,
            "gene" to find diseases for a gene.
        include_variants: Also return associated genetic variants.
        max_results: Max results per category (default 50).

    Returns:
        Dict with associated entities, counts, and query metadata.
    """
    try:
        curie = parse_id(identifier)
        result: dict[str, Any] = {
            "query": {"identifier": identifier, "entity_type": entity_type},
        }

        if entity_type == "disease":
            raw = await indra_post(
                "/api/get_genes_for_disease", {"disease": curie},
            )
            result["genes"], result["total_genes"] = cap_results(raw, max_results)
            if include_variants:
                vraw = await indra_post(
                    "/api/get_variants_for_disease", {"disease": curie},
                )
                result["variants"], result["total_variants"] = cap_results(
                    vraw, max_results,
                )

        elif entity_type == "gene":
            raw = await indra_post(
                "/api/get_diseases_for_gene", {"gene": curie},
            )
            result["diseases"], result["total_diseases"] = cap_results(
                raw, max_results,
            )
            if include_variants:
                vraw = await indra_post(
                    "/api/get_variants_for_gene", {"gene": curie},
                )
                result["variants"], result["total_variants"] = cap_results(
                    vraw, max_results,
                )
        else:
            return {
                "error": f"invalid entity_type '{entity_type}', use 'disease' or 'gene'",
            }

        return result

    except Exception as e:
        logger.error(f"query_gene_disease_network failed: {e}")
        return {
            "error": str(e),
            "query": {"identifier": identifier, "entity_type": entity_type},
        }


async def query_gene_codependents(
    gene_id: str,
    max_results: int = 50,
) -> dict[str, Any]:
    """Find genes codependent with a given gene (from DepMap CRISPR screens).

    Codependent genes are functionally linked: when one is essential in a cell
    line, the other tends to be too. Useful for discovering synthetic lethal
    targets and functional gene networks in cancer research.

    Args:
        gene_id: Gene in "HGNC:id" format.
            Examples: "HGNC:6407" (KRAS), "HGNC:3236" (EGFR), "HGNC:1097" (BRAF)
        max_results: Max codependent genes to return (default 50).

    Returns:
        Dict with codependent genes and counts.
    """
    try:
        curie = parse_id(gene_id)
        raw = await indra_post(
            "/api/get_codependents_for_gene", {"gene": curie},
        )
        genes, total = cap_results(raw, max_results)
        return {
            "codependent_genes": genes,
            "total_codependents": total,
            "query": {"gene_id": gene_id},
        }
    except Exception as e:
        logger.error(f"query_gene_codependents failed: {e}")
        return {"error": str(e), "query": {"gene_id": gene_id}}
