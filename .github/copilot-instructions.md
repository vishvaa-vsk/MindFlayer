# TestCortex: Copilot Implementation Guide

**Timeline: Jan 9, 2026 (14 days)**
**Competitions: AlgoQuest 2025 + Imagine Cup 2026**

---

## 🧠 CORE RULE (READ THIS FIRST)

> **You design the system. Copilot implements it.**

- ❌ Don't ask: "Build a test generator"
- ✅ Do ask: "Implement function X using schema Y following rules Z"

Copilot excels at **filling logic from explicit intent**, not at **deciding what matters**.

---

## 📦 PROJECT STRUCTURE

```
/backend
 ├─ models/           # Pydantic schemas (schemas first!)
 │  ├─ context.py
 │  ├─ test_plan.py
 │  └─ generated_test.py
 ├─ context/          # Parse requirements → extract endpoints
 │  └─ builder.py
 ├─ planner/          # Decide what tests should exist
 │  └─ test_planner.py
 ├─ generator/        # Generate test code
 │  └─ pytest_gen.py
 ├─ validator/        # Check coverage, remove dupes
 │  └─ coverage.py
 ├─ api/              # FastAPI wiring
 │  └─ routes.py
 └─ main.py           # Entry point
```

---

## 🎯 PHASE BREAKDOWN (14 DAYS)

### **PHASE 1: Schemas (Days 1-2) 🟢 CRITICAL**

**Why first?** Schemas are rails for Copilot. With clear input/output shapes, Copilot's accuracy jumps 10×.

#### Task 1.1: Create `models/context.py`

**Human**: Define what "context" means.

```
System context =
  - endpoints (name, method, auth_required)
  - dependencies (which endpoints need which)
  - auth rules
```

**Copilot Prompt:**

```
Create Pydantic schemas for:
- Endpoint (name: str, method: str, url_path: str, requires_auth: bool, depends_on: list[str])
- AuthRule (scope: str, required_for: list[str])
- SystemContext (endpoints: list[Endpoint], auth_rules: list[AuthRule], dependencies: dict[str, list[str]])

Add validation: no duplicate endpoint names, all dependencies must reference existing endpoints.
```

**Acceptance:** Run `python -c "from models.context import SystemContext; print(SystemContext.schema())"` — should print valid JSON schema.

---

#### Task 1.2: Create `models/test_plan.py`

**Human**: What test plan should look like.

**Copilot Prompt:**

```
Create Pydantic schemas:
- TestScenario (test_name: str, endpoint: str, description: str, test_type: str)
  where test_type in ["positive", "no_auth", "dependency_failure", "invalid_input"]
- TestPlan (scenarios: list[TestScenario], rationale: str)

Add constraint: test_name must be unique per plan, endpoint must exist.
```

**Acceptance:** Instantiate with sample data, validate it works.

---

#### Task 1.3: Create `models/generated_test.py`

**Copilot Prompt:**

```
Create Pydantic schema for:
- GeneratedTest (test_name: str, test_code: str, language: str, assertions: list[str])
- TestSuite (tests: list[GeneratedTest], coverage_percentage: float)

Add: language in ["python_pytest"], validate test_code is not empty.
```

**Acceptance:** Parse generated test code strings without errors.

---

**PHASE 1 CHECKPOINT:**

- [ ] All 3 schema files created
- [ ] Schemas import cleanly
- [ ] Team understands input/output shapes

---

### **PHASE 2: Context Builder (Days 3-4)**

**What:** Parse requirements text → extract Endpoint objects

**Task 2.1: Implement `context/builder.py`**

**Human:** Write out example requirements:

```
Requirements:
- POST /orders (requires user_auth)
- GET /orders/:id (requires user_auth, depends on POST /orders)
- POST /admin/users (requires admin_auth)
- DELETE /orders/:id (requires user_auth)
```

**Copilot Prompt:**

```
Implement function: parse_requirements_text(text: str) -> SystemContext

Rules (implement as comments first):
1. Split text by line
2. Extract endpoint: regex pattern "METHOD /path"
3. Extract auth requirement: look for "requires X_auth"
4. Extract dependencies: look for "depends on Y endpoint"
5. Build SystemContext object

Return SystemContext with all endpoints parsed, or raise ValueError with line number if malformed.

Test with this input:
```

POST /orders (requires user_auth)
GET /orders/:id (requires user_auth, depends on POST /orders)

````

