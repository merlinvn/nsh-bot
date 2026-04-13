"""Admin playground router for LLM testing and benchmarking."""
import asyncio
import statistics
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_admin_user, get_db
from app.api.schemas.playground import BenchmarkRequest, CompletionRequest, PlaygroundChatRequest
from app.api.services.llm_queue import enqueue_llm_request
from app.core.config import settings
from app.models.admin_user import AdminUser
from app.models.benchmark_result import BenchmarkItem, BenchmarkResult
from app.workers.conversation.llm import create_llm_client

router = APIRouter(prefix="/admin/playground", tags=["admin:playground"])


@router.post("/chat")
async def playground_chat(
    body: PlaygroundChatRequest,
    _: AdminUser = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Chat test via llm.process queue.

    System prompt is pre-loaded from DB (selected by user) but can be edited
    before sending. Conversation history is preserved between turns.
    """
    history_messages = [{"role": msg["role"], "content": msg["content"]} for msg in body.messages]

    result = await enqueue_llm_request({
        "channel": "playground",
        "system_prompt": body.system_prompt,
        "messages": history_messages,
        "new_message": body.user_message,
    })

    return {
        "content": result.get("text", ""),
        "usage": result.get("token_usage"),
        "latency_ms": result.get("latency_ms", 0),
        "tool_calls": result.get("tool_calls", []),
        "error": result.get("error"),
    }


@router.post("/complete")
async def single_completion(
    body: CompletionRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Single completion test using configured provider."""
    client = create_llm_client(
        provider=body.model_provider,
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_model=body.model_name,
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
        openai_model=body.model_name,
    )
    response = await client.complete(
        system_prompt=body.system_prompt,
        messages=body.messages,
        tools=[],  # No tools for playground
    )
    return {
        "content": response.text,
        "usage": response.token_usage,
        "latency_ms": response.latency_ms,
    }


@router.post("/benchmark")
async def run_benchmark(
    body: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> dict[str, Any]:
    """Start a benchmark run."""
    benchmark = BenchmarkResult(
        id=uuid.uuid4(),
        name=body.name,
        status="pending",
        iterations=body.iterations,
    )
    db.add(benchmark)
    await db.commit()

    # Background task to run benchmark
    asyncio.create_task(_run_benchmark_background(benchmark.id, body, settings))

    return {"id": str(benchmark.id), "status": "pending"}


async def _run_benchmark_background(benchmark_id: uuid.UUID, body: BenchmarkRequest, cfg) -> None:
    """Run benchmark in background."""
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        result = await db.execute(select(BenchmarkResult).where(BenchmarkResult.id == benchmark_id))
        benchmark = result.scalar_one_or_none()
        if not benchmark:
            return

        benchmark.status = "running"
        await db.commit()

        try:
            for model_cfg in body.models:
                client = create_llm_client(
                    provider=model_cfg["provider"],
                    anthropic_api_key=cfg.anthropic_api_key,
                    anthropic_model=model_cfg["name"],
                    openai_base_url=cfg.openai_base_url,
                    openai_api_key=cfg.openai_api_key,
                    openai_model=model_cfg["name"],
                )
                latencies = []
                input_tokens_list = []
                output_tokens_list = []
                raw_results = []

                for i in range(body.iterations):
                    for prompt_cfg in body.test_prompts:
                        try:
                            result = await client.complete(
                                system_prompt="",
                                messages=prompt_cfg["messages"],
                                tools=[],
                            )
                            latencies.append(result.latency_ms or 0)
                            if result.token_usage:
                                input_tokens_list.append(result.token_usage.get("input_tokens", 0))
                                output_tokens_list.append(result.token_usage.get("output_tokens", 0))
                            raw_results.append(
                                {"iteration": i, "prompt": prompt_cfg["name"], "latency_ms": result.latency_ms, "text_length": len(result.text)}
                            )
                        except Exception as exc:
                            raw_results.append(
                                {"iteration": i, "prompt": prompt_cfg["name"], "error": str(exc)}
                            )

                sorted_latencies = sorted(latencies)
                p95_idx = int(len(sorted_latencies) * 0.95)

                item = BenchmarkItem(
                    id=uuid.uuid4(),
                    benchmark_id=benchmark.id,
                    model_provider=model_cfg["provider"],
                    model_name=model_cfg["name"],
                    avg_latency_ms=statistics.mean(latencies) if latencies else None,
                    p95_latency_ms=sorted_latencies[p95_idx] if sorted_latencies and p95_idx < len(sorted_latencies) else None,
                    avg_input_tokens=int(statistics.mean(input_tokens_list)) if input_tokens_list else None,
                    avg_output_tokens=int(statistics.mean(output_tokens_list)) if output_tokens_list else None,
                    raw_results=raw_results,
                )
                db.add(item)

            benchmark.status = "completed"
            benchmark.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            benchmark.status = "failed"
            benchmark.error = str(exc)
        await db.commit()


@router.get("/benchmark/{benchmark_id}")
async def get_benchmark(
    benchmark_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get benchmark status."""
    result = await db.execute(select(BenchmarkResult).where(BenchmarkResult.id == benchmark_id))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return {
        "id": str(b.id),
        "name": b.name,
        "status": b.status,
        "error": b.error,
        "created_at": b.created_at.isoformat(),
    }


@router.get("/benchmark/{benchmark_id}/results")
async def get_benchmark_results(
    benchmark_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
):
    """Get benchmark results."""
    result = await db.execute(select(BenchmarkItem).where(BenchmarkItem.benchmark_id == benchmark_id))
    items = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "model_provider": i.model_provider,
            "model_name": i.model_name,
            "avg_latency_ms": i.avg_latency_ms,
            "p95_latency_ms": i.p95_latency_ms,
            "avg_input_tokens": i.avg_input_tokens,
            "avg_output_tokens": i.avg_output_tokens,
        }
        for i in items
    ]


@router.get("/models")
async def list_models(
    _: AdminUser = Depends(get_current_admin_user),
):
    """List available models (from configured providers)."""
    return {
        "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
        "openai-compat": ["llama3.2", "gpt-4o-mini"],
    }
