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
from validator.coverage import validate_coverage
from config import get_settings, update_settings


router = APIRouter()


# ── Request / Response Models ─────────────────────────────

class GenerateTestsRequest(BaseModel):
    """Request body for test generation endpoint."""
    requirements_text: str
    existing_test_names: list[str] = []


class GenerateTestsResponse(BaseModel):
    """Response body for test generation endpoint."""
    context: SystemContext
    test_plan: TestPlan
    generated_code: str
    validation: dict
    parsed_with_llm: bool = False


class SettingsUpdateRequest(BaseModel):
    """Request to update runtime settings."""
    openrouter_api_key: str | None = None
    parsing_model: str | None = None
    generation_model: str | None = None


class SettingsResponse(BaseModel):
    """Current settings state (sensitive fields masked)."""
    has_api_key: bool
    parsing_model: str
    generation_model: str
    app_name: str
    app_version: str


# ── Generate Tests (standard) ─────────────────────────────

@router.post("/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(request: GenerateTestsRequest):
    """
    Generate tests from requirements (prose or structured).

    Pipeline:
    1. Parse requirements_text → SystemContext
    2. Plan tests → TestPlan
    3. Generate code → str (with LLM)
    4. Validate coverage → report
    """
    try:
        used_llm = not is_structured_format(request.requirements_text)

        context = parse_requirements_text(request.requirements_text)
        test_plan = plan_tests(context, existing_tests=request.existing_test_names)
        generated_code = generate_pytest(test_plan, context)

        planned_test_names = [s.test_name for s in test_plan.scenarios]
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
        if "OPENROUTER_API_KEY" in error_msg or "API_KEY" in error_msg:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "api_key_missing",
                    "message": "OpenRouter API key not configured. Set it in the settings panel or use structured format (METHOD /path).",
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

            # Stage 3: Generating
            yield _sse_event("stage", {"stage": "generating", "message": "Generating test code with AI..."})
            await asyncio.sleep(0.1)

            generated_code = generate_pytest(test_plan, context)

            yield _sse_event("code_ready", {
                "stage": "generating",
                "message": f"Generated {len(test_plan.scenarios)} tests",
                "data": {"generated_code": generated_code},
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
                    "validation": validation,
                    "parsed_with_llm": used_llm,
                },
            })

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


# ── Settings ──────────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_current_settings():
    """Get current application settings (API key masked)."""
    settings = get_settings()
    return SettingsResponse(
        has_api_key=settings.has_api_key,
        parsing_model=settings.parsing_model,
        generation_model=settings.generation_model,
        app_name=settings.app_name,
        app_version=settings.app_version,
    )


@router.post("/settings", response_model=SettingsResponse)
async def update_app_settings(request: SettingsUpdateRequest):
    """Update runtime settings (API key, model selection)."""
    updates = {}
    if request.openrouter_api_key is not None:
        updates["openrouter_api_key"] = request.openrouter_api_key
    if request.parsing_model is not None:
        updates["parsing_model"] = request.parsing_model
    if request.generation_model is not None:
        updates["generation_model"] = request.generation_model

    if not updates:
        raise HTTPException(status_code=400, detail="No settings to update")

    settings = update_settings(**updates)
    return SettingsResponse(
        has_api_key=settings.has_api_key,
        parsing_model=settings.parsing_model,
        generation_model=settings.generation_model,
        app_name=settings.app_name,
        app_version=settings.app_version,
    )


# ── Health Check ──────────────────────────────────────────

@router.get("/health")
async def health():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "llm_configured": settings.has_api_key,
        "models": {
            "parsing": settings.parsing_model,
            "generation": settings.generation_model,
        },
        "features": [
            "Natural language requirement parsing",
            "Structured API endpoint parsing",
            "AI-powered test code generation",
            "Intelligent test planning",
            "Coverage analysis & gap detection",
            "Real-time streaming pipeline",
        ],
    }
