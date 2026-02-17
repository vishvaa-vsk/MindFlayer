"""FastAPI routes for MindFlayer test generation pipeline."""
import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models import SystemContext, TestPlan
from context.builder import parse_requirements_text, is_structured_format
from planner.test_planner import plan_tests
from generator.pytest_gen import generate_pytest
from generator.postman_gen import generate_postman
from generator.junit_gen import generate_junit_xml
from generator.gherkin_gen import generate_gherkin
from generator.openapi_gen import generate_openapi_spec
from validator.coverage import validate_coverage
from config import get_settings, update_settings
from adapters.registry import list_available_providers
from adapters.base import PrivacyViolationError, CircuitOpenError

router = APIRouter()

# ── Output Format Registry ────────────────────────────────

OUTPUT_FORMATS = {
    "pytest": {
        "name": "Pytest",
        "description": "Executable Python pytest test suite",
        "icon": "🐍",
        "language": "python",
        "extension": ".py",
    },
    "postman": {
        "name": "Postman Collection",
        "description": "Postman Collection v2.1 JSON — import directly into Postman",
        "icon": "📮",
        "language": "json",
        "extension": ".json",
    },
    "junit": {
        "name": "JUnit XML",
        "description": "JUnit XML report format — CI/CD compatible",
        "icon": "🧪",
        "language": "xml",
        "extension": ".xml",
    },
    "gherkin": {
        "name": "Gherkin / BDD",
        "description": "Gherkin .feature file with Given/When/Then scenarios",
        "icon": "🥒",
        "language": "gherkin",
        "extension": ".feature",
    },
    "openapi": {
        "name": "OpenAPI Spec",
        "description": "OpenAPI 3.0 specification with test extensions",
        "icon": "📋",
        "language": "yaml",
        "extension": ".yaml",
    },
}

FORMAT_GENERATORS = {
    "pytest": lambda plan, ctx: generate_pytest(plan, ctx),
    "postman": lambda plan, ctx: generate_postman(plan, ctx),
    "junit": lambda plan, ctx: generate_junit_xml(plan, ctx),
    "gherkin": lambda plan, ctx: generate_gherkin(plan, ctx),
    "openapi": lambda plan, ctx: generate_openapi_spec(plan, ctx),
}


# ── Request / Response Models ─────────────────────────────

class GenerateTestsRequest(BaseModel):
    """Request body for test generation endpoint."""
    requirements_text: str
    existing_test_names: list[str] = []
    output_formats: list[str] = ["pytest"]


class GenerateTestsResponse(BaseModel):
    """Response body for test generation endpoint."""
    context: SystemContext
    test_plan: TestPlan
    generated_code: str  # Legacy: first format output
    outputs: dict[str, str]  # format_name → generated content
    validation: dict
    parsed_with_llm: bool = False


class SettingsUpdateRequest(BaseModel):
    """Request to update runtime settings."""
    openrouter_api_key: str | None = None
    azure_api_key: str | None = None
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    azure_deployment_parsing: str | None = None
    azure_deployment_generation: str | None = None
    parsing_model: str | None = None
    generation_model: str | None = None
    llm_provider: str | None = None
    allow_external_calls: bool | None = None
    ollama_base_url: str | None = None
    vllm_base_url: str | None = None
    tgi_base_url: str | None = None


class SettingsResponse(BaseModel):
    """Current settings state (sensitive fields masked)."""
    has_api_key: bool
    parsing_model: str
    generation_model: str
    llm_provider: str
    allow_external_calls: bool
    app_name: str
    app_version: str


# ── Generate Tests (standard) ─────────────────────────────

@router.post("/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(request: GenerateTestsRequest):
    """
    Generate tests from requirements in multiple output formats.

    Pipeline:
    1. Parse requirements_text → SystemContext
    2. Plan tests → TestPlan
    3. Generate code → outputs dict (per requested format)
    4. Validate coverage → report
    """
    try:
        used_llm = not is_structured_format(request.requirements_text)
        context = parse_requirements_text(request.requirements_text)
        test_plan = plan_tests(context, existing_tests=request.existing_test_names)

        # Generate all requested formats
        outputs = {}
        for fmt in request.output_formats:
            if fmt in FORMAT_GENERATORS:
                outputs[fmt] = FORMAT_GENERATORS[fmt](test_plan, context)

        # Legacy field — first format output
        first_format = request.output_formats[0] if request.output_formats else "pytest"
        generated_code = outputs.get(first_format, outputs.get("pytest", ""))

        planned_test_names = [s.test_name for s in test_plan.scenarios]
        validation = validate_coverage(planned_test_names, request.existing_test_names)

        return GenerateTestsResponse(
            context=context,
            test_plan=test_plan,
            generated_code=generated_code,
            outputs=outputs,
            validation=validation,
            parsed_with_llm=used_llm,
        )

    except PrivacyViolationError as e:
        raise HTTPException(status_code=403, detail={"error": "privacy_violation", "message": str(e)})
    except CircuitOpenError as e:
        raise HTTPException(status_code=503, detail={"error": "circuit_open", "message": str(e)})
    except ValueError as e:
        error_msg = str(e)
        if "API_KEY" in error_msg.upper():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "api_key_missing",
                    "message": "API key not configured. Set it in the settings panel or use structured format (METHOD /path).",
                },
            )
        raise HTTPException(status_code=400, detail={"error": "invalid_input", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "generation_failed", "message": str(e)})


# ── Generate Tests (streaming via SSE) ────────────────────

