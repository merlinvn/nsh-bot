"""Tests for tenant config loading."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from nsh_mcp.pricing.config import _json_to_config, clear_cache


class TestJsonToConfig:
    def test_tiers_parsed_correctly(self):
        data = {
            "tenant_id": "test",
            "tiers": {
                "fast": [[50, 68500], [150, 67500]],
            },
            "volumetric_divisor": {"fast": 6000},
            "eta": {"fast": "3-6 ngày"},
            "surcharges": {},
            "insurance_rate": 0.05,
            "discounts": {},
        }
        config = _json_to_config(data)
        assert config.tenant_id == "test"
        assert config.tiers["fast"] == [(50.0, 68500), (150.0, 67500)]
        assert config.volumetric_divisor["fast"] == 6000.0
        assert config.eta["fast"] == "3-6 ngày"
        assert config.insurance_rate == 0.05

    def test_cache_ttl_default(self):
        data = {
            "tenant_id": "test",
            "tiers": {},
            "volumetric_divisor": {},
            "eta": {},
            "surcharges": {},
            "insurance_rate": 0.05,
            "discounts": {},
        }
        config = _json_to_config(data)
        assert config.cache_ttl_seconds == 900

    def test_cache_ttl_custom(self):
        data = {
            "tenant_id": "test",
            "tiers": {},
            "volumetric_divisor": {},
            "eta": {},
            "surcharges": {},
            "insurance_rate": 0.05,
            "discounts": {},
            "cache_ttl_seconds": 300,
        }
        config = _json_to_config(data)
        assert config.cache_ttl_seconds == 300

    def test_lot_minimum_kg_default(self):
        data = {
            "tenant_id": "test",
            "tiers": {},
            "volumetric_divisor": {},
            "eta": {},
            "surcharges": {},
            "insurance_rate": 0.05,
            "discounts": {},
        }
        config = _json_to_config(data)
        assert config.lot_minimum_kg == 50


class TestLoadPricingConfig:
    def test_loads_nsh_config(self, monkeypatch, tmp_path):
        """Patch CONFIG_DIR to use tmp_path data dir."""
        data_dir = tmp_path / "nsh"
        data_dir.mkdir()
        (data_dir / "pricing_rules.json").write_text(
            '{"tenant_id":"nsh","tiers":{"fast":[[50,68500],[150,67500]]},'
            '"volumetric_divisor":{"fast":6000},"eta":{"fast":"3-6 ngày"},'
            '"surcharges":{},"insurance_rate":0.05,"discounts":{}}'
        )
        import nsh_mcp.pricing.config as config_module
        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
        clear_cache()
        config = config_module.load_pricing_config("nsh")
        assert config.tenant_id == "nsh"
        assert "fast" in config.tiers
        assert config.tiers["fast"][0] == (50.0, 68500)
        clear_cache()

    def test_caches_after_first_load(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "nsh"
        data_dir.mkdir()
        (data_dir / "pricing_rules.json").write_text(
            '{"tenant_id":"nsh","tiers":{"fast":[[50,68500]]},'
            '"volumetric_divisor":{"fast":6000},"eta":{},'
            '"surcharges":{},"insurance_rate":0.05,"discounts":{}}'
        )
        import nsh_mcp.pricing.config as config_module
        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
        clear_cache()
        config1 = config_module.load_pricing_config("nsh")
        config2 = config_module.load_pricing_config("nsh")
        assert config1 is config2
        clear_cache()

    def test_unknown_tenant_raises(self):
        clear_cache()
        from nsh_mcp.pricing.config import load_pricing_config
        with pytest.raises(FileNotFoundError):
            load_pricing_config("unknown_tenant")
        clear_cache()
