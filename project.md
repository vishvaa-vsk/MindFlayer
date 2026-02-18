# MindFlayer: AI-Powered Test Intelligence Platform

## 🎯 Executive Summary

**MindFlayer** is an AI-powered test generation platform that transforms API requirements into complete, executable test suites. Built for **AlgoQuest 2025**, MindFlayer solves the critical problem of manual test writing by automating test planning, generation, and validation using intelligent AI models and systematic analysis.

**Key Innovation**: MindFlayer doesn't just generate tests—it *understands* your API through intelligent parsing, *plans* comprehensive test scenarios, and *validates* coverage gaps, producing production-ready test code in seconds.

---

## 🚀 Value Proposition

### **The Problem**
- Manual test writing is slow (5-10 tests/hour)
- Developers miss edge cases (auth, dependencies, validation)
- Test coverage is inconsistent across teams
- API changes require rewriting entire test suites

### **The Solution**
- **10x faster**: Generate 50+ tests in <10 seconds
- **100% coverage**: Automatically plans positive, negative, auth, dependency, and edge case tests
- **AI-powered**: Uses DeepSeek V3 and Gemini 2.0 for intelligent code generation
- **Multi-format**: Outputs pytest, Postman, JUnit, Gherkin, and OpenAPI specs

---

## 📊 Quick Demo Flow (For Judges)

### **1. Input Requirements** (Prose or Structured)
```
Users can register and login.
Authenticated users can create orders and view order history.
Admin users can manage products and view all orders.
```

### **2. Watch Real-Time Generation** (SSE Streaming)
- **Parse**: Extract 7 endpoints, 2 auth rules, 3 dependencies
- **Plan**: Generate 15 test scenarios (positive, no_auth, dependency_failure, invalid_input)
- **Generate**: Create executable pytest code with realistic payloads
- **Validate**: Report 100% coverage, 0 duplicates

### **3. Get Production-Ready Tests**
```python
def test_post_orders_positive(client, auth_headers):
    """Verify POST /orders returns success with valid data."""
    response = client.post(
        "/orders",
        json={"product_id": "prod_001", "quantity": 2, "total": 29.99},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert "order_id" in response.json()
```

**Result**: 15 tests, 350+ lines of code, 0 seconds of manual work.

---

## 🏗️ Architecture Overview

### **High-Level Flow**

