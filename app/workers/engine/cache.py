"""Redis cache layer for shipping quotes."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from app.workers.engine.pricing import QuoteInput, QuoteResult

if TYPE_CHECKING:
    import redis.asyncio

logger = logging.getLogger("engine.cache")

QUOTE_KEY_PREFIX = "quote"


def build_cache_key(tenant_id: str, input_data: QuoteInput) -> str:
    """Build a deterministic cache key from quote input."""
    fields = {
        "service_type": input_data.service_type,
        "actual_weight_kg": input_data.actual_weight_kg,
        "length_cm": input_data.length_cm,
        "width_cm": input_data.width_cm,
        "height_cm": input_data.height_cm,
    }
    normalized = json.dumps(fields, sort_keys=True, ensure_ascii=True)
    hash_hex = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"{QUOTE_KEY_PREFIX}:{tenant_id}:{hash_hex}"


async def get_cached_quote(
    redis_client: "redis.Redis",
    tenant_id: str,
    input_data: QuoteInput,
) -> QuoteResult | None:
    """Return cached QuoteResult or None on miss / Redis error (fail-open)."""
    key = build_cache_key(tenant_id, input_data)
    try:
        data = await redis_client.get(key)
        if data is None:
            return None
        result_dict = json.loads(data)
        # Reconstruct QuoteResult from dict
        return QuoteResult(
            status=result_dict["status"],
            message_to_customer=result_dict.get("message_to_customer", ""),
            missing_fields=result_dict.get("missing_fields", []),
            reason=result_dict.get("reason", ""),
            quote_data=result_dict.get("quote_data", {}),
        )
    except Exception as e:
        logger.warning("Quote cache get failed (ignoring, computing fresh): key=%s error=%s", key, e)
        return None


async def set_cached_quote(
    redis_client: "redis.Redis",
    tenant_id: str,
    input_data: QuoteInput,
    result: QuoteResult,
    ttl_seconds: int = 900,
) -> None:
    """Store QuoteResult in Redis. Silently fails on Redis error (fail-open)."""
    key = build_cache_key(tenant_id, input_data)
    try:
        data = json.dumps({
            "status": result.status,
            "message_to_customer": result.message_to_customer,
            "missing_fields": result.missing_fields,
            "reason": result.reason,
            "quote_data": result.quote_data,
        })
        await redis_client.setex(key, ttl_seconds, data)
    except Exception as e:
        logger.warning("Quote cache set failed (ignoring): key=%s error=%s", key, e)
