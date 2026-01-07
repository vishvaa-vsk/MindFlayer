"""FastAPI routes for test generation."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import SystemContext, TestPlan
from context.builder import parse_requirements_text, is_structured_format
from planner.test_planner import plan_tests
from generator.pytest_gen import generate_pytest
from validator.coverage import validate_coverage


router = APIRouter()


class GenerateTestsRequest(BaseModel):
    """Request body for test generation endpoint."""
    requirements_text: str  # Can be prose or structured format
    existing_test_names: list[str] = []


class GenerateTestsResponse(BaseModel):
    """Response body for test generation endpoint."""
    context: SystemContext
    test_plan: TestPlan
    generated_code: str
    validation: dict
    parsed_with_llm: bool = False


@router.post("/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(request: GenerateTestsRequest):
    """
    Generate tests from requirements (prose or structured).

    Pipeline:
    1. Parse requirements_text → SystemContext
       - Auto-detects prose vs structured format
       - Uses LLM for natural language conversion if available
    2. Plan tests → TestPlan
    3. Generate code → str (with LLM payloads)
    4. Validate coverage → report
    
    Request format:
    - Prose: "Users can create orders with authentication"
    - Structured: "POST /orders (requires user_auth)"
    """
    try:
        # Track if LLM was used
        used_llm = not is_structured_format(request.requirements_text)

        # Step 1: Parse requirements into SystemContext
        # Auto-detects and uses LLM if natural language
        context = parse_requirements_text(request.requirements_text)

        # Step 2: Plan what tests should exist
        test_plan = plan_tests(context, existing_tests=request.existing_test_names)

        # Step 3: Generate pytest code (with LLM payloads)
        generated_code = generate_pytest(test_plan)

        # Step 4: Validate coverage
        planned_test_names = [scenario.test_name for scenario in test_plan.scenarios]
        validation = validate_coverage(planned_test_names, request.existing_test_names)

        return GenerateTestsResponse(
            context=context,
            test_plan=test_plan,
            generated_code=generated_code,
            validation=validation,
            parsed_with_llm=used_llm,
        )

    except ValueError as e:
        error_msg = str(e)
        if "OPENAI_API_KEY" in error_msg:
            raise HTTPException(
                status_code=400,
                detail=f"Natural language parsing requires OpenAI API key. "
                       f"Either set OPENAI_API_KEY env var or use structured format "
                       f"(METHOD /path). Error: {error_msg}"
            )
        raise HTTPException(status_code=400, detail=f"Invalid requirements: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "llm_enabled": True,
        "features": [
            "Natural language requirement parsing",
            "Structured API endpoint parsing",
            "Intelligent test planning",
            "Smart payload generation",
            "Coverage analysis"
        ]
    }
