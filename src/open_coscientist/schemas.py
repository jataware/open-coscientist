"""
JSON schemas for LLM responses.

These schemas are used with response_format of type json_schema
to constrain LLM outputs to specific formats.
"""

from typing import Dict, Any, Optional


# Generation schema
GENERATION_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_generation",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The hypothesis text"},
                        "justification": {
                            "type": "string",
                            "description": "Brief explanation of novelty, significance, and scientific rationale",
                        },
                        "literature_review_used": {
                            "type": "string",
                            "description": "Succinct sharing of the literature review articles, references, or other aspects used to generate the hypothesis. REQUIRED only when literature review context was provided in the prompt. OMIT this field entirely if no literature review was available or used. Do not include this field if generating hypotheses without literature review context.",
                        },
                    },
                    "required": ["text", "justification"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["hypotheses"],
        "additionalProperties": False,
    },
}


# Generation draft schema (Phase 1: drafting without validation)
GENERATION_DRAFT_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_draft",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "drafts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The draft hypothesis text"},
                        "gap_reasoning": {
                            "type": "string",
                            "description": "Brief explanation of what gap in the literature this hypothesis addresses and why it seems promising",
                        },
                        "literature_sources": {
                            "type": "string",
                            "description": "Which pre-curated papers were examined to identify this gap (titles or key findings)",
                        },
                    },
                    "required": ["text", "gap_reasoning", "literature_sources"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["drafts"],
        "additionalProperties": False,
    },
}

# Review schema
REVIEW_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_review",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "hypothesis_text": {"type": "string", "description": "The hypothesis being reviewed"},
            "review_summary": {
                "type": "string",
                "description": "Overall assessment (2-3 sentences)",
            },
            "scores": {
                "type": "object",
                "properties": {
                    "scientific_soundness": {
                        "type": "integer",
                    },
                    "novelty": {
                        "type": "integer",
                    },
                    "relevance": {
                        "type": "integer",
                    },
                    "testability": {
                        "type": "integer",
                    },
                    "clarity": {
                        "type": "integer",
                    },
                    "potential_impact": {
                        "type": "integer",
                    },
                },
                "required": [
                    "scientific_soundness",
                    "novelty",
                    "relevance",
                    "testability",
                    "clarity",
                    "potential_impact",
                ],
                "additionalProperties": False,
            },
            "detailed_feedback": {
                "type": "object",
                "properties": {
                    "scientific_soundness": {
                        "type": "string",
                        "description": "Specific feedback on theoretical foundation and logical consistency",
                    },
                    "novelty": {
                        "type": "string",
                        "description": "Specific feedback on originality and unique contribution",
                    },
                    "relevance": {
                        "type": "string",
                        "description": "Specific feedback on alignment with research goal",
                    },
                    "testability": {
                        "type": "string",
                        "description": "Specific feedback on feasibility of testing",
                    },
                    "clarity": {
                        "type": "string",
                        "description": "Specific feedback on precision and clarity of formulation",
                    },
                    "potential_impact": {
                        "type": "string",
                        "description": "Specific feedback on potential significance",
                    },
                },
                "required": [
                    "scientific_soundness",
                    "novelty",
                    "relevance",
                    "testability",
                    "clarity",
                    "potential_impact",
                ],
                "additionalProperties": False,
            },
            "constructive_feedback": {
                "type": "string",
                "description": "Specific, actionable suggestions for improvement",
            },
            "safety_ethical_concerns": {
                "type": "string",
                "description": "Any ethical or safety concerns",
            },
            "overall_score": {
                "type": "number",
                "description": "Calculated as average of criterion scores",
            },
        },
        "required": [
            "hypothesis_text",
            "review_summary",
            "scores",
            "detailed_feedback",
            "constructive_feedback",
            "safety_ethical_concerns",
            "overall_score",
        ],
        "additionalProperties": False,
    },
}