**Acceptance:**
```python
ctx = parse_requirements_text(requirements_text)
assert len(ctx.endpoints) == 2
assert ctx.endpoints[0].method == "POST"
````

---

**PHASE 2 CHECKPOINT:**

- [ ] Context builder works on sample requirements
- [ ] Parses endpoints, methods, auth, dependencies
- [ ] Handles malformed input gracefully

---

### **PHASE 3: Test Planner (Days 5-6) 🔥 YOUR IP**

**What:** Given SystemContext, decide what tests should exist.

**Task 3.1: Implement `planner/test_planner.py`**

**Human:** Write planner rules as comments FIRST.

```python
# PLANNER RULES:
# For each endpoint:
#   1. Generate "positive" test (happy path, 200 OK)
#   2. If requires_auth → generate "no_auth" test (expect 401)
#   3. If depends_on another endpoint → generate "dependency_failure" test
#   4. For GET endpoints with :id → generate "invalid_id" test (404)
# Skip if test_name already in existing_tests (dedup)
```

**Copilot Prompt:**

```
Implement function: plan_tests(context: SystemContext, existing_tests: list[str]) -> TestPlan

Logic:
1. For each endpoint in context.endpoints:
   a. Create test_name = "{method}_{endpoint_path}".lower().replace("/", "_")
   b. Add "positive" test (test_name_basic)
   c. If requires_auth: add "no_auth" test (test_name_no_auth)
   d. If depends_on: add "dependency_failure" test (test_name_dependency_fail)
   e. If path contains :id: add "invalid_id" test (test_name_invalid_id)
2. Filter out tests already in existing_tests list
3. Return TestPlan with all scenarios and rationale string

Test with example SystemContext from Phase 2.
```

**Acceptance:**

```python
plan = plan_tests(sample_context, existing_tests=[])
assert len(plan.scenarios) >= 5  # At least positive + auth variations
assert all(s.test_type in ["positive", "no_auth", "dependency_failure", "invalid_id"] for s in plan.scenarios)
```

---

**PHASE 3 CHECKPOINT:**

- [ ] Planner generates 4+ scenarios per endpoint
- [ ] Deduplication works
- [ ] All test_type values are valid

---

### **PHASE 4: Code Generator (Days 7-8)**

**What:** Convert TestPlan → executable pytest code

**Task 4.1: Implement `generator/pytest_gen.py`**

**Copilot Prompt:**

```
Implement function: generate_pytest(test_plan: TestPlan) -> str

Output format: valid Python pytest code that can be executed.

For each scenario in test_plan:
1. test_name = scenario.test_name
2. Build test function def test_NAME(client):
3. Based on scenario.test_type:
   a. "positive": call endpoint, assert response.status_code == 200
   b. "no_auth": call endpoint without auth header, assert status == 401
   c. "dependency_failure": call endpoint, then call dependency endpoint first, assert proper error
   d. "invalid_id": call with id="invalid", assert status == 404
4. Add sample data/payloads (use reasonable defaults)

Use f-strings and inline comments.
Generate complete, runnable code (imports + fixtures).

Return as single string.
```

**Acceptance:**

```python
code = generate_pytest(test_plan)
assert "def test_" in code
assert "import pytest" in code
# Syntactically valid Python
compile(code, '<string>', 'exec')
```

---

**PHASE 4 CHECKPOINT:**

- [ ] Generated code is syntactically valid Python
- [ ] All test functions follow pytest pattern
- [ ] Can be executed with `pytest generated_tests.py`

---

### **PHASE 5: Validator (Days 9)**

**What:** Check coverage, dedup, quality gates

**Task 5.1: Implement `validator/coverage.py`**

**Copilot Prompt:**

```
Implement function: validate_coverage(planned_tests: list[str], existing_tests: list[str]) -> dict

Return structure:
{
  "total_planned": int,
  "already_covered": list[str],
  "new_tests": list[str],
  "duplicates": list[str],
  "coverage_improvement": float (0-1)
}

Logic:
1. Find tests in both lists → already_covered
2. Find tests only in planned → new_tests
3. Count duplicates in planned_tests itself
4. Coverage improvement = len(new_tests) / len(planned_tests)
```

**Acceptance:** Validate with sample lists.

---

**PHASE 5 CHECKPOINT:**

- [ ] Coverage report is accurate
- [ ] Duplicates are identified
- [ ] Improvement metric calculated

---

### **PHASE 6: FastAPI Wiring (Days 10-11)**

**What:** Wire everything into HTTP endpoint

**Task 6.1: Implement `api/routes.py`**

**Copilot Prompt:**

```
Create FastAPI endpoint: POST /generate-tests

