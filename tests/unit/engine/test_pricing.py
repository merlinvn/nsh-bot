"""Tests for the pricing engine — pure function, no I/O."""

import pytest

from nsh_mcp.pricing.pricing import (
    QuoteInput,
    QuoteResult,
    PricingConfig,
    calculate_quote,
    round_up_half,
    tier_price,
)


@pytest.fixture
def default_config() -> PricingConfig:
    """Default pricing config matching the nsh tenant JSON."""
    return PricingConfig(
        tenant_id="nsh",
        tiers={
            "fast": [(50, 68500), (150, 67500), (250, 66500), (350, 65500), (500, 64500)],
            "standard": [(50, 52500), (150, 51500), (250, 40500), (350, 49500), (500, 48500)],
            "bundle": [(50, 38000), (150, 37000), (250, 36000), (350, 35000), (500, 34000)],
            "lot": [(150, 23500), (250, 22500), (350, 21500), (500, 20500)],
        },
        volumetric_divisor={"fast": 6000, "standard": 6000, "bundle": 6000, "lot": 5000},
        eta={"fast": "3-6 ngày", "standard": "5-9 ngày", "bundle": "10-15 ngày", "lot": "15-25 ngày"},
        surcharges={"lot_clothing_per_kg": 3000, "lot_fragile_per_kg": 7000},
        insurance_rate=0.05,
        discounts={"voucher_over_100kg": 125000},
        max_chargeable_kg=500,
        lot_minimum_kg=50,
        cache_ttl_seconds=900,
    )


class TestRoundUpHalf:
    def test_exact_half(self):
        assert round_up_half(2.5) == 2.5

    def test_quarter_rounds_up(self):
        assert round_up_half(2.25) == 2.5

    def test_three_quarter_rounds_up(self):
        assert round_up_half(2.75) == 3.0

    def test_whole_number_rounds_up(self):
        assert round_up_half(3.0) == 3.0

    def test_large_weight(self):
        assert round_up_half(49.75) == 50.0


class TestTierPrice:
    def test_fast_tier_under_50kg(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 30) == 68500

    def test_fast_tier_50_to_150kg(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 75) == 67500

    def test_fast_tier_above_highest(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 200) is None

    def test_unknown_service(self):
        tiers = {"fast": [(50, 68500)]}
        assert tier_price(tiers, "unknown", 30) is None


class TestCalculateQuote:
    def test_fast_quote_under_50kg(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["unit_price_vnd_per_kg"] == 68500
        assert result.quote_data["chargeable_weight_kg"] == 30.0
        assert result.quote_data["total_vnd"] == 30 * 68500

    def test_fast_quote_volumetric_dominant(self, default_config):
        """When volumetric kg > actual kg, use average."""
        # 60x60x60 = 216000 cm3 / 6000 = 36 kg volumetric
        # actual = 20 kg, so (36 + 20) / 2 = 28 kg
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=20,
            length_cm=60,
            width_cm=60,
            height_cm=60,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["chargeable_weight_kg"] == 28.0

    def test_fast_rejects_battery_in_product_description(self, default_config):
        """Battery in product description → fast service not allowed."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="pin sạc dự phòng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"
        assert "gói nhanh" in result.message_to_customer.lower()

    def test_fast_rejects_liquid_in_product_description(self, default_config):
        """Liquid in product description → fast service not allowed."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="chất lỏng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"

    def test_fast_rejects_powder_in_product_description(self, default_config):
        """Powder in product description → fast service not allowed."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="bột màu",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"

    def test_rejects_prohibited_product(self, default_config):
        """Prohibited product → rejected."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="súng nhựa",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "rejected"

    def test_premium_brand_over_2kg_manual_review(self, default_config):
        """Premium brand electronics over 2kg → manual review."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=3,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="tai nghe Sony cao cấp",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"

    def test_missing_weight_returns_clarification(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=0,  # missing
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"
        assert "actual_weight_kg" in result.missing_fields

    def test_missing_service_type_returns_clarification(self, default_config):
        input_data = QuoteInput(
            service_type="",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"
        assert "service_type" in result.missing_fields

    def test_lot_requires_minimum_50kg(self, default_config):
        """Lot with actual weight below 50kg → manual review."""
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=30,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            product_description="quần áo lẻ",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"

    def test_lot_surcharge_clothing(self, default_config):
        """Lot with clothing category gets per-kg surcharge.

        Volumetric kg = 100*100*100/5000 = 200 kg
        At 200kg, tier is 22500 (150-250 bracket)
        Base: 200 * 22500 = 4,500,000
        Surcharge: 200 * 3000 = 600,000
        Total: 5,100,000
        """
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            product_description="quần áo lẻ",
            lot_surcharge_type="clothing",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["total_vnd"] == 5100000

    def test_lot_surcharge_fragile(self, default_config):
        """Volumetric kg = 200, base = 4,500,000, fragile surcharge = 200*7000 = 1,400,000."""
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            product_description="chảo inox",
            lot_surcharge_type="fragile",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["total_vnd"] == 5900000

    def test_bundle_takes_max_of_volumetric_and_actual(self, default_config):
        """Bundle service uses max(volumetric, actual), not average."""
        # 60x60x60 = 216000 cm3 / 6000 = 36 kg volumetric
        # actual = 20 kg, max = 36 kg
        input_data = QuoteInput(
            service_type="bundle",
            actual_weight_kg=20,
            length_cm=60,
            width_cm=60,
            height_cm=60,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["chargeable_weight_kg"] == 36.0

    def test_over_500kg_manual_review(self, default_config):
        """Over 500kg needs manual review."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=501,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            product_description="thú bông",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"

    def test_fragile_product_adds_note(self, default_config):
        """Fragile product adds warning note."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=5,
            length_cm=30,
            width_cm=30,
            height_cm=30,
            product_description="ly thủy tinh",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert len(result.notes) > 0
        assert any("dễ vỡ" in note.lower() for note in result.notes)

    def test_product_description_optional_for_quote(self, default_config):
        """Can still quote without product_description (but it's required by tool schema)."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=5,
            length_cm=30,
            width_cm=30,
            height_cm=30,
            product_description="",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
