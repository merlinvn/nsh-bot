"""Prompt evaluation router — run Q&A test suites against prompts."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.core.config import settings
from app.models.admin_user import AdminUser
from app.models.evaluation import EvaluationTestCase, PromptEvaluation
from app.models.prompt import Prompt
from app.workers.conversation.agent import AgentRunner
from app.workers.conversation.llm import create_llm_client
from app.workers.conversation.processor import MAX_LLM_STEPS, MAX_TOOL_CALLS_PER_STEP
from app.workers.conversation.registry import get_registry, LocalToolBackend
from app.workers.conversation.tools import ToolExecutor


router = APIRouter(prefix="/admin/evaluations", tags=["admin:evaluations"])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_evaluations(db: AsyncSession = Depends(get_db)):
    """List all evaluations."""
    result = await db.execute(select(PromptEvaluation).order_by(PromptEvaluation.created_at.desc()))
    evals = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "prompt_name": e.prompt_name,
            "status": e.status,
            "total": e.total,
            "passed": e.passed,
            "failed": e.failed,
            "created_at": e.created_at.isoformat(),
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        }
        for e in evals
    ]


@router.post("")
async def create_evaluation(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Create a new evaluation with test cases."""
    name = body.get("name")
    prompt_name = body.get("prompt_name")
    test_cases = body.get("test_cases", [])

    if not name or not prompt_name:
        raise HTTPException(status_code=400, detail="name and prompt_name required")

    evaluation = PromptEvaluation(
        name=name,
        prompt_name=prompt_name,
        status="draft",
    )
    db.add(evaluation)
    await db.flush()

    for tc in test_cases:
        tc_record = EvaluationTestCase(
            evaluation_id=evaluation.id,
            question=tc["question"],
            expected_answer=tc["expected_answer"],
        )
        db.add(tc_record)

    await db.commit()
    return {"id": str(evaluation.id), "name": evaluation.name, "status": evaluation.status}


@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: str, db: AsyncSession = Depends(get_db)):
    """Get evaluation with all test cases."""
    result = await db.execute(select(PromptEvaluation).where(PromptEvaluation.id == uuid.UUID(evaluation_id)))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    return {
        "id": str(evaluation.id),
        "name": evaluation.name,
        "prompt_name": evaluation.prompt_name,
        "status": evaluation.status,
        "total": evaluation.total,
        "passed": evaluation.passed,
        "failed": evaluation.failed,
        "error": evaluation.error,
        "created_at": evaluation.created_at.isoformat(),
        "completed_at": evaluation.completed_at.isoformat() if evaluation.completed_at else None,
        "test_cases": [
            {
                "id": str(tc.id),
                "question": tc.question,
                "expected_answer": tc.expected_answer,
                "actual_answer": tc.actual_answer,
                "passed": tc.passed,
                "latency_ms": tc.latency_ms,
                "error": tc.error,
            }
            for tc in evaluation.test_cases
        ],
    }


@router.delete("/{evaluation_id}")
async def delete_evaluation(evaluation_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an evaluation."""
    result = await db.execute(select(PromptEvaluation).where(PromptEvaluation.id == uuid.UUID(evaluation_id)))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    await db.delete(evaluation)
    await db.commit()
    return {"ok": True}


@router.post("/{evaluation_id}/test-cases")
async def add_test_case(
    evaluation_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Add a test case to an evaluation."""
    result = await db.execute(select(PromptEvaluation).where(PromptEvaluation.id == uuid.UUID(evaluation_id)))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    tc = EvaluationTestCase(
        evaluation_id=evaluation.id,
        question=body["question"],
        expected_answer=body["expected_answer"],
    )
    db.add(tc)
    await db.commit()
    return {"id": str(tc.id)}


@router.delete("/{evaluation_id}/test-cases/{tc_id}")
async def delete_test_case(evaluation_id: str, tc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a test case."""
    result = await db.execute(
        select(EvaluationTestCase).where(
            EvaluationTestCase.id == uuid.UUID(tc_id),
            EvaluationTestCase.evaluation_id == uuid.UUID(evaluation_id),
        )
    )
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await db.delete(tc)
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------


@router.post("/{evaluation_id}/run")
async def run_evaluation(
    evaluation_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Run all test cases in an evaluation against the prompt."""
    result = await db.execute(select(PromptEvaluation).where(PromptEvaluation.id == uuid.UUID(evaluation_id)))
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Get prompt template from DB
    prompt_result = await db.execute(select(Prompt).where(Prompt.name == evaluation.prompt_name))
    prompt_record = prompt_result.scalar_one_or_none()
    system_prompt = prompt_record.template if prompt_record else ""

    # Set up LLM
    client = create_llm_client(
        provider=settings.llm_provider,
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_model=settings.anthropic_model,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
    )
    registry = get_registry()
    backend = LocalToolBackend(registry)
    tool_executor = ToolExecutor(backend)

    runner = AgentRunner(
        llm=client,
        tool_executor=tool_executor,
        system_prompt=system_prompt,
        tool_definitions=registry.definitions(),
        max_steps=MAX_LLM_STEPS,
        max_tool_calls_per_step=MAX_TOOL_CALLS_PER_STEP,
    )

    # Mark as running
    evaluation.status = "running"
    await db.commit()

    passed_count = 0
    failed_count = 0
    error_msg: str | None = None

    try:
        for tc in evaluation.test_cases:
            try:
                result = await runner.run([], tc.question)

                actual = result.text.strip()

                # Simple string comparison (case-insensitive, stripped)
                expected_lower = tc.expected_answer.strip().lower()
                actual_lower = actual.lower()
                is_passed = expected_lower in actual_lower or actual_lower in expected_lower

                tc.actual_answer = actual
                tc.passed = is_passed
                tc.latency_ms = result.latency_ms
                tc.error = None

                if is_passed:
                    passed_count += 1
                else:
                    failed_count += 1

            except Exception as exc:
                tc.error = str(exc)
                tc.passed = False
                tc.actual_answer = None
                failed_count += 1

        evaluation.status = "completed"
        evaluation.completed_at = datetime.now(timezone.utc)
        evaluation.total = len(evaluation.test_cases)
        evaluation.passed = passed_count
        evaluation.failed = failed_count
        await db.commit()

    except Exception as exc:
        evaluation.status = "failed"
        evaluation.error = str(exc)
        evaluation.completed_at = datetime.now(timezone.utc)
        await db.commit()
        error_msg = str(exc)

    return {
        "id": str(evaluation.id),
        "status": evaluation.status,
        "total": evaluation.total,
        "passed": evaluation.passed,
        "failed": evaluation.failed,
        "error": error_msg,
    }