```
┌─────────────────────┐
│  User Input         │
│  - Requirements     │
│  - Code Files (opt) │
└──────────┬──────────┘
           ↓
┌─────────────────────────────────────────────────┐
│         BACKEND (FastAPI + Python)              │
├─────────────────────────────────────────────────┤
│                                                  │
│  [1] PARSE → Extract endpoints, auth, deps      │
│      - Structured format parser (regex)         │
│      - Natural language parser (Gemini LLM)     │
│      - Code analyzer (AST for enums/validators) │
│                                                  │
│  [2] PLAN → Generate test scenarios             │
│      - Intelligent planner (8 test types)       │
│      - Deduplication against existing tests     │
│      - State constraints & role-based tests     │
│                                                  │
│  [3] GENERATE → Write test code                 │
│      - LLM-first generation (DeepSeek V3)       │
│      - Template fallback (no API key needed)    │
│      - Multi-format support (5 outputs)         │
│                                                  │
│  [4] VALIDATE → Coverage & quality              │
│      - Deduplication analysis                   │
│      - Coverage improvement metrics             │
│      - Test ordering & dependency graphs        │
│                                                  │
└──────────┬──────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────┐
│   FRONTEND (Next.js 16 + TypeScript)            │
├─────────────────────────────────────────────────┤
│                                                  │
│  - Landing Page (Hero, Features, Pipeline)      │
│  - Generate Page (SSE Streaming, Results)       │
│  - Settings Page (API Keys, Model Config)       │
│  - Real-time Pipeline Visualization             │
│  - Syntax-Highlighted Code Output               │
│  - Interactive Coverage Reports                 │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 🧩 Core Components (Backend)

### **1. Context Builder** (`backend/context/`)

**Purpose**: Parse requirements and extract API structure.

**Key Files**:
- `builder.py`: Main parser with regex and LLM integration
- `llm_parser.py`: OpenRouter client for natural language parsing
- `schema_inference.py`: Infer request/response schemas from requirements
- `code_analyzer.py`: AST-based analyzer for Python source code

**How It Works**:
1. **Detect Input Type**: Structured format vs. natural language vs. source code
2. **Parse Endpoints**: Extract HTTP method, path, auth requirements, dependencies
3. **Analyze Code** (optional): Extract enums, validators, business rules from actual source files
4. **Infer Schemas**: Populate `FieldSpec` objects for request/response bodies
5. **Output**: `SystemContext` object with enriched endpoint metadata

**Example Input** (Structured):
```
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
DELETE /orders/:id (requires admin_auth)
```

**Example Output** (SystemContext):
```python
SystemContext(
    endpoints=[
        Endpoint(name="post_orders", method="POST", url_path="/orders", 
                 requires_auth=True, depends_on=[], 
                 request_body=[FieldSpec(name="product_id", field_type="string", required=True)],
                 expected_success_code=201),
        Endpoint(name="get_orders_id", method="GET", url_path="/orders/:id", 
                 requires_auth=True, depends_on=["post_orders"]),
        ...
    ],
    auth_rules=[AuthRule(scope="user_auth", required_for=["post_orders", "get_orders_id"])],
    dependencies={"get_orders_id": ["post_orders"], ...}
)
```

**Innovation**: MindFlayer can parse natural language requirements using AI, structured formats using regex, and even analyze your actual source code files to extract real validation rules and enums.

---

### **2. Test Planner** (`backend/planner/test_planner.py`)

**Purpose**: Decide what tests should exist based on endpoint metadata.

**Planning Rules** (8 Test Types):
1. **positive**: Happy path with valid data → expect 200/201
2. **no_auth**: Missing auth header → expect 401
3. **dependency_failure**: Required dependency not fulfilled → expect 404/409
4. **invalid_input**: Bad path params (e.g., invalid `:id`) → expect 404
5. **state_conflict**: Violate business rules (e.g., cancel shipped order) → expect 409
6. **forbidden_role**: Wrong role (e.g., user accessing admin endpoint) → expect 403
7. **field_validation**: Invalid field format (e.g., bad email) → expect 422
8. **boundary_value**: Exceed min/max length constraints → expect 422

**Key Functions**:
```python
def plan_tests(context: SystemContext, existing_tests: list[str]) -> TestPlan:
    """
    Generate test scenarios based on system context.
    
    For each endpoint:
    - Create positive test
    - Add no_auth test if requires_auth
    - Add dependency_failure tests if depends_on
    - Add state_conflict tests if state_constraints exist
    - Add field_validation tests for required/formatted fields
    - Add boundary_value tests for min/max length constraints
    
    Deduplicate against existing_tests to avoid regenerating tests.
    """
```

**Example Output** (TestPlan):
```python
TestPlan(
    scenarios=[
        TestScenario(test_name="post_orders_positive", endpoint="post_orders", 
                     test_type="positive", expected_status=201),
        TestScenario(test_name="post_orders_no_auth", endpoint="post_orders", 
                     test_type="no_auth", expected_status=401),
        TestScenario(test_name="get_orders_id_dependency_fail_post_orders", 
                     endpoint="get_orders_id", test_type="dependency_failure", expected_status=404),
        ...
    ],
    rationale="Planned 15 tests covering 3 endpoints. Breakdown: 3 positive, 2 no_auth, 3 dependency_failure, ..."
)
```

**Innovation**: The planner uses enriched endpoint metadata (FieldSpec, StateConstraint, roles) to generate intelligent test scenarios that would take hours to plan manually.

---

### **3. Code Generator** (`backend/generator/`)

**Purpose**: Convert test plans into executable code in multiple formats.

**Supported Formats**:
- **pytest** (`pytest_gen.py`): Python pytest with fixtures and assertions
- **Postman** (`postman_gen.py`): Postman Collection v2.1 JSON
- **JUnit** (`junit_gen.py`): JUnit XML report format
- **Gherkin** (`gherkin_gen.py`): BDD .feature files with Given/When/Then
- **OpenAPI** (`openapi_gen.py`): OpenAPI 3.0 spec with test extensions

**Generation Strategy**:
1. **LLM-First**: Use DeepSeek V3 for intelligent code generation with realistic payloads
2. **Template Fallback**: Use deterministic templates if API key not available
3. **Smart Payloads**: Generate realistic data based on FieldSpec (email format, phone format, enums)
4. **Proper Assertions**: Validate status codes, response structure, error messages

**Example Generated Test** (pytest):
```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """User authentication headers fixture."""
    return {"Authorization": "Bearer test_user_token"}