# Batch review schema - for reviewing multiple hypotheses together
REVIEW_BATCH_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_batch_review",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "reviews": {
                "type": "array",
                "description": "Array of reviews, one for each hypothesis",
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis_index": {
                            "type": "integer",
                            "description": "Index of the hypothesis being reviewed (0-based)",
                        },
                        "hypothesis_text": {
                            "type": "string",
                            "description": "The hypothesis being reviewed",
                        },
                        "review_summary": {
                            "type": "string",
                            "description": "Overall assessment (2-3 sentences)",
                        },
                        "scores": {
                            "type": "object",
                            "properties": {
                                "scientific_soundness": {
                                    "type": "integer",
                                },
                                "novelty": {
                                    "type": "integer",
                                },
                                "relevance": {
                                    "type": "integer",
                                },
                                "testability": {
                                    "type": "integer",
                                },
                                "clarity": {
                                    "type": "integer",
                                },
                                "potential_impact": {
                                    "type": "integer",
                                },
                            },
                            "required": [
                                "scientific_soundness",
                                "novelty",
                                "relevance",
                                "testability",
                                "clarity",
                                "potential_impact",
                            ],
                            "additionalProperties": False,
                        },
                        "detailed_feedback": {
                            "type": "object",
                            "properties": {
                                "scientific_soundness": {
                                    "type": "string",
                                    "description": "Specific feedback on theoretical foundation and logical consistency",
                                },
                                "novelty": {
                                    "type": "string",
                                    "description": "Specific feedback on originality and unique contribution",
                                },
                                "relevance": {
                                    "type": "string",
                                    "description": "Specific feedback on alignment with research goal",
                                },
                                "testability": {
                                    "type": "string",
                                    "description": "Specific feedback on feasibility of testing",
                                },
                                "clarity": {
                                    "type": "string",
                                    "description": "Specific feedback on precision and clarity of formulation",
                                },
                                "potential_impact": {
                                    "type": "string",
                                    "description": "Specific feedback on potential significance",
                                },
                            },
                            "required": [
                                "scientific_soundness",
                                "novelty",
                                "relevance",
                                "testability",
                                "clarity",
                                "potential_impact",
                            ],
                            "additionalProperties": False,
                        },
                        "constructive_feedback": {
                            "type": "string",
                            "description": "Specific, actionable suggestions for improvement",
                        },
                        "safety_ethical_concerns": {
                            "type": "string",
                            "description": "Any ethical or safety concerns",
                        },
                        "comparative_notes": {
                            "type": "string",
                            "description": "Brief note on how this hypothesis compares to the others",
                        },
                    },
                    "required": [
                        "hypothesis_index",
                        "hypothesis_text",
                        "review_summary",
                        "scores",
                        "detailed_feedback",
                        "constructive_feedback",
                        "safety_ethical_concerns",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["reviews"],
        "additionalProperties": False,
    },
}


# Evolution schema
EVOLUTION_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_evolution",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "original_hypothesis_text": {
                "type": "string",
                "description": "The original hypothesis text",
            },
            "refined_hypothesis_text": {
                "type": "string",
                "description": "The refined hypothesis text",
            },
            "refinement_summary": {
                "type": "string",
                "description": "Summary of changes and improvements",
            },
            "diversity_preserved": {
                "type": "boolean",
                "description": "Whether the unique core concept was preserved",
            },
        },
        "required": [
            "original_hypothesis_text",
            "refined_hypothesis_text",
            "refinement_summary",
            "diversity_preserved",
        ],
        "additionalProperties": False,
    },
}


# Meta-review schema
META_REVIEW_SCHEMA: Dict[str, Any] = {
    "name": "meta_review",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "meta_review_summary": {
                "type": "string",
                "description": "Overall summary of meta-review analysis",
            },
            "recurring_themes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "theme": {"type": "string"},
                        "description": {"type": "string"},
                        "frequency": {"type": "string"},
                    },
                    "required": ["theme", "description", "frequency"],
                    "additionalProperties": False,
                },
            },
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "process_assessment": {
                "type": "object",
                "properties": {
                    "generation_process": {"type": "string"},
                    "review_process": {"type": "string"},
                    "evolution_process": {"type": "string"},
                },
                "required": ["generation_process", "review_process", "evolution_process"],
                "additionalProperties": False,
            },
            "strategic_recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "focus_area": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "justification": {"type": "string"},
                    },
                    "required": ["focus_area", "recommendation", "justification"],
                    "additionalProperties": False,
                },
            },
            "potential_connections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "related_hypotheses": {"type": "array", "items": {"type": "string"}},
                        "connection_type": {"type": "string"},
                        "synthesis_opportunity": {"type": "string"},
                    },
                    "required": ["related_hypotheses", "connection_type", "synthesis_opportunity"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "meta_review_summary",
            "recurring_themes",
            "strengths",
            "weaknesses",
            "process_assessment",
            "strategic_recommendations",
            "potential_connections",
        ],
        "additionalProperties": False,
    },
}


