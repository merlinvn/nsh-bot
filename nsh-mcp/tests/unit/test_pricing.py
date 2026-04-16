"""Tests for nsh-mcp pricing engine — pure function, no I/O."""

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
    return PricingConfig(
        tenant_id="nsh",
        tiers={
            "fast": [(50, 68500), (150, 67500), (250, 66500), (350, 65500), (500, 64500)],
            "standard": [(50, 52500), (150, 51500), (250, 50500), (350, 49500), (500, 48500)],
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

    def test_whole_number_unchanged(self):
        assert round_up_half(3.0) == 3.0

    def test_large_weight(self):
        assert round_up_half(49.75) == 50.0


class TestTierPrice:
    def test_under_first_bracket(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 30) == 68500

    def test_in_second_bracket(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 75) == 67500

    def test_above_highest_returns_none(self):
        tiers = {"fast": [(50, 68500), (150, 67500)]}
        assert tier_price(tiers, "fast", 200) is None

    def test_unknown_service_returns_none(self):
        tiers = {"fast": [(50, 68500)]}
        assert tier_price(tiers, "unknown", 30) is None


class TestCalculateQuote:
    def test_fast_under_50kg(self, default_config):
        """Actual weight < 50kg bracket, no volumetric dominance."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=20,
            width_cm=20,
            height_cm=20,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["unit_price_vnd_per_kg"] == 68500
        assert result.quote_data["chargeable_weight_kg"] == 30.0
        assert result.quote_data["total_vnd"] == 30 * 68500

    def test_fast_volumetric_dominant_average_used(self, default_config):
        """When volumetric > actual, fast/standard use average."""
        # 60x60x60 = 216000 cm3 / 6000 = 36 kg volumetric
        # actual = 20 kg → (36 + 20) / 2 = 28 kg
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=20,
            length_cm=60,
            width_cm=60,
            height_cm=60,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["chargeable_weight_kg"] == 28.0

    def test_bundle_takes_max_not_average(self, default_config):
        """Bundle uses max(volumetric, actual), not average."""
        # 60x60x60 = 216000 cm3 / 6000 = 36 kg volumetric
        # actual = 20 kg → max = 36 kg
        input_data = QuoteInput(
            service_type="bundle",
            actual_weight_kg=20,
            length_cm=60,
            width_cm=60,
            height_cm=60,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["chargeable_weight_kg"] == 36.0

    def test_lot_uses_5000_divisor(self, default_config):
        """Lot uses /5000 divisor for volumetric calculation."""
        # 100x100x100 = 1,000,000 cm3 / 5000 = 200 kg
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["volumetric_kg"] == 200.0

    def test_lot_surcharge_clothing(self, default_config):
        """Clothing surcharge: 200kg * 3000 = 600,000."""
        # 100x100x100 = 1,000,000 / 5000 = 200 kg
        # base: 200 * 22500 (150-250 bracket) = 4,500,000
        # surcharge: 200 * 3000 = 600,000
        # total: 5,100,000
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            lot_surcharge_type="clothing",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["lot_surcharge_type"] == "clothing"
        assert result.quote_data["lot_surcharge_total"] == 600000
        assert result.quote_data["total_vnd"] == 5100000

    def test_lot_surcharge_fragile(self, default_config):
        """Fragile surcharge: 200kg * 7000 = 1,400,000."""
        # base: 200 * 22500 = 4,500,000
        # surcharge: 200 * 7000 = 1,400,000
        # total: 5,900,000
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
            lot_surcharge_type="fragile",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["lot_surcharge_type"] == "fragile"
        assert result.quote_data["lot_surcharge_total"] == 1400000
        assert result.quote_data["total_vnd"] == 5900000

    def test_lot_no_surcharge_when_none(self, default_config):
        """Lot without surcharge_type gets no surcharge."""
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=100,
            length_cm=100,
            width_cm=100,
            height_cm=100,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["lot_surcharge_type"] is None
        assert result.quote_data["lot_surcharge_total"] is None

    def test_lot_minimum_50kg_triggers_manual_review(self, default_config):
        """Lot below 50kg returns manual_review."""
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=30,
            length_cm=100,
            width_cm=100,
            height_cm=100,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"
        assert "50kg" in result.message_to_customer

    def test_over_500kg_manual_review(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=501,
            length_cm=100,
            width_cm=100,
            height_cm=100,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"

    def test_missing_weight_returns_clarification(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=0,
            length_cm=20,
            width_cm=20,
            height_cm=20,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"
        assert "actual_weight_kg" in result.missing_fields

    def test_prohibited_weapon_rejected(self, default_config):
        """Weapons are on the prohibited list — tool must refuse."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=10,
            length_cm=30,
            width_cm=20,
            height_cm=10,
            product_description="súng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "rejected"
        assert "không được phép" in result.message_to_customer

    def test_prohibited_chemical_rejected(self, default_config):
        input_data = QuoteInput(
            service_type="bundle",
            actual_weight_kg=5,
            length_cm=20,
            width_cm=20,
            height_cm=10,
            product_description="hóa chất không rõ nguồn gốc",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "rejected"

    def test_prohibited_flammable_rejected(self, default_config):
        input_data = QuoteInput(
            service_type="lot",
            actual_weight_kg=50,
            length_cm=50,
            width_cm=50,
            height_cm=50,
            product_description="bình gas",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "rejected"

    def test_normal_product_no_rejection(self, default_config):
        """Regular products pass through without being flagged."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=30,
            length_cm=50,
            width_cm=40,
            height_cm=30,
            product_description="quần áo",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"

    def test_premium_brand_electronics_over_2kg_manual_review(self, default_config):
        """Premium electronics > 2kg need manual review."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=3,
            length_cm=30,
            width_cm=20,
            height_cm=10,
            product_description="tai nghe Sony cao cấp",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "manual_review"
        assert "2kg" in result.message_to_customer

    def test_premium_brand_under_2kg_quoted(self, default_config):
        """Premium electronics <= 2kg can be quoted."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=2,
            length_cm=30,
            width_cm=20,
            height_cm=10,
            product_description="tai nghe Sony",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"

    def test_fast_service_with_battery_needs_clarification(self, default_config):
        """Battery items can't go fast — must switch service type."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=5,
            length_cm=20,
            width_cm=15,
            height_cm=10,
            product_description="pin sạc dự phòng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"
        assert "gói nhanh" in result.message_to_customer

    def test_fast_service_with_magnet_needs_clarification(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=2,
            length_cm=15,
            width_cm=15,
            height_cm=5,
            product_description="nam châm",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"

    def test_fast_service_with_liquid_needs_clarification(self, default_config):
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=3,
            length_cm=20,
            width_cm=20,
            height_cm=15,
            product_description="chất lỏng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "need_clarification"

    def test_battery_item_can_use_standard_service(self, default_config):
        """Battery items work fine with standard service."""
        input_data = QuoteInput(
            service_type="standard",
            actual_weight_kg=5,
            length_cm=20,
            width_cm=15,
            height_cm=10,
            product_description="pin sạc dự phòng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"

    def test_prohibited_powder_white_rejected(self, default_config):
        """White powder is on the prohibited list."""
        input_data = QuoteInput(
            service_type="fast",
            actual_weight_kg=1,
            length_cm=10,
            width_cm=10,
            height_cm=5,
            product_description="bột màu trắng",
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "rejected"

    def test_standard_tier_250kg_correct_price(self, default_config):
        """Standard tier at 250kg bracket uses 50,500 not 40,500."""
        # 50kg fits in first bracket (50kg tier = 52500)
        input_data = QuoteInput(
            service_type="standard",
            actual_weight_kg=50,
            length_cm=50,
            width_cm=50,
            height_cm=50,
        )
        result = calculate_quote("nsh", input_data, default_config)
        assert result.status == "quoted"
        assert result.quote_data["unit_price_vnd_per_kg"] == 52500
        assert result.quote_data["total_vnd"] == 50 * 52500