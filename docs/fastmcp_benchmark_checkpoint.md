# Fast MCP benchmark checkpoint

This document records the current successful state of the skeleton-backed `mempalace_fast_*` benchmark work, with direct side-by-side comparison against the legacy MCP path.

## What is already working

The repository now has a dedicated benchmark entrypoint for the fast skeleton MCP path:

- `benchmarks/fastmcp_bench.py`

It can measure:

- generation latency through `persist_autosave(...)` with `--sample-transcript`
- skeleton index latency
- skeleton module read latency
- legacy search latency
- fast search latency
- fast neighbors / graph stats / status latency

It also reports a simple equivalence summary:

- `same_result_count`
- `same_semantics`

## Benchmark commands that succeeded

```bash
python3 benchmarks/fastmcp_bench.py --query autosave
python3 benchmarks/fastmcp_bench.py --query benchmark
```

## Latest successful measured output

Measured against:

- snapshot: `snapshot_20260408_150119_stop`
- total snapshots: `6`
- total memory count: `303`

### Core performance comparison

| Operation | Legacy (`autosave`) | Fast (`autosave`) | Legacy (`benchmark`) | Fast (`benchmark`) | Current comparison |
| --- | ---: | ---: | ---: | ---: | --- |
| skeleton index read | 0.119 ms | 0.175 ms | 0.115 ms | 0.117 ms | near parity; fast slightly slower on `autosave`, near equal on `benchmark` |
| skeleton summary read | 0.095 ms | 0.066 ms | 0.082 ms | 0.064 ms | fast is faster |
| search | 300.156 ms | 60.849 ms | 273.457 ms | 72.826 ms | fast is much faster |

### Additional fast-only timings

| Operation | Fast (`autosave`) | Fast (`benchmark`) | Notes |
| --- | ---: | ---: | --- |
| fast summary_for | 0.126 ms | 0.102 ms | direct snapshot summary lookup |
| fast neighbors | 16.868 ms | 2.952 ms | depends on snapshot graph/cache state |
| fast graph_stats | 69.552 ms | 44.356 ms | still the heaviest fast aggregate call |
| fast status | 0.768 ms | 0.503 ms | now very cheap |

### Search equivalence summary

| Query | same_result_count | same_semantics | Interpretation |
| --- | --- | --- | --- |
| `autosave` | true | false | fast returns the same number of results, but ranking and semantics differ |
| `benchmark` | true | false | fast returns results for task-level wording, but is still not semantic-equivalent to legacy |

## Current conclusion

At the current stage:

- the fast path can find results for both explicit code-oriented queries and task-level queries
- the fast path is not semantically identical to the legacy vector search path
- the fast path is clearly faster for local search
- the fast path is slightly faster for snapshot summary reads
- the fast path is now roughly on par for skeleton index reads
- `fast_graph_stats` remains the slowest of the main fast aggregate operations

## What improved in this checkpoint

Compared with the earlier checkpoint, the fast path has improved in two important ways:

1. repeated parsing overhead has been reduced through in-process caching
2. `fast_search` now also uses snapshot-level task metadata:
   - `task_description`
   - `task_topics`
   - stronger score breakdown and ranking signals

That means the fast path is no longer limited to node preview, topic, and file-only matching. It can now also surface results from snapshot task intent more reliably.

## Why the results differ

The legacy path uses Qdrant-backed semantic search.

The fast path uses local skeleton projection signals such as:

- preview text
- extracted topics
- file references
- memory type
- snapshot task description
- snapshot task topics

So the fast path is currently best understood as:

- a local matching and structure-aware retrieval layer
- not a drop-in semantic equivalent to the legacy path

## Supporting implementation completed

The following work is already done:

- `mempalace_fast_*` MCP tools added to `mempalace/mcp_server.py`
- `mempalace/skeleton_search.py` added as the fast skeleton query layer
- AST-based parsing improved for generated skeleton files
- transcript caveat noise filtered out of task description extraction
- in-process caching added for repeated skeleton reads and aggregate computations
- `fast_search` ranking expanded to include snapshot-level task metadata
- benchmark instructions updated in `benchmarks/BENCHMARKS.md`

## Verification status

Focused regression tests are still passing:

```bash
python3 -m pytest tests/test_conversation_skeleton.py tests/test_autosave.py
```

Latest verified result:

- `8 passed`

## Next likely improvements

1. Continue improving fast search ranking if stronger hit ordering is needed.
2. Reduce full-record rebuilds further for status and taxonomy operations.
3. Consider persisting benchmark JSON outputs under `benchmarks/results_*.json` for repeated comparison.
4. Decide later whether to build the deferred fast-first / legacy-fallback unified query path.
