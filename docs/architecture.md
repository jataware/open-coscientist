# Architecture

Open Coscientist uses LangGraph to orchestrate 8-10 specialized AI agents in a multi-stage workflow. Each agent is implemented as a node that processes and updates shared state.

## Workflow Graph

The workflow consists of specialized nodes that handle different aspects of hypothesis generation and refinement:

```
┌─────────────────────────────────────────────────────────────────────┐
│                           WORKFLOW GRAPH                            │
└─────────────────────────────────────────────────────────────────────┘

                              START
                                │
                                ▼
                         ┌─────────────┐
                         │ SUPERVISOR  │  Creates research plan
                         └──────┬──────┘  and strategy
                                │
                     ┌──────────┴──────────┐
                     │   [MCP Available]   │
                     ▼                     ▼
          ┌──────────────────┐      ┌─────────────┐
          │ LITERATURE REVIEW│      │  GENERATE   │
          │(Yes, Recommended)│      │             │
          └────────┬─────────┘      └──────┬──────┘
                   │                       │
                   ▼                       │
          ┌─────────────────┐              │
          │    GENERATE     │              │
          │                 │              │
          └────────┬────────┘              │
                   │                       │
                   ▼                       │
          ┌──────────────────┐             │
          │   REFLECTION     │             │
          │ (uses literature)│             │
          └────────┬─────────┘             │
                   │                       │
                   └──────────┬────────────┘
                              ▼
                       ┌─────────────┐
                       │   REVIEW    │  Parallel peer review
                       └──────┬──────┘  with scoring
                              │
                              ▼
                       ┌─────────────┐
                       │    RANK     │  LLM-based ranking, runs Elo-based pairwise comparisons,
                       └──────┬──────┘  considering all criteria
                              │
                  ┌───────────┴───────────┐
                  │                       │
       [max_iterations > 0]      [max_iterations = 0]
                  │                       │
                  ▼                       ▼
           ┌─────────────┐              END
           │ META-REVIEW │  Synthesize
           └──────┬──────┘  cross-hypothesis review
                  │         insights
                  ▼
           ┌─────────────┐
           │   EVOLVE    │  Refine up to evolution_max_count
           └──────┬──────┘  with diversity
                  │         preservation
                  ▼
           ┌─────────────┐
           │  RE-REVIEW  │  Review evolved
           └──────┬──────┘  hypotheses
                  │
                  ▼
           ┌─────────────┐
           │  RE-RANK    │  Re-rank after
           └──────┬──────┘  evolution with re-tournament and elo ratings
                  │
                  ▼
           ┌─────────────┐
           │  PROXIMITY  │  Deduplicate
           └──────┬──────┘  similar hypotheses
                  │
                  │  [increment iteration]
                  │
                  └─────────┐
                            │
                  ┌─────────┴────────┐
                  │                  │
       [iteration < max]    [iteration >= max]
                  │                  │
                  └─────► LOOP       └─────► END
                         BACK TO
                       META-REVIEW
```

## Adaptive Review Strategy

The Review node uses an adaptive strategy based on hypothesis count:

- **Small batches (≤5 hypotheses)**: Comparative batch review where the LLM sees all hypotheses together and assigns differentiated scores based on relative strengths
- **Large batches (>5 hypotheses)**: Parallel individual reviews for better scalability

This approach balances score differentiation (important for small batches) with token efficiency and speed (critical for large batches).

## State Management

Open Coscientist uses a typed state dictionary (`WorkflowState`) that flows through all nodes. Each node:

1. Receives the current state
2. Performs its operation (often with LLM calls)
3. Updates relevant state fields
4. Returns state updates to merge

See state.py : class WorkflowState for state fields.

## Parallel Execution

Several nodes leverage parallel execution for performance:

- **Review node**: Reviews multiple hypotheses concurrently
- **Ranking node**: Runs pairwise comparisons in parallel
- **Evolve node**: Refines multiple hypotheses simultaneously

This parallelization significantly reduces total execution time, especially for large hypothesis pools.