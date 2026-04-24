# Context — LLM-Maintained Wiki System

**Enterprise-grade, multi-tenant knowledge base where an LLM incrementally builds and maintains structured wiki pages from your team's documents, URLs, and data sources.**

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [How It Works — Core Architecture](#2-how-it-works--core-architecture)
3. [Getting Started](#3-getting-started)
4. [Configuration Reference](#4-configuration-reference)
5. [Team Setup & Access Control](#5-team-setup--access-control)
6. [Core Workflows](#6-core-workflows)
   - [Ingest: Teaching the Wiki](#61-ingest-teaching-the-wiki)
   - [Query: Asking the Wiki](#62-query-asking-the-wiki)
   - [Lint: Quality Checks](#63-lint-quality-checks)
   - [Schema: Defining Your Knowledge Structure](#64-schema-defining-your-knowledge-structure)
7. [API Reference](#7-api-reference)
8. [Portal — Read-Only Web UI](#8-portal--read-only-web-ui)
9. [Knowledge Graph](#9-knowledge-graph)
10. [Semantic Drift & Quality Monitoring](#10-semantic-drift--quality-monitoring)
11. [Hallucination Gate](#11-hallucination-gate)
12. [Prompt Caching & Performance](#12-prompt-caching--performance)
13. [Background Workers](#13-background-workers)
14. [Git-Backed Storage](#14-git-backed-storage)
15. [Database Schema](#15-database-schema)
16. [Rate Limits](#16-rate-limits)
17. [Operations & Monitoring](#17-operations--monitoring)
18. [Scaling Guide](#18-scaling-guide)
19. [Examples: End-to-End Team Workflows](#19-examples-end-to-end-team-workflows)
20. [Troubleshooting](#20-troubleshooting)
21. [Claude Code Integration](#21-claude-code-integration)
22. [Kiro Integration](#22-kiro-integration)

---

## 1. What This Is

Context implements the **LLM Wiki pattern**: instead of doing raw RAG (retrieval-augmented generation) over source documents, an LLM incrementally writes and maintains structured Markdown wiki pages. Those pages become the primary knowledge layer your team queries.

### The Three Layers

```
┌─────────────────────────────────────┐
│          YOUR SOURCES               │  PDFs, URLs, Docs, Text files
│  (raw, messy, often contradictory)  │
└──────────────────┬──────────────────┘
                   │  Ingest worker reads + summarizes
                   ▼
┌─────────────────────────────────────┐
│            THE WIKI                 │  LLM-maintained Markdown pages
│  (structured, deduplicated, cited)  │  stored in git + PostgreSQL
└──────────────────┬──────────────────┘
                   │  Query worker reads + answers
                   ▼
┌─────────────────────────────────────┐
│            THE SCHEMA               │  Defines page types, entities,
│   (your knowledge vocabulary)       │  relationships, and rules
└─────────────────────────────────────┘
```

### The Three Operations

| Operation | What It Does | When to Use |
|-----------|-------------|-------------|
| **Ingest** | Reads a source, updates relevant wiki pages, extracts KG entities | When you add a new document |
| **Query** | Searches wiki + KG + source chunks, answers with citations | When a team member asks a question |
| **Lint** | Checks for orphan pages, semantic drift, contradictions | Scheduled (weekly) or after bulk ingests |

### Why Not Just RAG?

| Problem | RAG Approach | Wiki Approach |
|---------|-------------|---------------|
| 50 docs all mention "Company X" | Query-time dedup, inconsistent | Single `company-x.md` page, authoritative |
| Conflicting info across docs | LLM sees all conflicts, picks one | Lint detects contradiction, flags it |
| Context window filling up | Truncate docs | Compact wiki pages fit more context |
| "What do we know about X?" | Retrieves raw chunks | Returns curated wiki page |
| Knowledge changes over time | Stale embeddings | Git history, drift monitoring, versioning |

---

## 2. How It Works — Core Architecture

```
                         ┌─────────────────────┐
                         │   FastAPI (port 8000)│
                         │   /api/v1/*          │
                         └────────┬────────────-┘
                                  │ JWT auth
              ┌───────────────────┼───────────────────┐
              │                   │                   │
         POST /ingest        POST /query         POST /lint
              │                   │                   │
              ▼                   ▼                   ▼
        ┌──────────┐       ┌──────────────┐    ┌──────────┐
        │  Celery  │       │ Sync handler │    │  Celery  │
        │  Worker  │       │ (streaming   │    │  Worker  │
        │ (ingest) │       │  optional)   │    │  (lint)  │
        └────┬─────┘       └──────┬───────┘    └────┬─────┘
             │                   │                  │
             │         ┌─────────┴────────┐         │
             │         │  Hybrid Retrieval│         │
             │         │  ┌────────────┐  │         │
             │         │  │pgvector    │  │         │
             │         │  │ANN search  │  │         │
             │         │  └────────────┘  │         │
             │         │  ┌────────────┐  │         │
             │         │  │KG graph    │  │         │
             │         │  │traversal   │  │         │
             │         │  └────────────┘  │         │
             │         │  ┌────────────┐  │         │
             │         │  │RRF fusion  │  │         │
             │         │  └────────────┘  │         │
             │         └─────────┬────────┘         │
             │                   │                  │
             ▼                   ▼                  ▼
        ┌──────────────────────────────────────────────┐
        │              PostgreSQL + pgvector            │
        │  wiki_pages  │  kg_nodes  │  source_chunks    │
        │  (HNSW idx)  │  (HNSW)    │  (HNSW)           │
        └──────────────────────────────────────────────┘
             │
             ▼
        ┌──────────┐    ┌──────────┐    ┌──────────────┐
        │   Git    │    │  Redis   │    │  Anthropic   │
        │  Repos   │    │  Cache   │    │  Claude API  │
        │ (one per │    │  +Celery │    │  + Voyage AI │
        │workspace)│    │  broker  │    │  (embeddings)│
        └──────────┘    └──────────┘    └──────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 + pgvector (HNSW) |
| Cache / Queue | Redis 7 |
| Workers | Celery 5 (queues: ingest, lint, embedding, graph) |
| LLM | Anthropic Claude (opus-4-6 for ingest/lint, haiku-4-5 for gate) |
| Embeddings | Voyage AI `voyage-3-large` (1024-dim) |
| Wiki Storage | Git (gitpython), one repo per workspace |
| Graph | NetworkX + Louvain community detection |
| Auth | JWT (HS256), bcrypt passwords |

---

## 3. Getting Started

### Prerequisites

- Docker and Docker Compose
- An Anthropic API key (`claude-opus-4-6` access)
- A Voyage AI API key (free tier works for small teams)

### Quick Start

```bash
# 1. Clone and configure
git clone <repo> context && cd context
cp .env.example .env

# 2. Edit .env — set at minimum:
#   ANTHROPIC_API_KEY=sk-ant-...
#   VOYAGE_API_KEY=pa-...
#   SECRET_KEY=<random 32+ char string>
#   DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/context
#   REDIS_URL=redis://redis:6379/0

# 3. Start everything
make up
# This starts: PostgreSQL, Redis, API, Celery workers, Celery Beat, Flower

# 4. Verify health
curl http://localhost:8000/health
# → {"status": "ok", "environment": "development"}

# 5. Open the wiki portal (read-only browser UI)
open http://localhost:3000

# 6. View worker dashboard
open http://localhost:5555   # Flower UI
```

### First User & Workspace

```bash
# Register your first user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@company.com", "password": "your-secure-password"}'

# Login to get tokens
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@company.com", "password": "your-secure-password"}'
# → {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer"}

# Store the token
export TOKEN="eyJ..."

# Create your first workspace
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"slug": "engineering", "display_name": "Engineering Team"}'
# → {"id": "ws-uuid-here", "slug": "engineering", ...}

export WS_ID="ws-uuid-here"
```

### Environment Variables (`.env.example`)

```bash
# ── Database ────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/context

# ── Redis ───────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# ── AI APIs ─────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
ANTHROPIC_MODEL=claude-opus-4-6
ANTHROPIC_EMBEDDING_MODEL=voyage-3-large

# ── Auth ────────────────────────────────────────────────────
SECRET_KEY=change-this-to-a-random-64-char-string-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# ── Storage ─────────────────────────────────────────────────
STORAGE_BACKEND=local             # or "s3" for production
STORAGE_LOCAL_ROOT=./data/sources
# For S3:
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_S3_BUCKET=my-wiki-sources
# AWS_REGION=us-east-1

# ── Wiki Git ─────────────────────────────────────────────────
WIKI_REPOS_ROOT=./wiki_repos

# ── Portal ───────────────────────────────────────────────────
PUBLIC_API_ENABLED=true           # set false to disable the read-only portal API

# ── Quality Controls ─────────────────────────────────────────
DRIFT_ALERT_THRESHOLD=0.35        # cosine distance from original embedding
HALLUCINATION_GATE_ENABLED=true   # set false to speed up dev

# ── Performance ──────────────────────────────────────────────
HOT_PAGES_CACHE_TOP_N=10
HOT_PAGES_CACHE_TTL_SECONDS=900
KG_COMMUNITY_REBUILD_DEBOUNCE_MINUTES=10

# ── Rate Limits (requests/minute per user) ────────────────────
RATE_LIMIT_DEFAULT=120
RATE_LIMIT_INGEST=10
RATE_LIMIT_QUERY=60
RATE_LIMIT_LINT=5

# ── App ──────────────────────────────────────────────────────
ENVIRONMENT=production
LOG_LEVEL=INFO
```

---

## 4. Configuration Reference

### Key Settings Explained

#### `ANTHROPIC_MODEL`
Controls which Claude model is used for **ingest and lint**. `claude-opus-4-6` gives the best wiki quality. For cost-sensitive deployments, `claude-sonnet-4-6` works well for ingest; the hallucination gate always uses `claude-haiku-4-5-20251001` regardless of this setting.

#### `DRIFT_ALERT_THRESHOLD`
A page is flagged for semantic drift when:
```
cosine_distance(original_embedding, current_embedding) > threshold
```
Default `0.35`. Pages drifting past `threshold × 2 = 0.70` are flagged as `error` (not just `warning`). Lower values = more sensitive. Typical values:
- `0.20` — strict (flag any significant rewrite)
- `0.35` — balanced (default)
- `0.50` — lenient (only flag major topic shifts)

#### `HALLUCINATION_GATE_ENABLED`
When `true`, every proposed wiki page edit is verified against its source by `claude-haiku-4-5` before being committed to git. Adds ~0.5-1s per page edit but prevents hallucinations from entering the wiki. Set to `false` in local development to speed up testing.

#### `HOT_PAGES_CACHE_TOP_N`
The top N most-queried pages are cached in the Claude prompt's system block using `cache_control: ephemeral`. This dramatically reduces latency and cost for frequently accessed pages. Set to 10-20 for most teams.

#### `KG_COMMUNITY_REBUILD_DEBOUNCE_MINUTES`
After an ingest job, community detection (Louvain) is re-run, but debounced by this many minutes. If multiple ingests fire in quick succession, only one rebuild happens. Set lower (2-5) for real-time demos, higher (30-60) for bulk imports.

---

## 5. Team Setup & Access Control

### Role Hierarchy

```
platform_admin  ──┐
                  │ bypass all workspace checks
admin        ─────┤ manage workspace, members, schema
editor       ─────┤ ingest, edit wiki, run lint
reader       ─────┘ query only, read wiki pages
```

Roles are ordered: `reader (1) < editor (2) < admin (3)`. An endpoint requiring `editor` accepts `editor` or `admin`.

### Setting Up a Team

```bash
# 1. Create workspace (admin required)
POST /api/v1/workspaces
{"slug": "product-team", "display_name": "Product Team"}

# 2. Register team members
POST /api/v1/auth/register
{"email": "alice@company.com", "password": "..."}
# repeat for each member

# 3. Add members to workspace with their roles
POST /api/v1/workspaces/{ws_id}/members
{"user_id": "alice-uuid", "role": "editor"}

POST /api/v1/workspaces/{ws_id}/members
{"user_id": "bob-uuid", "role": "reader"}

# 4. Change a member's role
PATCH /api/v1/workspaces/{ws_id}/members/{user_id}
{"role": "admin"}

# 5. Remove a member
DELETE /api/v1/workspaces/{ws_id}/members/{user_id}
```

### Multi-Workspace Setup (Big Five Scale)

For a large organization, create one workspace per team or domain:

```
workspaces/
├── engineering        (slug)  → Software Engineering
├── product            (slug)  → Product Management
├── legal              (slug)  → Legal & Compliance
├── sales              (slug)  → Sales & GTM
└── executive          (slug)  → Executive / Strategy
```

Users can be members of multiple workspaces with different roles. A `platform_admin` flag bypasses workspace membership checks entirely — use this for internal tools admins.

### Example: Onboarding a New Engineer

```bash
# HR or admin runs this on day 1:

# Register the new hire
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "newengineer@company.com", "password": "temp-password-123"}'
# → {"id": "new-user-uuid", "email": "newengineer@company.com"}

# Add them as editor to Engineering workspace
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/members" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "new-user-uuid", "role": "editor"}'

# Add them as reader to cross-functional workspaces
curl -X POST "http://localhost:8000/api/v1/workspaces/$PRODUCT_WS_ID/members" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "new-user-uuid", "role": "reader"}'
```

---

## 6. Core Workflows

### 6.1 Ingest: Teaching the Wiki

Ingest reads source documents and has the LLM update wiki pages based on what it learns.

#### What Happens During Ingest

```
Source file → extract text → chunk → embed
                                        ↓
                              hybrid retrieval
                              (what wiki pages
                               are relevant?)
                                        ↓
                              LLM ingest call
                              (Claude reads source,
                               proposes wiki edits,
                               extracts KG entities)
                                        ↓
                              hallucination gate
                              (haiku verifies each
                               page edit vs source)
                                        ↓
                              git commit + DB update
                              + KG upsert
                                        ↓
                              community detection
                              (debounced 10 min)
```

#### Ingest a PDF

```bash
# Upload the file first
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/sources" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./quarterly-report-q1-2026.pdf" \
  -F "title=Q1 2026 Quarterly Report"
# → {"id": "source-uuid", "ingest_status": "pending", ...}

export SOURCE_ID="source-uuid"

# Trigger ingest
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"source_ids\": [\"$SOURCE_ID\"]}"
# → {"id": "job-uuid", "status": "queued", ...}  202 Accepted

export JOB_ID="job-uuid"

# Poll for completion
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/ingest/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN"
# → {"status": "done", "pages_touched": [...], "llm_tokens_used": 24500, "llm_cost_usd": 0.18}
```

#### Ingest a URL

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/sources/from-url" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://openai.com/research/gpt-4", "title": "GPT-4 Research Paper"}'
# → {"id": "source-uuid", ...}

# Then ingest as above
```

#### Bulk Ingest (Multiple Sources)

```bash
# Upload multiple files, collect IDs
SOURCE_IDS=("uuid1" "uuid2" "uuid3")

# Ingest all at once
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"source_ids\": [\"${SOURCE_IDS[@]}\"]}"
```

> **Note on bulk imports**: For very large imports (100+ documents), add them in batches of 10-20 to avoid overwhelming the LLM and to get faster feedback on which pages are being created.

#### Supported Source Types

| Type | How to Upload | Notes |
|------|-------------|-------|
| `pdf` | Multipart file upload | Text extracted via PyMuPDF |
| `text` | Multipart file upload | `.txt`, `.md`, any plain text |
| `url` | `POST /sources/from-url` | HTML stripped to plain text |
| `docx` | Multipart file upload | Decoded as UTF-8 text |
| `image` | Multipart file upload | Skipped (vision ingest not yet implemented) |

---

### 6.2 Query: Asking the Wiki

#### Simple Query

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is our API rate limiting strategy?",
    "top_k": 20
  }'
```

Response:
```json
{
  "answer": "The API uses a token-bucket rate limiter per user per endpoint. Limits are: default 120/min, ingest 10/min, query 60/min, lint 5/min. See [Rate Limits](pages/concepts/rate-limiting.md) for full details.\n\nThe implementation uses Redis with per-user keys, and returns HTTP 429 with a `Retry-After` header when exceeded. [Source: API Design Doc]",
  "citations": [
    {"title": "Rate Limits", "page_path": "pages/concepts/rate-limiting.md", "source_title": null},
    {"title": "API Design Doc", "page_path": null, "source_title": "API Design Doc v2.pdf"}
  ],
  "tokens_used": 3200,
  "cost_usd": 0.024
}
```

#### Query with User Context (Persona-Aware)

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How do I deploy a new service?",
    "user_context": "I am a new backend engineer, unfamiliar with Kubernetes"
  }'
```

The `user_context` field is appended to the query prompt, allowing the LLM to tailor its answer to the asker's experience level.

#### Streaming Query (SSE)

For long answers or real-time UI updates:

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question": "Summarize our entire authentication system"}'
# Streams server-sent events:
# data: {"chunk": "Our authentication system uses..."}
# data: {"chunk": " JWT tokens with HS256 signing..."}
# ...
# data: [DONE]
```

In JavaScript (browser/Node):
```javascript
const response = await fetch(`/api/v1/workspaces/${wsId}/query`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  },
  body: JSON.stringify({ question: "What is our deployment process?" }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let fullAnswer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const chunk = decoder.decode(value);
  // Parse SSE format: "data: {...}\n\n"
  for (const line of chunk.split('\n')) {
    if (line.startsWith('data: ') && line !== 'data: [DONE]') {
      const data = JSON.parse(line.slice(6));
      fullAnswer += data.chunk;
      updateUI(fullAnswer);
    }
  }
}
```

#### Save Query as Exploration Page

When `save_as_exploration: true`, the answer is written back to the wiki as a new page of type `exploration`, making it discoverable for future queries:

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are all the integrations we support?",
    "save_as_exploration": true
  }'
```

---

### 6.3 Lint: Quality Checks

Lint runs three phases over wiki pages:

| Phase | What It Checks | Method |
|-------|---------------|--------|
| 1 — Structural | Orphan pages (no inbound links, no KG edges) | Static analysis |
| 2 — Semantic Drift | Pages that have moved far from their original meaning | Vector distance (no LLM) |
| 3 — Contradictions | Factual conflicts between pages in the same KG community | LLM (Claude) |

#### Run a Full Lint Pass

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/lint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope": "full"}'
# → {"id": "run-uuid", "status": "queued"} 202 Accepted

# Poll
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/lint/$RUN_ID" \
  -H "Authorization: Bearer $TOKEN"
# → {"status": "done", "finding_count": 7, ...}

# Get findings
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/lint/$RUN_ID/findings" \
  -H "Authorization: Bearer $TOKEN"
```

Example findings response:
```json
[
  {
    "id": "finding-1",
    "finding_type": "orphan",
    "severity": "warning",
    "description": "Page 'pages/entities/old-vendor.md' has no inbound links or KG edges.",
    "wiki_page_id": "page-uuid",
    "evidence": null
  },
  {
    "id": "finding-2",
    "finding_type": "semantic_drift",
    "severity": "error",
    "description": "Page 'pages/concepts/authentication.md' has drifted 0.72 from its original meaning across 14 versions (threshold: 0.35).",
    "wiki_page_id": "page-uuid-2",
    "evidence": {
      "absolute_drift": 0.7200,
      "threshold": 0.35,
      "version_count": 14
    }
  },
  {
    "id": "finding-3",
    "finding_type": "contradiction",
    "severity": "error",
    "description": "Conflicting claim about API versioning strategy",
    "wiki_page_id": "page-uuid-3",
    "evidence": {
      "page_a": "pages/concepts/api-design.md",
      "page_b": "pages/concepts/versioning.md",
      "page_a_excerpt": "We use URL versioning (/v1/, /v2/)",
      "page_b_excerpt": "All APIs use header-based versioning (X-API-Version)"
    }
  }
]
```

#### Scoped Lint (After a Specific Ingest)

```bash
# Lint only the pages touched by a recent ingest
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/lint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "page_list",
    "page_ids": ["page-uuid-1", "page-uuid-2"]
  }'
```

#### Filter Findings by Severity

```bash
# Only errors
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/lint/$RUN_ID/findings?severity=error" \
  -H "Authorization: Bearer $TOKEN"

# Only contradictions
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/lint/$RUN_ID/findings?finding_type=contradiction" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 6.4 Schema: Defining Your Knowledge Structure

The schema is a Markdown document defining what entity types exist, how pages should be organized, and what relationships are meaningful for your domain. It's cached in the Claude prompt's system block so it influences every ingest and query.

#### Get Current Schema

```bash
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/schema" \
  -H "Authorization: Bearer $TOKEN"
```

#### Set Schema (Admin Only)

```bash
curl -X PUT "http://localhost:8000/api/v1/workspaces/$WS_ID/schema" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Engineering Wiki Schema\n\n## Page Types\n- **entity**: A specific person, system, or team\n- **concept**: An abstract technical concept or process\n- **summary**: A digest of a document or meeting\n- **index**: A top-level navigation page\n\n## Entity Types\n- **person**: Engineers, PMs, stakeholders\n- **system**: Services, databases, external APIs\n- **team**: Organizational units\n- **technology**: Languages, frameworks, tools\n\n## Key Relationships\n- person **works_on** system\n- system **depends_on** system\n- team **owns** system\n- system **uses** technology\n\n## Naming Conventions\n- Entities: pages/entities/{slug}.md\n- Concepts: pages/concepts/{slug}.md\n- Summaries: pages/summaries/{slug}.md\n\n## Cross-References\nUse [[pages/entities/my-service.md]] syntax for wiki links."
  }'
```

> **Best practice**: Keep the schema under 2000 tokens. It's included in every LLM call, so overly verbose schemas increase cost significantly.

#### Example Schema for a Product Team

```markdown
# Product Wiki Schema

## Page Types
- **entity**: A product, feature, or stakeholder
- **concept**: A product principle, strategy, or framework
- **summary**: Meeting notes, research synthesis, launch post-mortems
- **exploration**: Ad-hoc research from queries (auto-generated)
- **log**: Ongoing change log for a product area

## Entity Types
- **product**: A named product or product area
- **feature**: A specific feature or capability
- **person**: Stakeholder, PM, designer, eng lead
- **competitor**: Competitor products

## Relationships
- person **owns** product
- feature **part_of** product
- product **competes_with** competitor
- feature **depends_on** feature

## Naming
- pages/products/{product-slug}.md
- pages/features/{feature-slug}.md
- pages/people/{name-slug}.md
```

---

## 7. API Reference

All endpoints are under `/api/v1`. Authentication uses `Authorization: Bearer <access_token>`.

### Authentication

| Method | Path | Auth | Body | Response |
|--------|------|------|------|----------|
| POST | `/auth/register` | None | `{email, password}` | `{id, email}` 201 |
| POST | `/auth/login` | None | `{email, password}` | `{access_token, refresh_token, token_type}` |
| POST | `/auth/refresh` | None | `{refresh_token}` | `{access_token, refresh_token, token_type}` |

### Workspaces

| Method | Path | Role | Body | Response |
|--------|------|------|------|----------|
| GET | `/workspaces` | reader | — | `list[WorkspaceOut]` |
| POST | `/workspaces` | platform_admin | `{slug, display_name}` | `WorkspaceOut` 201 |
| GET | `/workspaces/{id}` | reader | — | `WorkspaceOut` |
| DELETE | `/workspaces/{id}` | admin | — | 204 |
| POST | `/workspaces/{id}/members` | admin | `{user_id, role}` | `{status}` 201 |
| PATCH | `/workspaces/{id}/members/{uid}` | admin | `{role}` | `{status}` |
| DELETE | `/workspaces/{id}/members/{uid}` | admin | — | 204 |

### Sources (under `/workspaces/{ws_id}/sources`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/sources` | reader | Params: `status_filter`, `limit` (max 200), `offset` |
| POST | `/sources` | editor | Multipart: `file` + `title` (Form field). Deduped by content hash. |
| GET | `/sources/{id}` | reader | — |
| POST | `/sources/from-url` | editor | Body: `{url, title}`. Fetches URL, stores as source. |
| DELETE | `/sources/{id}` | editor | — |

### Wiki Pages (under `/workspaces/{ws_id}/wiki`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/pages` | reader | Params: `page_type`, `limit` (max 200), `offset` |
| POST | `/pages` | editor | Body: `{page_path, title, page_type, content}` |
| GET | `/pages/{page_path}` | reader | `page_path` is URL-encoded (e.g. `pages%2Fentities%2Fopenai.md`) |
| PUT | `/pages/{page_path}` | editor | Body: `{content, title?}`. Commits to git. |
| GET | `/pages/{page_path}/history` | reader | Returns git log for this file |
| POST | `/pages/{page_path}/rollback` | editor | Body: `{commit_sha}`. Restores file at that SHA. |
| DELETE | `/pages/{page_path}` | editor | — |

### Ingest Jobs (under `/workspaces/{ws_id}/ingest`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| POST | `/ingest` | editor | Body: `{source_ids: [uuid, ...]}`. Returns 202, dispatches Celery task. |
| GET | `/ingest/{job_id}` | reader | Poll for status: `queued|running|done|failed` |
| DELETE | `/ingest/{job_id}` | editor | Cancel a queued job. |

### Query (under `/workspaces/{ws_id}/query`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| POST | `/query` | reader | Body: `{question, top_k?, save_as_exploration?, user_context?}`. SSE if `Accept: text/event-stream`. |

### Lint (under `/workspaces/{ws_id}/lint`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| POST | `/lint` | editor | Body: `{scope: "full"|"incremental"|"page_list", page_ids?: [...]}`. Returns 202. |
| GET | `/lint/{run_id}` | reader | Poll for status. |
| GET | `/lint/{run_id}/findings` | reader | Params: `severity`, `finding_type` |

### Schema (under `/workspaces/{ws_id}/schema`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/schema` | reader | — |
| PUT | `/schema` | admin | Body: `{content}`. Invalidates prompt cache. |

### Knowledge Graph (under `/workspaces/{ws_id}/graph`)

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/nodes` | reader | Params: `entity_type`, `community_id`, `limit` (max 500), `offset` |
| GET | `/nodes/{node_id}/neighbors` | reader | Param: `depth` (default 1) |
| GET | `/communities` | reader | All community summaries |
| POST | `/graph/search` | reader | Body: `{query, top_k?}`. Semantic search over KG nodes. |

### Admin

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/admin/cost-report` | platform_admin | Param: `workspace_id` (optional filter). Token + cost by workspace. |
| GET | `/admin/users` | platform_admin | All users in the system. |

### Public API (no authentication)

All routes are under `/api/v1/public`. No `Authorization` header required. Enabled/disabled via `PUBLIC_API_ENABLED` env var (returns `503` when disabled).

| Method | Path | Notes |
|--------|------|-------|
| GET | `/public/workspaces` | All workspaces (non-deleted) |
| GET | `/public/workspaces/{id}/pages` | Params: `page_type`, `limit` (max 200), `offset` |
| GET | `/public/workspaces/{id}/pages/{path}` | Full page content from git. `path` uses `/` not `%2F`. |
| GET | `/public/workspaces/{id}/sources` | Params: `status_filter`, `limit` (max 200), `offset` |
| GET | `/public/workspaces/{id}/sources/{sid}/pages` | Pages produced by a specific source |
| GET | `/public/workspaces/{id}/search` | Params: `q` (min 2 chars, required), `limit` (max 50). Title matches ranked first. |

These endpoints are consumed by the portal at `http://localhost:3000` but can be called directly from any HTTP client.

---

## 8. Portal — Read-Only Web UI

The portal is a Vite + React SPA that exposes the wiki to users who don't need API access. It runs as a separate Docker service on port 3000 and connects to the public API described above.

### Access

```
http://localhost:3000        # Docker (make up)
http://localhost:5173        # Local dev (cd portal && npm run dev)
```

### Features

| Feature | Description |
|---------|-------------|
| Browse pages | Sidebar lists all pages grouped by type; click to read Markdown |
| Sources audit | See every ingested source, its status, and the pages it produced |
| Search | Full-text search with context snippets (300ms debounce) |
| Multi-workspace | Workspace picker in the header; switching reloads all content |

### Enabling / Disabling

Set `PUBLIC_API_ENABLED=false` in `.env` to disable the portal API (all endpoints return `503`). The portal itself still serves static files — users see "Unable to connect" instead of content.

### Architecture

```
Browser → nginx (port 3000)
              ├── /           → React SPA (static)
              └── /api/*      → proxy → FastAPI (port 8000)
```

The nginx proxy eliminates CORS issues in production. The Vite dev server (`npm run dev`) has the same `/api` proxy configured in `vite.config.ts`.

### Local Development

```bash
cd portal
npm install
npm run dev       # http://localhost:5173 — hot-reload, proxies /api to localhost:8000
npm run build     # production bundle → dist/
```

---

## 8. Knowledge Graph

The KG is automatically built and updated during ingest. Every entity mentioned in source documents gets a node; relationships between entities become edges.

### Entity Types

| Type | Examples |
|------|---------|
| `person` | Engineers, executives, customers |
| `org` | Companies, teams, departments |
| `concept` | Authentication, rate limiting, microservices |
| `technology` | PostgreSQL, Kubernetes, React |
| `event` | Product launches, incidents, acquisitions |
| `place` | Data centers, offices, regions |

### Relation Types

`works_at` · `founded` · `acquired` · `uses` · `related_to` · `contradicts` · `part_of` · `created`

### Community Detection

Nodes are clustered into communities using the Louvain algorithm. Communities represent naturally cohesive groups of entities (e.g., "authentication systems", "data infrastructure", "product team"). These communities are used by the lint worker to find candidate page pairs for contradiction checking.

For workspaces with more than 500,000 edges, only the top-weight edges (by confidence score) are used for Louvain to prevent memory exhaustion.

### Using the KG

#### Explore Neighbors of a Node

```bash
# Find everything connected to "Authentication Service"
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/graph/nodes/$NODE_ID/neighbors?depth=2" \
  -H "Authorization: Bearer $TOKEN"
```

#### Semantic Search Over Entities

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/graph/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "identity and access management", "top_k": 10}'
# Returns nodes whose embeddings are semantically close to the query
```

#### Browse by Community

```bash
# List all communities
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/graph/communities" \
  -H "Authorization: Bearer $TOKEN"

# List nodes in a specific community
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/graph/nodes?community_id=$COMM_ID" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 9. Semantic Drift & Quality Monitoring

Drift monitoring detects when a wiki page's content has shifted far from its original meaning.

### How It Works

When a page is first created, its embedding is saved as `original_embedding` and **never updated**.  
Each time the page is edited, the system computes:

```
absolute_drift = cosine_distance(original_embedding, current_embedding)
```

This is a value from `0.0` (identical) to `2.0` (opposite). Values above the threshold trigger a lint finding.

### Why Absolute (Not Cumulative) Drift?

Cumulative drift sums incremental distances across all versions. This means a page that oscillates never reaches the threshold — each oscillation cancels out. Absolute drift catches this case correctly because it always measures against the *original intent* of the page, not the most recent version.

### Version History Drift

Each `WikiPageVersion` record also stores `semantic_drift_score`, which is the incremental distance from the previous version. This gives a version-by-version "change magnitude" signal — useful for auditing who made large changes.

### Responding to Drift Findings

When you see a `semantic_drift` finding:

1. **Read the page**: `GET /wiki/pages/{page_path}`
2. **Review history**: `GET /wiki/pages/{page_path}/history`
3. If the drift was unintentional: **rollback** to an earlier commit that had lower drift
4. If the page legitimately evolved: **reset the baseline** by manually updating `original_embedding` in the DB (or delete + recreate the page)

---

## 10. Hallucination Gate

Before any LLM-proposed wiki edit is committed to git, a secondary LLM call (claude-haiku-4-5) verifies the proposed content against the source material.

### Verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| `pass` | All claims supported by source | Commit normally |
| `needs_review` | Some claims unverified but not clearly wrong | Commit with a `> Note: requires human review` banner appended |
| `fail` | Contains claims contradicted by or absent from source | Skip this edit entirely — do NOT commit |

### When an Edit is Blocked

When an edit is blocked (`fail`), the following is logged:
```json
{
  "event": "hallucination_gate_blocked",
  "page_path": "pages/entities/openai.md",
  "unsupported_claims": [
    "OpenAI was founded in 2014",
    "Sam Altman is the CTO"
  ]
}
```

The source document is still ingested and its chunks are still embedded — only that specific page edit is skipped.

### Disabling for Development

Set `HALLUCINATION_GATE_ENABLED=false` in `.env` to skip verification during local development. Never disable in production.

---

## 11. Prompt Caching & Performance

The system uses Anthropic's prompt caching to minimize latency and cost. The system prompt is structured in three layers, ordered from most-stable to least-stable:

```
┌─────────────────────────────────────────────────────────┐
│  Block 1: Schema                                        │
│  (changes rarely — cached for hours)                    │
│  cache_control: ephemeral                               │
├─────────────────────────────────────────────────────────┤
│  Block 2: Hot Pages                                     │
│  (top-10 most queried pages — refreshed every 15 min)  │
│  cache_control: ephemeral                               │
├─────────────────────────────────────────────────────────┤
│  Block 3: Per-request context                           │
│  (retrieved wiki pages for this specific query)         │
│  (no cache — varies every call)                         │
└─────────────────────────────────────────────────────────┘
```

### Cost Impact

For a workspace with 10 hot pages (each ~1500 tokens) and a 1000-token schema:
- Without caching: ~12,500 system tokens per request
- With caching (cache hit): system tokens are billed at ~10% of normal rate
- **Savings**: 90% on system token cost for repeat queries

### Hot Pages

Pages are ranked by query frequency (tracked in Redis sorted set). The top `HOT_PAGES_CACHE_TOP_N` pages are automatically kept in the cached system block. When an ingest touches a hot page, the cache is invalidated and refreshed within 15 minutes by the Beat scheduler.

### Monitoring Cache Hit Rate

Check the Anthropic usage object in ingest job records:
```json
{
  "input_tokens": 4500,
  "output_tokens": 1200,
  "cache_creation_input_tokens": 11000,
  "cache_read_input_tokens": 0
}
```
- `cache_creation_input_tokens` > 0 → cache miss (wrote cache)
- `cache_read_input_tokens` > 0 → cache hit (read from cache)

---

## 12. Background Workers

The system uses four Celery queues. Each can be scaled independently.

### Queue Overview

| Queue | Worker | Typical Latency | Scale Strategy |
|-------|--------|----------------|----------------|
| `ingest` | `ingest_worker` | 30-120s per source | Scale by ingest volume |
| `lint` | `lint_worker` | 60-300s per run | 1-2 workers usually sufficient |
| `embedding` | `embedding_worker` | 1-3s per chunk | Scale for fast chunk embedding |
| `graph` | `graph_worker` | 10-60s | 1 worker (debounced) |

### Monitoring Workers

```bash
# Flower dashboard
open http://localhost:5555

# Check active tasks
curl http://localhost:5555/api/workers

# Check queue depths
docker compose exec redis redis-cli llen celery       # default queue
docker compose exec redis redis-cli llen ingest       # ingest queue
```

### Beat Schedule

The Celery Beat process runs one periodic task:

| Task | Schedule | Purpose |
|------|---------|---------|
| `refresh_hot_pages_all_workspaces` | Every 15 min | Refreshes prompt-cache hot pages for all workspaces |

### Manual Task Dispatch (Python)

```python
from app.workers.ingest_worker import process_ingest_job
from app.workers.lint_worker import run_lint_pass

# Dispatch ingest
process_ingest_job.apply_async(args=["job-uuid-str"], queue="ingest")

# Dispatch lint
run_lint_pass.apply_async(args=["run-uuid-str"], queue="lint")
```

---

## 13. Git-Backed Storage

Every workspace has its own git repository under `WIKI_REPOS_ROOT/{workspace_id}/`. All wiki page content is stored as Markdown files committed to git.

### Repository Structure

```
wiki_repos/{workspace_id}/
├── schema.md                    # Workspace schema (copy, for reference)
├── index.md                     # Auto-generated index page
├── log.md                       # Change log
└── pages/
    ├── entities/
    │   ├── openai.md
    │   ├── anthropic.md
    │   └── google-deepmind.md
    ├── concepts/
    │   ├── transformer-architecture.md
    │   └── rlhf.md
    └── summaries/
        └── q1-2026-report.md
```

### Version History

Every write creates a git commit. The commit message format is:
```
ingest:{source_id} — {change_summary[:80]}
```

### Rollback

```bash
# View history of a page
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/wiki/pages/pages%2Fentities%2Fopenai.md/history" \
  -H "Authorization: Bearer $TOKEN"
# → [{"sha": "abc123", "message": "ingest:... — added funding history", "author": "ingest-bot", "timestamp": "..."}]

# Rollback to a specific commit
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/wiki/pages/pages%2Fentities%2Fopenai.md/rollback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"commit_sha": "abc123"}'
```

### Direct Editing

Editors can manually edit wiki pages through the API (bypassing the LLM):

```bash
curl -X PUT "http://localhost:8000/api/v1/workspaces/$WS_ID/wiki/pages/pages%2Fentities%2Fopenai.md" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "OpenAI",
    "content": "# OpenAI\n\nOpenAI is an AI research company founded in 2015...\n\n## Products\n- GPT-4\n- DALL-E 3\n- Whisper"
  }'
```

---

## 14. Database Schema

### Core Tables

```
users
├── id (UUID, PK)
├── email (unique)
├── hashed_password
├── is_active
├── is_platform_admin
└── created_at / updated_at

user_workspace_memberships
├── id (UUID, PK)
├── user_id → users.id
├── workspace_id → workspaces.id
├── role (admin|editor|reader)
└── UNIQUE(user_id, workspace_id)

workspaces
├── id (UUID, PK)
├── slug (unique)
├── display_name
├── git_repo_path
├── schema_version
├── settings (JSONB)
└── deleted_at (soft delete)

sources
├── id (UUID, PK)
├── workspace_id
├── title, source_type
├── storage_key (S3 or local path)
├── content_hash (unique — deduplication)
├── byte_size, metadata (JSONB)
└── ingest_status (pending|processing|done|failed)

source_chunks
├── id (UUID, PK)
├── source_id → sources.id
├── chunk_index, chunk_text, token_count
└── embedding (Vector(1024)) [HNSW index]

wiki_pages
├── id (UUID, PK)
├── workspace_id, page_path (UNIQUE together)
├── title, page_type
├── git_commit_sha, content_hash, word_count
├── embedding (Vector(1024))         [HNSW index]
├── original_embedding (Vector(1024)) [set at creation, never updated]
└── last_lint_at, created_by, updated_by

wiki_page_versions
├── id (UUID, PK)
├── wiki_page_id → wiki_pages.id
├── git_commit_sha, content, diff_from_prev
├── semantic_drift_score (from previous version)
└── change_reason, changed_by

wiki_page_source_map
├── id (UUID, PK)
├── wiki_page_id → wiki_pages.id
├── source_id → sources.id
├── workspace_id
├── first_commit_sha, latest_commit_sha
└── UNIQUE(wiki_page_id, source_id)

kg_nodes
├── id (UUID, PK)
├── workspace_id, entity_name, entity_type
├── aliases (ARRAY)
├── wiki_page_id, source_ids (ARRAY)
├── embedding (Vector(1024)) [HNSW index]
├── community_id → kg_communities.id
└── UNIQUE(workspace_id, entity_name, entity_type)

kg_edges
├── id (UUID, PK)
├── workspace_id
├── source_node_id, target_node_id → kg_nodes.id
├── relation_type, weight (confidence)
└── evidence (JSONB)

kg_communities
├── id (UUID, PK)
├── workspace_id, label, member_count
├── summary, embedding (Vector(1024))
└── parent_community_id (for hierarchical communities)

ingest_jobs
├── id (UUID, PK)
├── workspace_id, celery_task_id
├── status (queued|running|done|failed|cancelled)
├── source_ids (ARRAY), pages_touched (ARRAY)
├── llm_tokens_used, llm_cost_usd
└── error_message, triggered_by, started_at, completed_at

lint_runs / lint_findings (see API Reference section)

audit_logs
├── workspace_id, user_id
├── action (string), resource_type, resource_id
├── old_value, new_value (JSONB)
└── ip_address, user_agent
```

### Running Migrations

```bash
# Apply all pending migrations
make migrate
# or: alembic upgrade head

# Create a new migration (after changing models)
make revision msg="add_feature_flags_table"
# or: alembic revision --autogenerate -m "add_feature_flags_table"

# Downgrade one step
docker compose exec api alembic downgrade -1
```

---

## 15. Rate Limits

Rate limits are enforced per user per endpoint using a token-bucket algorithm backed by Redis.

| Endpoint Pattern | Limit (req/min) | Rationale |
|-----------------|----------------|-----------|
| `POST /ingest` | 10 | LLM calls are expensive |
| `POST /query` | 60 | Normal interactive use |
| `POST /lint` | 5 | Heavy DB + LLM scan |
| All others | 120 | Standard API rate |

When a limit is exceeded, the API returns:
```
HTTP 429 Too Many Requests
Retry-After: 15
{"detail": "Rate limit exceeded. Try again in 15 seconds."}
```

### Increasing Limits

Edit `app/config.py` or set environment variables:
```bash
RATE_LIMIT_INGEST=20
RATE_LIMIT_QUERY=120
```

For dedicated service accounts (CI pipelines, integrations), consider creating a user with elevated limits or, for internal services, using a platform admin token.

---

## 16. Operations & Monitoring

### Health Check

```bash
curl http://localhost:8000/health
# → {"status": "ok", "environment": "production"}
```

### Structured Logging

All application logs use `structlog` with JSON output in production. Key log events:

| Event | Level | When |
|-------|-------|------|
| `ingest_job_completed` | INFO | After successful ingest |
| `ingest_job_failed` | ERROR | After max retries exhausted |
| `hallucination_gate_blocked` | WARNING | LLM edit rejected by gate |
| `high_semantic_drift` | WARNING | Page drift > threshold during ingest |
| `kg_communities_rebuilt` | INFO | After Louvain run |
| `kg_graph_exceeds_full_louvain_capacity` | WARNING | Edge count > 500k |
| `lint_run_completed` | INFO | After lint pass |
| `hot_pages_cache_refreshed` | INFO | After hot pages refresh |

### Flower (Worker Dashboard)

```bash
open http://localhost:5555
```

Flower shows: active tasks, task history, worker status, queue depths, failure rates.

### Cost Tracking

```bash
# Platform admin: total cost by workspace
curl "http://localhost:8000/api/v1/admin/cost-report" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Specific workspace
curl "http://localhost:8000/api/v1/admin/cost-report?workspace_id=$WS_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Response:
# [{"workspace_id": "...", "total_tokens": 1250000, "total_cost_usd": 9.38, "job_count": 47}]
```

### Audit Logs

All mutating API calls (`POST`, `PUT`, `PATCH`, `DELETE`) are logged to the `audit_logs` table with the user ID, resource affected, old and new values, and IP address. Access audit logs directly via SQL for compliance reporting.

### Git Remote Sync (Obsidian)

Push every wiki commit to a remote GitHub or GitLab repository so developers can clone the wiki and view it in Obsidian.

**Configure env vars** (add to `.env` or Kubernetes Secret):

```bash
WIKI_GIT_ENABLED=true
WIKI_GIT_PROVIDER=github          # or "gitlab"
WIKI_GIT_PROVIDER_TOKEN=ghp_...   # fine-grained PAT with repo scope
WIKI_GIT_ORG=your-org             # GitHub org or GitLab namespace
# WIKI_GIT_BASE_URL=              # only for self-hosted GitLab
```

**How it works**: After every wiki write (ingest, API edit, MCP tool call), a `git_push` Celery task is enqueued. The task acquires a per-workspace Redis lock and pushes to the remote using the token-embedded HTTPS URL. Push failures are logged but never block the wiki operation.

**Get the clone URL for a workspace**:

```bash
curl http://your-host/api/v1/workspaces/$WS_ID/clone-url \
  -H "Authorization: Bearer $TOKEN"
# → {"clone_url": "https://github.com/your-org/wiki-team.git", ...}

git clone https://github.com/your-org/wiki-team.git ~/wiki-team
# Open ~/wiki-team as an Obsidian vault
```

**Set up auto-pull in Obsidian**: Install the "Obsidian Git" community plugin → set Pull interval to `1` minute → enable "Pull on startup". Pages appear in Obsidian within ~90 seconds of an ingest.

**Verify push is working**:

```bash
kubectl logs -f deployment/context-worker | grep git_push
# {"event": "git_push_success", "workspace_id": "...", "sha": "..."}
```

Push log events: `git_push_start`, `git_push_success`, `git_push_error`.

---

## 17. Scaling Guide

### Single-Server (< 50 users, < 10k pages)

The default `docker-compose.yml` is sufficient. Default Celery concurrency of 4 workers handles ~2-4 concurrent ingest jobs.

### Medium Scale (50-500 users, 10k-100k pages)

```yaml
# docker-compose.yml adjustments:

worker:
  deploy:
    replicas: 3
  command: celery -A app.workers.celery_app worker
           -Q ingest,embedding --concurrency=8

worker-lint:
  image: app
  command: celery -A app.workers.celery_app worker
           -Q lint,graph --concurrency=2
```

Separate ingest (CPU + LLM bound) from lint (I/O + LLM bound) onto different worker pools.

### Large Scale (500+ users, 100k+ pages)

**Database:**
- Move PostgreSQL to a dedicated host with `pgvector` and adequate RAM (HNSW index for 1M+ vectors needs ~8-16GB RAM)
- Partition `source_chunks` and `wiki_page_versions` by `workspace_id`
- Add read replicas for query-path reads

**Redis:**
- Use Redis Cluster or Redis Sentinel for HA
- Separate Redis instances for Celery broker (`db=0`) and app cache (`db=1-3`)

**Celery:**
- Deploy separate worker groups per queue type
- Use `celery autoscale=10,2` for elastic scaling

**Storage:**
- Switch to S3 (`STORAGE_BACKEND=s3`) — local storage doesn't work across multiple API instances
- Mount wiki repos on shared NFS or switch to a remote git provider per workspace

**API:**
- Run multiple Uvicorn instances behind a load balancer (nginx or ALB)
- All state is in PostgreSQL + Redis, so API instances are stateless

**Knowledge Graph:**
- At >500k edges per workspace, community detection is automatically capped. For full graph coverage at Big Five scale, plan to migrate the KG to a dedicated graph database (Neo4j or Amazon Neptune).

---

## 18. Examples: End-to-End Team Workflows

### Example 1: Engineering Team — Onboarding a New Service

Your team just shipped a new microservice. The tech spec and README need to live in the wiki.

```bash
# 1. Upload the tech spec
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/sources" \
  -H "Authorization: Bearer $EDITOR_TOKEN" \
  -F "file=@./payment-service-tech-spec.pdf" \
  -F "title=Payment Service Tech Spec v1.2"

# 2. Also ingest the GitHub README as a URL
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/sources/from-url" \
  -H "Authorization: Bearer $EDITOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/company/payment-service#readme", "title": "Payment Service README"}'

# 3. Trigger ingest of both
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/ingest" \
  -H "Authorization: Bearer $EDITOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_ids": ["spec-uuid", "readme-uuid"]}'

# ── After ingest completes (usually 1-2 min) ──

# 4. A new engineer asks a question
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/query" \
  -H "Authorization: Bearer $NEW_ENG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What database does the payment service use, and why?",
    "user_context": "I am new to this team and learning the architecture"
  }'

# Example answer:
# "The Payment Service uses PostgreSQL as its primary data store, chosen for ACID
#  compliance requirements around financial transactions. Redis is used for idempotency
#  key caching to prevent double-charges. See [Payment Service](pages/entities/payment-service.md)
#  for full architecture details. [Source: Payment Service Tech Spec v1.2]"
```

---

### Example 2: Product Team — Synthesizing Customer Research

Your PM has 20 user interview transcripts and wants the wiki to know what customers care about.

```bash
# Upload all transcripts
for f in interviews/*.txt; do
  curl -X POST "http://localhost:8000/api/v1/workspaces/$PROD_WS_ID/sources" \
    -H "Authorization: Bearer $PM_TOKEN" \
    -F "file=@$f" \
    -F "title=Customer Interview: $(basename $f .txt)"
done

# Ingest all at once (collect the source IDs first via GET /sources)
curl "http://localhost:8000/api/v1/workspaces/$PROD_WS_ID/sources" \
  -H "Authorization: Bearer $PM_TOKEN" | jq '[.[] | .id]'

curl -X POST "http://localhost:8000/api/v1/workspaces/$PROD_WS_ID/ingest" \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_ids": ["id1", "id2", ... "id20"]}'

# ── After ingest ──

# Query the synthesized knowledge
curl -X POST "http://localhost:8000/api/v1/workspaces/$PROD_WS_ID/query" \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the top 3 pain points customers mentioned around onboarding?",
    "save_as_exploration": true
  }'
# The answer is saved as pages/explorations/onboarding-pain-points.md for future reference

# Run lint to check for contradictions across interviews
curl -X POST "http://localhost:8000/api/v1/workspaces/$PROD_WS_ID/lint" \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope": "full"}'
```

---

### Example 3: Legal/Compliance Team — Policy Document Management

Legal has 50 policy PDFs that need to be searchable and kept consistent.

```bash
# Set a schema specific to legal
curl -X PUT "http://localhost:8000/api/v1/workspaces/$LEGAL_WS_ID/schema" \
  -H "Authorization: Bearer $LEGAL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "# Legal Wiki Schema\n\n## Page Types\n- entity: A regulation, law, or standard\n- concept: A legal principle or procedure\n- summary: A policy document digest\n\n## Key Relationships\n- policy **supersedes** policy\n- policy **implements** regulation\n- policy **applies_to** org\n\n## Rules\n- Always cite the source document section\n- Note effective dates\n- Flag any contradictions between policies as high severity"
  }'

# Upload and ingest policies
# (same pattern as above)

# Schedule weekly lint to catch contradictions between policies
# (add a cron job or Celery beat task that calls POST /lint weekly)

# Query: "What is our data retention policy for EU customers?"
curl -X POST "http://localhost:8000/api/v1/workspaces/$LEGAL_WS_ID/query" \
  -H "Authorization: Bearer $STAFF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is our data retention policy for EU customer data under GDPR?"}'
```

---

### Example 4: Manual Wiki Editing with Rollback

A team member accidentally overwrites an important page. Roll it back.

```bash
# View history of the affected page
curl "http://localhost:8000/api/v1/workspaces/$WS_ID/wiki/pages/pages%2Fentities%2Fpayment-service.md/history" \
  -H "Authorization: Bearer $EDITOR_TOKEN"
# [
#   {"sha": "def456", "message": "ingest:... — updated dependencies", "timestamp": "2026-04-20T14:30:00Z"},
#   {"sha": "abc123", "message": "ingest:... — initial page creation", "timestamp": "2026-04-19T10:00:00Z"}
# ]

# Roll back to the version before the bad edit
curl -X POST "http://localhost:8000/api/v1/workspaces/$WS_ID/wiki/pages/pages%2Fentities%2Fpayment-service.md/rollback" \
  -H "Authorization: Bearer $EDITOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"commit_sha": "abc123"}'
```

---

### Example 5: Python SDK-style Integration

For teams building internal tools on top of the API:

```python
import httpx

class WikiClient:
    def __init__(self, base_url: str, token: str, workspace_id: str):
        self.base = base_url
        self.ws = workspace_id
        self.headers = {"Authorization": f"Bearer {token}"}

    def ingest_file(self, path: str, title: str) -> dict:
        with open(path, "rb") as f:
            r = httpx.post(
                f"{self.base}/api/v1/workspaces/{self.ws}/sources",
                headers=self.headers,
                files={"file": (path, f)},
                data={"title": title},
            )
        r.raise_for_status()
        source = r.json()

        job_r = httpx.post(
            f"{self.base}/api/v1/workspaces/{self.ws}/ingest",
            headers=self.headers,
            json={"source_ids": [source["id"]]},
        )
        job_r.raise_for_status()
        return job_r.json()

    def query(self, question: str, user_context: str = "") -> str:
        r = httpx.post(
            f"{self.base}/api/v1/workspaces/{self.ws}/query",
            headers=self.headers,
            json={"question": question, "user_context": user_context},
        )
        r.raise_for_status()
        return r.json()["answer"]

    def run_lint(self) -> dict:
        r = httpx.post(
            f"{self.base}/api/v1/workspaces/{self.ws}/lint",
            headers=self.headers,
            json={"scope": "full"},
        )
        r.raise_for_status()
        return r.json()


# Usage
client = WikiClient(
    base_url="http://localhost:8000",
    token="eyJ...",
    workspace_id="ws-uuid",
)

# Ingest a document
job = client.ingest_file("./design-doc.pdf", "System Design Doc v3")
print(f"Ingest job: {job['id']}")

# Ask a question
answer = client.query(
    "What are the failure modes of the payment service?",
    user_context="I am the on-call engineer investigating an incident",
)
print(answer)

# Run weekly lint
lint_run = client.run_lint()
print(f"Lint run: {lint_run['id']}, queued")
```

---

## 19. Troubleshooting

### Ingest job stuck in "queued"

**Check workers are running:**
```bash
docker compose ps
# All containers (api, worker, beat, db, redis) should be "Up"

# Check worker logs
docker compose logs worker --tail=50
```

**Check Celery can reach Redis:**
```bash
docker compose exec worker celery -A app.workers.celery_app inspect ping
```

---

### "Voyage API key is incorrect" or embedding errors

The Voyage API key is separate from the Anthropic key. Make sure `.env` has:
```bash
VOYAGE_API_KEY=pa-...   # NOT the same as ANTHROPIC_API_KEY
```

---

### Queries return "no relevant wiki pages found"

This usually means ingest hasn't run yet, or ran but created no pages.

1. Check the ingest job status: `GET /ingest/{job_id}`
2. If `status: "failed"`, check `error_message`
3. Check wiki pages exist: `GET /wiki/pages`
4. If pages exist but queries miss them, check `VOYAGE_API_KEY` — wrong key produces random embeddings that won't match anything

---

### High LLM costs

**Find the expensive workspaces:**
```bash
curl http://localhost:8000/api/v1/admin/cost-report \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Reduce cost:**
- Switch `ANTHROPIC_MODEL` to `claude-sonnet-4-6` for ingest (lower cost, slightly lower quality)
- Lower `HOT_PAGES_CACHE_TOP_N` to reduce system prompt size
- Enable `HALLUCINATION_GATE_ENABLED=false` in non-critical workspaces
- Avoid ingesting large files — chunk and deduplicate before uploading

---

### Drift threshold too noisy / too quiet

- Getting too many false positive drift warnings: increase `DRIFT_ALERT_THRESHOLD` to `0.45` or `0.50`
- Missing real drift: decrease to `0.25` or `0.30`
- After changing the threshold, re-run lint: `POST /lint {"scope": "full"}`

---

### git repo not found or write_file fails

The wiki git repo is created automatically when a workspace is created. If it's missing:
```bash
# Check the repos root
ls -la ./wiki_repos/

# The repo should be at:
ls -la ./wiki_repos/{workspace_id}/
```

If missing, the workspace needs to be recreated, or the `RepoManager.init()` method needs to be called manually (this is called during workspace creation in the API).

---

### "community detection running on top-weight edges only" log

This warning appears when a workspace has more than 500,000 KG edges. Community detection still runs, but only on the highest-confidence edges. The warning is informational — the system continues to work. For full coverage at this scale, migrate to a dedicated graph database.

---

### JWT token expired

Access tokens expire after 60 minutes. Use the refresh token to get a new one:
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

Refresh tokens expire after 30 days. After that, the user must log in again.

---

## 20. Claude Code Integration

[Claude Code](https://claude.ai/code) is Anthropic's agentic coding CLI. It reads your entire codebase, edits files, runs commands, and calls tools — making it a natural fit for operating this wiki system: ingesting documents, running lint passes, querying the wiki, and maintaining code.

### How It Fits

```
Developer ──► Claude Code CLI ──► Context API
                │                  (ingest / query / lint)
                │
                ├── reads .claude/CLAUDE.md  (project instructions)
                ├── runs custom /skills      (ingest, query, lint commands)
                ├── fires hooks              (auto-lint after edits)
                └── calls MCP server        (direct API access as tools)
```

### 20.1 — Project CLAUDE.md

`CLAUDE.md` gives Claude persistent context about this project so it never needs re-explaining. Place it at the project root and commit it.

Create `.claude/CLAUDE.md`:

```markdown
# Context Wiki System — Claude Code Instructions

## What This Project Is
An LLM-maintained wiki API. Sources (PDFs, URLs, text) are ingested into
structured Markdown wiki pages via Celery workers. Pages are stored in git
and PostgreSQL. Claude (claude-opus-4-6) does the actual writing.

## Stack
- FastAPI + SQLAlchemy 2.0 async (Python 3.12)
- PostgreSQL 16 + pgvector (HNSW indexes, 1024-dim Voyage embeddings)
- Celery 5 with Redis broker — queues: ingest, lint, embedding, graph
- Anthropic API (claude-opus-4-6 for ingest/lint, haiku-4-5 for gate)
- Voyage AI (voyage-3-large) for embeddings — separate key from Anthropic
- Git (gitpython) — one repo per workspace under ./wiki_repos/

## Development Commands
- `make up` — start full stack (PostgreSQL, Redis, API, workers, beat, flower)
- `make down` — stop everything
- `make migrate` — run alembic upgrade head
- `make test` — pytest with coverage
- `make lint` — ruff + mypy
- `make dev` — uvicorn with hot-reload (no workers)

## Key Architecture Rules
- Workers use `asyncio.run()` NOT `asyncio.get_event_loop()` — Celery tasks
  run in threads, not async context
- All prompt templates use `${var}` placeholders replaced via `.replace()`,
  NOT Python `.format()` — source content contains literal `{}` characters
- `original_embedding` on wiki_pages is set at creation and NEVER updated —
  it is the absolute drift anchor
- `get_redis_pool()` returns synchronously (lru_cache) — never `await` it
- Voyage AI and Anthropic are separate services with separate API keys

## Testing
- Unit tests: `tests/unit/` — no DB, no external services
- Integration tests: `tests/integration/` — requires running PostgreSQL
- Run specific test: `pytest tests/unit/test_drift.py -v`
- Coverage report: `pytest --cov=app --cov-report=html`

## Migrations
- After changing models in `app/models/`, always create a migration:
  `alembic revision --autogenerate -m "description"`
- Never edit existing migration files — always create new ones

## Code Conventions
- Async everywhere in app code; sync only at Celery task boundary
- All DB work inside `async with AsyncSessionLocal() as db:`
- Imports inside async functions (lazy loading) to avoid circular imports
  in worker files
- Structured logging: `logger.info("event_name", key=value)` — never
  f-string log messages
```

Claude Code reads this on every session start, so it always has the right mental model before touching any file.

### 20.2 — Path-Scoped Rules

For more granular guidance, add rule files that apply only to specific directories:

```
.claude/
├── CLAUDE.md               ← always loaded
└── rules/
    ├── workers.md          ← loaded when editing app/workers/**
    ├── migrations.md       ← loaded when editing alembic/**
    └── tests.md            ← loaded when editing tests/**
```

`.claude/rules/workers.md`:
```markdown
---
globs: app/workers/**/*.py
---
# Worker Rules

- Every Celery task function must be sync (def, not async def).
  Use the `_run(coro)` helper which calls `asyncio.run()`.
- All imports from app.* must be INSIDE the async helper function,
  not at module level, to prevent circular import issues at worker startup.
- Never use `asyncio.get_event_loop()` — always `asyncio.run()` in tasks
  and `asyncio.get_running_loop()` inside async functions.
- Retry counts: ingest max_retries=3, lint max_retries=2.
- Always call `_mark_job_failed` / `_mark_run_failed` before re-raising.
```

`.claude/rules/migrations.md`:
```markdown
---
globs: alembic/versions/**/*.py
---
# Migration Rules

- Never edit existing migration files — create new revisions instead.
- Always include `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` in
  the first migration of any new database.
- HNSW indexes must specify: postgresql_using="hnsw",
  postgresql_with={"m": 16, "ef_construction": 64},
  postgresql_ops={"column_name": "vector_cosine_ops"}
- Test downgrade() actually reverses the upgrade() — they must be symmetric.
```

`.claude/rules/tests.md`:
```markdown
---
globs: tests/**/*.py
---
# Test Rules

- Unit tests (tests/unit/) must not import AsyncSessionLocal, get_redis_pool,
  or any external service. Mock at the function boundary.
- Integration tests (tests/integration/) run against a real PostgreSQL
  instance — use the fixtures in conftest.py.
- Never mock _cosine_distance — test it with real vectors.
- All new workers must have at least one unit test covering the async helper.
```

### 20.3 — Custom Skills (Slash Commands)

Skills let you invoke common wiki workflows with a single `/command`. Create them in `.claude/skills/`.

#### `/ingest` — Upload and process a file

Create `.claude/skills/ingest/SKILL.md`:

```markdown
Ingest a source file into the wiki system.

Usage: /ingest <file_path> [workspace_id]

Steps:
1. Read the file at $0 to understand its content type (pdf/text/url).
2. Upload it to the sources API:
   POST /api/v1/workspaces/${workspace_id}/sources
   Use multipart form with file + title (derive title from filename).
3. Trigger ingest with the returned source ID:
   POST /api/v1/workspaces/${workspace_id}/ingest
   Body: {"source_ids": ["<id>"]}
4. Poll GET /api/v1/workspaces/${workspace_id}/ingest/<job_id> every 5s
   until status is "done" or "failed".
5. If done: report pages_touched, llm_tokens_used, llm_cost_usd.
6. If failed: report error_message and suggest checking worker logs.

Use TOKEN from environment or ask the user for their Bearer token.
Use WS_ID from environment or the second argument $1.
```

#### `/query-wiki` — Ask the wiki a question

Create `.claude/skills/query-wiki/SKILL.md`:

```markdown
Query the wiki and return the answer with citations.

Usage: /query-wiki <question> [--stream]

Steps:
1. Construct the query request:
   POST /api/v1/workspaces/$WS_ID/query
   Body: {"question": "$ARGUMENTS", "top_k": 20}
   If --stream flag present, add header: Accept: text/event-stream
2. Display the answer with citations formatted as:
   > [Page Title](page_path) and [Source: title]
3. Show token usage and cost at the bottom.
4. If answer mentions uncertainty or "not found", suggest running /lint
   to check for gaps or /ingest to add more sources.
```

#### `/run-lint` — Trigger a lint pass

Create `.claude/skills/run-lint/SKILL.md`:

```markdown
Run a lint pass and summarize findings.

Usage: /run-lint [--scope full|incremental] [--fix]

Steps:
1. POST /api/v1/workspaces/$WS_ID/lint
   Body: {"scope": "$0" or "full"}
2. Poll until status = "done".
3. GET /api/v1/workspaces/$WS_ID/lint/<run_id>/findings
4. Group findings by type and severity:
   - errors first (semantic_drift error, contradiction error)
   - then warnings (orphan, semantic_drift warning)
5. For each contradiction finding, display:
   - page_a, page_b paths
   - page_a_excerpt vs page_b_excerpt
   - Ask: "Would you like me to open both pages and propose a resolution?"
6. For each drift error, display:
   - page path, absolute_drift value, version_count
   - Ask: "Would you like to see the page history to identify when it drifted?"
```

#### `/wiki-status` — Workspace health summary

Create `.claude/skills/wiki-status/SKILL.md`:

```markdown
Show a health summary for the current workspace.

Steps:
1. GET /api/v1/workspaces/$WS_ID/wiki/pages?limit=200
   Count by page_type, sum word_count.
2. GET /api/v1/workspaces/$WS_ID/graph/communities
   Count communities and total nodes.
3. GET /api/v1/admin/cost-report?workspace_id=$WS_ID
   Show total tokens and cost.
4. GET /api/v1/workspaces/$WS_ID/ingest (last 5 jobs)
   Show recent ingest activity.
5. Format as a summary table:
   | Metric            | Value  |
   |-------------------|--------|
   | Wiki pages        | N      |
   | Total word count  | N      |
   | KG communities    | N      |
   | Total LLM cost    | $N.NN  |
   | Last ingest       | status |
```

### 20.4 — Hooks (Automated Quality Gates)

Hooks execute shell commands at Claude Code lifecycle events, letting you enforce quality checks automatically.

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": {
          "tool_name": "Edit",
          "file_pattern": "app/**/*.py"
        },
        "hooks": [
          {
            "type": "command",
            "command": "cd /Users/arleyfernandez/projects/context && ruff check --select E,F --fix $CLAUDE_TOOL_INPUT_FILE_PATH 2>&1 | head -20"
          }
        ]
      },
      {
        "matcher": {
          "tool_name": "Edit",
          "file_pattern": "alembic/versions/**/*.py"
        },
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Migration edited — remember to test downgrade(): alembic downgrade -1 && alembic upgrade head'"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": {
          "tool_name": "Bash",
          "command_pattern": ".*alembic downgrade.*"
        },
        "hooks": [
          {
            "type": "command",
            "command": "echo 'WARNING: alembic downgrade will modify the database. Confirm this is intentional.' && exit 1"
          }
        ]
      }
    ]
  }
}
```

**What these hooks do:**

| Hook | Trigger | Action |
|------|---------|--------|
| `PostToolUse` on `Edit` (`.py` files) | After any Python edit | Auto-fix ruff linting errors (E, F rules) |
| `PostToolUse` on `Edit` (migrations) | After editing any migration | Remind to test the downgrade path |
| `PreToolUse` on `Bash` (downgrade) | Before running alembic downgrade | Block + warn, requires explicit confirmation |

### 20.5 — MCP Server: Purpose-Built Python Tools

The project ships a purpose-built FastMCP server (`app/mcp/server.py`) with 13 intent-focused tools. This replaces the old OpenAPI-mirror approach — instead of 70+ raw REST endpoints, Claude gets a small set of composite, well-described tools that mirror how a developer actually uses the wiki.

#### How it works

```
Claude Code (stdio) ──► .claude/mcp-context-wiki.sh
                              │
                              ├─ waits for auth proxy health at :8001
                              └─ docker compose exec -T api python -m app.mcp.server
                                      │
                                      └─ FastMCP over stdio (13 tools)
                                         direct in-process DB + git access
```

No token management needed — the server runs inside the Docker container with the full app environment. The auth proxy health check ensures the stack is up before Claude tries to connect.

#### `.claude/mcp.json` (committed, no secrets)

```json
{
  "mcpServers": {
    "context-wiki": {
      "type": "stdio",
      "command": "/path/to/repo/.claude/mcp-context-wiki.sh",
      "args": [],
      "env": {},
      "description": "Context Wiki API — ingest, query, lint, wiki pages, knowledge graph"
    }
  }
}
```

Replace `/path/to/repo` with the absolute path to your clone. The path is already set correctly in the committed `.mcp.json` at the repo root.

#### Prerequisites

```bash
# The Docker stack must be running before Claude Code connects
make up

# Verify the auth proxy is healthy (the wrapper script checks this too)
curl http://localhost:8001/health
```

#### The 13 tools

| Tool | What it does |
|------|-------------|
| `list_workspaces` | Returns all workspaces with member counts |
| `get_workspace_status` | Aggregates quality + jobs + components into one status payload |
| `ingest_url` | Creates a source record and triggers ingest in one call |
| `ingest_file` | Uploads base64 file content and triggers ingest |
| `get_ingest_status` | Polls a running ingest job |
| `query_wiki` | Hybrid retrieval (vector + KG) + LLM answer with citations |
| `list_wiki_pages` | Lists pages with optional path-prefix filter |
| `get_wiki_page` | Full Markdown content of a single page |
| `create_wiki_page` | Creates and commits a new wiki page |
| `update_wiki_page` | Updates and commits an existing page |
| `list_sources` | Lists all ingested sources in a workspace |
| `trigger_lint` | Starts a lint run for drift/contradiction checks |
| `search_tools` | Returns full schemas for tools matching a keyword |

#### HTTP transport (remote agents)

The same 13 tools are also available over Streamable HTTP at `POST /mcp`. Useful for cloud-hosted agents that cannot run a local subprocess:

```bash
# With auth — returns 13-tool manifest
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Without auth — returns 401
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

### 20.6 — Typical Claude Code Session: Developer Workflow

Here's what a productive Claude Code session looks like for a developer on this project:

```
# Start Claude Code in the project directory
cd /path/to/context
claude

# Claude reads CLAUDE.md automatically. No need to re-explain the project.

Developer: "The hallucination gate is blocking too many valid edits.
            Can you look at what threshold it's using and make it
            configurable per workspace?"

Claude: [reads app/workers/ingest_worker.py, app/config.py,
         app/models/workspace.py]
        "I see the gate uses a binary pass/fail/needs_review verdict.
         I'll add a per-workspace `hallucination_gate_confidence_threshold`
         setting (default 0.7) and pass it to the verify prompt..."
        [edits config.py, ingest_worker.py, workspace model]
        [ruff auto-fix hook fires, cleans up trailing whitespace]
        [creates alembic migration for the new column]

Developer: /run-lint

Claude: [calls POST /lint, polls, fetches findings]
        "Lint complete: 2 warnings found.
         1 orphan page: pages/summaries/old-notes.md — no inbound links
         1 drift warning: pages/concepts/authentication.md (drift: 0.41)
         Would you like me to fix the orphan by adding a link from index.md?"
```

### 20.7 — Team Setup for Claude Code

Each developer should have:

```
project root/
├── CLAUDE.md              ← committed (shared project instructions)
├── .claude/
│   ├── CLAUDE.md          ← committed (structured rules)
│   ├── rules/
│   │   ├── workers.md     ← committed
│   │   ├── migrations.md  ← committed
│   │   └── tests.md       ← committed
│   ├── skills/
│   │   ├── ingest/        ← committed (team skills)
│   │   ├── query-wiki/    ← committed
│   │   ├── run-lint/      ← committed
│   │   └── wiki-status/   ← committed
│   ├── mcp.json           ← committed (MCP config without secrets)
│   ├── settings.json      ← committed (shared hooks)
│   └── settings.local.json ← gitignored (personal overrides)
└── .gitignore
    └── .claude/settings.local.json
```

`settings.local.json` can hold personal preferences like auto-approve rules for tools you trust:

```json
{
  "autoApprove": {
    "tools": ["Read", "Grep", "Glob"],
    "bash_patterns": ["pytest tests/unit/**", "ruff check --fix app/"]
  }
}
```

---

## 21. Kiro Integration

[Kiro](https://kiro.dev) is AWS's spec-driven AI IDE (built on Code OSS). It organizes AI assistance around *specifications* — you write what a feature should do, Kiro generates and maintains code that satisfies the spec. For this project it works best for: building new API endpoints, maintaining workers, and automating quality gates via hooks.

### How It Fits

```
Developer ──► Kiro IDE ──► Writes spec ──► Kiro generates code
               │
               ├── reads .kiro/steering/   (project guidelines)
               ├── fires agent hooks       (auto-ingest on doc save)
               └── calls MCP servers       (direct API + PostgreSQL access)
```

### 21.1 — Steering Files (Persistent Project Context)

Steering files in `.kiro/steering/` are automatically loaded by Kiro on every interaction. They give the AI durable knowledge about your project — equivalent to `CLAUDE.md` in Claude Code.

Create these files and commit them.

#### `.kiro/steering/project-overview.md`

```markdown
# Context Wiki System — Project Overview

## What This Is
An enterprise LLM-maintained wiki API. Sources (PDFs, URLs, text files) are
ingested by Celery workers that call the Anthropic API (claude-opus-4-6) to
write and update Markdown wiki pages. Pages live in per-workspace git repos
backed by PostgreSQL.

## Core Operations
- **Ingest**: source → LLM → wiki page edits + KG entities
- **Query**: question → hybrid retrieval → LLM → answer with citations
- **Lint**: wiki → structural checks + drift detection + contradiction scan

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg
- PostgreSQL 16 + pgvector (HNSW, cosine distance)
- Celery 5 + Redis (queues: ingest, lint, embedding, graph)
- Anthropic API (claude-opus-4-6) + Voyage AI (voyage-3-large, 1024-dim)
- gitpython (one git repo per workspace)
- NetworkX + Louvain (knowledge graph community detection)

## Entry Points
- API: app/main.py → app/api/router.py → app/api/v1/*.py
- Workers: app/workers/{ingest,lint,embedding,graph}_worker.py
- Models: app/models/*.py
- Config: app/config.py (Pydantic Settings, reads from .env)

## Development
- `make up` starts everything via docker-compose
- `make migrate` runs alembic upgrade head
- `make test` runs pytest with coverage
- API docs at http://localhost:8000/docs after `make up`
```

#### `.kiro/steering/coding-rules.md`

```markdown
# Coding Rules

## Async / Celery Pattern (CRITICAL)
Celery task functions are SYNC (def, not async def). They call `asyncio.run()`
via the `_run()` helper. Never use `asyncio.get_event_loop()` — it is
deprecated in Python 3.10+ and fails in Celery's thread context.

Correct pattern:
```python
@celery_app.task(name="...", bind=True)
def my_task(self, id: str):
    _run(_my_task_async(uuid.UUID(id)))

async def _my_task_async(id: uuid.UUID):
    from app.core.db import AsyncSessionLocal   # import INSIDE async fn
    async with AsyncSessionLocal() as db:
        ...
```

## Prompt Templates (CRITICAL)
ALL prompt templates use `${var}` placeholders replaced with `.replace()`.
Never use Python `.format()` or f-strings with user content — source
documents contain literal `{` and `}` characters that cause KeyError.

Correct:
```python
user_text = TEMPLATE.replace("${question}", question).replace("${context}", ctx)
```
Wrong:
```python
user_text = TEMPLATE.format(question=question)   # KeyError if question has {}
```

## Imports in Workers
All `app.*` imports must be INSIDE the async helper function body.
This prevents circular imports at Celery worker startup time.

## Redis
`get_redis_pool()` is decorated with `@lru_cache` and returns synchronously.
Never `await get_redis_pool()`.

## Drift Measurement
`original_embedding` on WikiPage is set ONCE at page creation and never
updated. Drift = cosine_distance(original_embedding, current_embedding).
Never sum incremental drifts — always compare against the original.

## API Keys
Voyage AI (embeddings) and Anthropic (LLM) are separate services with
separate keys: VOYAGE_API_KEY and ANTHROPIC_API_KEY. Never mix them.
```

#### `.kiro/steering/api-conventions.md`

```markdown
# API Conventions

## Authentication
All endpoints (except /auth/*) require:
  Authorization: Bearer <access_token>

Roles: reader < editor < admin (IntEnum: 1, 2, 3)
Platform admins (is_platform_admin=True) bypass workspace checks.

## URL Structure
All routes: /api/v1/{resource}
Workspace-scoped: /api/v1/workspaces/{workspace_id}/{resource}

## Response Codes
- 200: success (GET, PUT, PATCH)
- 201: created (POST)
- 202: accepted (async jobs — ingest, lint)
- 204: no content (DELETE)
- 409: conflict (duplicate content_hash on source upload)
- 429: rate limit exceeded

## Error Format
{"detail": "human readable message"}

## Pagination
Endpoints with lists support: ?limit=N&offset=N (max limit=200)
Always order by updated_at DESC.

## Async Jobs (Ingest / Lint)
POST returns 202 with {id, status: "queued"}.
Client polls GET /{id} until status is "done" or "failed".
Workers use Celery; results stored in PostgreSQL.

## Rate Limits (per user per endpoint, req/min)
ingest: 10 | query: 60 | lint: 5 | default: 120
```

#### `.kiro/steering/testing-rules.md`

```markdown
# Testing Rules

## Unit Tests (tests/unit/)
- No database, no external services, no Redis
- Import only pure functions: _cosine_distance, rrf_fuse, parse_lint_response
- Mock at the service boundary when needed (not below it)
- Test edge cases: None inputs, empty lists, zero vectors

## Integration Tests (tests/integration/)
- Require running PostgreSQL (use docker-compose for CI)
- Use conftest.py fixtures for DB session and test workspace
- Clean up after each test — truncate tables, not drop

## Coverage
Target: >80% for app/services/, app/retrieval/, app/llm/output_parsers/
Workers are tested via integration tests, not mocked unit tests.

## New Features
Every new worker task → at least one unit test for the async helper.
Every new API endpoint → at least one integration test.
```

### 21.2 — Agent Hooks (Automated Workflows)

Kiro hooks fire on IDE events (file save, file create, etc.) and run either an AI agent prompt or a shell command. Store them in `.kiro/hooks/` so the whole team shares them.

#### Hook 1: Auto-ingest on Document Save

Fires when a new document is dropped into the `data/sources/` directory.

Create `.kiro/hooks/auto-ingest-on-save.json`:

```json
{
  "name": "Auto-ingest New Source Document",
  "description": "When a file is saved to data/sources/, upload it to the wiki and trigger ingest",
  "triggers": [
    {
      "type": "fileCreate",
      "filePattern": "data/sources/**/*.{pdf,txt,md}"
    }
  ],
  "action": {
    "type": "agent",
    "prompt": "A new source file was just saved at: {{file.path}}\n\nDo the following:\n1. Upload the file to the Context API using multipart POST /api/v1/workspaces/$WS_ID/sources with title derived from the filename.\n2. Trigger ingest with the returned source ID: POST /api/v1/workspaces/$WS_ID/ingest {\"source_ids\": [\"<id>\"]}\n3. Report the job ID and tell the user to poll GET /api/v1/workspaces/$WS_ID/ingest/<job_id> for status.\nUse CONTEXT_API_TOKEN from environment for auth."
  }
}
```

#### Hook 2: Lint After Bulk Wiki Edits

Fires when 3 or more wiki page files are modified in the same session.

Create `.kiro/hooks/lint-after-wiki-edits.json`:

```json
{
  "name": "Suggest Lint After Wiki Changes",
  "description": "Remind to run lint when multiple wiki pages were edited",
  "triggers": [
    {
      "type": "userTriggered",
      "label": "Run lint after edits"
    }
  ],
  "action": {
    "type": "agent",
    "prompt": "Multiple wiki pages have been edited in this session. Run a lint pass to check for consistency:\n\nPOST /api/v1/workspaces/$WS_ID/lint {\"scope\": \"full\"}\n\nPoll until done, then show a summary of findings grouped by severity. For any contradiction findings, show the page paths and excerpts side by side."
  }
}
```

#### Hook 3: Security Scan Before Commit

Fires before any git commit — scans for leaked API keys.

Create `.kiro/hooks/security-scan.json`:

```json
{
  "name": "Pre-commit Security Scan",
  "description": "Scan staged files for API keys, tokens, and credentials before committing",
  "triggers": [
    {
      "type": "userTriggered",
      "label": "Security scan before commit"
    }
  ],
  "action": {
    "type": "command",
    "command": "git diff --cached | grep -E '(sk-ant-|pa-|AKIA|aws_secret|password\\s*=\\s*[\"\\x27][^\"\\']{8,}|Bearer\\s+[A-Za-z0-9]{20,})' && echo 'BLOCKED: Potential credential found in staged changes' && exit 1 || echo 'Security scan passed'"
  }
}
```

#### Hook 4: Auto-generate Tests for New Workers

Fires when a new `*_worker.py` file is created.

Create `.kiro/hooks/generate-worker-tests.json`:

```json
{
  "name": "Generate Tests for New Worker",
  "description": "When a new worker file is created, generate a unit test skeleton",
  "triggers": [
    {
      "type": "fileCreate",
      "filePattern": "app/workers/*_worker.py"
    }
  ],
  "action": {
    "type": "agent",
    "prompt": "A new worker file was created at {{file.path}}.\n\nRead the file and identify:\n1. The Celery task function name and its arguments\n2. The async helper function and what it does\n3. Any pure utility functions (_cosine_distance style)\n\nCreate a test file at tests/unit/test_{{file.basename}}.py that:\n- Tests each pure utility function with normal inputs, edge cases (None, empty), and boundary values\n- Adds a TODO comment for integration test of the async helper\n- Follows the pattern in tests/unit/test_drift.py\n\nDo NOT mock asyncio or the database — only test pure functions in unit tests."
  }
}
```

#### Hook 5: Update Schema Version on Schema Edit

Fires when `app/models/schema_config.py` is edited.

Create `.kiro/hooks/schema-version-reminder.json`:

```json
{
  "name": "Schema Version Reminder",
  "description": "Remind to create an Alembic migration after model changes",
  "triggers": [
    {
      "type": "fileEdit",
      "filePattern": "app/models/**/*.py"
    }
  ],
  "action": {
    "type": "command",
    "command": "echo '⚠ Model file edited. If you added/changed columns or tables, run: make revision msg=\"describe_your_change\"'"
  }
}
```

### 21.3 — MCP Server Configuration

Kiro supports MCP servers natively via HTTP. The project provides two connection options — use the auth proxy for automatic token management (recommended for local development), or connect directly to the Streamable HTTP endpoint with your own bearer token.

#### `.kiro/settings/mcp.json` (committed)

```json
{
  "mcpServers": {
    "context-wiki": {
      "type": "http",
      "url": "http://localhost:8001/mcp",
      "description": "Context Wiki — 13 purpose-built tools via auth proxy (token managed automatically)"
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "POSTGRES_CONNECTION_STRING": "${DATABASE_URL}"
      },
      "description": "Direct PostgreSQL access for schema inspection and debugging"
    }
  }
}
```

The `context-wiki` entry routes through the auth proxy at `:8001`. The proxy automatically fetches and refreshes a bearer token from `/api/v1/status/bootstrap` — no credentials needed in the MCP config. Requests are forwarded to `http://localhost:8000/mcp` (the Streamable HTTP MCP transport).

#### Direct connection (no proxy)

If the auth proxy is not running, connect directly and supply a token:

```json
{
  "mcpServers": {
    "context-wiki": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "description": "Context Wiki — direct connection, requires bearer token",
      "headers": {
        "Authorization": "Bearer ${CONTEXT_API_TOKEN}"
      }
    }
  }
}
```

```bash
export CONTEXT_API_TOKEN="eyJ..."   # add to ~/.zshrc or Kiro env settings
```

#### Prerequisites

```bash
# Full stack must be running — this starts api, workers, auth proxy, and portal
make up

# Verify proxy is healthy
curl http://localhost:8001/health

# Verify MCP endpoint responds (replace token)
curl -X POST http://localhost:8000/mcp \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

#### Available tools

Both Kiro and Claude Code get the same 13 tools — see the tool table in section 20.5.

With the `postgres` MCP server, Kiro can also directly inspect the database:
- "How many wiki pages does workspace X have?"
- "Show me the most recent lint findings"
- "What are the top 10 nodes in the knowledge graph?"

```bash
# postgres MCP requires DATABASE_URL pointing to the host-exposed port
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/context
```

### 21.4 — Spec-Driven Development for New Features

Kiro's core workflow: write a spec first, let Kiro generate and implement it. Here's how to add a new feature to this project using specs.

**Example: Adding a "page summary" endpoint**

In Kiro, open the spec panel and create a new spec:

```
Feature: Wiki Page AI Summary Endpoint

## Overview
Add a GET /wiki/pages/{page_path}/summary endpoint that returns a 
concise AI-generated summary of a wiki page using Claude.

## User Stories

Story 1: Get page summary
  WHEN a reader calls GET /wiki/pages/{path}/summary
  THEN the system returns a JSON object with:
    - summary (string, 2-3 sentences)
    - key_topics (list of 3-5 topic strings)
    - last_updated (ISO timestamp)
    - token_cost_usd (float, cost of generating the summary)

Story 2: Cached summaries
  WHEN the page has not changed since last summary generation
  THEN the system returns the cached summary without calling the LLM
  AND the response includes cache_hit: true

Story 3: Rate limiting
  WHEN a user calls this endpoint more than 20 times per minute
  THEN the system returns 429 Too Many Requests
```

Kiro reads the steering files (which describe the codebase conventions) and generates:
- The endpoint in `app/api/v1/wiki.py`
- A cache key in `app/llm/prompt_cache.py`
- Rate limit config in `app/config.py`
- A test skeleton in `tests/integration/test_page_summary.py`

All generated code follows the conventions in your steering files: async patterns, `${var}` templates, lazy imports in workers, etc.

### 21.5 — Kiro + Claude Code Together

These tools are complementary. A practical team workflow:

| Task | Best Tool | Why |
|------|-----------|-----|
| Adding a new API endpoint | **Kiro** | Spec-first; generates boilerplate, tests, and docs together |
| Debugging a production bug | **Claude Code** | Conversational; read logs, grep codebase, propose targeted fix |
| Ingesting a batch of documents | **Claude Code** `/ingest` skill | One-command workflow |
| Understanding an unfamiliar file | **Claude Code** | Can read, explain, and answer follow-up questions |
| Major refactor across many files | **Kiro** | Spec captures intent; hooks auto-test as it goes |
| Running lint + reviewing findings | **Claude Code** `/run-lint` skill | Interactive review and fix suggestions |
| Setting up a new workspace | **Either** | Both can drive the API setup sequence |

### 21.6 — Shared `.kiro/` Directory Structure

Commit the `.kiro/` directory so your whole team gets the same AI setup:

```
.kiro/
├── steering/
│   ├── project-overview.md      ← what the project is
│   ├── coding-rules.md          ← async, template, import rules
│   ├── api-conventions.md       ← endpoints, auth, status codes
│   └── testing-rules.md         ← unit vs integration, coverage
├── hooks/
│   ├── auto-ingest-on-save.json
│   ├── lint-after-wiki-edits.json
│   ├── security-scan.json
│   ├── generate-worker-tests.json
│   └── schema-version-reminder.json
└── settings/
    └── mcp.json                 ← MCP config (no secrets — uses ${ENV_VAR})
```

Add to `.gitignore`:
```
# Kiro — local-only overrides (contain secrets or personal settings)
.kiro/settings/mcp.local.json
.kiro/settings/*.local.json
```

### 21.7 — Onboarding a New Developer with Both Tools

After a new engineer clones the repo, they get full AI context automatically:

**For Claude Code:**
```bash
# Install Claude Code
brew install claude-code   # macOS
# or download from https://claude.ai/code

# Start in project directory — CLAUDE.md and all rules load automatically
cd context
claude

# First session: Claude already knows the full stack, conventions, and commands
# Type: "What should I know about this project?"
# Claude reads CLAUDE.md and gives a tailored onboarding answer
```

**For Kiro:**
```bash
# Download Kiro from https://kiro.dev
# Open the project directory in Kiro
# Steering files in .kiro/steering/ load automatically

# Hooks are already configured — no setup needed
# MCP servers connect once CONTEXT_API_TOKEN and DATABASE_URL are set in .env
```

**What they get out of the box:**
- Complete project context (no manual explanation needed)
- `/ingest`, `/query-wiki`, `/run-lint`, `/wiki-status` skills in Claude Code
- Auto-ingest hook, security scan, test generation in Kiro
- Direct API and database access via MCP
- Automated linting after Python edits (Claude Code hook)
- Migration reminders after model changes (Kiro hook)