# Ranking schema
RANKING_SCHEMA: Dict[str, Any] = {
    "name": "ranking_judgment",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "research_goal": {"type": "string"},
            "hypothesis_a": {"type": "string"},
            "hypothesis_b": {"type": "string"},
            "winner": {
                "type": "string",
                "enum": ["a", "b"],
                "description": "The winning hypothesis (a or b)",
            },
            "judgment_explanation": {
                "type": "object",
                "properties": {
                    "scientific_soundness_comparison": {"type": "string"},
                    "novelty_comparison": {"type": "string"},
                    "relevance_comparison": {"type": "string"},
                    "testability_comparison": {"type": "string"},
                    "clarity_comparison": {"type": "string"},
                    "impact_comparison": {"type": "string"},
                    "feasibility_comparison": {"type": "string"},
                },
                "required": [
                    "scientific_soundness_comparison",
                    "novelty_comparison",
                    "relevance_comparison",
                    "testability_comparison",
                    "clarity_comparison",
                    "impact_comparison",
                    "feasibility_comparison",
                ],
                "additionalProperties": False,
            },
            "decision_summary": {"type": "string"},
            "confidence_level": {"type": "string", "enum": ["High", "Medium", "Low"]},
        },
        "required": [
            "research_goal",
            "hypothesis_a",
            "hypothesis_b",
            "winner",
            "judgment_explanation",
            "decision_summary",
            "confidence_level",
        ],
        "additionalProperties": False,
    },
}


# Proximity schema
PROXIMITY_SCHEMA: Dict[str, Any] = {
    "name": "proximity_analysis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "similarity_clusters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cluster_id": {"type": "string"},
                        "cluster_name": {"type": "string"},
                        "central_theme": {"type": "string"},
                        "similar_hypotheses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "similarity_degree": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"],
                                    },
                                },
                                "required": ["text", "similarity_degree"],
                                "additionalProperties": False,
                            },
                        },
                        "synthesis_potential": {"type": "string"},
                    },
                    "required": [
                        "cluster_id",
                        "cluster_name",
                        "central_theme",
                        "similar_hypotheses",
                        "synthesis_potential",
                    ],
                    "additionalProperties": False,
                },
            },
            "diversity_assessment": {"type": "string"},
            "redundancy_assessment": {"type": "string"},
        },
        "required": ["similarity_clusters", "diversity_assessment", "redundancy_assessment"],
        "additionalProperties": False,
    },
}


# Reflection schema
REFLECTION_SCHEMA: Dict[str, Any] = {
    "name": "reflection_observations",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "hypothesis_text": {"type": "string", "description": "The hypothesis being analyzed"},
            "reasoning": {
                "type": "string",
                "description": "Detailed reasoning for the classification",
            },
            "classification": {
                "type": "string",
                "enum": [
                    "already explained",
                    "other explanations more likely",
                    "missing piece",
                    "neutral",
                    "disproved",
                ],
                "description": "Classification of hypothesis based on literature observations",
            },
        },
        "required": ["hypothesis_text", "reasoning", "classification"],
        "additionalProperties": False,
    },
}


# pdf analysis schema for subagent processing
PDF_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "name": "pdf_analysis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "key_findings": {
                "type": "array",
                "description": "main findings and conclusions from the paper",
                "items": {"type": "string"},
            },
            "methodologies": {
                "type": "array",
                "description": "research methods, datasets, experimental approaches used",
                "items": {"type": "string"},
            },
            "limitations": {
                "type": "array",
                "description": "limitations, gaps, or challenges identified by authors",
                "items": {"type": "string"},
            },
            "future_work": {
                "type": "array",
                "description": "future research directions or open problems mentioned",
                "items": {"type": "string"},
            },
            "relevance_to_research_goal": {
                "type": "string",
                "description": "how this paper relates to the research goal and what insights it provides",
            },
        },
        "required": [
            "key_findings",
            "methodologies",
            "limitations",
            "future_work",
            "relevance_to_research_goal",
        ],
        "additionalProperties": False,
    },
}