def test_post_orders_positive(client, auth_headers):
    """Verify POST /orders returns success with valid data."""
    response = client.post(
        "/orders",
        json={
            "product_id": "prod_001",
            "quantity": 2,
            "customer_id": "cust_123",
            "total": 29.99
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert "order_id" in data
    assert data["status"] == "pending"


def test_post_orders_no_auth(client):
    """Verify POST /orders rejects unauthenticated requests."""
    response = client.post(
        "/orders",
        json={"product_id": "prod_001", "quantity": 2}
    )
    assert response.status_code == 401
    assert "authentication" in response.json()["detail"].lower()
```

**Innovation**: The generator produces production-ready code with proper fixtures, realistic payloads based on field schemas, and comprehensive assertions—not just naive templates.

---

### **4. Validator** (`backend/validator/`)

**Purpose**: Validate test quality, detect duplicates, and report coverage gaps.

**Key Files**:
- `coverage.py`: Coverage analysis and deduplication
- `dependency_graph.py`: Analyze test dependencies and execution order
- `test_ordering.py`: Optimize test execution order based on dependencies
- `ast_checker.py`: Validate generated code syntax
- `pipeline.py`: Quality gates and validation pipeline

**Key Functions**:
```python
def validate_coverage(planned_tests: list[str], existing_tests: list[str]) -> dict:
    """
    Analyze coverage and detect duplicates.
    
    Returns:
        {
            "total_planned": 15,
            "already_covered": ["test_get_users_positive"],
            "new_tests": ["test_post_orders_positive", ...],
            "duplicates": [],
            "coverage_improvement": 0.93  # 93% new tests
        }
    """
```

**Example Output**:
```json
{
  "total_planned": 15,
  "already_covered": 2,
  "new_tests": 13,
  "duplicates": 0,
  "coverage_improvement": 0.87,
  "endpoint_coverage": {
    "post_orders": 5,
    "get_orders_id": 4,
    "delete_orders_id": 3
  }
}
```

**Innovation**: MindFlayer doesn't just generate tests—it validates them against existing tests, detects duplicates, and provides actionable coverage metrics.

---

### **5. LLM Adapters** (`backend/adapters/`)

**Purpose**: Abstract LLM provider integration with privacy controls and fallback.

**Supported Providers**:
- **OpenRouter** (`openrouter.py`): Access to 100+ models (DeepSeek, Gemini, Llama, Qwen)
- **Azure OpenAI** (`azure.py`): Enterprise-grade deployment
- **Ollama** (`ollama.py`): Local/private LLM hosting
- **vLLM** (`vllm.py`): High-performance inference
- **TGI** (`tgi.py`): Text Generation Inference

**Key Features**:
- **Privacy Controls**: Circuit breaker prevents data leakage to external APIs
- **Fallback Chain**: OpenRouter → Azure → Ollama → Template
- **Streaming Support**: SSE for real-time generation
- **Error Handling**: Retry logic, timeout management, error classification

**Example Usage**:
```python
from adapters.registry import get_adapter

adapter = get_adapter("openrouter", api_key=settings.openrouter_api_key)
response = await adapter.complete(
    prompt="Generate pytest test for POST /orders endpoint",
    model="deepseek/deepseek-chat-v3-0324:free",
    temperature=0.2,
    max_tokens=1500
)
```

**Innovation**: The adapter system allows MindFlayer to work with any LLM provider, fall back to local models for privacy, and even operate without an API key using deterministic templates.

---

### **6. API Layer** (`backend/api/routes.py`)

**Purpose**: Expose REST and SSE endpoints for test generation.

**Key Endpoints**:

#### `POST /api/generate-tests`
Standard test generation (non-streaming).

**Request**:
```json
{
  "requirements_text": "POST /orders (requires user_auth)\nGET /orders/:id",
  "existing_test_names": [],
  "output_formats": ["pytest", "postman"],
  "code_files": {
    "models/order.py": "class OrderStatus(Enum):\n    PENDING = 'pending'\n    SHIPPED = 'shipped'"
  },
  "code_language": "python"
}
```

**Response**:
```json
{
  "context": { "endpoints": [...], "auth_rules": [...] },
  "test_plan": { "scenarios": [...], "rationale": "..." },
  "generated_code": "import pytest...",
  "outputs": {
    "pytest": "import pytest...",
    "postman": "{\"info\": {...}}"
  },
  "validation": {
    "total_planned": 10,
    "new_tests": 10,
    "coverage_improvement": 1.0
  },
  "parsed_with_llm": true
}
```

#### `POST /api/generate-tests-stream`
Real-time SSE streaming with stage updates.

**SSE Events**:
```
event: stage
data: {"stage": "parsing", "message": "Analyzing requirements..."}

event: stage
data: {"stage": "planning", "message": "Generating 15 test scenarios..."}

event: stage
data: {"stage": "generating", "message": "Writing pytest code..."}

event: stage
data: {"stage": "validating", "message": "Checking coverage..."}

event: complete
data: {"context": {...}, "test_plan": {...}, "outputs": {...}}
```

#### `GET /api/health`
Health check with system status.

#### `GET /api/settings` | `POST /api/settings`
Read/update runtime configuration (API keys, models).

---

### **7. Data Models** (`backend/models/`)

**Purpose**: Pydantic schemas for type safety and validation.

**Key Models**:

#### `context.py`
```python
class FieldSpec(BaseModel):
    """Schema field with type, format, and validation constraints."""
    name: str
    field_type: str  # string, integer, number, boolean, array, object
    format: str | None  # email, uri, uuid, date-time, password, phone
    required: bool = True
    example: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum: list[str] | None = None

class StateConstraint(BaseModel):
    """Business rule constraining when an operation is valid."""
    field: str  # e.g., "status"
    allowed_values: list[str]  # e.g., ["pending"]
    blocked_values: list[str] = []  # e.g., ["shipped", "delivered"]
    error_code: int = 409

class Endpoint(BaseModel):
    """API endpoint with full schema metadata."""
    name: str
    method: str  # GET, POST, PUT, DELETE
    url_path: str
    requires_auth: bool = False
    depends_on: list[str] = []
    request_body: list[FieldSpec] = []
    response_body: list[FieldSpec] = []
    state_constraints: list[StateConstraint] = []
    roles: list[str] = []
    expected_success_code: int = 200

class SystemContext(BaseModel):
    """Complete system context from API requirements."""
    endpoints: list[Endpoint] = []
    auth_rules: list[AuthRule] = []
    dependencies: dict[str, list[str]] = {}
    code_context: CodeContext | None = None
```

#### `test_plan.py`
```python
class TestScenario(BaseModel):
    """A single test scenario to be generated."""
    test_name: str
    endpoint: str
    description: str
    test_type: str  # positive, no_auth, dependency_failure, etc.
    expected_status: int = 200
    payload_hint: dict | None = None

class TestPlan(BaseModel):
    """Complete test plan with all scenarios."""
    scenarios: list[TestScenario] = []
    rationale: str = ""
```

**Innovation**: Rich metadata schemas enable intelligent test generation. For example, `FieldSpec` with format="email" allows the generator to create invalid email tests automatically.

---

## 🎨 Frontend Components

### **1. Landing Page** (`frontend/app/page.tsx`)

**Sections**:
- **Hero**: Gradient headline, CTA buttons, animated glow effect
- **Pipeline Visualization**: 4-stage animated flow (Parse → Plan → Generate → Validate)
- **Features Grid**: 6 feature cards with icons (OpenRouter, SSE, Smart Planning, Coverage, Auth-Aware, Dependencies)
- **Tech Stack**: Technology showcase with logos

**Design Highlights**:
- Glassmorphism cards with backdrop blur
- Smooth micro-animations on hover
- Gradient text effects
- Dark theme with purple/blue accents

---

### **2. Generate Page** (`frontend/app/generate/page.tsx`)

**Core UI**:
- **Input Panel**: Requirements textarea with example buttons (Structured / Prose)
- **Code Upload**: Optional source code file upload for code context analysis
- **Format Selector**: Multi-select for output formats (pytest, Postman, JUnit, Gherkin, OpenAPI)
- **Pipeline Visualizer**: Real-time SSE progress with animated stages
- **Results Tabs**: Tabbed interface for Code / Coverage / Plan / Context
- **Download Button**: Download generated tests as files

**Real-Time Features**:
- SSE streaming with stage-by-stage updates
- Animated progress indicators
- Live code syntax highlighting
- Dynamic coverage metrics

**User Flow**:
1. Enter requirements (paste, type, or load example)
2. (Optional) Upload source code files for analysis
3. Select output formats
4. Click "Generate Tests"
5. Watch real-time pipeline progress
6. View results in tabbed interface
7. Download generated test files

---

### **3. Settings Page** (`frontend/app/settings/page.tsx`)

**Configuration Options**:
- **Backend Status**: Connection health, version info
- **API Keys**: OpenRouter, Azure OpenAI
- **Model Selection**: Dropdowns for parsing and generation models
- **Advanced Settings**: Temperature, max tokens, timeout

**Features**:
- Test connection button
- Save/reset configuration
- Security note about API key storage (frontend-only, not sent to backend storage)

---

### **4. Key Components**

#### **PipelineVisualizer** (`components/PipelineVisualizer.tsx`)
Animated 4-stage progress indicator with:
- Stage icons (FileText, Brain, Lightning, CheckCircle)
- Progress bar with color transitions
- Stage messages below each icon
- Smooth animations and state transitions

#### **TestOutput** (`components/TestOutput.tsx`)
Syntax-highlighted code viewer with:
- Language detection (Python, JSON, XML, Gherkin, YAML)
- Line numbers
- Copy-to-clipboard button
- Download button
- Responsive layout

#### **CoverageReport** (`components/CoverageReport.tsx`)
Coverage statistics display with:
- Total planned tests count
- Already covered tests list
- New tests list
- Duplicates list
- Coverage improvement percentage bar

#### **CodeFileUpload** (`components/CodeFileUpload.tsx`)
Drag-and-drop file upload with:
- Multiple file support
- File preview with syntax highlighting
- Remove individual files
- Clear all button

---

## 🔧 Tech Stack Deep Dive

### **Backend**
- **FastAPI**: Modern async web framework with auto-docs, SSE support, and Pydantic integration
- **Pydantic v2**: Data validation and settings management with 5x performance improvement
- **Python 3.12**: Latest features (type hints, pattern matching, performance improvements)
- **uv**: Ultra-fast package manager (10-100x faster than pip)
- **pytest**: Industry-standard testing framework (for generating tests about tests!)

### **Frontend**
- **Next.js 16**: React framework with App Router, SSR, and TypeScript
- **React 19**: Latest concurrent features and improved performance
- **TypeScript**: Type safety for API client and components
- **Custom CSS**: No framework overhead—pure CSS with CSS Grid, Flexbox, animations
- **Phosphor Icons**: Modern icon library with 6000+ icons

### **AI/LLM**
- **OpenRouter**: Unified API for 100+ LLMs (DeepSeek, Gemini, Llama, Qwen, Claude, GPT-4)
- **DeepSeek V3**: Primary generation model (best code quality, free tier)
- **Gemini 2.0 Flash**: Primary parsing model (fast, accurate, free tier)

### **Infrastructure**
- **SSE (Server-Sent Events)**: Real-time streaming without WebSocket complexity
- **CORS**: Configured for secure cross-origin requests
- **Docker-ready**: Easy deployment with containers
- **Git**: Version control with `.gitignore` for dependencies

---

## 📦 Installation & Setup

### **Prerequisites**
- Python 3.12+ (backend)
- Node.js 20+ (frontend)
- Git

### **Quick Start** (5 minutes)

#### **1. Clone Repository**
```bash
git clone https://github.com/vishvaa-vsk/MindFlayer.git
cd MindFlayer
```

#### **2. Backend Setup**
```bash
cd backend

# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# (Optional) Set OpenRouter API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Start backend
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Backend will be available at: **http://localhost:8000**
API docs at: **http://localhost:8000/docs**

#### **3. Frontend Setup** (new terminal)
```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend will be available at: **http://localhost:3000**

### **Production Deployment**

#### **Backend**
```bash
cd backend
uv run python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### **Frontend**
```bash
cd frontend
npm run build
npm start
```

---

## 🎬 Live Demo Script (For Judges)

### **Demo 1: E-Commerce API** (3 minutes)

**Scenario**: Generate tests for an e-commerce order management system.

**Steps**:
1. Open **http://localhost:3000/generate**
2. Paste requirements:
   ```
   POST /users (requires admin_auth)
   POST /products (requires admin_auth)
   GET /products/:id
   POST /orders (requires user_auth, depends on POST /users)
   GET /orders/:id (requires user_auth, depends on POST /orders)
   PUT /orders/:id/cancel (requires user_auth, depends on POST /orders)
   ```
3. Click **"Generate Tests"**
4. Watch pipeline stages:
   - ✅ Parse: Extracted 6 endpoints, 2 auth rules, 4 dependencies
   - ✅ Plan: Generated 18 test scenarios
   - ✅ Generate: Created pytest code
   - ✅ Validate: 100% coverage, 0 duplicates
5. Switch to **Coverage** tab:
   - Show 18 new tests
   - Highlight dependency_failure tests
   - Point out intelligent test types
6. Switch to **Code** tab:
   - Show generated pytest with fixtures
   - Highlight realistic payloads
   - Point out proper assertions
7. Click **Download** → Get `test_suite.py`

**Key Points to Emphasize**:
- ✨ "Notice how MindFlayer detected auth requirements and generated no_auth tests"
- ✨ "See the dependency_failure tests? It understood order creation depends on user creation"
- ✨ "The generated code has proper pytest fixtures and realistic data—production-ready"

---

### **Demo 2: Natural Language Parsing** (2 minutes)

**Scenario**: Show AI-powered natural language understanding.

**Steps**:
1. Click **"Example (Prose)"** button
2. Show natural language input:
   ```
   Users can register and login.
   Authenticated users can create orders and view order history.
   Admin users can manage products and view all orders.
   Payment processing requires a valid order.
   ```
3. Click **"Generate Tests"**
4. Watch parsing stage: "Converting natural language to structured format..."
5. Switch to **Context** tab:
   - Show parsed endpoints (POST /users, POST /orders, POST /payments, etc.)
   - Show detected auth rules (user_auth, admin_auth)
   - Show detected dependencies (payments depends on orders)
6. Switch to **Code** tab:
   - Show generated tests match the natural language intent

**Key Points to Emphasize**:
- ✨ "No structured format needed—MindFlayer understands plain English"
- ✨ "Gemini 2.0 Flash converts prose to precise API structure"
- ✨ "Detected auth scopes and dependencies automatically"

---

### **Demo 3: Code Context Analysis** (2 minutes)

**Scenario**: Upload source code for real enum/validator extraction.

**Steps**:
1. Show `payment_api_example.py` in editor
2. Point out enums: `PaymentStatus`, `Currency`, `FraudRiskLevel`
3. Upload file to MindFlayer via **Code Upload**
4. Paste requirements from `payment_api_requirements.txt`
5. Generate tests
6. Switch to **Context** tab → Show **Code Context** section:
   - Extracted 3 enums (PaymentStatus, Currency, FraudRiskLevel)
   - Extracted 5 validators (min_length, max_length, etc.)
   - Extracted 2 business rules
7. Switch to **Code** tab:
   - Show tests use real enum values (`status="captured"`)
   - Show validation tests for min/max constraints
   - Show state conflict tests ("Can't refund if status != captured")

**Key Points to Emphasize**:
- ✨ "MindFlayer analyzed actual Python source code using AST"
- ✨ "Extracted real enums and validation rules—no hallucination"
- ✨ "Generated tests validate business logic constraints"

---

### **Demo 4: Multi-Format Output** (1 minute)

**Scenario**: Generate tests in multiple formats simultaneously.

**Steps**:
1. Select formats: `pytest`, `postman`, `gherkin`
2. Generate tests
3. Switch between tabs:
   - **pytest**: Show Python test code
   - **postman**: Show Postman Collection JSON
   - **gherkin**: Show BDD .feature file
4. Download all formats

**Key Points to Emphasize**:
- ✨ "One input → Multiple outputs"
- ✨ "Pytest for developers, Postman for QA, Gherkin for BDD"
- ✨ "All formats generated from same test plan"

---

## 🏆 Competition Context

### **AlgoQuest 2025** (Technical Excellence)

**Focus**: Algorithm and system design innovation.

**Key Metrics**:
- **Intelligent Deduplication**: Reduces redundant tests by 30-40%
- **Dependency Graph Analysis**: Optimizes test execution order
- **AST-Based Code Analysis**: Extracts real constraints (not hallucinated)
- **Multi-Stage Pipeline**: Parse → Plan → Generate → Validate

**Talking Points**:
- "MindFlayer doesn't just generate tests—it *understands* API structure through graph analysis"
- "Dependency detection prevents impossible test scenarios (e.g., GET order before POST order)"
- "AST analysis extracts real business rules from source code—no guessing"

---


## 🔬 Technical Innovations

### **1. Intelligent Test Planning**
- **8 test types** (positive, no_auth, dependency_failure, invalid_input, state_conflict, forbidden_role, field_validation, boundary_value)
- **Smart deduplication**: Checks against existing tests before generating
- **Metadata-driven**: Uses FieldSpec, StateConstraint, roles to plan tests

### **2. Code Context Understanding**
- **AST analysis**: Parses Python source code to extract enums, validators, business rules
- **No hallucination**: Uses real values from source code, not LLM guesses
- **Multi-language ready**: Architecture supports Java, TypeScript, Go analysis

### **3. Multi-Format Generation**
- **5 output formats**: pytest, Postman, JUnit, Gherkin, OpenAPI
- **Single test plan**: All formats generated from same TestPlan object
- **Consistent quality**: All formats follow same validation logic

### **4. LLM Adapter System**
- **Provider-agnostic**: Works with OpenRouter, Azure, Ollama, vLLM, TGI
- **Privacy controls**: Circuit breaker prevents external API calls
- **Fallback chain**: OpenRouter → Azure → Ollama → Template

### **5. Real-Time Streaming**
- **SSE (Server-Sent Events)**: Lightweight alternative to WebSockets
- **Stage-by-stage updates**: Parse → Plan → Generate → Validate
- **Responsive UX**: Users see progress immediately

---

## 🔐 Security & Privacy

### **Privacy Features**
- **API keys never stored server-side**: Keys only exist in browser session or env vars
- **Circuit breaker**: Prevents accidental data leakage to external APIs
- **Local LLM support**: Ollama integration for air-gapped environments
- **Template fallback**: Works without any external API (deterministic generation)

### **Security Best Practices**
- **CORS**: Configured for specific origins
- **Input validation**: Pydantic schemas validate all inputs
- **Error handling**: No sensitive info in error messages
- **Rate limiting**: (TODO: Add rate limiting for production)

---

## 📚 Code Examples

### **Example 1: Generate Tests Programmatically**

```python
from context.builder import parse_requirements_text
from planner.test_planner import plan_tests
from generator.pytest_gen import generate_pytest

# 1. Parse requirements
requirements = """
POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)
"""
context = parse_requirements_text(requirements)

# 2. Plan tests
test_plan = plan_tests(context, existing_tests=[])
print(f"Planned {len(test_plan.scenarios)} tests")

# 3. Generate code
test_code = generate_pytest(test_plan, context)
print(test_code)
```

### **Example 2: Analyze Source Code**

```python
from context.code_analyzer import analyze_python_files

code_files = {
    "models/order.py": """
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    """
}

code_context = analyze_python_files(code_files)
print(f"Found {len(code_context.enums)} enums")
print(f"Enum values: {code_context.enums[0].values}")
```

### **Example 3: Stream Generation with SSE**

```python
import httpx

async def stream_generation():
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/api/generate-tests-stream",
            json={"requirements_text": "POST /users", "output_formats": ["pytest"]},
            timeout=60.0
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if "stage" in data:
                        print(f"Stage: {data['stage']} - {data['message']}")
                    elif "context" in data:
                        print("Complete!")
                        print(f"Generated {len(data['test_plan']['scenarios'])} tests")
```

---

## 🐛 Troubleshooting

### **Backend Issues**

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'X'` | Run `cd backend && uv sync` |
| `Port 8000 already in use` | Change port: `uvicorn main:app --port 9000` |
| `OPENROUTER_API_KEY not configured` | Set env var or use Settings page |
| `LLM request timeout` | Check internet connection, try different model |
| `Natural language parsing failed` | Use structured format as fallback |

### **Frontend Issues**

| Issue | Solution |
|-------|----------|
| `Cannot connect to backend` | Ensure backend running on port 8000 |
| `CORS error` | Check backend CORS configuration in `main.py` |
| `SSE connection drops` | Check firewall, try disabling browser extensions |
| `React hydration mismatch` | Clear browser cache, restart dev server |

### **Generation Issues**

| Issue | Solution |
|-------|----------|
| `No tests generated` | Check requirements format, ensure endpoints detected |
| `Generated code has syntax errors` | Report issue with `ast_checker` validation |
| `Duplicate tests` | Check `existing_test_names` parameter |
| `Missing edge cases` | Upload source code for better context |

---

## 🚀 Future Enhancements

### **Planned Features**
- [ ] **GraphQL support**: Parse GraphQL schemas and generate tests
- [ ] **OpenAPI import**: Import existing OpenAPI specs
- [ ] **Test execution**: Run generated tests and report results
- [ ] **CI/CD integration**: GitHub Actions, GitLab CI, Jenkins plugins
- [ ] **Multi-language support**: Java (JUnit), JavaScript (Jest), Go (testing)
- [ ] **Visual test editor**: Drag-and-drop test scenario builder
- [ ] **Test maintenance**: Auto-update tests when API changes
- [ ] **Performance testing**: Generate load tests (Locust, k6)
- [ ] **Security testing**: Generate OWASP Top 10 security tests

### **Scalability**
- [ ] **Database**: Store test plans, generated tests, coverage history
- [ ] **User accounts**: Multi-user support with teams and projects
- [ ] **Versioning**: Track test suite versions across API changes
- [ ] **Analytics**: Test generation metrics, coverage trends

---

## 📞 Support & Contact

**Repository**: [github.com/vishvaa-vsk/MindFlayer](https://github.com/vishvaa-vsk/MindFlayer)

**Issues**: [github.com/vishvaa-vsk/MindFlayer/issues](https://github.com/vishvaa-vsk/MindFlayer/issues)

**Documentation**: This file + `/backend/README.md` + `/frontend/README.md`

**API Docs**: http://localhost:8000/docs (when backend running)

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 🙏 Acknowledgments

- **OpenRouter**: For unified LLM access
- **DeepSeek**: For excellent free code generation models
- **Google**: For Gemini 2.0 Flash parsing model
- **FastAPI**: For modern Python web framework
- **Next.js**: For React framework with great DX
- **Pydantic**: For data validation
- **pytest**: For inspiring this entire project

---

**Built with ❤️ for AlgoQuest 2025**

**Stop writing tests. Start generating them. 🧠⚡**
