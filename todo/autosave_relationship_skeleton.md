# Autosave relationship skeleton TODO

## Goal
- Keep existing autosave behavior for conversation memories and code diff / code summary.
- Add a minimal conversation relationship layer.
- Do not introduce Neo4j or any third-party database.
- Export the relationship result as a deterministic Python-like skeleton.

## Scope
1. Keep current hook flow in `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh`.
2. Keep `mempalace/autosave.py` as the autosave entry point.
3. Reuse extracted conversation memories from `extract_memories(...)`.
4. Build lightweight relationships only:
   - `same_topic_as`
   - `follows_from`
   - `repeats_pattern`
   - `mentions_same_file`
   - `co_occurs_with`
5. Track simple metrics only:
   - frequency count
   - recency / latest source
   - support count
6. Export a compact Python-like skeleton artifact.

## Implementation steps
- Add a small helper/module to derive relationships from extracted memories.
- Add a formatter that renders a stable Python-like skeleton string.
- Call it from `persist_autosave(...)` after memory extraction.
- Store the skeleton as a dedicated autosave artifact.
- Avoid duplicate amplification by using stable relation signatures, not snapshot filename alone.
- Add tests for:
  - repeated topics
  - repeated file mentions
  - repeated patterns
  - deterministic skeleton output
  - autosave persistence of relationship artifact

## Verification
- Run focused pytest for autosave and relationship tests.
- Confirm git repos still store `code-diff`.
- Confirm non-git workspaces still store `code-summary`.
- Confirm a relationship skeleton artifact is generated from repeated conversational themes.

## Constraints
- Minimal intrusion.
- No commit yet.
- No third-party database.
- No broader transcript denoising beyond compact diff saving.
