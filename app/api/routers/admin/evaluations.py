"""Prompt evaluation router — run Q&A test suites against prompts."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.api.services.llm_queue import enqueue_llm_request
from app.models.admin_user import AdminUser
from app.models.evaluation import EvaluationTestCase, PromptEvaluation


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
    result = await db.execute(
        select(PromptEvaluation)
        .options(selectinload(PromptEvaluation.test_cases))
        .where(PromptEvaluation.id == uuid.UUID(evaluation_id))
    )
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
                "judgment": tc.judgment,
                "latency_ms": tc.latency_ms,
                "error": tc.error,
            }
            for tc in evaluation.test_cases
        ],
    }


@router.delete("/{evaluation_id}")
async def delete_evaluation(evaluation_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an evaluation."""
    result = await db.execute(
        select(PromptEvaluation)
        .options(selectinload(PromptEvaluation.test_cases))
        .where(PromptEvaluation.id == uuid.UUID(evaluation_id))
    )
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
    result = await db.execute(
        select(PromptEvaluation)
        .options(selectinload(PromptEvaluation.test_cases))
        .where(PromptEvaluation.id == uuid.UUID(evaluation_id))
    )
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
    """Run all test cases in an evaluation against the prompt via llm.process queue."""
    result = await db.execute(
        select(PromptEvaluation)
        .options(selectinload(PromptEvaluation.test_cases))
        .where(PromptEvaluation.id == uuid.UUID(evaluation_id))
    )
    evaluation = result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Mark as running
    evaluation.status = "running"
    await db.commit()

    error_msg: str | None = None

    try:
        for tc in evaluation.test_cases:
            # Publish to llm.process queue and wait for worker to process
            llm_result = await enqueue_llm_request({
                "channel": "evaluation",
                "evaluation_id": str(evaluation.id),
                "tc_id": str(tc.id),
                "question": tc.question,
                "expected_answer": tc.expected_answer,
                "prompt_name": evaluation.prompt_name,
            })

            # Worker updated DB directly; verify result
            if llm_result.get("error"):
                error_msg = llm_result["error"]
                break

    except Exception as exc:
        evaluation.status = "failed"
        evaluation.error = str(exc)
        evaluation.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "id": str(evaluation.id),
            "status": evaluation.status,
            "error": str(exc),
        }

    # Refresh evaluation from DB to get final counts
    await db.refresh(evaluation)
    return {
        "id": str(evaluation.id),
        "status": evaluation.status,
        "total": evaluation.total,
        "passed": evaluation.passed,
        "failed": evaluation.failed,
        "error": error_msg,
    }