# Supervisor schema
SUPERVISOR_SCHEMA: Dict[str, Any] = {
    "name": "supervisor_guidance",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "research_goal_analysis": {
                "type": "object",
                "properties": {
                    "goal_summary": {
                        "type": "string",
                        "description": "concise restatement of the research goal",
                    },
                    "key_areas": {"type": "array", "items": {"type": "string"}},
                    "constraints_identified": {"type": "array", "items": {"type": "string"}},
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "goal_summary",
                    "key_areas",
                    "constraints_identified",
                    "success_criteria",
                ],
                "additionalProperties": False,
            },
            "workflow_plan": {
                "type": "object",
                "properties": {
                    "generation_phase": {
                        "type": "object",
                        "properties": {
                            "focus_areas": {"type": "array", "items": {"type": "string"}},
                            "diversity_targets": {
                                "type": "string",
                                "description": "description of diversity targets for hypotheses",
                            },
                            "quantity_target": {
                                "type": "string",
                                "description": "target number of hypotheses",
                            },
                        },
                        "required": ["focus_areas", "diversity_targets", "quantity_target"],
                        "additionalProperties": False,
                    },
                    "review_phase": {
                        "type": "object",
                        "properties": {
                            "critical_criteria": {"type": "array", "items": {"type": "string"}},
                            "review_depth": {
                                "type": "string",
                                "description": "depth of review required",
                            },
                        },
                        "required": ["critical_criteria", "review_depth"],
                        "additionalProperties": False,
                    },
                    "ranking_phase": {
                        "type": "object",
                        "properties": {
                            "ranking_approach": {
                                "type": "string",
                                "description": "description of ranking approach",
                            },
                            "selection_criteria": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["ranking_approach", "selection_criteria"],
                        "additionalProperties": False,
                    },
                    "evolution_phase": {
                        "type": "object",
                        "properties": {
                            "refinement_priorities": {"type": "array", "items": {"type": "string"}},
                            "iteration_strategy": {
                                "type": "string",
                                "description": "description of iteration strategy",
                            },
                        },
                        "required": ["refinement_priorities", "iteration_strategy"],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "generation_phase",
                    "review_phase",
                    "ranking_phase",
                    "evolution_phase",
                ],
                "additionalProperties": False,
            },
            "performance_assessment": {
                "type": "object",
                "properties": {
                    "current_status": {
                        "type": "string",
                        "description": "assessment of current workflow status",
                    },
                    "bottlenecks_identified": {"type": "array", "items": {"type": "string"}},
                    "agent_performance": {
                        "type": "object",
                        "properties": {
                            "generation_agent": {
                                "type": "string",
                                "description": "assessment of generation agent performance",
                            },
                            "reflection_agent": {
                                "type": "string",
                                "description": "assessment of reflection agent performance",
                            },
                            "ranking_agent": {
                                "type": "string",
                                "description": "assessment of ranking agent performance",
                            },
                            "evolution_agent": {
                                "type": "string",
                                "description": "assessment of evolution agent performance",
                            },
                            "proximity_agent": {
                                "type": "string",
                                "description": "assessment of proximity agent performance",
                            },
                            "meta_review_agent": {
                                "type": "string",
                                "description": "assessment of meta-review agent performance",
                            },
                        },
                        "required": [
                            "generation_agent",
                            "reflection_agent",
                            "ranking_agent",
                            "evolution_agent",
                            "proximity_agent",
                            "meta_review_agent",
                        ],
                        "additionalProperties": False,
                    },
                },
                "required": ["current_status", "bottlenecks_identified", "agent_performance"],
                "additionalProperties": False,
            },
            "adjustment_recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "aspect": {"type": "string", "description": "aspect to adjust"},
                        "adjustment": {
                            "type": "string",
                            "description": "description of adjustment",
                        },
                        "justification": {
                            "type": "string",
                            "description": "reasoning behind this adjustment",
                        },
                    },
                    "required": ["aspect", "adjustment", "justification"],
                    "additionalProperties": False,
                },
            },
            "output_preparation": {
                "type": "object",
                "properties": {
                    "hypothesis_selection_strategy": {
                        "type": "string",
                        "description": "strategy for selecting final hypotheses",
                    },
                    "presentation_format": {
                        "type": "string",
                        "description": "format for presenting results to scientist",
                    },
                    "key_insights_to_highlight": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "hypothesis_selection_strategy",
                    "presentation_format",
                    "key_insights_to_highlight",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "research_goal_analysis",
            "workflow_plan",
            "performance_assessment",
            "adjustment_recommendations",
            "output_preparation",
        ],
        "additionalProperties": False,
    },
}


# Literature review query generation schema
LITERATURE_QUERY_SCHEMA: Dict[str, Any] = {
    "name": "pubmed_query_generation",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "description": "Natural language search queries for PubMed literature search",
                "items": {
                    "type": "string",
                    "description": "A focused search phrase covering a specific aspect of the research goal",
                },
            }
        },
        "required": ["queries"],
        "additionalProperties": False,
    },
}


