<div align="center">

<img src="assets/mempalace_logo.png" alt="MemPalace" width="280">

# MemPalace

### The highest-scoring AI memory system ever benchmarked. And it's free.

<br>

Every conversation you have with an AI — every decision, every debugging session, every architecture debate — disappears when the session ends. Six months of work, gone. You start over every time.

Other memory systems try to fix this by letting AI decide what's worth remembering. It extracts "user prefers Postgres" and throws away the conversation where you explained *why*. MemPalace takes a different approach: **store everything, then make it findable.**

**The Palace** — Ancient Greek orators memorized entire speeches by placing ideas in rooms of an imaginary building. Walk through the building, find the idea. MemPalace applies the same principle to AI memory: your conversations are organized into wings (people and projects), halls (types of memory), and rooms (specific ideas). No AI decides what matters — you keep every word, and the structure makes it searchable. That structure alone improves retrieval by 34%.

**AAAK** — A lossless shorthand dialect designed for AI agents. Not meant to be read by humans — meant to be read by your AI, fast. 30x compression, zero information loss. Your AI loads months of context in ~120 tokens. And because AAAK is just structured text with a universal grammar, it works with **any model that reads text** — Claude, GPT, Gemini, Llama, Mistral. No decoder, no fine-tuning, no cloud API required. Run it against a local model and your entire memory stack stays offline. Nothing else like it exists.

**Local, open, adaptable** — MemPalace runs entirely on your machine, on any data you have locally, without using any external API or services. It has been tested on conversations — but it can be adapted for different types of datastores. This is why we're open-sourcing it.

<br>

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]
[![][discord-shield]][discord-link]

<br>

