"""Tenant pricing config loader — loads from JSON files with per-tenant caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.workers.mcp.pricing.pricing import PricingConfig

if TYPE_CHECKING:
    from app.workers.mcp.pricing.pricing import PricingConfig

_config_cache: dict[str, PricingConfig] = {}

# Base directory for tenant config files
CONFIG_DIR = Path(__file__).parent / "tenants"
DEFAULT_TENANT = "nsh"


def _json_to_config(data: dict) -> PricingConfig:
    """Convert JSON dict to PricingConfig, converting tier lists."""
    tiers = {}
    for service, brackets in data.get("tiers", {}).items():
        tiers[service] = [(float(max_kg), int(price)) for max_kg, price in brackets]
    return PricingConfig(
        tenant_id=data["tenant_id"],
        tiers=tiers,
        volumetric_divisor={k: float(v) for k, v in data.get("volumetric_divisor", {}).items()},
        eta=data.get("eta", {}),
        surcharges=data.get("surcharges", {}),
        insurance_rate=float(data.get("insurance_rate", 0.05)),
        discounts=data.get("discounts", {}),
        max_chargeable_kg=float(data.get("max_chargeable_kg", 500)),
        lot_minimum_kg=float(data.get("lot_minimum_kg", 50)),
        cache_ttl_seconds=int(data.get("cache_ttl_seconds", 900)),
    )


def load_pricing_config(tenant_id: str = DEFAULT_TENANT) -> PricingConfig:
    """Load pricing config for tenant, cached in memory."""
    if tenant_id in _config_cache:
        return _config_cache[tenant_id]

    path = CONFIG_DIR / tenant_id / "pricing_rules.json"
    if not path.exists():
        raise FileNotFoundError(f"Pricing config not found: {path}")

    with open(path) as f:
        data = json.load(f)

    config = _json_to_config(data)
    _config_cache[tenant_id] = config
    return config


def clear_cache(tenant_id: str | None = None) -> None:
    """Clear in-memory config cache. Pass tenant_id to clear single tenant, or None for all."""
    if tenant_id is None:
        _config_cache.clear()
    elif tenant_id in _config_cache:
        del _config_cache[tenant_id]