@router.post("/generate-tests-stream")
async def generate_tests_stream(request: GenerateTestsRequest):
    """
    Streaming test generation via Server-Sent Events.

    Streams each pipeline stage so the UI can show real-time progress:
      - stage: parsing → context_ready
      - stage: planning → plan_ready
      - stage: generating → code_ready
      - stage: validating → complete
    """
    async def event_stream():
        try:
            # Stage 1: Parsing
            yield _sse_event("stage", {"stage": "parsing", "message": "Parsing requirements..."})
            await asyncio.sleep(0.1)

            used_llm = not is_structured_format(request.requirements_text)
            context = parse_requirements_text(request.requirements_text)

            yield _sse_event("context_ready", {
                "stage": "parsing",
                "message": f"Parsed {len(context.endpoints)} endpoints",
                "data": context.model_dump(),
            })
            await asyncio.sleep(0.1)

            # Stage 2: Planning
            yield _sse_event("stage", {"stage": "planning", "message": "Planning test scenarios..."})
            await asyncio.sleep(0.1)

            test_plan = plan_tests(context, existing_tests=request.existing_test_names)

            yield _sse_event("plan_ready", {
                "stage": "planning",
                "message": f"Planned {len(test_plan.scenarios)} test scenarios",
                "data": test_plan.model_dump(),
            })
            await asyncio.sleep(0.1)

            # Stage 3: Generating (all formats)
            formats = request.output_formats or ["pytest"]
            format_names = ", ".join(OUTPUT_FORMATS.get(f, {}).get("name", f) for f in formats)
            yield _sse_event("stage", {"stage": "generating", "message": f"Generating: {format_names}..."})
            await asyncio.sleep(0.1)

            outputs = {}
            for fmt in formats:
                if fmt in FORMAT_GENERATORS:
                    outputs[fmt] = FORMAT_GENERATORS[fmt](test_plan, context)

            first_format = formats[0] if formats else "pytest"
            generated_code = outputs.get(first_format, "")

            yield _sse_event("code_ready", {
                "stage": "generating",
                "message": f"Generated {len(test_plan.scenarios)} tests in {len(outputs)} format(s)",
                "data": {"generated_code": generated_code, "outputs": outputs},
            })
            await asyncio.sleep(0.1)

            # Stage 4: Validating
            yield _sse_event("stage", {"stage": "validating", "message": "Validating coverage..."})
            await asyncio.sleep(0.1)

            planned_names = [s.test_name for s in test_plan.scenarios]
            validation = validate_coverage(planned_names, request.existing_test_names)

            yield _sse_event("complete", {
                "stage": "complete",
                "message": "Generation complete!",
                "data": {
                    "context": context.model_dump(),
                    "test_plan": test_plan.model_dump(),
                    "generated_code": generated_code,
                    "outputs": outputs,
                    "validation": validation,
                    "parsed_with_llm": used_llm,
                },
            })

        except PrivacyViolationError as e:
            yield _sse_event("error", {"error": "privacy_violation", "message": str(e)})
        except CircuitOpenError as e:
            yield _sse_event("error", {"error": "circuit_open", "message": str(e)})
        except ValueError as e:
            yield _sse_event("error", {"error": "invalid_input", "message": str(e)})
        except Exception as e:
            yield _sse_event("error", {"error": "generation_failed", "message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ── Output Formats ────────────────────────────────────────

@router.get("/formats")
async def list_formats():
    """List available output formats."""
    return {"formats": OUTPUT_FORMATS}


# ── Providers ─────────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    """List all LLM providers with status and capabilities."""
    settings = get_settings()
    return {
        "current_provider": settings.llm_provider,
        "allow_external_calls": settings.allow_external_calls,
        "providers": list_available_providers(),
    }


# ── Settings ──────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_current_settings():
    """Get current application settings (API key masked)."""
    settings = get_settings()
    return SettingsResponse(
        has_api_key=settings.has_api_key,
        parsing_model=settings.parsing_model,
        generation_model=settings.generation_model,
        llm_provider=settings.llm_provider,
        allow_external_calls=settings.allow_external_calls,
        app_name=settings.app_name,
        app_version=settings.app_version,
    )


@router.post("/settings", response_model=SettingsResponse)
async def update_app_settings(request: SettingsUpdateRequest):
    """Update runtime settings (API key, model selection, provider, privacy)."""
    updates = {}
    for field_name in request.model_fields_set:
        value = getattr(request, field_name)
        if value is not None:
            updates[field_name] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No settings to update")

    settings = update_settings(**updates)
    return SettingsResponse(
        has_api_key=settings.has_api_key,
        parsing_model=settings.parsing_model,
        generation_model=settings.generation_model,
        llm_provider=settings.llm_provider,
        allow_external_calls=settings.allow_external_calls,
        app_name=settings.app_name,
        app_version=settings.app_version,
    )


# ── Health Check ──────────────────────────────────────────

@router.get("/health")
async def health():
    """Health check endpoint with provider status."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_provider": settings.llm_provider,
        "llm_configured": settings.has_api_key,
        "allow_external_calls": settings.allow_external_calls,
        "models": {
            "parsing": settings.parsing_model,
            "generation": settings.generation_model,
        },
        "output_formats": list(OUTPUT_FORMATS.keys()),
        "features": [
            "Multi-provider LLM support (OpenRouter, Ollama, vLLM, TGI, Azure)",
            "Local-only mode (ALLOW_EXTERNAL_CALLS=false)",
            "Retry with exponential backoff + circuit breaker",
            "Natural language requirement parsing",
            "Structured API endpoint parsing",
            "AI-powered test code generation",
            "Multi-format output (Pytest, Postman, JUnit XML, Gherkin, OpenAPI)",
            "Intelligent test planning",
            "Coverage analysis & gap detection",
            "Real-time streaming pipeline",
        ],
    }