[Quick Start](#quick-start) · [The Palace](#the-palace) · [AAAK Dialect](#aaak-compression) · [Benchmarks](#benchmarks) · [MCP Tools](#mcp-server)

<br>

### Highest LongMemEval score ever published — free or paid.

<table>
<tr>
<td align="center"><strong>96.6%</strong><br><sub>LongMemEval R@5<br>Zero API calls</sub></td>
<td align="center"><strong>100%</strong><br><sub>LongMemEval R@5<br>with Haiku rerank</sub></td>
<td align="center"><strong>+34%</strong><br><sub>Retrieval boost<br>from palace structure</sub></td>
<td align="center"><strong>$0</strong><br><sub>No subscription<br>No cloud. Local only.</sub></td>
</tr>
</table>

<sub>Reproducible — runners in <a href="benchmarks/">benchmarks/</a>. <a href="benchmarks/BENCHMARKS.md">Full results</a>.</sub>

</div>

---

## Quick Start

```bash
docker compose up -d qdrant

# Run everything inside containers
docker compose run --rm mempalace-cli init ~/projects/myapp
docker compose run --rm mempalace-cli mine ~/projects/myapp
docker compose run --rm mempalace-cli mine ~/chats/ --mode convos
docker compose run --rm mempalace-cli search "why did we switch to GraphQL"
docker compose run --rm mempalace-cli status
```

MemPalace now uses Qdrant for vector storage and expects embeddings from Ollama. The default container configuration connects to a local Qdrant on ports `6333/6334` and a remote Ollama endpoint at `http://115.231.236.153:11434` with model `mxbai-embed-large:latest` and dimension `1024`. These defaults can be overridden with environment variables or `~/.mempalace/config.json`.

  ┌─────────────────────────────────────────────────────────────┐
  │  WING: Person                                              │
  │                                                            │
  │    ┌──────────┐  ──hall──  ┌──────────┐                    │
  │    │  Room A  │            │  Room B  │                    │
  │    └────┬─────┘            └──────────┘                    │
  │         │                                                  │
  │         ▼                                                  │
  │    ┌──────────┐      ┌──────────┐                          │
  │    │  Closet  │ ───▶ │  Drawer  │                          │
  │    └──────────┘      └──────────┘                          │
  └─────────┼──────────────────────────────────────────────────┘
            │
          tunnel
            │
  ┌─────────┼──────────────────────────────────────────────────┐
  │  WING: Project                                             │
  │         │                                                  │
  │    ┌────┴─────┐  ──hall──  ┌──────────┐                    │
  │    │  Room A  │            │  Room C  │                    │
  │    └────┬─────┘            └──────────┘                    │
  │         │                                                  │
  │         ▼                                                  │
  │    ┌──────────┐      ┌──────────┐                          │
  │    │  Closet  │ ───▶ │  Drawer  │                          │
  │    └──────────┘      └──────────┘                          │
  └─────────────────────────────────────────────────────────────┘
```

**Wings** — a person or project. As many as you need.
**Rooms** — specific topics within a wing. Auth, billing, deploy — endless rooms.
**Halls** — connections between related rooms *within* the same wing. If Room A (auth) and Room B (security) are related, a hall links them.
**Tunnels** — connections *between* wings. When Person A and a Project both have a room about "auth," a tunnel cross-references them automatically.
**Closets** — compressed summaries that point to the original content. Fast for AI to read.
**Drawers** — the original verbatim files. The exact words, never summarized.

**Halls** are memory types — the same in every wing, acting as corridors:
- `hall_facts` — decisions made, choices locked in
- `hall_events` — sessions, milestones, debugging
- `hall_discoveries` — breakthroughs, new insights
- `hall_preferences` — habits, likes, opinions
- `hall_advice` — recommendations and solutions

**Rooms** are named ideas — `auth-migration`, `graphql-switch`, `ci-pipeline`. When the same room appears in different wings, it creates a **tunnel** — connecting the same topic across domains:

```
wing_kai       / hall_events / auth-migration  → "Kai debugged the OAuth token refresh"
wing_driftwood / hall_facts  / auth-migration  → "team decided to migrate auth to Clerk"
wing_priya     / hall_advice / auth-migration  → "Priya approved Clerk over Auth0"
```

Same room. Three wings. The tunnel connects them.

### Why Structure Matters

Tested on 22,000+ real conversation memories:

```
Search all closets:          60.9%  R@10
Search within wing:          73.1%  (+12%)
Search wing + hall:          84.8%  (+24%)
Search wing + room:          94.8%  (+34%)
```

Wings and rooms aren't cosmetic. They're a **34% retrieval improvement**. The palace structure is the product.

### The Memory Stack

| Layer | What | Size | When |
|-------|------|------|------|
| **L0** | Identity — who is this AI? | ~50 tokens | Always loaded |
| **L1** | Critical facts — team, projects, preferences | ~120 tokens (AAAK) | Always loaded |
| **L2** | Room recall — recent sessions, current project | On demand | When topic comes up |
| **L3** | Deep search — semantic query across all closets | On demand | When explicitly asked |

Your AI wakes up with L0 + L1 (~170 tokens) and knows your world. Searches only fire when needed.

### AAAK Compression

AAAK is a lossless dialect — 30x compression, readable by any LLM without a decoder. It works with **Claude, GPT, Gemini, Llama, Mistral** — any model that reads text. Run it against a local Llama model and your whole memory stack stays offline.

**English (~1000 tokens):**
```
Priya manages the Driftwood team: Kai (backend, 3 years), Soren (frontend),
Maya (infrastructure), and Leo (junior, started last month). They're building
a SaaS analytics platform. Current sprint: auth migration to Clerk.
Kai recommended Clerk over Auth0 based on pricing and DX.
```

**AAAK (~120 tokens):**
```
TEAM: PRI(lead) | KAI(backend,3yr) SOR(frontend) MAY(infra) LEO(junior,new)
PROJ: DRIFTWOOD(saas.analytics) | SPRINT: auth.migration→clerk
DECISION: KAI.rec:clerk>auth0(pricing+dx) | ★★★★
```

Same information. 8x fewer tokens. Your AI learns AAAK automatically from the MCP server — no manual setup.

### Contradiction Detection

MemPalace catches mistakes before they reach you:

```
Input:  "Soren finished the auth migration"
Output: 🔴 AUTH-MIGRATION: attribution conflict — Maya was assigned, not Soren

Input:  "Kai has been here 2 years"
Output: 🟡 KAI: wrong_tenure — records show 3 years (started 2023-04)

Input:  "The sprint ends Friday"
Output: 🟡 SPRINT: stale_date — current sprint ends Thursday (updated 2 days ago)
```

Facts checked against the knowledge graph. Ages, dates, and tenures calculated dynamically — not hardcoded.

---

## Real-World Examples

### Solo developer across multiple projects

```bash
# Mine each project's conversations
mempalace mine ~/chats/orion/  --mode convos --wing orion
mempalace mine ~/chats/nova/   --mode convos --wing nova
mempalace mine ~/chats/helios/ --mode convos --wing helios

# Six months later: "why did I use Postgres here?"
mempalace search "database decision" --wing orion
# → "Chose Postgres over SQLite because Orion needs concurrent writes
#    and the dataset will exceed 10GB. Decided 2025-11-03."

# Cross-project search
mempalace search "rate limiting approach"
# → finds your approach in Orion AND Nova, shows the differences
```

### Team lead managing a product

```bash
# Mine Slack exports and AI conversations
mempalace mine ~/exports/slack/ --mode convos --wing driftwood
mempalace mine ~/.claude/projects/ --mode convos

# "What did Soren work on last sprint?"
mempalace search "Soren sprint" --wing driftwood
# → 14 closets: OAuth refactor, dark mode, component library migration

# "Who decided to use Clerk?"
mempalace search "Clerk decision" --wing driftwood
# → "Kai recommended Clerk over Auth0 — pricing + developer experience.
#    Team agreed 2026-01-15. Maya handling the migration."
```

### Before mining: split mega-files

Some transcript exports concatenate multiple sessions into one huge file:

```bash
mempalace split ~/chats/                      # split into per-session files
mempalace split ~/chats/ --dry-run            # preview first
mempalace split ~/chats/ --min-sessions 3     # only split files with 3+ sessions
```

---

## Knowledge Graph

Temporal entity-relationship triples — like Zep's Graphiti, but SQLite instead of Neo4j. Local and free.

```python
from mempalace.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_triple("Kai", "works_on", "Orion", valid_from="2025-06-01")
kg.add_triple("Maya", "assigned_to", "auth-migration", valid_from="2026-01-15")
kg.add_triple("Maya", "completed", "auth-migration", valid_from="2026-02-01")

# What's Kai working on?
kg.query_entity("Kai")
# → [Kai → works_on → Orion (current), Kai → recommended → Clerk (2026-01)]

# What was true in January?
kg.query_entity("Maya", as_of="2026-01-20")
# → [Maya → assigned_to → auth-migration (active)]

# Timeline
kg.timeline("Orion")
# → chronological story of the project
```

Facts have validity windows. When something stops being true, invalidate it:

```python
kg.invalidate("Kai", "works_on", "Orion", ended="2026-03-01")
```

Now queries for Kai's current work won't return Orion. Historical queries still will.

| Feature | MemPalace | Zep (Graphiti) |
|---------|-----------|----------------|
| Storage | SQLite (local) | Neo4j (cloud) |
| Cost | Free | $25/mo+ |
| Temporal validity | Yes | Yes |
| Self-hosted | Always | Enterprise only |
| Privacy | Everything local | SOC 2, HIPAA |

---

## Specialist Agents

Create agents that focus on specific areas. Each agent gets its own wing and diary in the palace — not in your CLAUDE.md. Add 50 agents, your config stays the same size.

```
~/.mempalace/agents/
  ├── reviewer.json       # code quality, patterns, bugs
  ├── architect.json      # design decisions, tradeoffs
  └── ops.json            # deploys, incidents, infra
```

Your CLAUDE.md just needs one line:

```
You have MemPalace agents. Run mempalace_list_agents to see them.
```

The AI discovers its agents from the palace at runtime. Each agent:

- **Has a focus** — what it pays attention to
- **Keeps a diary** — written in AAAK, persists across sessions
- **Builds expertise** — reads its own history to stay sharp in its domain

```
# Agent writes to its diary after a code review
mempalace_diary_write("reviewer",
    "PR#42|auth.bypass.found|missing.middleware.check|pattern:3rd.time.this.quarter|★★★★")

# Agent reads back its history
mempalace_diary_read("reviewer", last_n=10)
# → last 10 findings, compressed in AAAK
```

Each agent is a specialist lens on your data. The reviewer remembers every bug pattern it's seen. The architect remembers every design decision. The ops agent remembers every incident. They don't share a scratchpad — they each maintain their own memory.

Letta charges $20–200/mo for agent-managed memory. MemPalace does it with a wing.

---

## MCP Server

```bash
claude mcp add mempalace -- python -m mempalace.mcp_server
```

### 19 Tools

**Palace (read)**

| Tool | What |
|------|------|
| `mempalace_status` | Palace overview + AAAK spec + memory protocol |
| `mempalace_list_wings` | Wings with counts |
| `mempalace_list_rooms` | Rooms within a wing |
| `mempalace_get_taxonomy` | Full wing → room → count tree |
| `mempalace_search` | Semantic search with wing/room filters |
| `mempalace_check_duplicate` | Check before filing |
| `mempalace_get_aaak_spec` | AAAK dialect reference |

**Palace (write)**

| Tool | What |
|------|------|
| `mempalace_add_drawer` | File verbatim content |
| `mempalace_delete_drawer` | Remove by ID |

**Knowledge Graph**

| Tool | What |
|------|------|
| `mempalace_kg_query` | Entity relationships with time filtering |
| `mempalace_kg_add` | Add facts |
| `mempalace_kg_invalidate` | Mark facts as ended |
| `mempalace_kg_timeline` | Chronological entity story |
| `mempalace_kg_stats` | Graph overview |

**Navigation**

| Tool | What |
|------|------|
| `mempalace_traverse` | Walk the graph from a room across wings |
| `mempalace_find_tunnels` | Find rooms bridging two wings |
| `mempalace_graph_stats` | Graph connectivity overview |

**Agent Diary**

| Tool | What |
|------|------|
| `mempalace_diary_write` | Write AAAK diary entry |
| `mempalace_diary_read` | Read recent diary entries |

The AI learns AAAK and the memory protocol automatically from the `mempalace_status` response. No manual configuration.

---

## Auto-Save Hooks

Two hooks for Claude Code that automatically save memories during work:

**Save Hook** — every 15 messages, triggers a structured save. Topics, decisions, quotes, code changes. Also regenerates the critical facts layer.

**PreCompact Hook** — fires before context compression. Emergency save before the window shrinks.

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/mempalace/hooks/mempal_save_hook.sh"}]}],
    "PreCompact": [{"matcher": "", "hooks": [{"type": "command", "command": "/path/to/mempalace/hooks/mempal_precompact_hook.sh"}]}]
  }
}
```

---

## Benchmarks

Tested on standard academic benchmarks — reproducible, published datasets.

| Benchmark | Mode | Score | API Calls |
|-----------|------|-------|-----------|
| **LongMemEval R@5** | Raw (ChromaDB only) | **96.6%** | Zero |
| **LongMemEval R@5** | Hybrid + Haiku rerank | **100%** (500/500) | ~500 |
| **LoCoMo R@10** | Raw, session level | **60.3%** | Zero |
| **Personal palace R@10** | Heuristic bench | **85%** | Zero |
| **Palace structure impact** | Wing+room filtering | **+34%** R@10 | Zero |

The 96.6% raw score is the highest published LongMemEval result requiring no API key, no cloud, and no LLM at any stage.

### vs Published Systems

| System | LongMemEval R@5 | API Required | Cost |
|--------|----------------|--------------|------|
| **MemPalace (hybrid)** | **100%** | Optional | Free |
| Supermemory ASMR | ~99% | Yes | — |
| **MemPalace (raw)** | **96.6%** | **None** | **Free** |
| Mastra | 94.87% | Yes (GPT) | API costs |
| Mem0 | ~85% | Yes | $19–249/mo |
| Zep | ~85% | Yes | $25/mo+ |

---

## All Commands

```bash
# Setup
mempalace init <dir>                              # guided onboarding + AAAK bootstrap

# Mining
mempalace mine <dir>                              # mine project files
mempalace mine <dir> --mode convos                # mine conversation exports
mempalace mine <dir> --mode convos --wing myapp   # tag with a wing name

# Splitting
mempalace split <dir>                             # split concatenated transcripts
mempalace split <dir> --dry-run                   # preview

# Search
mempalace search "query"                          # search everything
mempalace search "query" --wing myapp             # within a wing
mempalace search "query" --room auth-migration    # within a room

# Memory stack
mempalace wake-up                                 # load L0 + L1 context
mempalace wake-up --wing driftwood                # project-specific

# Compression
mempalace compress --wing myapp                   # AAAK compress

# Status
mempalace status                                  # palace overview
```

All commands accept `--palace <path>` to override the default location.

---

## Configuration

### Global (`~/.mempalace/config.json`)

```json
{
  "palace_path": "/custom/path/to/palace",
  "collection_name": "mempalace_drawers",
  "people_map": {"Kai": "KAI", "Priya": "PRI"}
}
```

### Wing config (`~/.mempalace/wing_config.json`)

Generated by `mempalace init`. Maps your people and projects to wings:

```json
{
  "default_wing": "wing_general",
  "wings": {
    "wing_kai": {"type": "person", "keywords": ["kai", "kai's"]},
    "wing_driftwood": {"type": "project", "keywords": ["driftwood", "analytics", "saas"]}
  }
}
```

### Identity (`~/.mempalace/identity.txt`)

Plain text. Becomes Layer 0 — loaded every session.

---

## File Reference

| File | What |
|------|------|
| `cli.py` | CLI entry point |
| `config.py` | Configuration loading and defaults |
| `normalize.py` | Converts 5 chat formats to standard transcript |
| `mcp_server.py` | MCP server — 19 tools, AAAK auto-teach, memory protocol |
| `miner.py` | Project file ingest |
| `convo_miner.py` | Conversation ingest — chunks by exchange pair |
| `searcher.py` | Semantic search via ChromaDB |
| `layers.py` | 4-layer memory stack |
| `dialect.py` | AAAK compression — 30x lossless |
| `knowledge_graph.py` | Temporal entity-relationship graph (SQLite) |
| `palace_graph.py` | Room-based navigation graph |
| `onboarding.py` | Guided setup — generates AAAK bootstrap + wing config |
| `entity_registry.py` | Entity code registry |
| `entity_detector.py` | Auto-detect people and projects from content |
| `split_mega_files.py` | Split concatenated transcripts into per-session files |
| `hooks/mempal_save_hook.sh` | Auto-save every N messages |
| `hooks/mempal_precompact_hook.sh` | Emergency save before compaction |

---

## Project Structure

```
mempalace/
├── README.md                  ← you are here
├── mempalace/                 ← core package (README)
│   ├── cli.py                 ← CLI entry point
│   ├── mcp_server.py          ← MCP server (19 tools)
│   ├── knowledge_graph.py     ← temporal entity graph
│   ├── palace_graph.py        ← room navigation graph
│   ├── dialect.py             ← AAAK compression
│   ├── miner.py               ← project file ingest
│   ├── convo_miner.py         ← conversation ingest
│   ├── searcher.py            ← semantic search
│   ├── onboarding.py          ← guided setup
│   └── ...                    ← see mempalace/README.md
├── benchmarks/                ← reproducible benchmark runners
│   ├── README.md              ← reproduction guide
│   ├── BENCHMARKS.md          ← full results + methodology
│   ├── longmemeval_bench.py   ← LongMemEval runner
│   ├── locomo_bench.py        ← LoCoMo runner
│   └── membench_bench.py      ← MemBench runner
├── hooks/                     ← Claude Code auto-save hooks
│   ├── README.md              ← hook setup guide
│   ├── mempal_save_hook.sh    ← save every N messages
│   └── mempal_precompact_hook.sh ← emergency save
├── examples/                  ← usage examples
│   ├── basic_mining.py
│   ├── convo_import.py
│   └── mcp_setup.md
├── tests/                     ← test suite (README)
├── assets/                    ← logo + brand assets
└── pyproject.toml             ← package config (v3.0.0)
```

---

## Requirements

- Python 3.9+
- `chromadb>=0.4.0`
- `pyyaml>=6.0`

No API key. No internet after install. Everything local.

```bash
pip install mempalace
```

---

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and guidelines.

## License

MIT — see [LICENSE](LICENSE).

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.0.0-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/milla-jovovich/mempalace/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/milla-jovovich/mempalace/blob/main/LICENSE
[discord-shield]: https://img.shields.io/badge/discord-join-5865F2?style=flat-square&labelColor=0a0e14&logo=discord&logoColor=5865F2
[discord-link]: https://discord.com/invite/ycTQQCu6kn