Request body:
{
  "requirements_text": str,
  "existing_test_names": list[str]
}

Response:
{
  "context": SystemContext,
  "test_plan": TestPlan,
  "generated_code": str,
  "validation": {coverage report}
}

Implementation:
1. Parse requirements_text → SystemContext (use context builder)
2. Plan tests → TestPlan (use planner)
3. Generate code → str (use generator)
4. Validate → report (use validator)
5. Return all as JSON

Add error handling: if any step fails, return 400 with error message.
```

**Acceptance:** Call endpoint with sample requirements, get back valid response.

---

**Task 6.2: Create `main.py`**

```python
from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="TestCortex")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

**PHASE 6 CHECKPOINT:**

- [ ] API runs: `python main.py`
- [ ] POST /generate-tests works end-to-end
- [ ] Sample request → valid response

---

### **PHASE 7: Polish & Demo (Days 12-14)**

**What:** Bug fixes, edge cases, demo script

**Tasks:**

- [ ] Test context builder on 5+ edge cases
- [ ] Test planner dedup on overlapping requirements
- [ ] Test generator code quality (runs without errors)
- [ ] Create `demo.md` with:
  - Sample requirements
  - Curl command to API
  - Generated test code output
- [ ] Add README.md with setup instructions
- [ ] Time yourself: requirements → tests < 5 seconds

---

## 💻 COPILOT PROMPTS TEMPLATE

**Never ask:** "Build X" or "Make it smart"

**Always ask:**

```
Implement function: [FUNCTION_NAME]([INPUTS]) -> [OUTPUT_TYPE]

Rules (step by step):
1. [Rule 1]
2. [Rule 2]
...

Test with: [EXAMPLE INPUT]

Return: [EXPECTED OUTPUT]
```

---

## ❌ AVOID THESE MISTAKES

| Mistake                             | Why Bad                  | Fix                              |
| ----------------------------------- | ------------------------ | -------------------------------- |
| Vague prompts to Copilot            | Output is mediocre       | Write explicit rules first       |
| Adding "smart AI" logic             | It breaks in edge cases  | Keep logic deterministic         |
| Accepting code you don't understand | It'll fail in production | Rewrite until you own it         |
| Over-engineering schemas            | Wasted time              | Use `str, int, bool, list` first |
| Building UI first                   | Judges don't care        | Demo in terminal with curl       |

---

## 📊 DAILY CHECKLIST

**Day 1-2:** Schemas ✅

- [ ] context.py works
- [ ] test_plan.py works
- [ ] generated_test.py works

**Day 3-4:** Context Builder ✅

- [ ] parse_requirements_text works
- [ ] tested on 3+ examples

**Day 5-6:** Planner ✅

- [ ] plan_tests works
- [ ] dedup verified
- [ ] outputs valid TestPlan

**Day 7-8:** Generator ✅

- [ ] generate_pytest produces valid Python
- [ ] generated tests run without syntax errors

**Day 9:** Validator ✅

- [ ] Coverage report accurate
- [ ] Dedup logic verified

**Day 10-11:** API ✅

- [ ] POST /generate-tests works end-to-end
- [ ] Server runs without crashing

**Day 12-14:** Polish ✅

- [ ] Demo works
- [ ] README complete
- [ ] Ready to submit

---

## 🎯 SUBMISSION MESSAGING

### **For AlgoQuest (Technical):**

- Focus: "Intelligent test planning reduces redundancy"
- Metric: "Generated 30% fewer tests than naive approach"
- Demo: Show dedup logic in action

### **For Imagine Cup (Impact):**

- Focus: "Automates 80% of test case writing"
- Metric: "5-10x faster test generation than manual"
- Demo: Requirements → Full test suite in 10 seconds

---

## 🚨 IF YOU GET STUCK

**Copilot gives wrong code?**
→ Rewrite the prompt more explicitly. Add examples.

**Phase taking too long?**
→ Cut scope: remove invalid_id tests, cut validator details.

**Generated tests don't run?**
→ Copilot prompt: "Fix these pytest errors: [ERROR TEXT]"

---

## 🏁 FINAL RULE

> If you can't explain it in plain English, Copilot can't implement it.

Write the rule first. Then ask Copilot to code it.

Good luck! 🚀
