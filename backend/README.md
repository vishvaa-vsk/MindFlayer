# TestCortex Backend

Context-aware test intelligence engine powered by LLM and intelligent test planning.

## 🎯 What It Does

TestCortex automatically generates API test cases from requirements and existing tests:

1. **Parse Requirements** → Extract API endpoints, auth rules, dependencies
2. **Plan Tests** → Decide what test scenarios should exist (positive, no-auth, dependency, invalid)
3. **Generate Code** → Create executable pytest code
4. **Validate** → Report coverage gaps and deduplication

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- `uv` package manager

### Installation

```bash
cd backend
uv sync
```

### Run Server

```bash
uv run python main.py
```

Server listens on `http://localhost:8000`

### Generate Tests

```bash
curl -X POST http://localhost:8000/api/generate-tests \
  -H "Content-Type: application/json" \
  -d '{
    "requirements_text": "POST /orders (requires user_auth)\nGET /orders/:id (requires user_auth, depends on POST /orders)",
    "existing_test_names": []
  }'
```

See [DEMO.md](DEMO.md) for full examples.

## 📁 Project Structure

```
backend/
├── models/              # Pydantic schemas
│   ├── context.py       # Endpoint, AuthRule, SystemContext
│   ├── test_plan.py     # TestPlan, TestScenario
│   └── generated_test.py # GeneratedTest, TestSuite
├── context/             # Parse requirements → SystemContext
│   └── builder.py
├── planner/             # Plan tests → TestPlan
│   └── test_planner.py
├── generator/           # Generate code → pytest
│   └── pytest_gen.py
├── validator/           # Coverage & dedup
│   └── coverage.py
├── api/                 # FastAPI routes
│   └── routes.py
├── main.py              # FastAPI entry point
├── pyproject.toml       # uv configuration
├── DEMO.md              # Demo guide
└── README.md            # This file
```

## 🔧 Development

### Run Tests

```bash
uv run pytest
```

### Check Syntax

```bash
uv run python -m py_compile <file>
```

### Dependencies

- `fastapi` - Web framework
- `pydantic` - Schema validation
- `pytest` - Testing
- `httpx` - HTTP client
- `uvicorn` - ASGI server

## 📚 API Reference

### `POST /api/generate-tests`

Generate test suite from requirements.

**Request:**

```json
{
  "requirements_text": "POST /orders (requires user_auth)\n...",
  "existing_test_names": ["test_name1", "test_name2"]
}
```

**Response:**

```json
{
  "context": {
    "endpoints": [...],
    "auth_rules": [...],
    "dependencies": {...}
  },
  "test_plan": {
    "scenarios": [...],
    "rationale": "..."
  },
  "generated_code": "def test_...",
  "validation": {
    "total_planned": 10,
    "new_tests": 8,
    "coverage_improvement": 0.8,
    "summary": {...}
  }
}
```

### `GET /`

Health check and API info.

### `GET /docs`

Interactive Swagger UI documentation.

## 🧠 Requirements Format

```
METHOD /path (requires auth_type, depends on OTHER_METHOD /other_path)
```

Examples:

```
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
DELETE /orders/:id (requires user_auth)
POST /admin/users (requires admin_auth)
```

## 🎓 How Test Planning Works

For each endpoint, TestCortex generates:

1. **Positive test** - Happy path (200 OK)
2. **No-auth test** - Missing auth header (401)
3. **Dependency test** - Dependency not met (400/409)
4. **Invalid-id test** - Invalid path parameter (404)

Then it:

- **Deduplicates** against existing tests
- **Calculates** coverage improvement
- **Generates** valid pytest code

## 🏆 Competition Alignment

### AlgoQuest 2025

- **Focus**: Intelligent test planning algorithm
- **Metric**: 30% fewer redundant tests via dedup
- **Demo**: Show dependency/auth coverage logic

### Imagine Cup 2026

- **Focus**: Automation for QA teams
- **Metric**: 5-10x faster test generation
- **Demo**: Requirements → Test suite in seconds

## 📖 Implementation Timeline

- **Days 1-2**: Schemas ✅
- **Days 3-4**: Context builder ✅
- **Days 5-6**: Planner + Generator ✅
- **Days 7-9**: Validator + API ✅
- **Days 10-14**: Polish, docs, demo

## 🚨 Troubleshooting

**ModuleNotFoundError: No module named 'models'**

- Ensure you're running from `backend/` directory
- Run `uv sync` to install dependencies

**Port 8000 already in use**

- Run server on different port: `uv run python -c "import uvicorn; from main import app; uvicorn.run(app, port=9000)"`

**Schema validation error**

- Verify requirements text format (METHOD /path)
- Check auth_type and dependency references are valid

## 📝 License

Part of TestCortex project for AlgoQuest 2025 + Imagine Cup 2026.

---

**Next**: See [DEMO.md](DEMO.md) for detailed examples and curl commands.