# Literature review paper analysis schema
LITERATURE_PAPER_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "name": "paper_analysis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "key_findings": {
                "type": "string",
                "description": "main contributions and results from this work",
            },
            "gaps_identified": {
                "type": "string",
                "description": "limitations or gaps explicitly mentioned by authors",
            },
            "future_work": {
                "type": "string",
                "description": "future research suggested by the authors",
            },
            "methodology_limitations": {
                "type": "string",
                "description": "constraints or limitations in their methods",
            },
            "unexplored_areas": {
                "type": "string",
                "description": "topics mentioned but not investigated",
            },
            "relevance": {
                "type": "string",
                "description": "how this paper relates to the research goal",
            },
        },
        "required": [
            "key_findings",
            "gaps_identified",
            "future_work",
            "methodology_limitations",
            "unexplored_areas",
            "relevance",
        ],
        "additionalProperties": False,
    },
}


# Hypothesis novelty analysis schema
HYPOTHESIS_NOVELTY_ANALYSIS_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_novelty_analysis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "methods_used": {
                "type": "string",
                "description": "what methods/techniques this paper employs",
            },
            "populations_studied": {
                "type": "string",
                "description": "what populations/contexts are covered",
            },
            "mechanisms_investigated": {
                "type": "string",
                "description": "what mechanisms/targets are studied",
            },
            "key_findings": {
                "type": "string",
                "description": "main findings relevant to the hypothesis",
            },
            "stated_limitations": {
                "type": "string",
                "description": "limitations or gaps the authors mention",
            },
            "future_work_suggested": {
                "type": "string",
                "description": "future directions the authors propose",
            },
            "novelty_assessment": {
                "type": "string",
                "description": "how hypothesis compares to this paper",
                "enum": ["overlapping", "complementary", "orthogonal", "addresses_gaps"],
            },
            "overlap_explanation": {
                "type": "string",
                "description": "detailed explanation of how hypothesis compares to this paper",
            },
        },
        "required": [
            "methods_used",
            "populations_studied",
            "mechanisms_investigated",
            "key_findings",
            "stated_limitations",
            "future_work_suggested",
            "novelty_assessment",
            "overlap_explanation",
        ],
        "additionalProperties": False,
    },
}


# Hypothesis validation synthesis schema
HYPOTHESIS_VALIDATION_SYNTHESIS_SCHEMA: Dict[str, Any] = {
    "name": "hypothesis_validation_synthesis",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "final hypothesis text (approved/refined/pivoted)",
                        },
                        "justification": {
                            "type": "string",
                            "description": "why this hypothesis is significant",
                        },
                        "novelty_validation": {
                            "type": "object",
                            "properties": {
                                "decision": {
                                    "type": "string",
                                    "description": "validation decision",
                                    "enum": ["approved", "refined", "pivoted"],
                                }
                            },
                            "required": ["decision"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["text", "justification", "novelty_validation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["hypotheses"],
        "additionalProperties": False,
    },
}


def get_schema_for_prompt(prompt_name: str) -> Optional[Dict[str, Any]]:
    """
    Get the JSON schema for a given prompt name.

    Args:
        prompt_name: Name of the prompt (e.g., "generation", "review")

    Returns:
        JSON schema dict or None if no schema is defined for this prompt
    """
    schema_map = {
        "generation": GENERATION_SCHEMA,
        "generation_with_literature_review": GENERATION_SCHEMA,
        "generation_draft_with_tools": GENERATION_DRAFT_SCHEMA,
        "generation_after_debate": GENERATION_SCHEMA,
        "review": REVIEW_SCHEMA,
        "review_batch": REVIEW_BATCH_SCHEMA,
        "evolution": EVOLUTION_SCHEMA,
        "meta_review": META_REVIEW_SCHEMA,
        "ranking": RANKING_SCHEMA,
        "proximity": PROXIMITY_SCHEMA,
        "reflection_observations": REFLECTION_SCHEMA,
        "pdf_analysis": PDF_ANALYSIS_SCHEMA,
        "supervisor": SUPERVISOR_SCHEMA,
        "literature_query_generation": LITERATURE_QUERY_SCHEMA,
        "literature_review_paper_analysis": LITERATURE_PAPER_ANALYSIS_SCHEMA,
        "hypothesis_novelty_analysis": HYPOTHESIS_NOVELTY_ANALYSIS_SCHEMA,
        "hypothesis_validation_synthesis": HYPOTHESIS_VALIDATION_SYNTHESIS_SCHEMA,
    }

    return schema_map.get(prompt_name)
