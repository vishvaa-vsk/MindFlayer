# MindFlayer

AI-powered test generation engine that converts API requirements into complete, executable pytest suites — with intelligent planning, coverage analysis, and real-time streaming.

---

## Quick Start

```bash
# Terminal 1 — Backend
cd backend
uv sync
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**

> Set your OpenRouter API key at **Settings** page or via `OPENROUTER_API_KEY` env var for LLM-powered generation. Without it, the template fallback still produces working tests.

---

## What It Does

```
API Requirements (structured or natural language)
    ↓
[1] Parse      → Extract endpoints, auth rules, dependencies
    ↓
[2] Plan       → Generate test scenarios (positive, auth, dependency, invalid input)
    ↓
[3] Generate   → Write executable pytest code (LLM-first, template fallback)
    ↓
[4] Validate   → Deduplicate, calculate coverage, report gaps
    ↓
Complete test suite + coverage report
```

### Input Formats

**Structured:**
```
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
DELETE /orders/:id (requires admin_auth)
```

**Natural Language:**
```
Users can register, login, and create orders.
Authenticated users can view order history and cancel pending orders.
Admin users can manage products and view all orders.
```

---

## Architecture

```
MindFlayer/
├── backend/                    # FastAPI + Python
│   ├── api/
│   │   └── routes.py           # REST + SSE streaming endpoints
│   ├── context/
│   │   ├── builder.py          # Requirements parser (regex + LLM detection)
│   │   └── llm_parser.py       # OpenRouter LLM client (parse + generate)
│   ├── planner/
│   │   └── test_planner.py     # Intelligent test scenario planning
│   ├── generator/
│   │   └── pytest_gen.py       # Code generation (LLM-first + template fallback)
│   ├── validator/
│   │   └── coverage.py         # Deduplication + coverage metrics
│   ├── models/
│   │   ├── context.py          # Endpoint, AuthRule, SystemContext
│   │   ├── test_plan.py        # TestScenario, TestPlan
│   │   └── generated_test.py   # GeneratedTest, TestSuite
│   ├── config.py               # Centralized settings (pydantic-settings)
│   ├── main.py                 # FastAPI app + lifespan + CORS
│   └── pyproject.toml          # Dependencies (uv)
│
└── frontend/                   # Next.js 16 + TypeScript
    ├── app/
    │   ├── page.tsx             # Landing page (hero, pipeline, features)
    │   ├── generate/page.tsx    # Main generation page (SSE + tabbed results)
    │   └── settings/page.tsx    # API key + model configuration
    ├── components/
    │   ├── Navbar.tsx           # Scroll-aware glassmorphism navbar
    │   ├── PipelineVisualizer.tsx  # 4-stage animated progress
    │   ├── TestOutput.tsx       # Code viewer with syntax highlighting
    │   └── CoverageReport.tsx   # Stats cards + progress bar + test lists
    └── lib/
        └── api.ts              # TypeScript API client + SSE parser
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Next.js 16 (App Router) | SSR, routing, TypeScript |
| Styling | Custom CSS | Dark theme, glassmorphism, animations |
| Backend | FastAPI | Async API, SSE streaming, auto-docs |
| Validation | Pydantic v2 | Schema enforcement |
| Config | pydantic-settings | Env vars, runtime updates |
| LLM | OpenRouter | Access to Gemini, DeepSeek, Llama, etc. |
| Package Mgr | uv (backend), npm (frontend) | Fast, reproducible |

---

## API Endpoints

### `POST /api/generate-tests`
Standard (non-streaming) test generation.

```bash
curl -X POST http://localhost:8000/api/generate-tests \
  -H "Content-Type: application/json" \
  -d '{
    "requirements_text": "POST /orders (requires user_auth)\nGET /orders/:id (requires user_auth, depends on POST /orders)",
    "existing_test_names": []
  }'
```

### `POST /api/generate-tests-stream`
Real-time SSE streaming with stage-by-stage progress updates.

### `GET /api/health`
Returns app status, configured models, feature list.

### `GET /api/settings` | `POST /api/settings`
Read and update runtime config (API key, models).

### `GET /docs`
Interactive Swagger UI.

---

## LLM Configuration

| Model | Role | Default |
|-------|------|---------|
| Parsing | Convert natural language → structured format | `google/gemini-2.0-flash-001` |
| Generation | Write intelligent pytest code | `deepseek/deepseek-chat-v3-0324:free` |

**Recommended free models on OpenRouter:**
- `deepseek/deepseek-chat-v3-0324:free`
- `google/gemini-2.0-flash-001`
- `meta-llama/llama-3.3-70b-instruct:free`
- `qwen/qwen-2.5-coder-32b-instruct:free`

Models can be changed at runtime via the Settings page or `POST /api/settings`.

---

## Test Planning Logic

For each endpoint, MindFlayer generates:

| Test Type | Description | Expected |
|-----------|-------------|----------|
| `positive` | Happy path | 200/201 |
| `no_auth` | Missing auth header | 401/403 |
| `dependency_failure` | Required dependency not met | 400/404/409 |
| `invalid_input` | Invalid path params (e.g. bad ID) | 404 |

Then it:
- **Deduplicates** against existing test names
- **Calculates** coverage improvement (0–100%)
- **Reports** gaps and redundancies

---

## Frontend Pages

| Page | Route | Description |
|------|-------|-------------|
| Landing | `/` | Hero, pipeline visualization, features grid, CTA |
| Generate | `/generate` | Requirements input, SSE pipeline, tabbed results (code/coverage/plan) |
| Settings | `/settings` | Backend status, API key, model selector |

### Design
- Premium dark theme with glassmorphism
- Smooth micro-animations and hover effects
- Python syntax highlighting with line numbers
- Responsive layout (desktop + mobile)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | No* | OpenRouter API key for LLM features |
| `PARSING_MODEL` | No | Override parsing model |
| `GENERATION_MODEL` | No | Override code generation model |
| `CORS_ORIGINS` | No | Allowed origins (default: localhost:3000,3001) |
| `PORT` | No | Backend port (default: 8000) |

*Without an API key, structured parsing and template-based code generation still work.

---

## Development

```bash
# Backend — run with hot reload
cd backend && uv run python -m uvicorn main:app --reload --port 8000

# Frontend — dev server
cd frontend && npm run dev

# TypeScript check
cd frontend && npx tsc --noEmit

# Backend dependency sync
cd backend && uv sync
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run from `backend/` directory, run `uv sync` |
| Port 8000 in use | Change with `--port 9000` |
| `OPENROUTER_API_KEY not set` | Set env var or configure in Settings page |
| Natural language not parsed | Requires API key — use structured format as fallback |
| Frontend can't reach backend | Ensure backend is running on port 8000, check CORS |
